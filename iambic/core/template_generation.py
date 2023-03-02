from __future__ import annotations

from collections import defaultdict
from typing import Union

import xxhash
from iambic.core import noq_json as json
from iambic.core.context import ctx
from iambic.core.logger import log
from iambic.core.models import AccessModelMixin, BaseModel, BaseTemplate, ProviderChild
from iambic.core.parser import load_templates
from iambic.core.utils import (
    evaluate_on_provider,
    gather_templates,
    get_provider_value,
    is_regex_match,
)
from iambic.plugins.v0_1_0.aws.models import AWSAccount


async def get_existing_template_map(repo_dir: str, template_type: str) -> dict:
    """Used to keep track of existing templates on import

     Write to the existing file before creating a new one.

    :param repo_dir:
    :param template_type:
    :return: {resource_id: template}
    """
    templates = load_templates(await gather_templates(repo_dir, template_type))
    return {template.resource_id: template for template in templates}


def templatize_resource(aws_account: AWSAccount, resource):
    resource_type = type(resource)

    if isinstance(resource, dict) or isinstance(resource, list):
        resource = json.dumps(resource)
    elif resource_type != str:
        resource = str(resource)

    resource = resource.replace(aws_account.account_id, "{{account_id}}")
    resource = resource.replace(aws_account.account_name, "{{account_name}}")
    for var in aws_account.variables:
        resource = resource.replace(var.value, "{{{}}}".format(var.key))

    return (
        json.loads(resource)
        if resource_type == dict or resource_type == list
        else resource_type(resource)
    )


def base_group_int_attribute(account_vals: dict) -> dict[int, list[dict[str, str]]]:
    """Groups an int attribute by a shared name across of aws_accounts

    Just call group_int_or_str_attribute

    :param account_vals: dict(resource_val: int = list[str])
    :return: dict(attribute_val: int = list[dict(account_id: str)])
    """
    response: dict[int, list[dict]] = defaultdict(list)

    for account_id, resource_val in account_vals.items():
        response[resource_val].append({"account_id": account_id})

    return response


async def base_group_str_attribute(
    aws_account_map: dict[str, AWSAccount], account_resources: list[dict]
) -> dict[str, list]:
    """Groups a string attribute by a shared name across of aws_accounts

    The ability to pass in and maintain arbitrary keys is necessary for
        parsing resource names related to a boto3 response

    Call group_int_or_str_attribute instead unless you need to transform this response.
    An example would be grouping role names for generating the template where you need to keep the file_path ref.

    :param aws_account_map: dict(account_id:str = AWSAccount)
    :param account_resources: list[dict(account_id:str, resources=list[dict(resource_val: str, **)])]
    :return: dict(attribute_val: str = list[dict(resource_val: str, account_id: str, **)])
    """

    """
    Create map with different representations of a resource value for each account

    The purpose is to add the 2 ways look-ups are done and maintain o(1) performance.
    The resource_val to the corresponding list element in account_resources[elem]["resources"]
        Under resource_val_map
    The reverse of resource_val_map which is an int representing the elem with a list of all resource_val reprs
        Under elem_resource_val_map
    """
    for account_resource_elem, account_resource in enumerate(account_resources):
        account_resources[account_resource_elem]["resource_val_map"] = dict()
        account_resources[account_resource_elem]["elem_resource_val_map"] = dict()
        aws_account = aws_account_map[account_resource["account_id"]]
        for resource_elem, resource in enumerate(account_resource["resources"]):
            account_resource["resources"][resource_elem][
                "account_id"
            ] = account_resource["account_id"]
            resource_val = resource["resource_val"]
            templatized_resource_val = templatize_resource(aws_account, resource_val)

            account_resources[account_resource_elem]["resource_val_map"][
                resource_val
            ] = resource_elem
            account_resources[account_resource_elem]["elem_resource_val_map"][
                resource_elem
            ] = [resource_val]
            if templatized_resource_val != resource_val:
                account_resources[account_resource_elem]["resource_val_map"][
                    templatized_resource_val
                ] = resource_elem
                account_resources[account_resource_elem]["elem_resource_val_map"][
                    resource_elem
                ].append(templatized_resource_val)

    grouped_resource_map = defaultdict(
        list
    )  # val:str = list(dict(name: str, path: str, account_id: str))
    # Iterate everything looking for shared names across aws_accounts
    for outer_elem in range(len(account_resources)):
        for resource_val, outer_resource_elem in account_resources[outer_elem][
            "resource_val_map"
        ].items():
            if outer_resource_elem is None:  # It hit on something already
                continue
            for inner_elem in range(outer_elem + 1, len(account_resources)):
                if (
                    inner_resource_elem := account_resources[inner_elem][
                        "resource_val_map"
                    ].get(resource_val)
                ) is not None:
                    if not grouped_resource_map.get(resource_val):
                        # Null out the outer_resource_elem in all the places
                        for rn in account_resources[outer_elem][
                            "elem_resource_val_map"
                        ][outer_resource_elem]:
                            account_resources[outer_elem]["resource_val_map"][rn] = None
                        account_resources[outer_elem]["elem_resource_val_map"][
                            outer_resource_elem
                        ] = []

                        grouped_resource_map[resource_val] = [
                            account_resources[inner_elem]["resources"][
                                inner_resource_elem
                            ],
                            account_resources[outer_elem]["resources"][
                                outer_resource_elem
                            ],
                        ]
                    else:
                        grouped_resource_map[resource_val].append(
                            account_resources[inner_elem]["resources"][
                                inner_resource_elem
                            ]
                        )

                    for rn in account_resources[inner_elem]["elem_resource_val_map"][
                        inner_resource_elem
                    ]:
                        account_resources[inner_elem]["resource_val_map"][rn] = None
                    account_resources[inner_elem]["elem_resource_val_map"][
                        inner_resource_elem
                    ] = []

    # Set the remaining attributes unique attributes
    for account_resource in account_resources:
        for elem, resource_vals in account_resource["elem_resource_val_map"].items():
            if not resource_vals:
                continue
            elif len(resource_vals) == 1:
                resource_val = resource_vals[0]
            else:
                # Take priority over raw output
                resource_val = [rv for rv in resource_vals if "{{" not in rv][0]

            account_resource["resources"][elem]["account_id"] = account_resource[
                "account_id"
            ]
            grouped_resource_map[resource_val] = [account_resource["resources"][elem]]

    return grouped_resource_map


