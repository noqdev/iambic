from __future__ import annotations

import random
import uuid

from functional_tests.conftest import IAMBIC_TEST_DETAILS
from iambic.core.iambic_enum import Command
from iambic.core.models import ExecutionMessage
from iambic.core.template_generation import get_existing_template_map
from iambic.plugins.v0_1_0.aws.iam.user.models import AwsIamUserTemplate
from iambic.plugins.v0_1_0.aws.iam.user.template_generation import (
    collect_aws_users,
    generate_aws_user_templates,
    get_template_dir,
)
from iambic.plugins.v0_1_0.aws.iam.user.utils import list_users


async def generate_user_template_from_base(
    repo_dir: str,
) -> AwsIamUserTemplate:
    user_dir = get_template_dir(repo_dir)
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
    user_template = AwsIamUserTemplate.load(file_path)

    return user_template


async def get_modifiable_user(iam_client):
    account_users = await list_users(iam_client)
    return random.choice(account_users)


async def user_full_import(detect_messages: list = None):
    exe_message = ExecutionMessage(
        execution_id=str(uuid.uuid4()), command=Command.IMPORT, provider_type="aws"
    )
    iam_template_map = await get_existing_template_map(
        repo_dir=IAMBIC_TEST_DETAILS.template_dir_path,
        template_type="AWS::IAM.*",
        nested=True,
    )

    # Refresh the template
    await collect_aws_users(
        exe_message,
        IAMBIC_TEST_DETAILS.config.aws,
        iam_template_map,
        detect_messages,
    )
    await generate_aws_user_templates(
        exe_message,
        IAMBIC_TEST_DETAILS.config.aws,
        IAMBIC_TEST_DETAILS.template_dir_path,
        iam_template_map,
        detect_messages,
    )
