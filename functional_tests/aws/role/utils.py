from __future__ import annotations

import random

from iambic.plugins.v0_1_0.aws.iam.role.models import RoleAccess, RoleTemplate
from iambic.plugins.v0_1_0.aws.iam.role.template_generation import get_role_dir
from iambic.plugins.v0_1_0.aws.iam.role.utils import list_roles
from iambic.plugins.v0_1_0.aws.models import AWSAccount


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
    role_dir = get_role_dir(repo_dir)
    identifier = f"iambic_test_{random.randint(0, 10000)}"
    file_path = f"{role_dir}/{identifier}.yaml"
    role_template = f"""
template_type: NOQ::AWS::IAM::Role
included_accounts:
  - '*'
identifier: {identifier}
properties:
  description: This was created by a functional test.
  assume_role_policy_document:
    Statement:
      - Action: sts:AssumeRole
        Effect: Deny
        Principal:
          Service: ec2.amazonaws.com
    Version: '2012-10-17'
  inline_policies:
    - policy_name: spoke-acct-policy
      statement:
        - action:
            - s3:initialpolicy
          effect: Allow
          resource: '*'
      version: '2012-10-17'
  managed_policies:
    - policy_arn: arn:aws:iam::aws:policy/job-function/ViewOnlyAccess
  path: /iambic_test/
  role_name: {identifier}
"""
    with open(file_path, "w") as f:
        f.write(role_template)
    role_template = RoleTemplate.load(file_path)

    return role_template


async def get_modifiable_role(iam_client):
    account_roles = await list_roles(iam_client)
    account_roles = [
        role
        for role in account_roles
        if "service-role" not in role["Path"] and "AWSReserved" not in role["RoleName"]
    ]
    return random.choice(account_roles)