async def base_group_dict_attribute(
    aws_account_map: dict[str, AWSAccount], account_resources: list[dict]
) -> list[dict]:
    """Groups an attribute that is a dict or list of dicts with matching aws_accounts

    Call group_dict_attribute instead unless you need to transform this response.
    An example would be tags which also contain access_rules.

    :param aws_account_map: dict(account_id:str = AWSAccount)
    :param account_resources: list[dict(account_id:str, resources=list[dict])]
    :return: list[dict(included_accounts: str, resource_val=list[dict]|dict)]
    """
    """
    Create map with different representations of a resource value for each account

    Create a resource_hash to the corresponding list element in account_resources[elem]["resources"]
        Under resource_hash_map
    Create a reverse of resource_hash_map which is an int representing the elem with a list of all resource_hash reprs
        Under elem_resource_hash_map
    """
    hash_map = dict()

    for account_resource_elem, account_resource in enumerate(account_resources):
        account_resources[account_resource_elem]["resource_hash_map"] = dict()
        account_resources[account_resource_elem]["elem_resource_hash_map"] = dict()
        aws_account = aws_account_map[account_resource["account_id"]]
        for resource_elem, resource in enumerate(account_resource["resources"]):
            account_resource["resources"][resource_elem][
                "account_id"
            ] = account_resource["account_id"]
            # Set raw dict
            resource_hash = xxhash.xxh32(
                json.dumps(resource["resource_val"])
            ).hexdigest()
            hash_map[resource_hash] = resource["resource_val"]
            # Set dict with attempted interpolation
            templatized_dict = templatize_resource(
                aws_account, resource["resource_val"]
            )
            templatized_resource_hash = xxhash.xxh32(
                json.dumps(templatized_dict)
            ).hexdigest()
            hash_map[templatized_resource_hash] = templatized_dict
            # Define resource hash mappings
            account_resources[account_resource_elem]["resource_hash_map"][
                resource_hash
            ] = resource_elem
            account_resources[account_resource_elem]["elem_resource_hash_map"][
                resource_elem
            ] = [resource_hash]
            if templatized_resource_hash != resource_hash:
                account_resources[account_resource_elem]["resource_hash_map"][
                    templatized_resource_hash
                ] = resource_elem
                account_resources[account_resource_elem]["elem_resource_hash_map"][
                    resource_elem
                ].append(templatized_resource_hash)

    grouped_resource_map = (
        dict()
    )  # val:str = list(dict(name: str, path: str, account_id: str))
    # Iterate everything looking for shared names across aws_accounts
    for outer_elem in range(len(account_resources)):
        for resource_hash, outer_resource_elem in account_resources[outer_elem][
            "resource_hash_map"
        ].items():
            if outer_resource_elem is None:  # It hit on something already
                continue
            for inner_elem in range(outer_elem + 1, len(account_resources)):
                if (
                    inner_resource_elem := account_resources[inner_elem][
                        "resource_hash_map"
                    ].get(resource_hash)
                ) is not None:
                    if not grouped_resource_map.get(resource_hash):
                        grouped_resource_map[resource_hash] = {
                            "resource_val": hash_map[resource_hash],
                            "included_accounts": [
                                account_resources[inner_elem]["account_id"],
                                account_resources[outer_elem]["account_id"],
                            ],
                        }

                        # Null out the outer_resource_elem in all the places
                        for rn in account_resources[outer_elem][
                            "elem_resource_hash_map"
                        ][outer_resource_elem]:
                            account_resources[outer_elem]["resource_hash_map"][
                                rn
                            ] = None
                        account_resources[outer_elem]["elem_resource_hash_map"][
                            outer_resource_elem
                        ] = []
                    else:
                        grouped_resource_map[resource_hash]["included_accounts"].append(
                            account_resources[inner_elem]["account_id"]
                        )

                    # Null out the inner_resource_elem in all the places
                    for rn in account_resources[inner_elem]["elem_resource_hash_map"][
                        inner_resource_elem
                    ]:
                        account_resources[inner_elem]["resource_hash_map"][rn] = None
                    account_resources[inner_elem]["elem_resource_hash_map"][
                        inner_resource_elem
                    ] = []

    # Set the remaining attributes unique attributes
    for account_resource in account_resources:
        for elem, resource_hashes in account_resource["elem_resource_hash_map"].items():
            if not resource_hashes:
                continue
            elif len(resource_hashes) == 1:
                resource_hash = resource_hashes[0]
            else:
                # Take priority over raw output
                resource_hash = [
                    rv for rv in resource_hashes if "{{" not in str(hash_map[rv])
                ][0]

            grouped_resource_map[resource_hash] = {
                "resource_val": hash_map[resource_hash],
                "included_accounts": [account_resource["account_id"]],
            }

    return list(grouped_resource_map.values())


