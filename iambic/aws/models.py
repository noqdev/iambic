from __future__ import annotations

import asyncio
from enum import Enum
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
from iambic.core.iambic_enum import IambicManaged
from iambic.core.logger import log
from iambic.core.models import (
    AccountChangeDetails,
    BaseModel,
    BaseTemplate,
    ExpiryModel,
    TemplateChangeDetails,
    Variable,
)
from iambic.core.utils import NoqSemaphore, aio_wrapper

if TYPE_CHECKING:
    from iambic.config.models import Config

ARN_RE = r"(^arn:([^:]*):([^:]*):([^:]*):(|\*|[\d]{12}|cloudfront|aws|{{account_id}}):(.+)$)|^\*$"


class Partition(Enum):
    AWS = "aws"
    AWS_GOV = "aws-us-gov"
    AWS_CHINA = "aws-cn"


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

    async def get_boto3_session(self, region_name: Optional[str] = None):
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
            boto3_session = await create_assume_role_session(
                session,
                self.assume_role_arn,
                region_name,
                external_id=self.external_id,
            )
            if boto3_session:
                self.boto3_session_map[region_name] = boto3_session
                return boto3_session

        self.boto3_session_map[region_name] = session
        return self.boto3_session_map[region_name]

    async def get_boto3_client(self, service: str, region_name: Optional[str] = None):
        return (await self.get_boto3_session(region_name)).client(
            service, config=botocore.client.Config(max_pool_connections=50)
        )

    async def get_active_regions(self) -> list[str]:
        client = await self.get_boto3_client("ec2")
        res = await aio_wrapper(client.describe_regions)
        return [region["RegionName"] for region in res["Regions"]]

    def __init__(self, **kwargs):
        super(BaseAWSAccountAndOrgModel, self).__init__(**kwargs)
        self.default_region = self.default_region.value


class IdentityCenterDetails(PydanticBaseModel):
    region: str
    instance_arn: Optional[str] = None
    identity_store_id: Optional[str] = None
    permission_set_map: Optional[Union[dict, None]] = None
    user_map: Optional[Union[dict, None]] = None
    group_map: Optional[Union[dict, None]] = None
    org_account_map: Optional[Union[dict, None]] = None

    def get_resource_name(self, resource_type: str, resource_id: str):
        resource_type = resource_type.lower()
        name_map = {"user": "UserName", "group": "DisplayName"}
        resource_map = getattr(self, f"{resource_type.lower()}_map")
        return resource_map.get(resource_id)[name_map[resource_type]]


