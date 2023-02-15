from __future__ import annotations

import random

from iambic.core.logger import log
from iambic.core.utils import gather_templates
from iambic.plugins.aws.iam.policy.models import (
    AWS_MANAGED_POLICY_TEMPLATE_TYPE,
    ManagedPolicyDocument,
    ManagedPolicyTemplate,
)
from iambic.plugins.aws.iam.policy.template_generation import get_managed_policy_dir


async def generate_managed_policy_template_from_base(
    repo_dir: str,
) -> ManagedPolicyTemplate:
    managed_policies = await gather_templates(
        repo_dir, AWS_MANAGED_POLICY_TEMPLATE_TYPE
    )
    managed_policy_dir = get_managed_policy_dir(repo_dir)
    managed_policy_template = ManagedPolicyTemplate.load(
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
