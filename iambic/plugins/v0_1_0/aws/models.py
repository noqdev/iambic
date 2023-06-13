from __future__ import annotations

import asyncio
import os
from enum import Enum
from typing import TYPE_CHECKING, List, Optional, Union

import boto3
import botocore
from aws_error_utils.aws_error_utils import errors
from pydantic import BaseModel as PydanticBaseModel
from pydantic import Extra, Field, constr, validator
from ruamel.yaml import YAML, yaml_object

from iambic.core.context import ctx
from iambic.core.iambic_enum import IambicManaged
from iambic.core.logger import log
from iambic.core.models import (
    AccessModelMixin,
    AccountChangeDetails,
    BaseModel,
    BaseTemplate,
    ExpiryModel,
    ProposedChange,
    ProposedChangeType,
    ProviderChild,
    TemplateChangeDetails,
    Variable,
)
from iambic.core.utils import (
    NoqSemaphore,
    evaluate_on_provider,
    get_provider_value,
    sort_dict,
)
from iambic.plugins.v0_1_0.aws.utils import (
    RegionName,
    boto_crud_call,
    create_assume_role_session,
    get_current_role_arn,
    legacy_paginated_search,
    set_org_account_variables,
)

yaml = YAML()

if TYPE_CHECKING:
    from iambic.plugins.v0_1_0.aws.iambic_plugin import AWSConfig

ARN_RE = r"(^arn:([^:]*):([^:]*):([^:]*):(|\*|[\d]{12}|cloudfront|aws|{{var.account_id}}):(.+)$)|^\*$"

IAMBIC_HUB_ROLE_NAME = os.getenv("IAMBIC_HUB_ROLE_NAME", "IambicHubRole")
IAMBIC_SPOKE_ROLE_NAME = os.getenv("IAMBIC_SPOKE_ROLE_NAME", "IambicSpokeRole")
IAMBIC_CHANGE_DETECTION_SUFFIX = os.getenv("IAMBIC_CHANGE_DETECTION_SUFFIX", "")


def get_hub_role_arn(account_id: str, role_name=None) -> str:
    if not role_name:
        role_name = IAMBIC_HUB_ROLE_NAME
    return f"arn:aws:iam::{account_id}:role/{role_name}"


def get_spoke_role_arn(account_id: str, role_name=None) -> str:
    if not role_name:
        role_name = IAMBIC_SPOKE_ROLE_NAME
    return f"arn:aws:iam::{account_id}:role/{role_name}"


class StatementEffect(str, Enum):
    ALLOW = "Allow"
    DENY = "Deny"


@yaml_object(yaml)
class Partition(Enum):
    AWS = "aws"
    AWS_GOV = "aws-us-gov"
    AWS_CHINA = "aws-cn"

    @classmethod
    def to_yaml(cls, representer, node):
        return representer.represent_scalar("!Partition", f"{node._value_}")

    @classmethod
    def from_yaml(cls, constructor, node):
        return cls(node.value)


class AccessModel(AccessModelMixin, BaseModel):
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

    @validator(
        "included_accounts", "excluded_accounts", "included_orgs", "excluded_orgs"
    )
    def sort_list_of_str(cls, v: list[str]):
        return sorted(v)

    @property
    def included_children(self):
        return self.included_accounts

    def set_included_children(self, value):
        self.included_accounts = value

    @property
    def excluded_children(self):
        return self.excluded_accounts

    def set_excluded_children(self, value):
        self.excluded_accounts = value

    @property
    def included_parents(self):
        return self.included_orgs

    def set_included_parents(self, value):
        self.included_orgs = value

    @property
    def excluded_parents(self):
        return self.excluded_orgs

    def set_excluded_parents(self, value):
        self.excluded_orgs = value


class Tag(ExpiryModel, AccessModel):
    key: str
    value: str

    @property
    def resource_type(self):
        return "Tag"

    @property
    def resource_id(self):
        return f"{self.key}:{self.value}"


