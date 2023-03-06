from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from iambic.plugins.v0_1_0.aws_lambda_remote_execution_engine.iambic_plugin import (
        AWSLambdaRemoteExecutionEngineConfig,
    )


async def load(
    config: AWSLambdaRemoteExecutionEngineConfig,
) -> AWSLambdaRemoteExecutionEngineConfig:

    return config


async def import_lambda_resources(
    config: AWSLambdaRemoteExecutionEngineConfig,
    base_output_dir: str,
    messages: list = None,
):
    tasks = []
    await asyncio.gather(*tasks)
