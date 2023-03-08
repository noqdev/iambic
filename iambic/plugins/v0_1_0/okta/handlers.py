from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from iambic.core.context import ctx
from iambic.core.iambic_enum import IambicManaged
from iambic.core.logger import log
from iambic.core.models import ExecutionMessage
from iambic.plugins.v0_1_0.okta.app.template_generation import (
    collect_org_apps,
    generate_app_templates,
)
from iambic.plugins.v0_1_0.okta.group.template_generation import (
    collect_org_groups,
    generate_group_templates,
)
from iambic.plugins.v0_1_0.okta.user.template_generation import (
    collect_org_users,
    generate_user_templates,
)

if TYPE_CHECKING:
    from iambic.plugins.v0_1_0.okta.iambic_plugin import OktaConfig


async def load(config: OktaConfig) -> OktaConfig:
    return config


async def import_okta_resources(
    exe_message: ExecutionMessage,
    config: OktaConfig,
    base_output_dir: str,
    messages: list = None,
    remote_worker=None,
):
    base_runner = bool(not exe_message.provider_id)
    collector_tasks = []

    for organization in config.organizations:
        if organization.iambic_managed == IambicManaged.DISABLED:
            continue
        elif (
            exe_message.provider_id and exe_message.provider_id != organization.idp_name
        ):
            continue

        task_message = exe_message.copy()
        task_message.provider_id = organization.idp_name

        collector_tasks.extend(
            [
                collect_org_apps(task_message, config),
                collect_org_groups(task_message, config),
                collect_org_users(task_message, config),
            ]
        )

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
            generate_app_templates(exe_message, base_output_dir),
            generate_group_templates(exe_message, base_output_dir),
            generate_user_templates(exe_message, base_output_dir),
        ]
        await asyncio.gather(*generator_tasks)
