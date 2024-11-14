from __future__ import annotations

import random
import uuid

from functional_tests.conftest import IAMBIC_TEST_DETAILS

from iambic.core.iambic_enum import Command
from iambic.core.models import ExecutionMessage
from iambic.core.template_generation import get_existing_template_map
from iambic.plugins.v0_1_0.aws.iam.group.models import AwsIamGroupTemplate
from iambic.plugins.v0_1_0.aws.iam.group.template_generation import (
    collect_aws_groups,
    generate_aws_group_templates,
    get_template_dir,
)
from iambic.plugins.v0_1_0.aws.iam.group.utils import list_groups


async def generate_group_template_from_base(
    repo_dir: str,
) -> AwsIamGroupTemplate:
    group_dir = get_template_dir(repo_dir)
    identifier = f"iambic_test_{random.randint(0, 10000)}"
    file_path = f"{group_dir}/{identifier}.yaml"
    group_template = f"""
template_type: NOQ::AWS::IAM::Group
included_accounts:
  - '*'
identifier: {identifier}
properties:
  group_name: {identifier}
  path: /iambic_test/
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
"""
    with open(file_path, "w") as f:
        f.write(group_template)
    group_template = AwsIamGroupTemplate.load(file_path)

    return group_template


async def get_modifiable_group(iam_client):
    account_groups = await list_groups(iam_client)
    account_groups = [
        group
        for group in account_groups
        if "service-group" not in group["Path"]
        and "AWSReserved" not in group["GroupName"]
    ]
    return random.choice(account_groups)


async def group_full_import(detect_messages: list = None):
    exe_message = ExecutionMessage(
        execution_id=str(uuid.uuid4()), command=Command.IMPORT, provider_type="aws"
    )
    iam_template_map = await get_existing_template_map(
        repo_dir=IAMBIC_TEST_DETAILS.template_dir_path,
        template_type="AWS::IAM.*",
        template_map=IAMBIC_TEST_DETAILS.config.aws.template_map,
        nested=True,
    )

    await collect_aws_groups(
        exe_message,
        IAMBIC_TEST_DETAILS.config.aws,
        iam_template_map,
        detect_messages,
    )
    await generate_aws_group_templates(
        exe_message,
        IAMBIC_TEST_DETAILS.config.aws,
        IAMBIC_TEST_DETAILS.template_dir_path,
        iam_template_map,
        detect_messages,
    )
