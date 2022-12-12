import asyncio
import os

from iambic.aws.cloudcontrol.template_generation import generate_cloudcontrol_templates
from iambic.aws.iam.policy.template_generation import (
    MANAGED_POLICY_RESPONSE_DIR,
    generate_aws_managed_policy_templates,
)
from iambic.aws.iam.role.template_generation import (
    ROLE_RESPONSE_DIR,
    generate_aws_role_templates,
)
from iambic.config.models import Config
from iambic.google.group.template_generation import generate_group_templates


async def generate_templates(configs: list[Config], output_dir: str):
    # TODO: Create a setting to enable support for google groups
    # TODO: Ensure google_groups are not excluded from sync
    response_dir_list = [output_dir, ROLE_RESPONSE_DIR, MANAGED_POLICY_RESPONSE_DIR]
    for response_dir in response_dir_list:
        os.makedirs(str(response_dir), exist_ok=True)

    tasks = [
        # generate_aws_role_templates(configs, output_dir),
        generate_aws_managed_policy_templates(configs, output_dir),
        generate_cloudcontrol_templates(configs, output_dir),
    ]
    for config in configs:
        for project in config.google_projects:
            for subject in project.subjects:
                tasks.append(
                    generate_group_templates(
                        config, subject.domain, output_dir, project
                    )
                )

    await asyncio.gather(*tasks)
