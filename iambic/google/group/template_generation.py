import os

from iambic.google.group.utils import list_groups


async def generate_group_templates(config, domain, output_dir, google_project):
    """List all groups in the domain, along with members and
    settings"""

    groups = await list_groups(domain, google_project)

    base_path = os.path.expanduser(output_dir)
    for group in groups:
        file_path = os.path.expanduser(group.file_path)
        group.file_path = os.path.join(base_path, file_path)
        group.write()
    return groups
