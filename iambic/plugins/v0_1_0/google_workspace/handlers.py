from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from iambic.core.context import ctx
from iambic.core.iambic_enum import IambicManaged
from iambic.core.logger import log
from iambic.core.models import ExecutionMessage
from iambic.plugins.v0_1_0.google_workspace.group.template_generation import (
    collect_project_groups,
    generate_group_templates,
)

if TYPE_CHECKING:
    from iambic.plugins.v0_1_0.google_workspace.iambic_plugin import (
        GoogleWorkspaceConfig,
    )


async def load(config: GoogleWorkspaceConfig) -> GoogleWorkspaceConfig:
    return config


async def import_google_resources(
    exe_message: ExecutionMessage,
    config: GoogleWorkspaceConfig,
    base_output_dir: str,
    messages: list = None,
    remote_worker=None,
):
    base_runner = bool(not exe_message.provider_id)
    collector_tasks = []

    for workspace in config.workspaces:
        if workspace.iambic_managed == IambicManaged.DISABLED:
            continue
        elif (
            exe_message.provider_id and exe_message.provider_id != workspace.project_id
        ):
            continue

        task_message = exe_message.copy()
        task_message.provider_id = workspace.project_id
        collector_tasks.append(collect_project_groups(task_message, config))

    if collector_tasks:
        if base_runner and ctx.use_remote and remote_worker and not messages:
            # TODO: Update to use the remote_worker
            await asyncio.gather(*collector_tasks)
            # TODO: Add a process to gather status messages from the remote worker
        else:
            if remote_worker:
                log.warning(
                    "The remote worker definition must be defined in the config to run remote execution."
                )
            await asyncio.gather(*collector_tasks)

    if base_runner:
        generator_tasks = [
            generate_group_templates(exe_message, config, base_output_dir)
        ]
        await asyncio.gather(*generator_tasks)
