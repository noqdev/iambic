from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from iambic.core.models import BaseTemplate, ExecutionMessage, TemplateChangeDetails

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
    exe_message: ExecutionMessage,
    config: AzureADConfig,
    base_output_dir: str,
    messages: list = None,
    remote_worker=None,
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


async def apply(
    config: AzureADConfig, templates: list[BaseTemplate]
) -> list[TemplateChangeDetails]:
    """
    The apply callable for the AzureAD IambicPlugin class.

    :param config: The config object.
    :param templates: The list of templates to apply.
    """
    pass
    # if any(
    #     isinstance(template, AWSIdentityCenterPermissionSetTemplate)
    #     for template in templates
    # ):
    #     await generate_permission_set_map(config.accounts, templates)

    # template_changes = await asyncio.gather(
    #     *[template.apply(config, ctx) for template in templates]
    # )

    # return [
    #     template_change
    #     for template_change in template_changes
    #     if template_change.proposed_changes
    # ]
