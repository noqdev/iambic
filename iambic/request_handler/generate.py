import asyncio
import os

from iambic.aws.iam.policy.template_generation import (
    MANAGED_POLICY_RESPONSE_DIR,
    generate_aws_managed_policy_templates,
)
from iambic.aws.iam.role.template_generation import (
    ROLE_RESPONSE_DIR,
    generate_aws_role_templates,
)
from iambic.config.models import Config

# TODO: This is a plugin anti-pattern. We need to make a real plugin architecture.
from iambic.google.group.template_generation import generate_group_templates
from iambic.okta.group.template_generation import (
    generate_group_templates as generate_okta_group_templates,
)


async def generate_templates(configs: list[Config], output_dir: str):
    # TODO: Create a setting to enable support for google groups
    # TODO: Ensure google_groups are not excluded from sync
    response_dir_list = [output_dir, ROLE_RESPONSE_DIR, MANAGED_POLICY_RESPONSE_DIR]
    for response_dir in response_dir_list:
        os.makedirs(str(response_dir), exist_ok=True)
    tasks = [
        generate_aws_role_templates(configs, output_dir),
        generate_aws_managed_policy_templates(configs, output_dir),
    ]
    for config in configs:
        for project in config.google_projects:
            for subject in project.subjects:
                tasks.append(
                    generate_group_templates(
                        config, subject.domain, output_dir, project
                    )
                )
        for okta_organization in config.okta_organizations:
            tasks.append(
                generate_okta_group_templates(config, output_dir, okta_organization)
            )

    await asyncio.gather(*tasks)
