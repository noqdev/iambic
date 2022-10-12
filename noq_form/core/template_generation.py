from collections import defaultdict
from typing import Union

import xxhash

from noq_form.config.models import AccountConfig
from noq_form.core import noq_json as json


def templatize_resource(account_config: AccountConfig, resource):
    resource_type = type(resource)

    if isinstance(resource, dict) or isinstance(resource, list):
        resource = json.dumps(resource)
    elif resource_type != str:
        resource = str(resource)

    resource = resource.replace(account_config.account_id, "{{account_id}}")
    resource = resource.replace(account_config.account_name, "{{account_name}}")
    for var in account_config.variables:
        resource = resource.replace(var.value, "{{{}}}".format(var.key))

    return (
        json.loads(resource)
        if resource_type == dict or resource_type == list
        else resource_type(resource)
    )


def group_int_attribute(account_vals: dict) -> Union[dict[int, list] | int]:
    """Groups a string attribute by a shared name across of accounts

    :return: dict(attribute_val: int = list[dict(resource_val: int, account_id: str)])
    :param account_vals: dict(resource_val: int = list[str])
    """
    response: dict[int, list[dict]] = defaultdict(list)

    for account_id, resource_val in account_vals.items():
        response[resource_val].append(account_id)

    if len(response) == 1:
        return list(response.keys())[0]

    return response


async def group_str_attribute(
    account_configs: list[AccountConfig], account_resources: list[dict]
) -> Union[str | dict[str, list]]:
    """Groups a string attribute by a shared name across of accounts

    The ability to pass in and maintain arbitrary keys is necessary for
        parsing resource names related to a boto3 response

    :param account_configs: list[AccountConfig]
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
    account_id_map = {
        account_config.account_id: account_config for account_config in account_configs
    }

    for account_resource_elem, account_resource in enumerate(account_resources):
        account_resources[account_resource_elem]["resource_val_map"] = dict()
        account_resources[account_resource_elem]["elem_resource_val_map"] = dict()
        account_config = account_id_map[account_resource["account_id"]]
        for resource_elem, resource in enumerate(account_resource["resources"]):
            account_resource["resources"][resource_elem][
                "account_id"
            ] = account_resource["account_id"]
            resource_val = resource["resource_val"]
            templatized_resource_val = templatize_resource(account_config, resource_val)

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
    # Iterate everything looking for shared names across accounts
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

    if len(grouped_resource_map) == 1:
        return list(grouped_resource_map.keys())[0]

    return grouped_resource_map


async def group_dict_attribute(
    account_configs: list[AccountConfig], account_resources: list[dict]
):
    """Groups an attribute that is a dict or list of dicts with matching accounts

    :param account_configs: list[AccountConfig]
    :param account_resources: list[dict(account_id:str, resources=list[dict])]
    :return: list[dict(included_accounts: str, resource_val=list[dict]|dict)]
    """
    """
    Create map with different representations of a resource value for each account

    The purpose is to add the 2 ways look-ups are done and maintain o(1) performance.
    The resource_hash to the corresponding list element in account_resources[elem]["resources"]
        Under resource_hash_map
    The reverse of resource_hash_map which is an int representing the elem with a list of all resource_hash reprs
        Under elem_resource_hash_map
    """
    account_id_map = {
        account_config.account_id: account_config for account_config in account_configs
    }
    hash_map = dict()

    for account_resource_elem, account_resource in enumerate(account_resources):
        account_resources[account_resource_elem]["resource_hash_map"] = dict()
        account_resources[account_resource_elem]["elem_resource_hash_map"] = dict()
        account_config = account_id_map[account_resource["account_id"]]
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
                account_config, resource["resource_val"]
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
    # Iterate everything looking for shared names across accounts
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
    account_configs: list[AccountConfig],
    number_of_accounts_resource_on: int,
    grouped_attribute,
):
    account_id_map = {
        account_config.account_id: account_config for account_config in account_configs
    }

    if isinstance(grouped_attribute, dict):  # via group_str_attribute
        for k, resource_vals in grouped_attribute.items():
            included_accounts = [
                account_id_map[rv["account_id"]].account_name for rv in resource_vals
            ]
            if len(included_accounts) == number_of_accounts_resource_on:
                included_accounts = ["*"]
            grouped_attribute[k] = included_accounts

        return grouped_attribute

    elif isinstance(grouped_attribute, list):  # Generated via group_dict_attribute
        for elem in range(len(grouped_attribute)):
            if (
                len(grouped_attribute[elem]["included_accounts"])
                == number_of_accounts_resource_on
            ):
                grouped_attribute[elem]["included_accounts"] = ["*"]
            else:
                included_accounts = [
                    account_id_map[rv].account_name
                    for rv in grouped_attribute[elem]["included_accounts"]
                ]
                grouped_attribute[elem]["included_accounts"] = included_accounts

        return grouped_attribute
