import asyncio
import json
from datetime import datetime
from typing import List, Optional, Union

from jinja2 import BaseLoader, Environment
from pydantic import BaseModel as PydanticBaseModel

from noq_form.config.models import AccountConfig, Config
from noq_form.core.context import ctx
from noq_form.core.logger import log
from noq_form.core.utils import (
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
            "enabled",
            "expires_at",
            "included_accounts",
            "excluded_accounts",
            "included_orgs",
            "excluded_orgs",
            "owner",
            "template_type",
            "file_path",
        }

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

        return self._resource_dict_case_normalizer(resource_dict)

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
    def exclude_keys(self):
        return set()

    @staticmethod
    def _resource_dict_case_normalizer(resource_dict) -> dict:
        return {snake_to_camelcap(k): v for k, v in resource_dict.items()}


class AccessModel(BaseModel):
    included_accounts: List = ["*"]
    excluded_accounts: Optional[List] = []
    included_orgs: List = ["*"]
    excluded_orgs: Optional[List] = []


class Enabled(AccessModel):
    enabled: bool


class ExpiryModel(BaseModel):
    expires_at: Optional[datetime] = None
    enabled: Optional[Union[bool | List[Enabled]]] = True

    @property
    def resource_type(self):
        raise NotImplementedError

    @property
    def resource_name(self):
        raise NotImplementedError


class Tag(ExpiryModel, AccessModel):
    key: str
    value: str

    @property
    def resource_type(self):
        return "Tag"

    @property
    def resource_name(self):
        return self.key


class NoqTemplate(ExpiryModel):
    template_type: str
    file_path: str
    dry_run_only: Optional[bool] = False

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
            resource_type=self.resource_type, resource_name=self.resource_name
        )
        for account in config.accounts:
            if evaluate_on_account(self, account):
                log.info(
                    "Applying changes to resource.", account=str(account), **log_params
                )
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
            log.info("No changes detected for resource on any account.", **log_params)

        return changes_made

    @classmethod
    def load(cls, file_path: str):
        return cls(file_path=file_path, **yaml.load(open(file_path)))
