from __future__ import annotations

import asyncio

from pydantic import BaseModel, Field

from iambic.aws.iam.group.models import GroupTemplate
from iambic.aws.iam.group.template_generation import generate_aws_group_templates
from iambic.aws.iam.role.models import RoleTemplate
from iambic.aws.iam.role.template_generation import generate_aws_role_templates
from iambic.aws.iam.user.models import UserTemplate
from iambic.aws.iam.user.template_generation import generate_aws_user_templates
from iambic.aws.identity_center.permission_set.models import (
    AWSIdentityCenterPermissionSetTemplate,
)
from iambic.aws.identity_center.permission_set.template_generation import (
    generate_aws_permission_set_templates,
)
from iambic.aws.models import AWSAccount, AWSOrganization
from iambic.config.models import Config
from iambic.core.iambic_plugin import ProviderClassDefinition, ProviderPlugin
from iambic.core.logger import log


async def load(config: Config) -> Config:
    config_account_idx_map = {
        account.account_id: idx for idx, account in enumerate(config.aws.accounts)
    }
    if config.aws.organizations:
        if any(account.hub_role_arn for account in config.aws.accounts):
            raise AttributeError(
                "You cannot specify a hub_role_arn on an AWS Account if you are using an AWS Organization"
            )

        orgs_accounts = await asyncio.gather(
            *[org.get_accounts() for org in config.aws.organizations]
        )
        for org_accounts in orgs_accounts:
            for account in org_accounts:
                if (
                    account_elem := config_account_idx_map.get(account.account_id)
                ) is not None:
                    config.aws.accounts[
                        account_elem
                    ].hub_session_info = account.hub_session_info
                    config.aws.accounts[
                        account_elem
                    ].identity_center_details = account.identity_center_details
                else:
                    log.warning(
                        "Account not found in config. Account will be ignored.",
                        account_id=account.account_id,
                        account_name=account.account_name,
                    )
    elif config.aws.accounts:
        hub_account = [
            account for account in config.aws.accounts if account.hub_role_arn
        ]
        if len(hub_account) > 1:
            raise AttributeError("Only one AWS Account can specify the hub_role_arn")
        elif not hub_account:
            raise AttributeError("One of the AWS Accounts must define the hub_role_arn")
        else:
            hub_account = hub_account[0]
            await hub_account.set_hub_session_info()
            hub_session_info = hub_account.hub_session_info
            if not hub_session_info:
                raise Exception("Unable to assume into the hub_role_arn")
            for account in config.aws.accounts:
                if account.account_id != hub_account.account_id:
                    account.hub_session_info = hub_session_info
    return config


async def import_aws_resources(
    config: Config, base_output_dir: str, messages: list = None
):
    await asyncio.gather(
        generate_aws_permission_set_templates([config], base_output_dir, messages),
        generate_aws_role_templates([config], base_output_dir, messages),
    )
    await generate_aws_user_templates([config], base_output_dir, messages)
    await generate_aws_group_templates([config], base_output_dir, messages)


class AWSConfig(BaseModel):
    min_accounts_required_for_wildcard_included_accounts: int = Field(
        3,
        description=(
            "Iambic will set included_accounts = * on imported resources "
            "that exist on all accounts if the minimum number of accounts is met."
        ),
    )

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


IAMBIC_PLUGIN = ProviderPlugin(
    config_name="aws",
    child_definition=ProviderClassDefinition(
        config_name="accounts",
        provider_class=AWSAccount,
    ),
    parent_definition=ProviderClassDefinition(
        config_name="organizations",
        provider_class=AWSOrganization,
    ),
    provider_config=AWSConfig,
    async_import_callable=import_aws_resources,
    async_load_callable=load,
    templates=[
        AWSIdentityCenterPermissionSetTemplate,
        GroupTemplate,
        RoleTemplate,
        UserTemplate,
    ],
)
