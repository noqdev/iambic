from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from iambic.plugins.v0_1_0.okta.app.template_generation import generate_app_templates
from iambic.plugins.v0_1_0.okta.group.template_generation import (
    generate_group_templates,
)
from iambic.plugins.v0_1_0.okta.user.template_generation import generate_user_templates

if TYPE_CHECKING:
    from iambic.plugins.v0_1_0.okta.iambic_plugin import OktaConfig


async def load(config: OktaConfig, sparse: bool = False) -> OktaConfig:
    return config


async def import_okta_resources(
    config: OktaConfig, base_output_dir: str, messages: list = None
):
    tasks = []

    for organization in config.organizations:
        tasks.extend(
            [
                generate_app_templates(config, base_output_dir, organization),
                generate_group_templates(config, base_output_dir, organization),
                generate_user_templates(config, base_output_dir, organization),
            ]
        )

    await asyncio.gather(*tasks)
