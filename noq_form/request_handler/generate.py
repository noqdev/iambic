import asyncio
import os

from noq_form.aws.iam.role.template_generation import (
    ROLE_RESPONSE_DIR,
    generate_aws_role_templates,
)
from noq_form.config.models import Config
from noq_form.google.models import generate_group_templates


async def generate_templates(configs: list[Config], output_dir):
    # TODO: Create a setting to enable support for google groups
    # TODO: Ensure google_groups are not excluded from sync
    response_dir_list = [output_dir, ROLE_RESPONSE_DIR]
    for response_dir in response_dir_list:
        os.makedirs(str(response_dir), exist_ok=True)

    tasks = [
        generate_group_templates(config, "noq.dev", output_dir) for config in configs
    ]
    tasks.append(generate_aws_role_templates(configs, output_dir))
    await asyncio.gather(*tasks)
