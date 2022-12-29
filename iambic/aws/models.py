from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, List, Optional, Union

import boto3
import botocore
from pydantic import BaseModel as PydanticBaseModel
from pydantic import Field, constr

from iambic.aws.utils import (
    RegionName,
    create_assume_role_session,
    evaluate_on_account,
    get_account_value,
    legacy_paginated_search,
    set_org_account_variables,
)
from iambic.core.context import ExecutionContext
from iambic.core.logger import log
from iambic.core.models import (
    AccountChangeDetails,
    BaseModel,
    BaseTemplate,
    ExpiryModel,
    TemplateChangeDetails,
    Variable,
)
from iambic.core.utils import aio_wrapper

if TYPE_CHECKING:
    from iambic.config.models import Config

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


class Tag(ExpiryModel, AccessModel):
    key: str
    value: str

    @property
    def resource_type(self):
        return "Tag"

    @property
    def resource_id(self):
        return self.key


class AssumeRoleConfiguration(PydanticBaseModel):
    arn: str = Field(
        description="The role arn to assume into when making calls to the account",
    )
    kwargs: dict = Field(
        {},
        description="Additional kwargs to pass to the assume_role call",
    )


class BaseAWSAccountAndOrgModel(PydanticBaseModel):
    default_region: Optional[RegionName] = Field(
        RegionName.us_east_1,
        description="Default region to use when making AWS requests",
    )
    aws_profile: Optional[str] = Field(
        None,
        description="The AWS profile used when making calls to the account",
    )
    assume_role_arns: list[AssumeRoleConfiguration] = Field(
        [],
        description="The role arns to assume into when making calls to the account",
    )
    boto3_session_map: Optional[dict] = None

    async def get_boto3_session(self, region_name: str = None):
        region_name = region_name or self.default_region
        # Get a boto3 session for this account by using the AWS profile if it exists,
        # And then assuming into the list of roles if they exist

        if self.boto3_session_map is None:
            self.boto3_session_map = {}
        elif boto3_session := self.boto3_session_map.get(region_name):
            return boto3_session

        session = boto3.Session(region_name=region_name)

        if self.aws_profile:
            try:
                session = boto3.Session(
                    profile_name=self.aws_profile, region_name=region_name
                )
            except Exception as err:
                log.exception(err)

        session = await create_assume_role_session(
            session, self.assume_role_arns, region_name
        )

        self.boto3_session_map[region_name] = session
        return self.boto3_session_map[region_name]

    async def get_boto3_client(self, service: str, region_name: str = None):
        return (await self.get_boto3_session(region_name)).client(
            service, config=botocore.client.Config(max_pool_connections=50)
        )

    def __init__(self, **kwargs):
        super(BaseAWSAccountAndOrgModel, self).__init__(**kwargs)
        self.default_region = self.default_region.value


class AWSAccount(BaseAWSAccountAndOrgModel):
    account_id: constr(min_length=12, max_length=12) = Field(
        None, description="The AWS Account ID"
    )
    org_id: Optional[str] = Field(
        None,
        description="A unique identifier designating the identity of the organization",
    )
    account_name: Optional[str] = None
    role_access_tag: Optional[str] = Field(
        None,
        description="The key of the tag used to store users and groups that can assume into the role the tag is on",
    )
    read_only: Optional[bool] = Field(
        False,
        description="If set to True, iambic will only log drift instead of apply changes when drift is detected.",
    )
    variables: Optional[List[Variable]] = Field(
        [],
        description="A list of variables to be used when creating templates",
    )
    org_session_info: Optional[dict] = None

    async def get_boto3_session(self, region_name: str = None):
        region_name = region_name or self.default_region

        if self.boto3_session_map is None:
            self.boto3_session_map = {}
        elif boto3_session := self.boto3_session_map.get(region_name):
            return boto3_session

        if self.org_session_info:
            boto3_session = await create_assume_role_session(
                self.org_session_info["boto3_session"],
                self.assume_role_arns,
                region_name,
            )
            if boto3_session:
                self.boto3_session_map[region_name] = boto3_session
                return boto3_session

        return await super(AWSAccount, self).get_boto3_session(region_name)

    def __str__(self):
        return f"{self.account_name} - ({self.account_id})"

    def __init__(self, **kwargs):
        super(AWSAccount, self).__init__(**kwargs)
        if not isinstance(self.default_region, str):
            self.default_region = self.default_region.value


class BaseAWSOrgRule(BaseModel):
    enabled: Optional[bool] = Field(
        True,
        description="If set to False, iambic will ignore the included accounts.",
    )
    read_only: Optional[bool] = Field(
        False,
        description="If set to True, iambic will only log drift instead of apply changes when drift is detected.",
    )
    assume_role_name: Optional[Union[str, list[str]]] = Field(
        default=["OrganizationAccountAccessRole", "AWSControlTowerExecution"],
        description="The role name(s) to use when assuming into an included account. "
        "If not provided, this iambic will use the default AWS organization role(s).",
    )


class AWSOrgAccountRule(BaseAWSOrgRule):
    included_accounts: list[str] = Field(
        ["*"],
        description=(
            "A list of account ids and/or account names this rule applies to. "
            "Account ids/names can be represented as a regex and string"
        ),
    )
    excluded_accounts: Optional[list[str]] = Field(
        [],
        description=(
            "A list of account ids and/or account names this rule explicitly does not apply to. "
            "Account ids/names can be represented as a regex and string"
        ),
    )


