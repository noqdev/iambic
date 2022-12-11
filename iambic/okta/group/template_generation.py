import json
import os

from iambic.core.utils import yaml
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
