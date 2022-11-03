import json
from enum import Enum
from typing import Optional, Union

from jinja2 import BaseLoader, Environment
from pydantic import BaseModel as PydanticBaseModel
from pydantic import Field

from iambic.aws.utils import apply_to_account
from iambic.config.models import AWSAccount, Config
from iambic.core.context import ExecutionContext
from iambic.core.utils import snake_to_camelcap, yaml


class BaseModel(PydanticBaseModel):
    def get_attribute_val_for_account(
        self,
        aws_account: AWSAccount,
        attr: str,
        as_boto_dict: bool = True,
        context: ExecutionContext = None,
    ):
        attr_val = getattr(self, attr)

        if as_boto_dict and hasattr(attr_val, "_apply_resource_dict"):
            return attr_val._apply_resource_dict(aws_account)
        elif not isinstance(attr_val, list):
            return attr_val

        matching_definitions = [
            val for val in attr_val if apply_to_account(val, aws_account)
        ]
        if len(matching_definitions) == 0:
            # Fallback to the default definition
            return self.__fields__[attr].default
        elif as_boto_dict:
            return [
                match._apply_resource_dict(aws_account)
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

        if aws_account:
            resource_dict = {
                k: self.get_attribute_val_for_account(aws_account, k, context=context)
                for k in self.__dict__.keys()
                if k not in exclude_keys
            }
            resource_dict = {k: v for k, v in resource_dict.items() if bool(v)}
        else:
            resource_dict = self.dict(
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
        if owner := getattr(self, "owner"):
            variables["owner"] = owner

        rtemplate = Environment(loader=BaseLoader()).from_string(json.dumps(response))
        data = rtemplate.render(**variables)
        return json.loads(data)

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
    current_value: Optional[Union[list | dict | str | int]]
    new_value: Optional[Union[list | dict | str | int]]
    change_summary: Optional[dict]


class AccountChangeDetails(PydanticBaseModel):
    account: Union[str | int]
    resource_id: Union[str | int]
    current_value: Optional[dict]
    new_value: Optional[dict]
    proposed_changes: list[ProposedChange] = Field(default=[])


class TemplateChangeDetails(PydanticBaseModel):
    resource_id: str
    resource_type: str
    template_path: str
    # Supports multi-account providers and single-account providers
    proposed_changes: Optional[list[AccountChangeDetails] | list[ProposedChange]]

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


class BaseTemplate(BaseModel):
    template_type: str
    file_path: str
    read_only: Optional[bool] = Field(
        False,
        description="If set to True, iambic will only log drift instead of apply changes when drift is detected.",
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

    def write(self):
        as_yaml = yaml.dump(self.dict())
        # Force template_type to be at the top of the yaml
        template_type_str = f"template_type: {self.template_type}"
        as_yaml = as_yaml.replace(f"\n{template_type_str}", "")
        as_yaml = f"{template_type_str}\n{as_yaml}"
        with open(self.file_path, "w") as f:
            f.write(as_yaml)

    async def apply(
        self, config: Config, context: ExecutionContext
    ) -> TemplateChangeDetails:
        raise NotImplementedError

    @classmethod
    def load(cls, file_path: str):
        return cls(file_path=file_path, **yaml.load(open(file_path)))
