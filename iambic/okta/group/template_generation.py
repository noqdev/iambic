import os

from iambic.okta.group.models import get_group_template
from iambic.okta.group.utils import list_all_groups


async def generate_group_templates(config, output_dir, okta_organization):
    """List all groups in the domain, along with members and
    settings"""

    groups = await list_all_groups(okta_organization)

    base_path = os.path.expanduser(output_dir)
    for okta_group in groups:
        group = await get_group_template(okta_group)
        file_path = os.path.expanduser(group.file_path)
        group.file_path = os.path.join(base_path, file_path)
        group.write()
    return groups
