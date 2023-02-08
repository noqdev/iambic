from __future__ import annotations

import os

from iambic.core.template_generation import (
    create_or_update_template as common_create_or_update_template,
)
from iambic.core.template_generation import get_existing_template_map
from iambic.google.group.models import GOOGLE_GROUP_TEMPLATE_TYPE, GroupTemplate
from iambic.google.group.utils import list_groups


def get_group_dir(base_dir: str) -> str:
    return str(os.path.join(base_dir, "resources", "google", "groups"))


def get_templated_resource_file_path(
    resource_dir: str,
    resource_domain: str,
    resource_email: str,
) -> str:
    unwanted_chars = ["}}_", "}}", ".", "-", " "]
    resource_domain.replace("{{", "").lower()
    resource_name = resource_email.split("@")[0].replace("{{", "").lower()
    for unwanted_char in unwanted_chars:
        resource_domain = resource_domain.replace(unwanted_char, "_")
        resource_name = resource_name.replace(unwanted_char, "_")
    return str(os.path.join(resource_dir, resource_domain, f"{resource_name}.yaml"))


async def update_or_create_group_template(
    discovered_group_template: GroupTemplate,
    existing_template_map: dict,
    group_dir: str,
):

    discovered_group_template.file_path = get_templated_resource_file_path(
        group_dir,
        discovered_group_template.properties.domain,
        discovered_group_template.properties.email,
    )

    common_create_or_update_template(
        discovered_group_template.file_path,
        existing_template_map,
        discovered_group_template.resource_id,
        GroupTemplate,
        {},
        discovered_group_template.properties,
        []
    )


async def generate_group_templates(config, domain, output_dir, google_project):
    """List all groups in the domain, along with members and
    settings"""

    base_path = os.path.expanduser(output_dir)
    groups = await list_groups(domain, google_project)
    existing_template_map = await get_existing_template_map(
        base_path, GOOGLE_GROUP_TEMPLATE_TYPE
    )
    group_dir = get_group_dir(base_path)

    # Update or create templates
    for group in groups:
        await update_or_create_group_template(group, existing_template_map, group_dir)

    # Delete templates that no longer exist
    discovered_groups = [g.resource_id for g in groups]
    for group_id, template in existing_template_map.items():
        if group_id not in discovered_groups:
            template.delete()
