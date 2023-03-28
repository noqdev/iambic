from __future__ import annotations

import os
from typing import TYPE_CHECKING

from iambic.core.logger import log
from iambic.core.models import ExecutionMessage
from iambic.core.template_generation import (
    create_or_update_template,
    delete_orphaned_templates,
    get_existing_template_map,
)
from iambic.plugins.v0_1_0.azure_ad.group.models import (
    AZURE_AD_GROUP_TEMPLATE_TYPE,
    AzureActiveDirectoryGroupTemplate,
)
from iambic.plugins.v0_1_0.azure_ad.group.utils import list_groups

if TYPE_CHECKING:
    from iambic.plugins.v0_1_0.azure_ad.iambic_plugin import AzureADConfig


def get_resource_dir_args() -> list:
    return ["group"]


def get_response_dir(exe_message: ExecutionMessage) -> str:
    return exe_message.get_directory(*get_resource_dir_args(), "templates")


async def update_or_create_group_template(
    discovered_template: AzureActiveDirectoryGroupTemplate, existing_template_map: dict
) -> AzureActiveDirectoryGroupTemplate:
    """
    Update or create an AzureActiveDirectoryGroupTemplate object from the provided Group object.

    Args:
        discovered_template (Group): The Group template generated from the Azure AD cloud response.
        existing_template_map (dict): Existing IAMbic Azure AD group templates.
    """

    return create_or_update_template(
        discovered_template.file_path,
        existing_template_map,
        discovered_template.resource_id,
        AzureActiveDirectoryGroupTemplate,
        {"idp_name": discovered_template.idp_name},
        discovered_template.properties,
        [],
    )


async def collect_org_groups(exe_message: ExecutionMessage, config: AzureADConfig):
    assert exe_message.provider_id
    base_path = get_response_dir(exe_message)
    azure_organization = config.get_organization(exe_message.provider_id)
    log.info(
        "Beginning to retrieve Azure AD groups.", organization=exe_message.provider_id
    )

    groups = await list_groups(azure_organization)
    for group in groups:
        azure_group = AzureActiveDirectoryGroupTemplate(
            file_path="unset",
            idp_name=azure_organization.idp_name,
            properties=group,
        )
        azure_group.file_path = os.path.join(base_path, f"{group.name}.yaml")
        azure_group.write()

    log.info(
        "Finished retrieving Azure AD groups.",
        azure_org=exe_message.provider_id,
        group_count=len(groups),
    )


async def generate_group_templates(
    exe_message: ExecutionMessage, output_dir: str, detect_messages: list = None
):
    """Create the templates for all collected groups in the domain"""
    base_path = os.path.expanduser(output_dir)
    existing_template_map = await get_existing_template_map(
        base_path, AZURE_AD_GROUP_TEMPLATE_TYPE
    )
    all_resource_ids = set()

    log.info("Updating and creating Azure AD group templates.")

    groups = await exe_message.get_sub_exe_files(
        *get_resource_dir_args(), "templates", file_name_and_extension="**.yaml"
    )
    # Update or create templates
    for group in groups:
        group = AzureActiveDirectoryGroupTemplate(file_path="unset", **group)
        group.set_default_file_path(output_dir, group.properties.name)
        resource_template = await update_or_create_group_template(
            group, existing_template_map
        )
        if not resource_template:
            # Template not updated. Most likely because it's an `enforced` template.
            continue
        all_resource_ids.add(resource_template.resource_id)

    # Delete templates that no longer exist
    delete_orphaned_templates(list(existing_template_map.values()), all_resource_ids)

    log.info("Finished updating and creating Azure AD group templates.")
