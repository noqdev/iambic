from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

# from iambic.plugins.v0_1_0.azure_ad.app.template_generation import generate_app_templates
from iambic.plugins.v0_1_0.azure_ad.group.template_generation import (
    generate_group_templates,
)

# from iambic.plugins.v0_1_0.azure_ad.user.template_generation import generate_user_templates

if TYPE_CHECKING:
    from iambic.plugins.v0_1_0.azure_ad.iambic_plugin import AzureADConfig


async def load(config: AzureADConfig) -> AzureADConfig:
    return config


async def import_azure_ad_resources(
    config: AzureADConfig, base_output_dir: str, messages: list = None
):
    tasks = []

    for organization in config.organizations:
        tasks.extend(
            [
                # generate_app_templates(config, base_output_dir, organization),
                generate_group_templates(config, base_output_dir, organization),
                # generate_user_templates(config, base_output_dir, organization),
            ]
        )

    await asyncio.gather(*tasks)
