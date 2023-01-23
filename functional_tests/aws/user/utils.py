from __future__ import annotations

import random

from iambic.aws.iam.user.models import UserTemplate
from iambic.aws.iam.user.template_generation import get_user_dir
from iambic.aws.iam.user.utils import list_users


async def generate_user_template_from_base(
    repo_dir: str,
) -> UserTemplate:
    user_dir = get_user_dir(repo_dir)
    identifier = f"iambic_test_{random.randint(0, 10000)}"
    file_path = f"{user_dir}/{identifier}.yaml"
    user_template = f"""
template_type: NOQ::AWS::IAM::User
included_accounts:
  - '*'
identifier: {identifier}
properties:
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
  user_name: {identifier}
"""
    with open(file_path, "w") as f:
        f.write(user_template)
    user_template = UserTemplate.load(file_path)

    return user_template


async def get_modifiable_user(iam_client):
    account_users = await list_users(iam_client)
    return random.choice(account_users)
