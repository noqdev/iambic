from __future__ import annotations

import asyncio
import datetime
import inspect
import json
import os
from enum import Enum
from types import GenericAlias
from typing import TYPE_CHECKING, List, Optional, Set, Union, get_args, get_origin

import dateparser
from deepdiff.model import PrettyOrderedSet
from git import Repo
from jinja2 import BaseLoader, Environment
from pydantic import BaseModel as PydanticBaseModel
from pydantic import Field, validator
from pydantic.fields import ModelField

from iambic.core.context import ExecutionContext, ctx
from iambic.core.iambic_enum import IambicManaged
from iambic.core.logger import log
from iambic.core.utils import (
    apply_to_provider,
    create_commented_map,
    evaluate_on_provider,
    get_provider_value,
    snake_to_camelcap,
    sort_dict,
    transform_commments,
    yaml,
)

if TYPE_CHECKING:
    from iambic.aws.models import AWSAccount
    from iambic.config.models import Config


class IambicPydanticBaseModel(PydanticBaseModel):

    metadata_iambic_fields = Field(
        set(), description="metadata for iambic", exclude=True
    )
    metadata_commented_dict: dict = Field({}, description="yaml inline comments")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        ancestors = inspect.getmro(type(self))
        for ancestor in ancestors:
            if getattr(ancestor, "iambic_specific_knowledge", None):
                self.metadata_iambic_fields = self.metadata_iambic_fields.union(
                    ancestor.iambic_specific_knowledge()
                )

    class Config:
        json_encoders = {Set: list}

    @classmethod
    def iambic_specific_knowledge(cls) -> set[str]:
        return {"metadata_commented_dict"}


