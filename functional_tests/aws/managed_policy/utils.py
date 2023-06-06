from __future__ import annotations

import random
import uuid

from functional_tests.conftest import IAMBIC_TEST_DETAILS

from iambic.core.iambic_enum import Command
from iambic.core.logger import log
from iambic.core.models import ExecutionMessage
from iambic.core.template_generation import get_existing_template_map
from iambic.core.utils import gather_templates
from iambic.plugins.v0_1_0.aws.iam.policy.models import (
    AWS_MANAGED_POLICY_TEMPLATE_TYPE,
    AwsIamManagedPolicyTemplate,
    ManagedPolicyDocument,
)
from iambic.plugins.v0_1_0.aws.iam.policy.template_generation import (
    collect_aws_managed_policies,
    generate_aws_managed_policy_templates,
    get_template_dir,
)


async def generate_managed_policy_template_from_base(
    repo_dir: str,
) -> AwsIamManagedPolicyTemplate:
    managed_policies = await gather_templates(
        repo_dir, AWS_MANAGED_POLICY_TEMPLATE_TYPE
    )
    managed_policy_dir = get_template_dir(repo_dir)
    managed_policy_template = AwsIamManagedPolicyTemplate.load(
        random.choice(managed_policies)
    )
    log.info(
        "Using managed policy as base",
        managed_policy=managed_policy_template.identifier,
    )

    managed_policy_template.identifier = f"iambic_test_{random.randint(0, 10000)}"
    managed_policy_template.file_path = (
        f"{managed_policy_dir}/{managed_policy_template.identifier}.yaml"
    )
    managed_policy_template.properties.path = "/iambic_test/"
    managed_policy_template.properties.policy_name = managed_policy_template.identifier
    managed_policy_template.properties.description = (
        "This was created by a functional test."
    )
    managed_policy_template.properties.policy_document = ManagedPolicyDocument(
        version="2012-10-17",
        statement=[
            {
                "Action": "s3:ListObject",
                "Effect": "Deny",
                "Resource": ["*"],
            }
        ],
    )
    managed_policy_template.write()
    return managed_policy_template


async def managed_policy_full_import(detect_messages: list = None):
    exe_message = ExecutionMessage(
        execution_id=str(uuid.uuid4()), command=Command.IMPORT, provider_type="aws"
    )
    iam_template_map = await get_existing_template_map(
        repo_dir=IAMBIC_TEST_DETAILS.template_dir_path,
        template_type="AWS::IAM.*",
        template_map=IAMBIC_TEST_DETAILS.config.aws.template_map,
        nested=True,
    )

    await collect_aws_managed_policies(
        exe_message,
        IAMBIC_TEST_DETAILS.config.aws,
        iam_template_map,
        detect_messages,
    )
    await generate_aws_managed_policy_templates(
        exe_message,
        IAMBIC_TEST_DETAILS.config.aws,
        IAMBIC_TEST_DETAILS.template_dir_path,
        iam_template_map,
        detect_messages,
    )
