from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from iambic.plugins.v0_1_0.example.iambic_plugin import ExampleConfig


async def load(config: ExampleConfig) -> ExampleConfig:
    return config


async def import_example_resources(
    config: ExampleConfig, base_output_dir: str, messages: list = None
):
    tasks = []
    await asyncio.gather(*tasks)