class AWSOrganization(BaseAWSAccountAndOrgModel):
    org_id: str = Field(
        None,
        description="A unique identifier designating the identity of the organization",
    )
    org_name: Optional[str] = None
    default_rule: BaseAWSOrgRule = Field(
        description="The rule used to determine how an organization account should be handled if the account was not found in account_rules.",
    )
    account_rules: Optional[List[AWSOrgAccountRule]] = Field(
        [],
        description="A list of rules used to determine how organization accounts are handled",
    )

    async def _create_org_account_instance(
        self, account: dict, session: boto3.Session
    ) -> Optional[AWSAccount]:
        """Create an AWSAccount instance from an AWS Organization account and account dict

        Evaluate rules to determine if the account should be added to the config and if it is a read-only account.
        """
        account_id = account["Id"]
        account_name = account["Name"]
        account_rule = self.default_rule

        if self.account_rules and (
            new_rule := get_account_value(self.account_rules, account_id, account_name)
        ):
            account_rule = new_rule

        if not account_rule.enabled:
            return

        region_name = str(self.default_region)
        aws_account = AWSAccount(
            account_id=account_id,
            account_name=account_name,
            org_id=self.org_id,
            variables=account["variables"],
            read_only=account_rule.read_only,
        )
        aws_account.boto3_session_map = {}
        assume_role_names = account_rule.assume_role_name
        if not isinstance(assume_role_names, list):
            assume_role_names = [assume_role_names]

        # Determine the assume_role_arn by attempting to assume into the provided assume_role_names.
        for assume_role_name in assume_role_names:
            assume_role_arn = f"arn:aws:iam::{account_id}:role/{assume_role_name}"
            boto3_session = await create_assume_role_session(
                session,
                [AssumeRoleConfiguration(arn=assume_role_arn)],
                region_name,
            )
            if boto3_session:
                try:
                    await aio_wrapper(boto3_session.get_credentials)
                    aws_account.boto3_session_map[region_name] = boto3_session
                    aws_account.org_session_info = dict(boto3_session=boto3_session)
                    aws_account.assume_role_arn = assume_role_arn
                    return aws_account
                except Exception as err:
                    log.debug(
                        "Failed to assume role",
                        assume_role_arn=assume_role_arn,
                        error=err,
                    )
                    continue

    async def get_accounts(
        self, existing_accounts_map: dict[str, AWSAccount] = None
    ) -> list[AWSAccount]:
        """Get all accounts in an AWS Organization

        Also extends variables for accounts that are already in the config.
        Does not overwrite variables.
        """
        if existing_accounts_map is None:
            existing_accounts_map = {}

        session = await self.get_boto3_session(
            self.default_region,
        )
        client = session.client("organizations")
        org_accounts = await legacy_paginated_search(
            client.list_accounts,
            "Accounts",
        )
        org_accounts = await asyncio.gather(
            *[
                set_org_account_variables(client, account)
                for account in org_accounts
                if account["Status"] == "ACTIVE"
            ]
        )
        response = list()
        discovered_accounts = list()

        for org_account in org_accounts:
            account_id = org_account["Id"]
            if account := existing_accounts_map.get(account_id):
                account.org_id = self.org_id
                existing_vars = {var["key"] for var in account.variables}
                for org_var in org_account["variables"]:
                    if org_var["key"] not in existing_vars:
                        account.variables.append(org_var)
                response.append(account)
            else:
                discovered_accounts.append(org_account)

        discovered_accounts = await asyncio.gather(
            *[
                self._create_org_account_instance(account, session)
                for account in discovered_accounts
            ]
        )
        response.extend([account for account in discovered_accounts if account])
        return response

    def __str__(self):
        return f"{self.org_name} - ({self.org_id})"


class AWSTemplate(BaseTemplate, ExpiryModel):
    async def _apply_to_account(
        self, aws_account: AWSAccount, context: ExecutionContext
    ) -> AccountChangeDetails:
        raise NotImplementedError

    async def apply(
        self, config: Config, context: ExecutionContext
    ) -> TemplateChangeDetails:
        tasks = []
        template_changes = TemplateChangeDetails(
            resource_id=self.resource_id,
            resource_type=self.resource_type,
            template_path=self.file_path,
        )
        log_params = dict(
            resource_type=self.resource_type, resource_id=self.resource_id
        )
        for account in config.aws.accounts:
            if evaluate_on_account(self, account, context):
                if context.execute:
                    log_str = "Applying changes to resource."
                else:
                    log_str = "Detecting changes for resource."
                log.info(log_str, account=str(account), **log_params)
                tasks.append(self._apply_to_account(account, context))

        account_changes = await asyncio.gather(*tasks)
        template_changes.proposed_changes = [
            account_change
            for account_change in account_changes
            if any(account_change.proposed_changes)
        ]
        if account_changes and context.execute:
            log.info(
                "Successfully applied resource changes to all aws_accounts.",
                **log_params,
            )
        elif account_changes and not context.execute:
            log.info(
                "Successfully detected required resource changes on all aws_accounts.",
                **log_params,
            )
        else:
            log.debug("No changes detected for resource on any account.", **log_params)

        return template_changes
