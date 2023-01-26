from __future__ import annotations

import os

from iambic.core.template_generation import (
    create_or_update_template,
    get_existing_template_map,
)
from iambic.okta.group.models import (
    OKTA_GROUP_TEMPLATE_TYPE,
    OktaGroupTemplate,
    get_group_template,
)
from iambic.okta.group.utils import list_all_groups


async def generate_group_templates(config, output_dir, okta_organization):
    """List all groups in the domain, along with members and
    settings"""

    groups = await list_all_groups(okta_organization)

    base_path = os.path.expanduser(output_dir)
    existing_template_map = await get_existing_template_map(
        base_path, OKTA_GROUP_TEMPLATE_TYPE
    )

    for okta_group in groups:
        group: OktaGroupTemplate = await get_group_template(okta_group)
        file_path = os.path.expanduser(group.file_path)
        group.file_path = os.path.join(base_path, file_path)

        create_or_update_template(
            group.file_path,
            existing_template_map,
            group.properties.resource_id,
            OktaGroupTemplate,
            {},
            group.properties,
        )

    return groups