class BaseAWSAccountAndOrgModel(PydanticBaseModel):
    default_region: Optional[RegionName] = Field(
        RegionName.us_east_1,
        description="Default region to use when making AWS requests",
    )
    aws_profile: Optional[str] = Field(
        None,
        description="The AWS profile used when making calls to the account",
    )
    hub_role_arn: Optional[str] = Field(
        None,
        description="The role arn to assume into when making calls to the account",
    )
    external_id: Optional[str] = Field(
        None,
        description="The external id to use for assuming into a role when making calls to the account",
    )
    boto3_session_map: Optional[dict] = None

    class Config:
        fields = {"boto3_session_map": {"exclude": True}}
        extra = Extra.forbid

    @property
    def region_name(self):
        return (
            self.default_region
            if isinstance(self.default_region, str)
            else self.default_region.value
        )

    async def get_boto3_session(self, region_name: Optional[str] = None):
        region_name = region_name or self.region_name

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
                log.warning(err)

        sts_client = session.client("sts", region_name=region_name)
        if self.hub_role_arn and self.hub_role_arn != get_current_role_arn(sts_client):
            boto3_session = await create_assume_role_session(
                session,
                self.hub_role_arn,
                region_name,
                external_id=self.external_id,
                session_name=os.environ.get("IAMBIC_SESSION_NAME", None),
            )
            if boto3_session:
                self.boto3_session_map[region_name] = boto3_session
                return boto3_session

        self.boto3_session_map[region_name] = session
        return self.boto3_session_map[region_name]

    async def get_boto3_client(self, service: str, region_name: Optional[str] = None):
        region_name = region_name or self.region_name

        if self.boto3_session_map is None:
            self.boto3_session_map = {}

        if (
            client := self.boto3_session_map.get("client", {})
            .get(service, {})
            .get(region_name)
        ):
            return client

        client = (await self.get_boto3_session(region_name)).client(
            service,
            config=botocore.client.Config(
                max_pool_connections=50, region_name=region_name
            ),
        )
        self.boto3_session_map.setdefault("client", {}).setdefault(service, {})[
            region_name
        ] = client
        return client

    async def get_active_regions(self) -> list[str]:
        client = await self.get_boto3_client("ec2")
        res = await boto_crud_call(client.describe_regions)
        return [region["RegionName"] for region in res["Regions"]]


class IdentityCenterDetails(PydanticBaseModel):
    region: RegionName = Field(RegionName.us_east_1)
    instance_arn: Optional[str] = None
    identity_store_id: Optional[str] = None
    permission_set_map: Optional[Union[dict, None]] = None
    user_map: Optional[Union[dict, None]] = None
    group_map: Optional[Union[dict, None]] = None
    org_account_map: Optional[Union[dict, None]] = None

    @property
    def region_name(self):
        return self.region if isinstance(self.region, str) else self.region.value

    def get_resource_name(self, resource_type: str, resource_id: str):
        resource_type = resource_type.lower()
        name_map = {"user": "UserName", "group": "DisplayName"}
        resource_map = getattr(self, f"{resource_type.lower()}_map")
        return resource_map.get(resource_id)[name_map[resource_type]]


