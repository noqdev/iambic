from __future__ import annotations

import json
import os

from iambic.core.template_generation import (
    create_or_update_template as common_create_or_update_template,
)
from iambic.core.template_generation import get_existing_template_map
from iambic.okta.group.models import (
    OKTA_GROUP_TEMPLATE_TYPE,
    OktaGroupTemplate,
    OktaGroupTemplateProperties,
    UserSimple,
)
from iambic.okta.group.utils import list_all_groups
from iambic.okta.models import Group


def get_group_dir(base_dir: str, idp_name: str) -> str:
    return str(os.path.join(base_dir, "resources", "okta", idp_name, "groups"))


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
    Update or create an OktaGroupTemplate object from the provided Group object.

    Args:
        group (Group): The Group object to generate the template from.
        existing_template_map (dict): Existing IAMbic Okta group templates.
        group_dir (str): The default directory to store the template in.
    """
    properties = OktaGroupTemplateProperties(
        group_id=group.group_id,
        idp_name=group.idp_name,
        name=group.name,
        description=group.description,
        members=[json.loads(m.json()) for m in group.members],
    )

    file_path = get_templated_resource_file_path(group_dir, group.name)
    UserSimple.update_forward_refs()
    OktaGroupTemplate.update_forward_refs()

    common_create_or_update_template(
        file_path,
        existing_template_map,
        group.group_id,
        OktaGroupTemplate,
        {},
        properties,
    )


async def generate_group_templates(config, output_dir, okta_organization):
    groups = await list_all_groups(okta_organization)
    base_path = os.path.expanduser(output_dir)
    existing_template_map = await get_existing_template_map(
        base_path, OKTA_GROUP_TEMPLATE_TYPE
    )
    group_dir = get_group_dir(base_path, okta_organization.idp_name)

    # Update or create templates
    for okta_group in groups:
        await update_or_create_group_template(
            okta_group, existing_template_map, group_dir
        )

    # Delete templates that no longer exist
    discovered_group_ids = [g.group_id for g in groups]
    for group_id, template in existing_template_map.items():
        if group_id not in discovered_group_ids:
            template.delete()
