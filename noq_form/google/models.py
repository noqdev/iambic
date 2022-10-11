import json
import os
from datetime import datetime
from enum import Enum
from typing import List, Optional

import googleapiclient.discovery
from google.oauth2 import service_account
from pydantic import Field

from noq_form.config.models import Config
from noq_form.core.models import BaseModel, ExpiryModel
from noq_form.core.utils import aio_wrapper, yaml


class WhoCanInvite(Enum):
    ALL_MANAGERS_CAN_INVITE = "ALL_MANAGERS_CAN_INVITE"
    ALL_MEMBERS_CAN_INVITE = "ALL_MEMBERS_CAN_INVITE"


class WhoCanJoin(Enum):
    ALL_IN_DOMAIN_CAN_JOIN = "ALL_IN_DOMAIN_CAN_JOIN"
    ANYONE_CAN_JOIN = "ANYONE_CAN_JOIN"
    CAN_REQUEST_TO_JOIN = "CAN_REQUEST_TO_JOIN"


class WhoCanPostMessage(Enum):
    ALL_IN_DOMAIN_CAN_POST = "ALL_IN_DOMAIN_CAN_POST"
    ALL_MANAGERS_CAN_POST = "ALL_MANAGERS_CAN_POST"
    ALL_MEMBERS_CAN_POST = "ALL_MEMBERS_CAN_POST"
    ANYONE_CAN_POST = "ANYONE_CAN_POST"
    NONE_CAN_POST = "NONE_CAN_POST"


class WhoCanViewGroup(Enum):
    ALL_IN_DOMAIN_CAN_VIEW = "ALL_IN_DOMAIN_CAN_VIEW"
    ALL_MANAGERS_CAN_VIEW = "ALL_MANAGERS_CAN_VIEW"
    ALL_MEMBERS_CAN_VIEW = "ALL_MEMBERS_CAN_VIEW"
    ANYONE_CAN_VIEW = "ANYONE_CAN_VIEW"


class WhoCanViewMembership(Enum):
    ALL_IN_DOMAIN_CAN_VIEW = "ALL_IN_DOMAIN_CAN_VIEW"
    ALL_MANAGERS_CAN_VIEW = "ALL_MANAGERS_CAN_VIEW"
    ALL_MEMBERS_CAN_VIEW = "ALL_MEMBERS_CAN_VIEW"
    ANYONE_CAN_VIEW = "ANYONE_CAN_VIEW"


class GroupMemberRole(Enum):
    OWNER = "OWNER"
    MANAGER = "MANAGER"
    MEMBER = "MEMBER"


class GroupMemberSubscription(Enum):
    EACH_EMAIL = "EACH_EMAIL"
    DIGEST = "DIGEST"
    ABRIDGED = "ABRIDGED"
    NO_EMAIL = "NO_EMAIL"


class Posting(Enum):
    ALLOWED = "ALLOWED"
    NOT_ALLOWED = "NOT_ALLOWED"
    MODERATED = "MODERATED"


class GroupMemberType(Enum):
    USER = "USER"
    GROUP = "GROUP"
    EXTERNAL = "EXTERNAL"


class GroupMemberStatus(Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    PENDING = "PENDING"


class GroupMember(ExpiryModel):
    email: str
    expand: bool = Field(
        False,
        description="Expand the group into the members of the group. This is useful for nested groups.",
    )
    expires_at: Optional[datetime] = None
    role: GroupMemberRole = GroupMemberRole.MEMBER
    type: GroupMemberType = GroupMemberType.USER
    status: GroupMemberStatus = GroupMemberStatus.ACTIVE
    subscription: GroupMemberSubscription = GroupMemberSubscription.EACH_EMAIL


class Group(BaseModel):
    template_type = "NOQ::Google::Group"
    file_path: str
    enabled: Optional[bool] = True
    deleted: Optional[bool] = False
    expires_at: Optional[datetime] = None
    name: str
    email: str
    description: str
    welcome_message: Optional[str]
    members: List[GroupMember]
    who_can_invite: WhoCanInvite = "ALL_MANAGERS_CAN_INVITE"
    who_can_join: WhoCanJoin = "CAN_REQUEST_TO_JOIN"
    who_can_post_message: WhoCanPostMessage = "NONE_CAN_POST"
    who_can_view_group: WhoCanViewGroup = "ALL_MANAGERS_CAN_VIEW"
    who_can_view_membership: WhoCanViewMembership = "ALL_MANAGERS_CAN_VIEW"
    # TODO: who_can_contact_group_members
    # TODO: who_can_view_member_email_addresses
    # TODO: allow_email_posting
    # TODO: allow_web_posting
    # TODO: conversation_history
    # TODO: There is more. Check google group settings page


async def get_service(
    config: Config,
    service_name: str,
    service_path: str,
):
    """
    Get a service connection to Google. You'll need to generate a GCP service account first.

    Noq requires that you either have a service key file with content like below,
    and you've set the configuration for `google.service_key_file` to the full path of that file on disk,
    or you've just put the json for this in your Noq configuration in the `secrets.google.service_key_dict` configuration
    key.


    """

    service_key = config.secrets.get("google", {}).get("service_key")
    credential_subjects = config.secrets.get("google", {}).get("credential_subjects")

    admin_credentials = service_account.Credentials.from_service_account_info(
        service_key,
        scopes=[
            "https://www.googleapis.com/auth/admin.directory.user.security",
            "https://www.googleapis.com/auth/admin.reports.audit.readonly",
            "https://www.googleapis.com/auth/admin.directory.user",
            "https://www.googleapis.com/auth/admin.directory.group",
            "https://www.googleapis.com/auth/admin.directory.group.member",
        ],
    )

    credential_subject = None
    for k, v in credential_subjects.items():
        # TODO: If we want to support multiple domains in the feature, such as
        # noq.dev and noqcontractors.dev, we would need to account for this here.
        credential_subject = v
        break

    admin_delegated_credentials = admin_credentials.with_subject(credential_subject)
    service = await aio_wrapper(
        googleapiclient.discovery.build,
        service_name,
        service_path,
        credentials=admin_delegated_credentials,
        thread_sensitive=True,
    )

    return service


async def generate_group_templates(config, domain, output_dir):
    """List all groups in the domain, along with members and
    settings"""
    groups = []
    service = await get_service(config, "admin", "directory_v1")

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
                Group(
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