async def set_included_accounts_for_grouped_attribute(
    aws_account_map: dict[str, AWSAccount],
    number_of_accounts_resource_on: int,
    grouped_attribute,
) -> Union[list, dict]:
    """Takes a grouped attribute and formats its included aws_accounts to * or a list of account names

    :param aws_account_map: {account_id: aws_account}
    :param number_of_accounts_resource_on:
    :param grouped_attribute:
    :return:
    """
    if isinstance(grouped_attribute, dict):  # via base_group_str_attribute
        for k, resource_vals in grouped_attribute.items():
            if len(resource_vals) == number_of_accounts_resource_on:
                included_accounts = ["*"]
            else:
                included_accounts = [
                    aws_account_map[rv["account_id"]].account_name
                    for rv in resource_vals
                ]
            grouped_attribute[k] = included_accounts

        return grouped_attribute

    elif isinstance(grouped_attribute, list):  # Generated via base_group_dict_attribute
        for elem in range(len(grouped_attribute)):
            if (
                len(grouped_attribute[elem]["included_accounts"])
                == number_of_accounts_resource_on
            ):
                grouped_attribute[elem]["included_accounts"] = ["*"]
            else:
                included_accounts = [
                    aws_account_map[rv].account_name
                    for rv in grouped_attribute[elem]["included_accounts"]
                ]
                grouped_attribute[elem]["included_accounts"] = included_accounts

        return grouped_attribute