class AWSAccount(BaseAWSAccountAndOrgModel):
    account_id: constr(min_length=12, max_length=12) = Field(
        None, description="The AWS Account ID"
    )
    org_id: Optional[str] = Field(
        None,
        description="A unique identifier designating the identity of the organization",
    )
    account_name: Optional[str] = None
    partition: Optional[Partition] = Field(
        Partition.AWS,
        description="The AWS partition the account is in. Options are aws, aws-us-gov, and aws-cn",
    )
    role_access_tag: Optional[str] = Field(
        None,
        description="The key of the tag used to store users and groups that can assume into the role the tag is on",
    )
    iambic_managed: Optional[IambicManaged] = Field(
        IambicManaged.UNDEFINED,
        description="Controls the directionality of iambic changes",
    )
    variables: Optional[List[Variable]] = Field(
        [],
        description="A list of variables to be used when creating templates",
    )
    org_session_info: Optional[dict] = None
    identity_center_details: Optional[Union[IdentityCenterDetails, None]] = None

    async def get_boto3_session(self, region_name: str = None):
        region_name = region_name or self.default_region

        if self.boto3_session_map is None:
            self.boto3_session_map = {}
        elif boto3_session := self.boto3_session_map.get(region_name):
            return boto3_session

        if self.org_session_info:
            boto3_session = await create_assume_role_session(
                self.org_session_info["boto3_session"],
                self.assume_role_arn,
                region_name,
                external_id=self.external_id,
            )
            if boto3_session:
                self.boto3_session_map[region_name] = boto3_session
                return boto3_session

        return await super(AWSAccount, self).get_boto3_session(region_name)

    async def set_identity_center_details(
        self, set_identity_center_map: bool = True
    ) -> None:
        if self.identity_center_details:
            region = self.identity_center_details.region
            identity_center_client = await self.get_boto3_client(
                "sso-admin", region_name=region
            )
            identity_store_client = await self.get_boto3_client(
                "identitystore", region_name=region
            )

            identity_center_instances = await aio_wrapper(
                identity_center_client.list_instances
            )

            if not identity_center_instances.get("Instances"):
                raise ValueError("No Identity Center instances found")

            self.identity_center_details.instance_arn = identity_center_instances[
                "Instances"
            ][0]["InstanceArn"]
            self.identity_center_details.identity_store_id = identity_center_instances[
                "Instances"
            ][0]["IdentityStoreId"]

            if not set_identity_center_map:
                return

            permission_set_arns = await legacy_paginated_search(
                identity_center_client.list_permission_sets,
                response_key="PermissionSets",
                InstanceArn=self.identity_center_details.instance_arn,
            )
            if permission_set_arns:
                permission_set_detail_semaphore = NoqSemaphore(
                    identity_center_client.describe_permission_set, 35, False
                )
                permission_set_details = await permission_set_detail_semaphore.process(
                    [
                        {
                            "InstanceArn": self.identity_center_details.instance_arn,
                            "PermissionSetArn": permission_set_arn,
                        }
                        for permission_set_arn in permission_set_arns
                    ]
                )
                self.identity_center_details.permission_set_map = {
                    permission_set["PermissionSet"]["Name"]: permission_set[
                        "PermissionSet"
                    ]
                    for permission_set in permission_set_details
                }

            users_and_groups = await asyncio.gather(
                *[
                    legacy_paginated_search(
                        identity_store_client.list_users,
                        response_key="Users",
                        retain_key=True,
                        IdentityStoreId=self.identity_center_details.identity_store_id,
                    ),
                    legacy_paginated_search(
                        identity_store_client.list_groups,
                        response_key="Groups",
                        retain_key=True,
                        IdentityStoreId=self.identity_center_details.identity_store_id,
                    ),
                ]
            )
            for user_or_group in users_and_groups:
                if "Users" in user_or_group:
                    self.identity_center_details.user_map = {
                        user["UserId"]: user for user in user_or_group["Users"]
                    }
                else:
                    self.identity_center_details.group_map = {
                        group["GroupId"]: group for group in user_or_group["Groups"]
                    }

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
    iambic_managed: Optional[IambicManaged] = Field(
        IambicManaged.UNDEFINED,
        description="Controls the directionality of iambic changes",
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


class AWSIdentityCenterAccount(PydanticBaseModel):
    account_id: constr(min_length=12, max_length=12) = Field(
        None, description="The AWS Account ID"
    )
    region: str


class AWSOrganization(BaseAWSAccountAndOrgModel):
    org_id: str = Field(
        None,
        description="A unique identifier designating the identity of the organization",
    )
    org_name: Optional[str] = None
    identity_center_account: Optional[AWSIdentityCenterAccount] = Field(
        default=None,
        description="The AWS Account ID and region of the AWS Identity Center instance to use for this organization",
    )
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
        if getattr(self.identity_center_account, "account_id", None) == account_id:
            identity_center_details = IdentityCenterDetails(
                region=self.identity_center_account.region
            )
        else:
            identity_center_details = None

        aws_account = AWSAccount(
            account_id=account_id,
            account_name=account_name,
            org_id=self.org_id,
            variables=account["variables"],
            identity_center_details=identity_center_details,
            iambic_managed=account_rule.iambic_managed,
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
                assume_role_arn,
                region_name,
                external_id=self.external_id,
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

    async def get_accounts(self) -> list[AWSAccount]:
        """Get all accounts in an AWS Organization

        Also extends variables for accounts that are already in the config.
        Does not overwrite variables.
        """

        session = await self.get_boto3_session()
        client = await self.get_boto3_client("organizations")
        org_accounts = await legacy_paginated_search(
            client.list_accounts,
            "Accounts",
        )

        active_accounts = [
            account for account in org_accounts if account["Status"] == "ACTIVE"
        ]
        org_accounts = await asyncio.gather(
            *[set_org_account_variables(client, account) for account in active_accounts]
        )
        discovered_accounts = [
            org_account for org_account in org_accounts if org_account
        ]

        discovered_accounts = await asyncio.gather(
            *[
                self._create_org_account_instance(account, session)
                for account in discovered_accounts
            ]
        )
        response = [account for account in discovered_accounts if account]

        if self.identity_center_account:
            for elem, account in enumerate(response):
                if account.account_id == self.identity_center_account.account_id:
                    response[elem].identity_center_details.org_account_map = {
                        account["Id"]: account["Name"] for account in active_accounts
                    }

        return response

    def __str__(self):
        return f"{self.org_name} - ({self.org_id})"


class AWSTemplate(BaseTemplate, ExpiryModel):
    identifier: str

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

    @property
    def resource_type(self):
        return self.identifier


class Description(AccessModel):
    description: Optional[str] = ""
