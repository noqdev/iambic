import asyncio
import json
from datetime import datetime
from typing import List, Optional, Union

from jinja2 import BaseLoader, Environment
from pydantic import BaseModel as PydanticBaseModel
from pydantic import Field

from iambic.config.models import AccountConfig, Config
from iambic.core.context import ctx
from iambic.core.logger import log
from iambic.core.utils import (
    apply_to_account,
    evaluate_on_account,
    snake_to_camelcap,
    yaml,
)


class BaseModel(PydanticBaseModel):
    def get_attribute_val_for_account(
        self, account_config: AccountConfig, attr: str, as_boto_dict: bool = True
    ):
        attr_val = getattr(self, attr)

        if as_boto_dict and hasattr(attr_val, "_apply_resource_dict"):
            return attr_val._apply_resource_dict(account_config)
        elif not isinstance(attr_val, list):
            return attr_val

        matching_definitions = [
            val for val in attr_val if apply_to_account(val, account_config)
        ]
        if len(matching_definitions) == 0:
            # Fallback to the default definition
            return self.__fields__[attr].default
        elif as_boto_dict:
            return [
                match._apply_resource_dict(account_config)
                if hasattr(match, "_apply_resource_dict")
                else match
                for match in matching_definitions
            ]
        else:
            return matching_definitions

    def _apply_resource_dict(self, account_config: AccountConfig = None) -> dict:
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

        if account_config:
            resource_dict = {
                k: self.get_attribute_val_for_account(account_config, k)
                for k in self.__dict__.keys()
                if k not in exclude_keys
            }
            resource_dict = {k: v for k, v in resource_dict.items() if bool(v)}
        else:
            resource_dict = self.dict(
                exclude=exclude_keys, exclude_none=True, exclude_unset=False
            )

        return {self.case_convention(k): v for k, v in resource_dict.items()}

    def apply_resource_dict(self, account_config: AccountConfig) -> dict:
        response = self._apply_resource_dict(account_config)
        variables = {var.key: var.value for var in account_config.variables}
        variables["account_id"] = account_config.account_id
        variables["account_name"] = account_config.account_name
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


class AccessModel(BaseModel):
    included_accounts: List = Field(
        ["*"],
        description="A list of account ids and/or account names this statement applies to. "
        "Account ids/names can be represented as a regex and string",
    )
    excluded_accounts: Optional[List] = Field(
        [],
        description="A list of account ids and/or account names this statement explicitly does not apply to. "
        "Account ids/names can be represented as a regex and string",
    )
    included_orgs: List = Field(
        ["*"],
        description="A list of AWS organization ids this statement applies to. "
        "Org ids can be represented as a regex and string",
    )
    excluded_orgs: Optional[List] = Field(
        [],
        description="A list of AWS organization ids this statement explicitly does not apply to. "
        "Org ids can be represented as a regex and string",
    )


class Deleted(AccessModel):
    deleted: bool = Field(
        description="Denotes whether the resource has been removed from AWS."
        "Upon being set to true, the resource will be deleted the next time iambic is ran.",
    )


class ExpiryModel(BaseModel):
    expires_at: Optional[datetime] = Field(
        None, description="The date and time the resource will be/was set to deleted."
    )
    deleted: Optional[Union[bool | List[Deleted]]] = Field(
        False,
        description="Denotes whether the resource has been removed from AWS."
        "Upon being set to true, the resource will be deleted the next time iambic is ran.",
    )

    @property
    def resource_type(self) -> str:
        raise NotImplementedError

    @property
    def resource_id(self) -> str:
        raise NotImplementedError


class Tag(ExpiryModel, AccessModel):
    key: str
    value: str

    @property
    def resource_type(self):
        return "Tag"

    @property
    def resource_id(self):
        return self.key


class NoqTemplate(ExpiryModel):
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
        with open(self.file_path, "w") as f:
            f.write(yaml.dump(self.dict()))

    async def _apply_to_account(self, account_config: AccountConfig) -> bool:
        # The bool represents whether the resource was altered in any way in the cloud
        raise NotImplementedError

    async def apply_all(self, config: Config) -> bool:
        tasks = []
        log_params = dict(
            resource_type=self.resource_type, resource_id=self.resource_id
        )
        for account in config.accounts:
            if evaluate_on_account(self, account):
                if ctx.execute:
                    log_str = "Applying changes to resource."
                else:
                    log_str = "Detecting changes for resource."
                log.info(log_str, account=str(account), **log_params)
                tasks.append(self._apply_to_account(account))

        changes_made = await asyncio.gather(*tasks)
        changes_made = bool(any(changes_made))
        if changes_made and ctx.execute:
            log.info(
                "Successfully applied resource changes to all accounts.", **log_params
            )
        elif changes_made and not ctx.execute:
            log.info(
                "Successfully detected required resource changes on all accounts.",
                **log_params,
            )
        else:
            log.debug("No changes detected for resource on any account.", **log_params)

        return changes_made

    @classmethod
    def load(cls, file_path: str):
        return cls(file_path=file_path, **yaml.load(open(file_path)))
