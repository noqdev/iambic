import asyncio
import os

from iambic.aws.iam.role.template_generation import (
    ROLE_RESPONSE_DIR,
    generate_aws_role_templates,
)
from iambic.config.models import Config
from iambic.google.models import generate_group_templates


async def generate_templates(configs: list[Config], output_dir):
    # TODO: Create a setting to enable support for google groups
    # TODO: Ensure google_groups are not excluded from sync
    response_dir_list = [output_dir, ROLE_RESPONSE_DIR]
    for response_dir in response_dir_list:
        os.makedirs(str(response_dir), exist_ok=True)

    tasks = [generate_aws_role_templates(configs, output_dir)]
    for config in configs:
        if config.google and config.google.groups.enabled:
            tasks.extend(
                generate_group_templates(config, "noq.dev", output_dir)
                for config in configs
            )

    await asyncio.gather(*tasks)
