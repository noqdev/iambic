import asyncio
from datetime import datetime
from typing import List, Optional, Union

from pydantic import Field

from iambic.aws.utils import evaluate_on_account
from iambic.config.models import AWSAccount, Config
from iambic.core.context import ctx
from iambic.core.logger import log
from iambic.core.models import (
    AccountChangeDetails,
    BaseModel,
    BaseTemplate,
    TemplateChangeDetails,
)

ARN_RE = r"(^arn:([^:]*):([^:]*):([^:]*):(|\*|[\d]{12}|cloudfront|aws|{{account_id}}):(.+)$)|^\*$"


class AccessModel(BaseModel):
    included_accounts: list[str] = Field(
        ["*"],
        description=(
            "A list of account ids and/or account names this statement applies to. "
            "Account ids/names can be represented as a regex and string"
        ),
    )
    excluded_accounts: Optional[list[str]] = Field(
        [],
        description=(
            "A list of account ids and/or account names this statement explicitly does not apply to. "
            "Account ids/names can be represented as a regex and string"
        ),
    )
    included_orgs: list[str] = Field(
        ["*"],
        description=(
            "A list of AWS organization ids this statement applies to. "
            "Org ids can be represented as a regex and string"
        ),
    )
    excluded_orgs: Optional[list[str]] = Field(
        [],
        description=(
            "A list of AWS organization ids this statement explicitly does not apply to. "
            "Org ids can be represented as a regex and string"
        ),
    )


class Deleted(AccessModel):
    deleted: bool = Field(
        description=(
            "Denotes whether the resource has been removed from AWS."
            "Upon being set to true, the resource will be deleted the next time iambic is ran."
        ),
    )


class ExpiryModel(BaseModel):
    expires_at: Optional[datetime] = Field(
        None, description="The date and time the resource will be/was set to deleted."
    )
    deleted: Optional[Union[bool, List[Deleted]]] = Field(
        False,
        description=(
            "Denotes whether the resource has been removed from AWS."
            "Upon being set to true, the resource will be deleted the next time iambic is ran."
        ),
    )


class Tag(ExpiryModel, AccessModel):
    key: str
    value: str

    @property
    def resource_type(self):
        return "Tag"

    @property
    def resource_id(self):
        return self.key


class AWSTemplate(BaseTemplate, ExpiryModel):
    async def _apply_to_account(self, aws_account: AWSAccount) -> AccountChangeDetails:
        raise NotImplementedError

    async def apply(self, config: Config) -> TemplateChangeDetails:
        tasks = []
        template_changes = TemplateChangeDetails(
            resource_id=self.resource_id,
            resource_type=self.resource_type,
            template_path=self.file_path,
        )
        log_params = dict(
            resource_type=self.resource_type, resource_id=self.resource_id
        )
        for account in config.aws_accounts:
            if evaluate_on_account(self, account):
                if ctx.execute:
                    log_str = "Applying changes to resource."
                else:
                    log_str = "Detecting changes for resource."
                log.info(log_str, account=str(account), **log_params)
                tasks.append(self._apply_to_account(account))

        account_changes = await asyncio.gather(*tasks)
        template_changes.proposed_changes = [
            account_change
            for account_change in account_changes
            if any(account_change.proposed_changes)
        ]
        if account_changes and ctx.execute:
            log.info(
                "Successfully applied resource changes to all aws_accounts.",
                **log_params,
            )
        elif account_changes and not ctx.execute:
            log.info(
                "Successfully detected required resource changes on all aws_accounts.",
                **log_params,
            )
        else:
            log.debug("No changes detected for resource on any account.", **log_params)

        return template_changes
