from __future__ import annotations

import asyncio
import datetime
import json
import os
from enum import Enum
from types import GenericAlias
from typing import TYPE_CHECKING, Any, List, Optional, Set, Union, get_args, get_origin

import dateparser
from deepdiff.model import PrettyOrderedSet
from git import Repo
from jinja2 import BaseLoader, Environment
from pydantic import BaseModel as PydanticBaseModel
from pydantic import Field, validator
from pydantic.fields import ModelField

from iambic.aws.utils import apply_to_account
from iambic.core.context import ExecutionContext
from iambic.core.iambic_enum import IambicManaged
from iambic.core.logger import log
from iambic.core.utils import snake_to_camelcap, sort_dict, yaml

if TYPE_CHECKING:
    from iambic.aws.models import AWSAccount, Deleted
    from iambic.config.models import Config


class BaseModel(PydanticBaseModel):
    @classmethod
    def update_forward_refs(cls, **kwargs):
        from iambic.aws.models import Deleted

        kwargs.update({"Union": Union, "Deleted": Deleted})
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
    def get_field_type(field: Any) -> Any:
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
            val for val in attr_val if apply_to_account(val, aws_account, context)
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
                if self.expires_at < datetime.datetime.utcnow():
                    self.deleted = True
                    return self
        for field_name in self.__fields__.keys():
            field_val = getattr(self, field_name)
            if isinstance(field_val, list):
                await asyncio.gather(
                    *[elem.remove_expired_resources(context) for elem in field_val]
                )
                for elem in field_val:
                    if getattr(elem, "deleted", None) is True:
                        field_val.remove(elem)

            elif not (
                isinstance(field_val, BaseModel) or isinstance(field_val, ExpiryModel)
            ):
                continue

            else:
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


class ProposedChangeType(Enum):
    CREATE = "Create"
    UPDATE = "Update"
    DELETE = "Delete"
    ATTACH = "Attach"
    DETACH = "Detach"


class ProposedChange(PydanticBaseModel):
    change_type: ProposedChangeType
    attribute: Optional[str]
    resource_id: Optional[str]
    resource_type: Optional[str]
    current_value: Optional[Union[list, dict, str, int]]
    new_value: Optional[Union[list, dict, str, int]]
    change_summary: Optional[dict]


class AccountChangeDetails(PydanticBaseModel):
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

    def write(self, exclude_none=True, exclude_unset=True, exclude_defaults=True):
        input_dict = self.dict(
            exclude_none=exclude_none,
            exclude_unset=exclude_unset,
            exclude_defaults=exclude_defaults,
            exclude={"file_path"},
        )
        sorted_input_dict = sort_dict(input_dict)
        as_yaml = yaml.dump(sorted_input_dict)
        # Force template_type to be at the top of the yaml
        template_type_str = f"template_type: {self.template_type}"
        as_yaml = as_yaml.replace(f"{template_type_str}\n", "")
        as_yaml = as_yaml.replace(f"\n{template_type_str}", "")
        as_yaml = f"{template_type_str}\n{as_yaml}"
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
        return cls(file_path=file_path, **yaml.load(open(file_path)))


class Variable(PydanticBaseModel):
    key: str
    value: str


class ExpiryModel(PydanticBaseModel):
    expires_at: Optional[Union[str, datetime.datetime, datetime.date]] = Field(
        None, description="The date and time the resource will be/was set to deleted."
    )
    deleted: Optional[Union[bool, List[Deleted]]] = Field(
        False,
        description=(
            "Denotes whether the resource has been removed from AWS."
            "Upon being set to true, the resource will be deleted the next time iambic is ran."
        ),
    )

    @validator("expires_at", pre=True)
    def parse_expires_at(cls, value):
        if not value or isinstance(value, datetime.datetime):
            return value
        elif isinstance(value, datetime.date):
            return datetime.datetime.combine(value, datetime.datetime.min.time())
        return dateparser.parse(
            value,
        )