async def group_int_or_str_attribute(
    aws_account_map: dict[str, AWSAccount],
    number_of_accounts_resource_on: int,
    account_resources: Union[dict, list[dict]],
    key: Union[int, str],
) -> Union[int, str, list[dict]]:
    """Groups an attribute by aws_accounts, formats the attribute and normalizes the included aws_accounts.

    :param aws_account_map:
    :param number_of_accounts_resource_on:
    :param account_resources: dict(account_id: str = int_val) , list[dict(account_id:str, resources=list[dict])]
    :param key: Used to form the list[dict] response when there are multiple values for the attribute.
    :return:
    """
    if isinstance(account_resources, list):
        grouped_attribute = await base_group_str_attribute(
            aws_account_map, account_resources
        )
    else:
        grouped_attribute = base_group_int_attribute(account_resources)

    if len(grouped_attribute) == 1:
        return list(grouped_attribute.keys())[0]

    response = []
    grouped_attribute = await set_included_accounts_for_grouped_attribute(
        aws_account_map, number_of_accounts_resource_on, grouped_attribute
    )

    for resource_val, included_accounts in grouped_attribute.items():
        if included_accounts[0] == "*":
            response.append({key: resource_val})
        else:
            response.append({key: resource_val, "included_accounts": included_accounts})

    return response


async def group_dict_attribute(
    aws_account_map: dict[str, AWSAccount],
    number_of_accounts_resource_on: int,
    account_resources: list[dict],
    is_dict_attr: bool = True,
) -> Union[dict, list[dict]]:
    """Groups an attribute by aws_accounts, formats the attribute and normalizes the included aws_accounts.

    :param aws_account_map: {account_id: aws_account}
    :param number_of_accounts_resource_on:
    :param account_resources: list[dict(account_id:str, resources=list[dict])]
    :param is_dict_attr: If false and only one hit, still return as a list. Useful for things like inline_policies.
    :return:
    """

    response = []
    grouped_attributes = await set_included_accounts_for_grouped_attribute(
        aws_account_map,
        number_of_accounts_resource_on,
        (await base_group_dict_attribute(aws_account_map, account_resources)),
    )

    if len(grouped_attributes) == 1 and is_dict_attr:
        attr_val = grouped_attributes[0]["resource_val"]
        included_accounts = grouped_attributes[0]["included_accounts"]
        if included_accounts != ["*"]:
            attr_val["included_accounts"] = included_accounts

        return attr_val

    for grouped_attr in grouped_attributes:
        attr_val = grouped_attr["resource_val"]
        included_accounts = grouped_attr["included_accounts"]
        if included_accounts != ["*"]:
            attr_val["included_accounts"] = included_accounts

        response.append(attr_val)

    return response


def create_or_update_template(
    file_path,
    existing_template_map,
    identifier,
    template_cls,
    template_params,
    properties,
    all_provider_children: list[ProviderChild],
):

    new_template = template_cls(
        file_path=file_path,
        properties=properties,
        **template_params,
    )

    # iambic-specific knowledge requires us to load the existing template
    # because it will not be reflected by AWS API.
    if existing_template := existing_template_map.get(identifier, None):
        merged_template = merge_model(
            new_template, existing_template, all_provider_children
        )

        try:
            merged_template.write()
            return merged_template
        except Exception as err:
            log.exception(
                f"Unable to update {template_cls} template.",
                error=str(err),
                template_params=template_params,
            )
            raise
    else:
        try:
            new_template.write()
            return new_template
        except Exception as err:
            log.exception(
                f"Unable to create {template_cls} template.",
                error=str(err),
                template_params=template_params,
            )
            raise


def get_resource_id_to_model_map(models: list[BaseModel]) -> dict[str, BaseModel]:
    resource_id_to_model_map = {}
    for existing_model in models:
        existing_resource_id = None
        try:
            existing_resource_id = existing_model.resource_id
        except NotImplementedError:
            pass
        if existing_resource_id:
            resource_id_to_model_map[existing_resource_id] = existing_model
    return resource_id_to_model_map


def sync_access_model_scope(
    source_access_model: AccessModelMixin, destination_access_model: AccessModelMixin
) -> tuple[AccessModelMixin, AccessModelMixin]:
    destination_access_model.set_included_children(
        sorted(source_access_model.included_children)
    )
    destination_access_model.set_excluded_children(
        sorted(source_access_model.excluded_children)
    )
    destination_access_model.set_included_parents(
        sorted(source_access_model.included_parents)
    )
    destination_access_model.set_excluded_parents(
        sorted(source_access_model.excluded_parents)
    )
    return source_access_model, destination_access_model