class BaseModel(IambicPydanticBaseModel):
    @classmethod
    def update_forward_refs(cls, **kwargs):
        kwargs.update({"Union": Union})
        super().update_forward_refs(**kwargs)

    class Config:
        alias_generator = snake_to_camelcap
        allow_population_by_field_name = True

    @classmethod
    def required_fields(cls) -> list[str]:
        return [
            field_name
            for field_name, field in cls.__dict__.get("__fields__", {}).items()
            if field != Optional
        ]

    @staticmethod
    def get_field_type(field: any) -> any:
        """
        Resolves the base field type for a model
        """
        field_type = field.type_ if isinstance(field, ModelField) else field
        if field_type == Optional:
            field_type = field_type[0]

        if (
            type(field_type) in [dict, GenericAlias, list, List, Set, set]
            or get_origin(field_type) == Union
        ) and (field_types := get_args(field_type)):
            return BaseModel.get_field_type(field_types[0])

        return field_type

    def get_attribute_val_for_account(
        self,
        aws_account: AWSAccount,
        attr: str,
        as_boto_dict: bool = True,
        context: ExecutionContext = None,
    ):
        # Support for nested attributes via dot notation. Example: properties.tags
        attr_val = self
        for attr_key in attr.split("."):
            attr_val = getattr(attr_val, attr_key)

        if as_boto_dict and hasattr(attr_val, "_apply_resource_dict"):
            return attr_val._apply_resource_dict(aws_account, context)
        elif not isinstance(attr_val, list):
            return attr_val

        matching_definitions = [
            val for val in attr_val if apply_to_provider(val, aws_account, context)
        ]
        if len(matching_definitions) == 0:
            # Fallback to the default definition
            field = self
            split_key = attr.split(".")
            if len(split_key) > 1:
                for key in split_key[:-1]:
                    field = getattr(field, key)
            return field.__fields__[split_key[-1]].default
        elif as_boto_dict:
            return [
                match._apply_resource_dict(aws_account, context)
                if hasattr(match, "_apply_resource_dict")
                else match
                for match in matching_definitions
            ]
        else:
            return matching_definitions

    def _apply_resource_dict(
        self, aws_account: AWSAccount = None, context: ExecutionContext = None
    ) -> dict:
        exclude_keys = {
            "deleted",
            "expires_at",
            "included_accounts",
            "excluded_accounts",
            "included_orgs",
            "excluded_orgs",
            "owner",
            "template_type",
            "file_path",
            "metadata_iambic_fields",
            "metadata_commented_dict",
        }
        exclude_keys.update(self.exclude_keys)
        has_properties = hasattr(self, "properties")
        properties = getattr(self, "properties", self)
        if aws_account:
            resource_dict = {
                k: self.get_attribute_val_for_account(
                    aws_account,
                    f"properties.{k}" if has_properties else k,
                    context=context,
                )
                for k in properties.__dict__.keys()
                if k not in exclude_keys
            }
            resource_dict = {k: v for k, v in resource_dict.items() if bool(v)}
        else:
            resource_dict = properties.dict(
                exclude=exclude_keys, exclude_none=True, exclude_unset=False
            )

        return {self.case_convention(k): v for k, v in resource_dict.items()}

    def apply_resource_dict(
        self, aws_account: AWSAccount, context: ExecutionContext
    ) -> dict:
        response = self._apply_resource_dict(aws_account, context)
        variables = {var.key: var.value for var in aws_account.variables}
        variables["account_id"] = aws_account.account_id
        variables["account_name"] = aws_account.account_name
        if hasattr(self, "owner") and (owner := getattr(self, "owner", None)):
            variables["owner"] = owner

        rtemplate = Environment(loader=BaseLoader()).from_string(json.dumps(response))
        data = rtemplate.render(**variables)
        return json.loads(data)

    async def remove_expired_resources(self, context: ExecutionContext):
        # Look at current model and recurse through submodules to see if it is a subclass of ExpiryModel
        # If it is, then call the remove_expired_resources method

        if issubclass(type(self), ExpiryModel):
            if hasattr(self, "expires_at") and self.expires_at:
                if self.expires_at < datetime.datetime.now(datetime.timezone.utc):
                    self.deleted = True
                    log.info("Expired resource found, marking for deletion")
                    return self
        for field_name in self.__fields__.keys():
            field_val = getattr(self, field_name)
            if isinstance(field_val, list):
                await asyncio.gather(
                    *[
                        elem.remove_expired_resources(context)
                        for elem in field_val
                        if isinstance(elem, BaseModel)
                    ]
                )
                for elem in field_val:
                    if getattr(elem, "deleted", None) is True:
                        field_val.remove(elem)

            elif not (
                isinstance(field_val, BaseModel) or isinstance(field_val, ExpiryModel)
            ):
                continue

            else:
                if isinstance(field_val, BaseModel):
                    await field_val.remove_expired_resources(context)
                    if getattr(field_val, "deleted", None) is True:
                        setattr(self, field_name, None)

    @property
    def exclude_keys(self) -> set:
        return set()

    @property
    def case_convention(self):
        return snake_to_camelcap

    @property
    def resource_type(self) -> str:
        raise NotImplementedError

    @property
    def resource_id(self) -> str:
        raise NotImplementedError


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
        source_access_model.included_children
    )
    destination_access_model.set_excluded_children(
        source_access_model.excluded_children
    )
    destination_access_model.set_included_parents(source_access_model.included_parents)
    destination_access_model.set_excluded_parents(source_access_model.excluded_parents)
    return source_access_model, destination_access_model


def update_access_attributes(
    new_model: AccessModelMixin,
    existing_model: AccessModelMixin,
    all_provider_children: list[ProviderChild],
) -> Union[
    tuple[AccessModelMixin, AccessModelMixin],
    tuple[AccessModelMixin, list[AccessModelMixin]],
]:
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
        # elif len(matching_existing_models) == 1:
        #     merged_model = merge_model(
        #         new_model, matching_existing_models[0], all_provider_children
        #     )
        #     if merged_model:
        #         merged_list.append(merged_model)
        elif new_model.included_children == ["*"]:
            # Find the least specific
            matching_existing_models = sort_access_models_by_included_children(
                matching_existing_models, False
            )
            merged_model = merge_model(
                new_model, matching_existing_models[0], all_provider_children
            )
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
                    sub_merged_model_list.append(merged_model)

            merged_list.extend(sub_merged_model_list)
            new_model.set_included_children(
                [
                    child
                    for child in new_model.included_children
                    if "*" not in child and child not in resolved_children
                ]
            )
            if new_model.included_children:
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
    if new_model is None:
        # The attribute was set to None
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


