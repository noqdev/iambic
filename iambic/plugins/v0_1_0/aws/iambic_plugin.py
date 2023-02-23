from __future__ import annotations

import asyncio
from typing import Optional

from pydantic import BaseModel, Field, validator

from iambic.core.iambic_plugin import ProviderPlugin
from iambic.plugins.v0_1_0 import PLUGIN_VERSION
from iambic.plugins.v0_1_0.aws.handlers import (
    apply,
    aws_account_update_and_discovery,
    decode_aws_secret,
    detect_changes,
    import_aws_resources,
    load,
)
from iambic.plugins.v0_1_0.aws.iam.group.models import GroupTemplate
from iambic.plugins.v0_1_0.aws.iam.policy.models import ManagedPolicyTemplate
from iambic.plugins.v0_1_0.aws.iam.role.models import RoleTemplate
from iambic.plugins.v0_1_0.aws.iam.user.models import UserTemplate
from iambic.plugins.v0_1_0.aws.identity_center.permission_set.models import (
    AWSIdentityCenterPermissionSetTemplate,
)
from iambic.plugins.v0_1_0.aws.models import AWSAccount, AWSOrganization


class AWSConfig(BaseModel):
    organizations: list[AWSOrganization] = Field(
        [], description="A list of AWS Organizations to be managed by iambic"
    )
    accounts: list[AWSAccount] = Field(
        [], description="A list of AWS Accounts to be managed by iambic"
    )
    min_accounts_required_for_wildcard_included_accounts: int = Field(
        3,
        description=(
            "Iambic will set included_accounts = * on imported resources "
            "that exist on all accounts if the minimum number of accounts is met."
        ),
    )
    sqs_cloudtrail_changes_queues: Optional[list[str]] = []

    @validator("organizations", allow_reuse=True)
    def validate_organizations(cls, organizations):
        if len(organizations) > 1:
            raise ValueError("Only one AWS Organization is supported at this time.")
        return organizations

    @property
    def hub_role_arn(self):
        if self.organizations:
            return self.organizations[0].hub_role_arn
        else:
            return [
                account.hub_role_arn
                for account in self.accounts
                if account.hub_role_arn
            ][0]

    async def set_identity_center_details(self):
        if self.accounts:
            await asyncio.gather(
                *[account.set_identity_center_details() for account in self.accounts]
            )

    async def get_boto_session_from_arn(self, arn: str, region_name: str = None):
        region_name = region_name or arn.split(":")[3]
        account_id = arn.split(":")[4]
        aws_account_map = {account.account_id: account for account in self.accounts}
        aws_account = aws_account_map[account_id]
        return await aws_account.get_boto3_session(region_name)


IAMBIC_PLUGIN = ProviderPlugin(
    config_name="aws",
    version=PLUGIN_VERSION,
    provider_config=AWSConfig,
    async_apply_callable=apply,
    async_import_callable=import_aws_resources,
    async_load_callable=load,
    async_decode_secret_callable=decode_aws_secret,
    async_detect_changes_callable=detect_changes,
    async_discover_upstream_config_changes_callable=aws_account_update_and_discovery,
    templates=[
        AWSIdentityCenterPermissionSetTemplate,
        GroupTemplate,
        RoleTemplate,
        UserTemplate,
        ManagedPolicyTemplate,
    ],
)