def update_access_attributes(
    new_model: AccessModelMixin,
    existing_model: AccessModelMixin,
    all_provider_children: list[ProviderChild],
) -> tuple[AccessModelMixin, AccessModelMixin]:
    """
        Syncs the access attributes of the new model with the existing model.

        How it works:
            For each included account in the new value:
            Check if the account would be excluded by the existing value
                Either implicitly or explicitly using rule weighting
            If it would be excluded, add it to included_accounts
                and remove it from excluded_accounts if the full provider name is defined in the excluded_accounts.
                For example, if the excluded_accounts is "prod*" and the account name is prod-1234, the rule is unchanged.
                However, if the excluded_accounts is "prod-1234" the rule will be removed.

    for every known account that is not in included_accounts:
        Check if the account would be included by the existing value
        If it would be included, add it to excluded_accounts

        :param new_model: The new model to sync with the existing model.
        :param existing_model: The existing model to sync with the new model.
        :param all_provider_children: All the children of the provider.
        :return: The new model and the existing model.
    """
    if "*" in new_model.included_children:
        new_model, existing_model = sync_access_model_scope(new_model, existing_model)
        return new_model, existing_model

    if "*" in existing_model.included_children:
        for child in all_provider_children:

            if (
                child.preferred_identifier not in new_model.included_children
                and evaluate_on_provider(existing_model, child, ctx, False)
            ):
                existing_model.excluded_children.append(child.preferred_identifier)
    else:
        for child in all_provider_children:
            currently_evaluated = evaluate_on_provider(
                existing_model, child, ctx, False
            )
            evaluated_on_new_model = bool(
                child.preferred_identifier in new_model.included_children
            )
            if evaluated_on_new_model and not currently_evaluated:
                if (
                    child.parent_id
                    and child.parent_id in existing_model.excluded_parents
                ):
                    # Unable to preserve original rules because we may include an unwanted child
                    existing_model, new_model = sync_access_model_scope(
                        existing_model, new_model
                    )
                    return new_model, existing_model

                excluded_children = [
                    ec
                    for ec in existing_model.excluded_children
                    if ec not in child.all_identifiers
                ]
                if excluded_children != existing_model.excluded_children:
                    existing_model.set_excluded_children(excluded_children)
                else:
                    existing_model.included_children.append(child.preferred_identifier)

            if not evaluated_on_new_model and currently_evaluated:
                existing_model.excluded_children.append(child.preferred_identifier)

    existing_model, new_model = sync_access_model_scope(existing_model, new_model)
    return new_model, existing_model


def sort_access_models_by_included_children(
    access_models: list[AccessModelMixin], as_most_specific: bool = True
) -> list[AccessModelMixin]:
    return sorted(
        access_models,
        key=lambda x: max(len(child) for child in x.included_children),
        reverse=as_most_specific,
    )


def resolve_model_orphaned_children(
    new_model: AccessModelMixin,
    merged_model_list: list[AccessModelMixin],
    resolved_children: set[str],
    provider_child_map: dict[str, ProviderChild],
) -> tuple[list[AccessModelMixin], set]:
    """
    Attempts to attach "orphaned" children to a model with matching IAMbic metadata.
    This is because the metadata is the only preserved attribute when merging models.

    These children are ones that didn't hit on an existing model's included_children
    """
    all_provider_children = list(provider_child_map.values())

    for included_child in new_model.included_children:
        provider_child = provider_child_map.get(included_child)
        if not provider_child:
            continue

        if any(is_regex_match(included_child, child) for child in resolved_children):
            continue

        for elem, matching_model in enumerate(merged_model_list):
            if any(
                is_regex_match(child, provider_child.preferred_identifier)
                for child in matching_model.excluded_children
            ):
                # Don't merge the child if the model excludes it explicitly
                continue

            """
            If the model does not have iambic_specific_knowledge
                or the model has iambic_specific_knowledge
                    and the new model has the same values for the attributes
                attempt to merge, if successful update the merged_model
            """
            if not getattr(matching_model, "iambic_specific_knowledge", None) or all(
                getattr(new_model, attr, None) == getattr(matching_model, attr, None)
                for attr in matching_model.iambic_specific_knowledge()
            ):
                resolved_children.add(included_child)
                merged_model = merge_model(
                    new_model, matching_model, all_provider_children
                )
                if merged_model:
                    merged_model_list[elem] = merged_model
                    break

    return merged_model_list, resolved_children


