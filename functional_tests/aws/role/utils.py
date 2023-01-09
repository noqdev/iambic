from __future__ import annotations

import asyncio
import random

from iambic.aws.iam.role.models import (
    AWS_IAM_ROLE_TEMPLATE_TYPE,
    RoleAccess,
    RoleTemplate,
)
from iambic.aws.iam.role.template_generation import get_role_dir
from iambic.aws.iam.role.utils import get_role, list_roles
from iambic.aws.models import AWSAccount
from iambic.core.logger import log
from iambic.core.utils import gather_templates


def attach_access_rule(
    role_template: RoleTemplate,
    aws_account: AWSAccount,
    exclude_accounts: int = 0,
) -> RoleTemplate:
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

    role_template.access_rules.append(
        RoleAccess(
            users=users[: random.randint(1, len(users))],
            groups=users[: random.randint(1, len(groups))],
            excluded_accounts=excluded_accounts,
            included_accounts=included_accounts,
        )
    )

    return role_template


async def generate_role_template_from_base(
    repo_dir: str,
) -> RoleTemplate:
    roles = await gather_templates(repo_dir, AWS_IAM_ROLE_TEMPLATE_TYPE)
    role_dir = get_role_dir(repo_dir)

    while True:
        log.info("Setting a valid base role template")
        role_template = RoleTemplate.load(random.choice(roles))
        if "service-role" not in role_template.properties.path:
            break

    log.info(
        "Using permission set as base",
        permission_set=role_template.identifier,
    )

    role_template.identifier = f"iambic_test_{random.randint(0, 10000)}"
    role_template.file_path = f"{role_dir}/{role_template.identifier}.yaml"
    role_template.properties.path = "/iambic_test/"
    role_template.properties.role_name = role_template.identifier
    role_template.properties.description = "This was created by a functional test."
    role_template.properties.max_session_duration = 3600

    role_template.properties.assume_role_policy_document = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Deny",
                "Principal": {"Service": "ec2.amazonaws.com"},
                "Action": "sts:AssumeRole",
            }
        ],
    }

    if isinstance(role_template.properties.assume_role_policy_document, list):
        policy_doc = role_template.properties.assume_role_policy_document[0]
        policy_doc.included_accounts = ["*"]
        policy_doc.excluded_accounts = []
        role_template.properties.assume_role_policy_document = policy_doc

    if role_template.properties.inline_policies:
        policy_doc = role_template.properties.inline_policies[0]
        policy_doc.included_accounts = ["*"]
        policy_doc.excluded_accounts = []
        role_template.properties.inline_policies = [policy_doc]

    role_template.write()
    return role_template


async def get_role_across_accounts(
    aws_accounts: list[AWSAccount], role_name: str, include_policies: bool = True
) -> dict:
    async def get_role_for_account(aws_account: AWSAccount):
        iam_client = await aws_account.get_boto3_client("iam")
        return {
            aws_account.account_id: await get_role(
                role_name, iam_client, include_policies
            )
        }

    account_on_roles = await asyncio.gather(
        *[get_role_for_account(aws_account) for aws_account in aws_accounts]
    )
    return {
        account_id: role
        for resp in account_on_roles
        for account_id, role in resp.items()
    }


async def get_modifiable_role(iam_client):
    account_roles = await list_roles(iam_client)
    account_roles = [
        role
        for role in account_roles
        if "service-role" not in role["Path"] and "AWSReserved" not in role["RoleName"]
    ]
    return random.choice(account_roles)
