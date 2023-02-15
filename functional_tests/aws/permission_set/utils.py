from __future__ import annotations

import random

from iambic.core.logger import log
from iambic.core.utils import gather_templates
from iambic.plugins.v0_1_0.aws.identity_center.permission_set.models import (
    AWS_IDENTITY_CENTER_PERMISSION_SET_TEMPLATE_TYPE,
    AWSIdentityCenterPermissionSetTemplate,
    PermissionSetAccess,
)
from iambic.plugins.v0_1_0.aws.identity_center.permission_set.template_generation import (
    get_permission_set_dir,
)
from iambic.plugins.v0_1_0.aws.models import AWSAccount


def attach_access_rule(
    permission_set_template: AWSIdentityCenterPermissionSetTemplate,
    aws_account: AWSAccount,
    exclude_accounts: int = 0,
) -> AWSIdentityCenterPermissionSetTemplate:
    users = [
        details["UserName"]
        for details in aws_account.identity_center_details.user_map.values()
    ]
    groups = [
        details["DisplayName"]
        for details in aws_account.identity_center_details.user_map.values()
    ]
    org_accounts = list(aws_account.identity_center_details.org_account_map.values())
    if exclude_accounts:
        exclude_accounts = min(exclude_accounts, len(org_accounts) - 1)

    excluded_accounts = [] if not exclude_accounts else org_accounts[exclude_accounts:]
    include_accounts = random.randint(0, len(org_accounts) - exclude_accounts)
    if include_accounts == len(org_accounts) - 1:
        included_accounts = ["*"]
    else:
        included_accounts = org_accounts[:include_accounts]

    permission_set_template.access_rules.append(
        PermissionSetAccess(
            users=users[: random.randint(1, len(users))],
            groups=users[: random.randint(1, len(groups))],
            excluded_accounts=excluded_accounts,
            included_accounts=included_accounts,
        )
    )

    return permission_set_template


async def generate_permission_set_template_from_base(
    repo_dir: str,
) -> AWSIdentityCenterPermissionSetTemplate:
    permission_sets = await gather_templates(
        repo_dir, AWS_IDENTITY_CENTER_PERMISSION_SET_TEMPLATE_TYPE
    )
    permission_set_dir = get_permission_set_dir(repo_dir)
    permission_set_template = AWSIdentityCenterPermissionSetTemplate.load(
        random.choice(permission_sets)
    )
    log.info(
        "Using permission set as base",
        permission_set=permission_set_template.identifier,
    )

    permission_set_template.identifier = f"iambic_test_{random.randint(0, 10000)}"
    permission_set_template.file_path = (
        f"{permission_set_dir}/{permission_set_template.identifier}.yaml"
    )

    permission_set_template.properties.name = permission_set_template.identifier
    permission_set_template.properties.description = (
        "This was created by a functional test."
    )

    permission_set_template.write()
    return permission_set_template
