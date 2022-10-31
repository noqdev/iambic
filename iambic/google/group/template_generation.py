import json
import os

from iambic.core.utils import yaml
from iambic.google.group.utils import list_groups


async def generate_group_templates(config, domain, output_dir, google_project):
    """List all groups in the domain, along with members and
    settings"""

    groups = await list_groups(domain, google_project)

    base_path = os.path.expanduser(output_dir)
    for group in groups:
        file_path = os.path.expanduser(group.file_path)
        path = os.path.join(base_path, file_path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(
                yaml.dump(
                    {
                        "template_type": group.template_type,
                        **json.loads(
                            group.json(
                                exclude_unset=True,
                                exclude_defaults=True,
                                exclude={"file_path"},
                            )
                        ),
                    }
                )
            )
    return groups
