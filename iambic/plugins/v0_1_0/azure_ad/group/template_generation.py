from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING

from iambic.core.template_generation import (
    create_or_update_template as common_create_or_update_template,
)
from iambic.core.template_generation import get_existing_template_map
from iambic.plugins.v0_1_0.azure_ad.group.models import (
    AZURE_AD_GROUP_TEMPLATE_TYPE,
    AzureADGroupTemplate,
    AzureADGroupTemplateProperties,
)
from iambic.plugins.v0_1_0.azure_ad.group.utils import list_all_groups
from iambic.plugins.v0_1_0.azure_ad.models import Group

if TYPE_CHECKING:
    from iambic.plugins.v0_1_0.azure_ad.iambic_plugin import (
        AzureADConfig,
        AzureADOrganization,
    )


def get_group_dir(base_dir: str, idp_name: str) -> str:
    return str(os.path.join(base_dir, "resources", "azure_ad", idp_name, "groups"))


def get_templated_resource_file_path(
    resource_dir: str,
    resource_name: str,
) -> str:
    unwanted_chars = ["}}_", "}}", ".", "-", " "]
    resource_name = resource_name.replace("{{", "").lower()
    for unwanted_char in unwanted_chars:
        resource_name = resource_name.replace(unwanted_char, "_")

    return str(os.path.join(resource_dir, f"{resource_name}.yaml"))


async def update_or_create_group_template(
    group: Group, existing_template_map: dict, group_dir: str
):
    """
    Update or create an AzureADGroupTemplate object from the provided Group object.

    Args:
        group (Group): The Group object to generate the template from.
        existing_template_map (dict): Existing IAMbic Azure AD group templates.
        group_dir (str): The default directory to store the template in.
    """
    properties = AzureADGroupTemplateProperties(
        group_id=group.group_id,
        idp_name=group.idp_name,
        display_name=group.display_name,
        description=group.description,
        mail_nickname=group.mail_nickname,
        security_enabled=group.security_enabled,
        members=group.members,
    )

    file_path = get_templated_resource_file_path(group_dir, group.display_name)
    AzureADGroupTemplate.update_forward_refs()

    common_create_or_update_template(
        file_path,
        existing_template_map,
        group.group_id,
        AzureADGroupTemplate,
        {},
        properties,
        [],
    )


async def generate_group_templates(
    config: AzureADConfig, output_dir: str, azure_ad_organization: AzureADOrganization
):
    groups = await list_all_groups(azure_ad_organization)
    base_path = os.path.expanduser(output_dir)
    existing_template_map = await get_existing_template_map(
        base_path, AZURE_AD_GROUP_TEMPLATE_TYPE
    )
    group_dir = get_group_dir(base_path, azure_ad_organization.idp_name)

    # Update or create templates
    for azure_ad_group in groups:
        await update_or_create_group_template(
            azure_ad_group, existing_template_map, group_dir
        )

    # Delete templates that no longer exist
    discovered_group_ids = [g.group_id for g in groups]
    for group_id, template in existing_template_map.items():
        if group_id not in discovered_group_ids:
            template.delete()
