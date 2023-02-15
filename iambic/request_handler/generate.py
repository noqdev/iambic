from __future__ import annotations

import asyncio
from enum import Enum
from typing import TYPE_CHECKING

# TODO: This is a plugin anti-pattern. We need to make a real plugin architecture.
from iambic.google.group.template_generation import generate_group_templates
from iambic.okta.app.template_generation import generate_app_templates
from iambic.okta.group.template_generation import (
    generate_group_templates as generate_okta_group_templates,
)
from iambic.okta.user.template_generation import generate_user_templates
from iambic.plugins.v0_1_0.aws.iam.group.template_generation import (
    generate_aws_group_templates,
)
from iambic.plugins.v0_1_0.aws.iam.policy.template_generation import (
    generate_aws_managed_policy_templates,
)
from iambic.plugins.v0_1_0.aws.iam.role.template_generation import (
    generate_aws_role_templates,
)
from iambic.plugins.v0_1_0.aws.iam.user.template_generation import (
    generate_aws_user_templates,
)
from iambic.plugins.v0_1_0.aws.identity_center.permission_set.template_generation import (
    generate_aws_permission_set_templates,
)

if TYPE_CHECKING:
    from iambic.config.dynamic_config import Config


class GenerateTemplateScope(Enum):
    ALL = "all"
    OKTA_AND_GOOGLE = "okta_and_google"
    AWS = "aws"


async def generate_templates(
    config: Config,
    output_dir: str,
    scope: GenerateTemplateScope = GenerateTemplateScope.ALL,
):
    if scope == GenerateTemplateScope.OKTA_AND_GOOGLE:
        tasks = []
    else:
        tasks = [
            generate_aws_managed_policy_templates(config, output_dir),
            generate_aws_permission_set_templates(config, output_dir),
        ]

    if scope != GenerateTemplateScope.AWS:
        for project in config.google_projects:
            for subject in project.subjects:
                tasks.append(
                    generate_group_templates(
                        config, subject.domain, output_dir, project
                    )
                )

        for okta_organization in config.okta_organizations:
            tasks.append(generate_user_templates(config, output_dir, okta_organization))
            tasks.append(
                generate_okta_group_templates(config, output_dir, okta_organization)
            )
            tasks.append(generate_app_templates(config, output_dir, okta_organization))

    await asyncio.gather(*tasks)

    if scope != GenerateTemplateScope.OKTA_AND_GOOGLE:
        # Broken up to prevent AWS rate limiting.
        iam_tasks = [
            generate_aws_role_templates(config, output_dir),
            generate_aws_user_templates(config, output_dir),
            generate_aws_group_templates(config, output_dir),
        ]
        for iam_task in iam_tasks:
            await iam_task