class AWSAccount(ProviderChild, BaseAWSAccountAndOrgModel):
    account_id: constr(min_length=12, max_length=12) = Field(
        None, description="The AWS Account ID"
    )
    org_id: Optional[str] = Field(
        None,
        description="A unique identifier designating the identity of the organization",
    )
    account_name: str
    partition: Optional[Partition] = Field(
        Partition.AWS,
        description="The AWS partition the account is in. Options are aws, aws-us-gov, and aws-cn",
    )
    variables: list[Variable] = Field(
        [],
        description="A list of variables to be used when creating templates",
    )
    hub_session_info: Optional[dict] = None
    identity_center_details: Optional[Union[IdentityCenterDetails, None]] = None
    spoke_role_arn: str = Field(
        None,
        description="(Auto-populated) The role arn to assume into when making calls to the account",
    )
    assume_role_arn: Optional[str] = Field(
        None,
        description="The role arn to assume into when making calls to the account",
        exclude=True,
    )
    organization: Optional[AWSOrganization] = Field(
        None, description="The AWS Organization this account belongs to"
    )
    aws_config: Optional[AWSConfig] = Field(
        None,
        description="when an account is an organization account, it needs the AWS Config settings",
    )

    class Config:
        fields = {"hub_session_info": {"exclude": True}}
        extra = Extra.forbid

    async def get_boto3_session(self, region_name: str = None):
        region_name = region_name or self.region_name

        if self.boto3_session_map is None:
            self.boto3_session_map = {}
        elif boto3_session := self.boto3_session_map.get(region_name):
            return boto3_session

        if not self.hub_session_info:
            await self.set_hub_session_info()

        boto3_session = await create_assume_role_session(
            self.hub_session_info["boto3_session"],
            self.spoke_role_arn,
            region_name,
            external_id=self.external_id,
        )
        if boto3_session:
            self.boto3_session_map[region_name] = boto3_session
            return boto3_session

        return await super().get_boto3_session(region_name)

    async def set_hub_session_info(self):
        region_name = self.region_name
        session = boto3.Session(region_name=region_name)
        if self.aws_profile:
            try:
                session = boto3.Session(
                    profile_name=self.aws_profile, region_name=region_name
                )
            except Exception as err:
                log.warning(err)

        self.hub_session_info = dict(boto3_session=session)
        if self.hub_role_arn and self.hub_role_arn != get_current_role_arn(
            session.client("sts")
        ):
            session = await create_assume_role_session(
                session,
                self.hub_role_arn,
                region_name,
                external_id=self.external_id,
                session_name=os.environ.get("IAMBIC_SESSION_NAME", None),
            )
            if session:
                self.hub_session_info = dict(boto3_session=session)
                return session

        return session

    async def set_identity_center_details(
        self, set_identity_center_map: bool = True, batch_size: int = 35
    ) -> None:
        if self.identity_center_details:
            region = self.identity_center_details.region_name
            identity_center_client = await self.get_boto3_client(
                "sso-admin", region_name=region
            )
            identity_store_client = await self.get_boto3_client(
                "identitystore", region_name=region
            )
            try:
                identity_center_instances = await boto_crud_call(
                    identity_center_client.list_instances
                )
            except errors.AccessDeniedException as err:
                raise Exception(
                    "Please ensure you've specified the correct AWS Identity Center region in "
                    "IAMbic's configuration and that the spoke role has the correct permissions. ",
                    f"Original Exception: {err}",
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

            self.identity_center_details.permission_set_map = {}
            self.identity_center_details.user_map = {}
            self.identity_center_details.group_map = {}

            permission_set_arns = await legacy_paginated_search(
                identity_center_client.list_permission_sets,
                response_key="PermissionSets",
                InstanceArn=self.identity_center_details.instance_arn,
            )
            if permission_set_arns:
                # WARNING
                # current implementation does not do well if there is permission set
                # destruction interleave between earlier paginated_search and the sub-
                # sequent describe-permission-set
                permission_set_detail_semaphore = NoqSemaphore(
                    boto_crud_call, batch_size
                )
                permission_set_details = await permission_set_detail_semaphore.process(
                    [
                        {
                            "boto_fnc": identity_center_client.describe_permission_set,
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

    async def set_account_organization_details(
        self,
        organization: AWSOrganization,
        config: AWSConfig,
    ):
        """Set the account's organization details
        when the account is the organization account
        """
        self.organization = organization
        self.aws_config = config

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
        required_exclude = {
            "boto3_session_map",
            "hub_session_info",
            "identity_center_details",
            "organization_account",
            "organization",
            "aws_config",
        }
        if exclude:
            exclude.update(required_exclude)
        else:
            exclude = required_exclude

        resp = super(AWSAccount, self).dict(
            include=include,
            exclude=exclude,
            by_alias=by_alias,
            skip_defaults=skip_defaults,
            exclude_unset=exclude_unset,
            exclude_defaults=exclude_defaults,
            exclude_none=exclude_none,
        )

        if "variables" in resp:
            resp["variables"] = [
                i
                for i in resp.get("variables", [])
                if i.get("key") not in ["account_id", "account_name"]
            ]

            if resp["variables"] == []:
                resp.pop("variables")

        return sort_dict(
            resp,
            [
                "account_id",
                "account_name",
                "org_id",
                "identity_center",
                "default_rule",
            ],
        )

    @property
    def parent_id(self) -> Optional[str]:
        return self.org_id

    @property
    def preferred_identifier(self) -> str:
        return self.account_name

    @property
    def all_identifiers(self) -> set[str]:
        if self.account_name:
            return {self.account_id, self.account_name.lower()}
        else:
            return set(self.account_id)

    @property
    def organization_account(self) -> bool:
        """if current account is an organization account"""
        return bool(self.organization and self.aws_config)

    def __str__(self):
        return f"{self.account_name} - ({self.account_id})"


class BaseAWSOrgRule(BaseModel):
    iambic_managed: IambicManaged = Field(
        IambicManaged.UNDEFINED,
        description="Controls the directionality of iambic changes",
    )


class AWSOrgAccountRule(AccessModelMixin, BaseAWSOrgRule):
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

    @property
    def included_children(self):
        return self.included_accounts

    @property
    def excluded_children(self):
        return self.excluded_accounts

    @property
    def included_parents(self):
        return []

    @property
    def excluded_parents(self):
        return []


class AWSIdentityCenter(PydanticBaseModel):
    region: Optional[RegionName] = Field(
        RegionName.us_east_1,
        description="Region identity center is configured on",
    )

    @property
    def region_name(self):
        return self.region if isinstance(self.region, str) else self.region.value


class AWSOrganization(BaseAWSAccountAndOrgModel):
    org_name: Optional[str] = Field(
        None,
        description="Optional friendly name for the organization",
        exclude=True,
    )
    org_id: str = Field(
        None,
        description="A unique identifier designating the identity of the organization",
    )
    org_account_id: constr(min_length=12, max_length=12) = Field(
        description="The AWS Organization's master account ID"
    )
    identity_center: Optional[AWSIdentityCenter] = Field(
        default=None,
        description="The AWS Account ID and region of the AWS Identity Center instance to use for this organization",
    )
    default_rule: BaseAWSOrgRule = Field(
        BaseAWSOrgRule(iambic_managed=IambicManaged.UNDEFINED),
        description="The rule used to determine how an organization account should be handled if the account was not found in account_rules.",
    )
    account_rules: Optional[List[AWSOrgAccountRule]] = Field(
        [],
        description="A list of rules used to determine how organization accounts are handled",
    )
    hub_role_arn: str = Field(
        description="The role arn to assume into when making calls to the account",
    )
    spoke_role_is_read_only: bool = Field(
        False,
        description="if true, the spoke role will be limited to read-only permissions",
    )
    preferred_spoke_role_name: Optional[str] = Field(
        IAMBIC_SPOKE_ROLE_NAME,
        description="SpokeRoleName use across organization",
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
            new_rule := get_provider_value(
                self.account_rules, {account_id, account_name}
            )
        ):
            account_rule = new_rule

        region_name = self.region_name
        if self.identity_center and self.org_account_id == account_id:
            identity_center_details = IdentityCenterDetails(
                region=self.identity_center.region
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
            spoke_role_arn=get_spoke_role_arn(
                account_id, role_name=self.preferred_spoke_role_name
            ),
            hub_session_info=dict(boto3_session=session),
            default_region=region_name,
            boto3_session_map={},
        )
        try:
            await aws_account.get_boto3_session()
            return aws_account
        except Exception as err:
            log.debug(
                "Failed to assume role",
                assume_role_arn=aws_account.spoke_role_arn,
                error=err,
            )

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

        if self.identity_center:
            for elem, account in enumerate(response):
                if account.account_id == self.org_account_id:
                    response[elem].identity_center_details.org_account_map = {
                        account["Id"]: account["Name"] for account in active_accounts
                    }

        return response

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
            exclude.add("boto3_session_map")
        else:
            exclude = {"boto3_session_map"}

        resp = super(AWSOrganization, self).dict(
            include=include,
            exclude=exclude,
            by_alias=by_alias,
            skip_defaults=skip_defaults,
            exclude_unset=exclude_unset,
            exclude_defaults=exclude_defaults,
            exclude_none=exclude_none,
        )
        return sort_dict(resp, ["org_id"])

    def __str__(self):
        return self.org_id


class AWSTemplate(BaseTemplate, ExpiryModel):
    identifier: str

    async def _apply_to_account(self, aws_account: AWSAccount) -> AccountChangeDetails:
        raise NotImplementedError

    async def apply(self, config: AWSConfig) -> TemplateChangeDetails:
        tasks = []
        template_changes = TemplateChangeDetails(
            resource_id=self.resource_id,
            resource_type=self.resource_type,
            template_path=self.file_path,
        )
        log_params = dict(
            resource_type=self.resource_type, resource_id=self.resource_id
        )
        relevant_accounts = []

        for account in config.accounts:
            if evaluate_on_provider(self, account):
                relevant_accounts.append(account)
                tasks.append(self._apply_to_account(account))

        if not relevant_accounts:
            if ctx.execute:
                if self.deleted:
                    log_str = "Successfully removed resource."
                    self.delete()
                else:
                    log_str = "No changes detected for resource."
                log.info(log_str, **log_params)

            return template_changes

        if ctx.execute:
            log_str = "Applying changes to resource."
        else:
            log_str = "Detecting changes for resource."

        relevant_accounts_str = [str(account) for account in relevant_accounts]
        log.info(log_str, accounts=relevant_accounts_str, **log_params)

        account_changes: list[AccountChangeDetails] = await asyncio.gather(
            *tasks, return_exceptions=True
        )
        proposed_changes: list[AccountChangeDetails] = []
        exceptions_seen = list()

        for account_change in account_changes:
            if isinstance(account_change, AccountChangeDetails):
                proposed_changes.append(account_change)
            else:
                exceptions_seen.append(
                    ProposedChange(
                        change_type=ProposedChangeType.UNKNOWN,
                        exceptions_seen=[str(account_change)],
                    )  # type: ignore
                )

        if exceptions_seen:
            exceptions_seen = list(exceptions_seen)
            proposed_change_accounts = set(
                change.account for change in proposed_changes
            )
            for aws_account in relevant_accounts:
                if str(aws_account) in proposed_change_accounts:
                    continue
                proposed_changes.append(
                    AccountChangeDetails(
                        account=str(aws_account),
                        resource_id=self.resource_id,
                        resource_type=self.resource_type,
                        exceptions_seen=exceptions_seen,
                    )  # type: ignore
                )

        template_changes.extend_changes(proposed_changes)

        if template_changes.exceptions_seen:
            if self.deleted:
                cmd_verb = "removing"
            elif ctx.execute:
                cmd_verb = "applying"
            else:
                cmd_verb = "detecting"
            log_str = f"Error encountered when {cmd_verb} resource changes."
            log.error(log_str, accounts=relevant_accounts_str, **log_params)
        else:
            if account_changes and ctx.execute:
                if self.deleted:
                    self.delete()
                    log_str = "Successfully removed resource."
                else:
                    log_str = "Successfully applied resource changes."
            elif account_changes:
                log_str = "Successfully detected required resource changes."
            else:
                log_str = "No changes detected for resource."

            log.info(log_str, accounts=relevant_accounts_str, **log_params)
        return template_changes

    @property
    def resource_id(self):
        return self.properties.resource_id

    @property
    def resource_type(self):
        return self.properties.resource_type


class Description(AccessModel):
    description: str = ""

    @property
    def resource_type(self) -> str:
        return "aws::description"

    @property
    def resource_id(self) -> str:
        return self.description

    @classmethod
    def new_instance_from_string(cls, s: str) -> Description:
        return Description(description=s)