class ProposedChangeType(Enum):
    CREATE = "Create"
    UPDATE = "Update"
    DELETE = "Delete"
    ATTACH = "Attach"
    DETACH = "Detach"


class ProposedChange(PydanticBaseModel):
    change_type: ProposedChangeType
    account: Optional[
        str
    ]  # Used for Org related changes like permission set account assignments
    attribute: Optional[str]
    resource_id: Optional[str]
    resource_type: Optional[str]
    current_value: Optional[Union[list, dict, str, int]]
    new_value: Optional[Union[list, dict, str, int]]
    change_summary: Optional[dict]


class AccountChangeDetails(PydanticBaseModel):
    org_id: Optional[str]
    account: Union[str, int]
    resource_id: Union[str, int]
    current_value: Optional[dict]
    new_value: Optional[dict]
    proposed_changes: list[ProposedChange] = Field(default=[])


class TemplateChangeDetails(PydanticBaseModel):
    resource_id: str
    resource_type: str
    template_path: str
    # Supports multi-account providers and single-account providers
    proposed_changes: Optional[
        Union[list[AccountChangeDetails], list[ProposedChange]]
    ] = None

    class Config:
        json_encoders = {PrettyOrderedSet: list}

    def dict(
        self,
        *,
        include: Optional[
            Union["AbstractSetIntStr", "MappingIntStrAny"]  # noqa
        ] = None,
        exclude: Optional[
            Union["AbstractSetIntStr", "MappingIntStrAny"]  # noqa
        ] = None,
        by_alias: bool = False,
        skip_defaults: Optional[bool] = None,
        exclude_unset: bool = True,
        exclude_defaults: bool = False,
        exclude_none: bool = True,
    ) -> "DictStrAny":  # noqa
        response = self.json(
            include=include,
            exclude=exclude,
            by_alias=by_alias,
            skip_defaults=skip_defaults,
            exclude_unset=exclude_unset,
            exclude_defaults=exclude_defaults,
            exclude_none=exclude_none,
        )
        return json.loads(response)


class ProviderChild(PydanticBaseModel):
    """
    Inherited by the provider class to provide a consistent interface for AccessModelMixin

    For AWS, this is the AWS account
    For GCP, this is the GCP project
    For Okta, this is the IDP domain
    """

    iambic_managed: Optional[IambicManaged] = Field(
        IambicManaged.UNDEFINED,
        description="Controls the directionality of iambic changes",
    )

    @property
    def parent_id(self) -> Optional[str]:
        """
        For example, the parent_id of an AWS account is the AWS organization ID
        """
        raise NotImplementedError

    @property
    def preferred_identifier(self) -> str:
        raise NotImplementedError

    @property
    def all_identifiers(self) -> set[str]:
        raise NotImplementedError


class AccessModelMixin:
    @property
    def included_children(self):
        raise NotImplementedError

    def set_included_children(self, value):
        raise NotImplementedError

    @property
    def excluded_children(self):
        raise NotImplementedError

    def set_excluded_children(self, value):
        raise NotImplementedError

    @property
    def included_parents(self):
        raise NotImplementedError

    def set_included_parents(self, value):
        raise NotImplementedError

    @property
    def excluded_parents(self):
        raise NotImplementedError

    def set_excluded_parents(self, value):
        raise NotImplementedError

    def access_model_sort_weight(self):
        return (
            str(self.included_children)
            + str(self.excluded_children)
            + str(self.included_parents)
            + str(self.excluded_parents)
        )