def merge_access_model_list(
    new_list: list[AccessModelMixin],
    existing_list: list[AccessModelMixin],
    all_provider_children: list[ProviderChild],
) -> list[AccessModelMixin]:
    """
    If the field is a list of objects that inherit from AccessModel:
    Attempt to resolve the matching model between the 2 lists
        If found, refer to "if the field inherits from AccessModel"
        If not found in the existing value, add the new model to the list
        If not found in the new value, remove the existing model from the list
    """
    merged_list = []
    provider_child_map = {
        child.preferred_identifier: child for child in all_provider_children
    }
    for new_model in new_list:
        matching_existing_models = [
            existing_model
            for existing_model in existing_list
            if existing_model.resource_id == new_model.resource_id
        ]
        if not matching_existing_models:
            merged_list.append(new_model)
        elif new_model.included_children == ["*"]:
            # Find the least specific
            matching_existing_models = sort_access_models_by_included_children(
                matching_existing_models, False
            )
            merged_model = merge_model(
                new_model, matching_existing_models[0], all_provider_children
            )
            if merged_model:
                merged_list.append(merged_model)
        else:
            # Find the most specific
            matching_existing_models = sort_access_models_by_included_children(
                matching_existing_models
            )
            """
            Attempt to find in sub_merged_model_list
            if found, skip, add to resolved_children
            if not found, attempt to find in matching_existing_models
            if found, merge, add to sub_merged_model_list, add to resolved_children
            if not found, continue
            Remove all resolved_children from new_model.included_children
            if new model included_children is not empty, add to merged_list
            """
            sub_merged_model_list = []
            resolved_children = set()

            for included_child in new_model.included_children:
                provider_child = provider_child_map.get(included_child)
                if not provider_child:
                    continue

                if sub_merged_model_list:
                    if get_provider_value(
                        sub_merged_model_list, provider_child.all_identifiers
                    ):
                        resolved_children.add(included_child)
                        continue

                existing_model = get_provider_value(
                    matching_existing_models, provider_child.all_identifiers
                )
                if existing_model:
                    resolved_children.add(included_child)
                    merged_model = merge_model(
                        new_model, existing_model, all_provider_children
                    )
                    if merged_model:
                        sub_merged_model_list.append(merged_model)

            # Cannot short circuit simply by resolved_children and
            # included_children length because included_children
            # may not have been expanded (regex like prod*)
            if sub_merged_model_list:
                (
                    sub_merged_model_list,
                    resolved_children,
                ) = resolve_model_orphaned_children(
                    new_model,
                    sub_merged_model_list,
                    resolved_children,
                    provider_child_map,
                )

            merged_list.extend(sub_merged_model_list)
            new_model.set_included_children(
                [
                    child
                    for child in new_model.included_children
                    if "*" not in child and child not in resolved_children
                ]
            )
            if new_model.included_children:
                # Add new_model containing children that were not resolved and couldn't be attached to a model
                merged_list.append(new_model)

    return merged_list


def merge_model_list(
    new_list: list[BaseModel],
    existing_list: list[BaseModel],
    all_provider_children: list[ProviderChild],
) -> list:
    existing_resource_id_to_model_map = get_resource_id_to_model_map(existing_list)
    merged_list = []
    for new_index, new_model in enumerate(new_list):
        new_model_resource_id = None
        try:
            new_model_resource_id = new_model.resource_id
        except NotImplementedError:
            pass
        if (
            new_model_resource_id
            and new_model_resource_id in existing_resource_id_to_model_map
        ):
            existing_model = existing_resource_id_to_model_map[new_model_resource_id]
            merged_list.append(
                merge_model(new_model, existing_model, all_provider_children)
            )
        elif not new_model_resource_id and new_index < len(existing_list):
            # when we cannot use
            existing_model = existing_list[new_index]
            merged_list.append(
                merge_model(new_model, existing_model, all_provider_children)
            )
        else:
            merged_list.append(new_model.copy())
    return merged_list


