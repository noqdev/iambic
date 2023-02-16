from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from iambic.plugins.v0_1_0.google.group.template_generation import (
    generate_group_templates,
)

if TYPE_CHECKING:
    from iambic.plugins.v0_1_0.google.iambic_plugin import GoogleConfig


async def load(config: GoogleConfig) -> GoogleConfig:
    return config


async def import_google_resources(
    config: GoogleConfig, base_output_dir: str, messages: list = None
):
    tasks = []

    for project in config.projects:
        for subject in project.subjects:
            tasks.append(
                generate_group_templates(
                    config, subject.domain, base_output_dir, project
                )
            )

    await asyncio.gather(*tasks)