class BaseTemplate(
    BaseModel,
):
    template_type: str
    file_path: str
    iambic_managed: Optional[IambicManaged] = Field(
        IambicManaged.UNDEFINED,
        description="Controls the directionality of Iambic changes",
    )

    def dict(
        self,
        *,
        include: Optional[
            Union["AbstractSetIntStr", "MappingIntStrAny"]  # noqa
        ] = None,
        exclude: Optional[
            Union["AbstractSetIntStr", "MappingIntStrAny"]  # noqa
        ] = None,
        by_alias: bool = False,
        skip_defaults: Optional[bool] = None,
        exclude_unset: bool = True,
        exclude_defaults: bool = False,
        exclude_none: bool = True,
    ) -> "DictStrAny":  # noqa
        if exclude:
            exclude.add("file_path")
        else:
            exclude = {"file_path"}

        template_dict = self.json(
            include=include,
            exclude=exclude,
            by_alias=by_alias,
            skip_defaults=skip_defaults,
            exclude_unset=exclude_unset,
            exclude_defaults=exclude_defaults,
            exclude_none=exclude_none,
        )
        template_dict = json.loads(template_dict)
        template_dict["template_type"] = self.template_type
        return template_dict

    def get_body(self, exclude_none=True, exclude_unset=True, exclude_defaults=True):
        input_dict = self.dict(
            exclude_none=exclude_none,
            exclude_unset=exclude_unset,
            exclude_defaults=exclude_defaults,
            exclude={"file_path"},
        )
        sorted_input_dict = sort_dict(input_dict)
        sorted_input_dict = create_commented_map(sorted_input_dict)
        as_yaml = yaml.dump(sorted_input_dict)
        # Force template_type to be at the top of the yaml
        template_type_str = f"template_type: {self.template_type}"
        as_yaml = as_yaml.replace(f"{template_type_str}\n", "")
        as_yaml = as_yaml.replace(f"\n{template_type_str}", "")
        as_yaml = f"{template_type_str}\n{as_yaml}"
        return as_yaml

    def write(self, exclude_none=True, exclude_unset=True, exclude_defaults=True):
        as_yaml = self.get_body(exclude_none, exclude_unset, exclude_defaults)
        os.makedirs(os.path.dirname(os.path.expanduser(self.file_path)), exist_ok=True)
        with open(self.file_path, "w") as f:
            f.write(as_yaml)

    def delete(self):
        log.info("Deleting template file", file_path=self.file_path)
        try:
            repo = Repo(self.file_path, search_parent_directories=True)
            repo.index.remove([self.file_path], working_tree=True)
        except Exception as e:
            log.error(
                "Unable to remove file from local Git repo. Deleting manually",
                error=e,
                file_path=self.file_path,
            )
            os.remove(self.file_path)

    async def apply(
        self, config: Config, context: ExecutionContext
    ) -> TemplateChangeDetails:
        raise NotImplementedError

    @classmethod
    def load(cls, file_path: str):
        return cls(
            file_path=file_path, **transform_commments(yaml.load(open(file_path)))
        )

    @classmethod
    def iambic_specific_knowledge(cls) -> set[str]:
        return {"iambic_managed", "file_path"}


class Variable(PydanticBaseModel):
    key: str
    value: str


class ExpiryModel(IambicPydanticBaseModel):
    expires_at: Optional[Union[str, datetime.datetime, datetime.date]] = Field(
        None, description="The date and time the resource will be/was set to deleted."
    )
    deleted: Optional[bool] = Field(
        False,
        description=(
            "Denotes whether the resource has been removed from AWS."
            "Upon being set to true, the resource will be deleted the next time iambic is ran."
        ),
    )

    @validator("expires_at", pre=True)
    def parse_expires_at(cls, value):
        dt = None
        if not value:
            return value
        if isinstance(value, datetime.date):
            dt = datetime.datetime.combine(
                value, datetime.datetime.min.time()
            ).astimezone(datetime.timezone.utc)
            return dt
        if isinstance(value, datetime.datetime):
            dt = value
            if not dt.tzinfo:
                dt = dt.replace(tzinfo=datetime.timezone.utc)
            return dt
        dt = dateparser.parse(
            value, settings={"TIMEZONE": "UTC", "RETURN_AS_TIMEZONE_AWARE": True}
        )
        return dt

    @classmethod
    def iambic_specific_knowledge(cls) -> set[str]:
        return {"expires_at", "deleted"}
