from __future__ import annotations

import asyncio
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional, Union

import boto3
import botocore
from pydantic import BaseModel as PydanticBaseModel
from pydantic import Field, constr

from iambic.aws.utils import RegionName, evaluate_on_account
from iambic.core.context import ExecutionContext
from iambic.core.logger import log
from iambic.core.models import (
    AccountChangeDetails,
    BaseModel,
    BaseTemplate,
    TemplateChangeDetails,
    Variable,
)

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


class ExpiryModel(PydanticBaseModel):
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


class BaseAWSAccountAndOrgModel(PydanticBaseModel):
    default_region: Optional[RegionName] = Field(
        RegionName.us_east_1,
        description="Default region to use when making AWS requests",
    )
    aws_profile: Optional[str] = Field(
        None,
        description="The AWS profile used when making calls to the account",
    )
    assume_role_arn: Optional[str] = Field(
        None,
        description="The role arn to assume into when making calls to the account",
    )
    external_id: Optional[str] = Field(
        None,
        description="The external id to use for assuming into a role when making calls to the account",
    )
    boto3_session_map: Optional[dict] = None

    def get_boto3_session(self, region_name: str = None):
        region_name = region_name or self.default_region

        if self.boto3_session_map is None:
            self.boto3_session_map = {}
        elif boto3_session := self.boto3_session_map.get(region_name):
            return boto3_session

        if self.aws_profile:
            try:
                self.boto3_session_map[region_name] = boto3.Session(
                    profile_name=self.aws_profile, region_name=region_name
                )
            except Exception as err:
                log.exception(err)
            else:
                return self.boto3_session_map[region_name]

        session = boto3.Session(region_name=region_name)
        if self.assume_role_arn:
            try:
                sts = session.client("sts")
                role_params = dict(
                    RoleArn=self.assume_role_arn,
                    RoleSessionName="iambic",
                )
                if self.external_id:
                    role_params["ExternalId"] = self.external_id
                role = sts.assume_role(**role_params)
                self.boto3_session_map[region_name] = boto3.Session(
                    region_name=region_name,
                    aws_access_key_id=role["Credentials"]["AccessKeyId"],
                    aws_secret_access_key=role["Credentials"]["SecretAccessKey"],
                    aws_session_token=role["Credentials"]["SessionToken"],
                )
            except Exception as err:
                log.exception(err)
            else:
                return self.boto3_session_map[region_name]

        self.boto3_session_map[region_name] = session
        return self.boto3_session_map[region_name]

    def get_boto3_client(self, service: str, region_name: str = None):
        return self.get_boto3_session(region_name).client(
            service, config=botocore.client.Config(max_pool_connections=50)
        )

    def __init__(self, **kwargs):
        super(BaseAWSAccountAndOrgModel, self).__init__(**kwargs)
        self.default_region = self.default_region.value


class AWSAccount(PydanticBaseModel):
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

    def get_boto3_session(self, region_name: str = None):
        region_name = region_name or self.default_region

        if self.boto3_session_map is None:
            self.boto3_session_map = {}
        elif boto3_session := self.boto3_session_map.get(region_name):
            return boto3_session

        if self.aws_profile:
            try:
                self.boto3_session_map[region_name] = boto3.Session(
                    profile_name=self.aws_profile, region_name=region_name
                )
            except Exception as err:
                log.exception(err)
            else:
                return self.boto3_session_map[region_name]

        session = boto3.Session(region_name=region_name)
        if self.assume_role_arn:
            try:
                sts = session.client("sts")
                role_params = dict(
                    RoleArn=self.assume_role_arn,
                    RoleSessionName="iambic",
                )
                if self.external_id:
                    role_params["ExternalId"] = self.external_id
                role = sts.assume_role(**role_params)
                self.boto3_session_map[region_name] = boto3.Session(
                    region_name=region_name,
                    aws_access_key_id=role["Credentials"]["AccessKeyId"],
                    aws_secret_access_key=role["Credentials"]["SecretAccessKey"],
                    aws_session_token=role["Credentials"]["SessionToken"],
                )
            except Exception as err:
                log.exception(err)
            else:
                return self.boto3_session_map[region_name]

        self.boto3_session_map[region_name] = session
        return self.boto3_session_map[region_name]

    def get_boto3_client(self, service: str, region_name: str = None):
        return self.get_boto3_session(region_name).client(
            service, config=botocore.client.Config(max_pool_connections=50)
        )

    def __str__(self):
        return f"{self.account_name} - ({self.account_id})"

    def __init__(self, **kwargs):
        super(AWSAccount, self).__init__(**kwargs)
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
    assume_role_name: Optional[Union[str | list[str]]] = Field(
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
        for account in config.aws_accounts:
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
