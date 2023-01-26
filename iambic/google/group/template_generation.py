from __future__ import annotations

import os

from iambic.core.template_generation import (
    create_or_update_template,
    get_existing_template_map,
)
from iambic.google.group.models import GOOGLE_GROUP_TEMPLATE_TYPE, GroupTemplate
from iambic.google.group.utils import list_groups


async def generate_group_templates(config, domain, output_dir, google_project):
    """List all groups in the domain, along with members and
    settings"""

    base_path = os.path.expanduser(output_dir)
    existing_template_map = await get_existing_template_map(
        base_path, GOOGLE_GROUP_TEMPLATE_TYPE
    )
    groups = await list_groups(domain, google_project)

    for group in groups:
        file_path = os.path.expanduser(group.file_path)
        group.file_path = os.path.join(base_path, file_path)

        create_or_update_template(
            group.file_path,
            existing_template_map,
            group.properties.resource_id,
            GroupTemplate,
            {},
            group.properties,
        )

    return groups
