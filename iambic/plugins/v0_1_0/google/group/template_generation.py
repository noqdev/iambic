from __future__ import annotations

import os
from typing import TYPE_CHECKING

from iambic.core.template_generation import (
    create_or_update_template as common_create_or_update_template,
)
from iambic.core.template_generation import (
    delete_orphaned_templates,
    get_existing_template_map,
)
from iambic.plugins.v0_1_0.google.group.models import (
    GOOGLE_GROUP_TEMPLATE_TYPE,
    GroupTemplate,
)
from iambic.plugins.v0_1_0.google.group.utils import list_groups

if TYPE_CHECKING:
    from iambic.plugins.v0_1_0.google.iambic_plugin import GoogleConfig, GoogleProject


def get_group_dir(
    base_dir: str,
    idp_name: str,
) -> str:
    return str(os.path.join(base_dir, "resources", "google", idp_name, "groups"))


def get_templated_resource_file_path(
    resource_dir: str,
    resource_email: str,
) -> str:
    unwanted_chars = ["}}_", "}}", ".", "-", " "]
    resource_name = resource_email.split("@")[0].replace("{{", "").lower()
    for unwanted_char in unwanted_chars:
        resource_name = resource_name.replace(unwanted_char, "_")
    return str(os.path.join(resource_dir, f"{resource_name}.yaml"))


async def update_or_create_group_template(
    discovered_group_template: GroupTemplate,
    existing_template_map: dict,
    group_dir: str,
) -> GroupTemplate:

    discovered_group_template.file_path = get_templated_resource_file_path(
        group_dir,
        discovered_group_template.properties.email,
    )

    return common_create_or_update_template(
        discovered_group_template.file_path,
        existing_template_map,
        discovered_group_template.resource_id,
        GroupTemplate,
        {},
        discovered_group_template.properties,
        [],
    )


async def generate_group_templates(
    config: GoogleConfig, domain, output_dir: str, google_project: GoogleProject
):
    """List all groups in the domain, along with members and
    settings"""

    base_path = os.path.expanduser(output_dir)
    groups = await list_groups(domain, google_project)
    existing_template_map = await get_existing_template_map(
        base_path, GOOGLE_GROUP_TEMPLATE_TYPE
    )
    group_dir = get_group_dir(base_path, domain)

    # Update or create templates
    all_resource_ids = set()
    for group in groups:
        resource_template = await update_or_create_group_template(
            group, existing_template_map, group_dir
        )
        all_resource_ids.add(resource_template.resource_id)

    # Delete templates that no longer exist
    delete_orphaned_templates(list(existing_template_map.values()), all_resource_ids)
