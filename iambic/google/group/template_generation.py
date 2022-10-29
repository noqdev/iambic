import json
import os

from iambic.core.logger import log
from iambic.core.utils import yaml
from iambic.google.group.models import GroupMember, GroupTemplate
from iambic.google.models import GroupMemberRole, GroupMemberStatus, GroupMemberType


async def generate_group_templates(config, domain, output_dir):
    """List all groups in the domain, along with members and
    settings"""
    groups = []

    try:
        service = await get_service(config, "admin", "directory_v1")
        if not service:
            return []
    except AttributeError as err:
        log.exception("Unable to process google groups.", error=err)
        return

    req = service.groups().list(domain=domain)  # TODO: Async
    res = req.execute()
    if res and "groups" in res:
        for group in res["groups"]:
            member_req = service.members().list(groupKey=group["email"])
            member_res = member_req.execute() or {}
            members = [
                GroupMember(
                    email=member["email"],
                    role=GroupMemberRole(member["role"]),
                    type=GroupMemberType(member["type"]),
                    status=GroupMemberStatus(member["status"]),
                )
                for member in member_res.get("members", [])
            ]
            file_name = f"{group['email'].split('@')[0]}.yaml"
            groups.append(
                GroupTemplate(
                    file_path=f"google_groups/{domain}/{file_name}",
                    name=group["name"],
                    email=group["email"],
                    description=group["description"],
                    members=members,
                )
            )
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