def merge_model(
    new_model: BaseModel,
    existing_model: BaseModel,
    all_provider_children: list[ProviderChild],
) -> Union[BaseModel, list[BaseModel], None]:
    """
    Update the metadata of the new IAMbic model using the existing model.
    The merging process supports merging lists of objects that inherit from the AccessModelMixin, as well as
    merging nested models that inherit from IAMbic's BaseModel.
    This is to preserve metadata on import.

    Args:
    - new_model (BaseModel): The incoming IAMbic BaseModel to be merged with the existing model
    - existing_model (BaseModel): The IAMbic BaseModel to be used to set the new_model's metadata
    - all_provider_children (list[ProviderChild]): A list of provider children used to resolve conflicts when merging
        lists of objects that inherit from the AccessModelMixin

    Returns:
    - Union[BaseModel, list[BaseModel], None]: The merged IAMbic model,
        or a list of merged IAMbic models,
        or None if the new model was set to None

    """
    if new_model is None:
        # The attribute was set to None
        if existing_model:
            log.warn(
                "merge_model: the incoming value is None when existing value is not None"
            )
        return new_model

    merged_model = existing_model.copy()
    iambic_fields = existing_model.metadata_iambic_fields
    field_names = new_model.__fields__.keys()

    if isinstance(merged_model, AccessModelMixin) and isinstance(
        new_model, AccessModelMixin
    ):
        """
        If the field is a list of objects that inherit from AccessModel:
        Attempt to resolve the matching model between the 2 lists
            If found, refer to "if the field inherits from AccessModel"
            If not found in the existing value, add the new model to the list
            If not found in the new value, remove the existing model from the list
        """
        new_model, merged_model = update_access_attributes(
            new_model, merged_model, all_provider_children
        )

    if isinstance(new_model, list) and not isinstance(merged_model, list):
        """
        If the new value is a list while the existing value is not:
            Cast existing model to a list and have merge_access_model_list attempt to resolve the matching model
        """
        existing_model = [existing_model]
        merged_model = [merged_model]

    elif isinstance(merged_model, list) and not isinstance(new_model, list):
        """
        If the existing value is a list while the new value is not:
            Cast new model to a list and have merge_access_model_list attempt to resolve the matching model
        """
        new_model = [new_model]

    for key in field_names:
        new_value = getattr(new_model, key)
        value_as_list = isinstance(new_value, list)
        existing_value = getattr(existing_model, key)
        if isinstance(existing_value, list):
            if len(existing_value) > 0:
                inner_element = existing_value[0]

                if isinstance(inner_element, AccessModelMixin):
                    """
                    If the field is a list of objects that inherit from the AccessModelMixin:
                    Attempt to resolve the matching model between the 2 lists
                        If found, refer to "if the field inherits from AccessModel"
                        If not found in the existing value, add the new model to the list
                        If not found in the new value, remove the existing model from the list
                    """
                    new_value = merge_access_model_list(
                        new_value, existing_value, all_provider_children
                    )
                    setattr(
                        merged_model, key, new_value if value_as_list else new_value[0]
                    )
                elif isinstance(inner_element, BaseModel):
                    new_value = merge_model_list(
                        new_value, existing_value, all_provider_children
                    )
                    setattr(
                        merged_model, key, new_value if value_as_list else new_value[0]
                    )
                else:
                    setattr(merged_model, key, new_value)
            else:
                setattr(merged_model, key, new_value)
        elif isinstance(existing_value, BaseModel):
            setattr(
                merged_model,
                key,
                merge_model(new_value, existing_value, all_provider_children),
            )
        elif key not in iambic_fields:
            setattr(merged_model, key, new_value)
    return merged_model


def delete_orphaned_templates(
    existing_templates: list[BaseTemplate], resource_ids: set[str]
):
    """
    Delete templates that were not found in the latest import for a single template type

    Args:
    - existing_templates (list[BaseTemplate]): List of templates that were already in IAMbic
    - resource_ids (set[str]): The set of resource ids that were found in the latest import
    """
    for existing_template in existing_templates:
        if existing_template.resource_id not in resource_ids:
            log.warning(
                "Removing template that references deleted resource",
                resource_type=existing_template.resource_type,
                resource_id=existing_template.resource_id,
            )
            existing_template.delete()
