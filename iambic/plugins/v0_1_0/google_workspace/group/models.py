from __future__ import annotations

import asyncio
from itertools import chain
from typing import TYPE_CHECKING, Any, List, Optional

from pydantic import Field, validator

from iambic.core.context import ctx
from iambic.core.iambic_enum import Command, IambicManaged
from iambic.core.logger import log
from iambic.core.models import (
    AccountChangeDetails,
    BaseModel,
    ExpiryModel,
    ProposedChange,
    ProposedChangeType,
)
from iambic.plugins.v0_1_0.google_workspace.group.utils import (
    create_group,
    get_group,
    get_group_members,
    maybe_delete_group,
    update_group_description,
    update_group_domain,
    update_group_email,
    update_group_members,
    update_group_name,
)
from iambic.plugins.v0_1_0.google_workspace.models import (
    GoogleTemplate,
    GroupMemberRole,
    GroupMemberStatus,
    GroupMemberSubscription,
    GroupMemberType,
    WhoCanInvite,
    WhoCanJoin,
    WhoCanPostMessage,
    WhoCanViewGroup,
    WhoCanViewMembership,
)

if TYPE_CHECKING:
    from iambic.plugins.v0_1_0.google_workspace.iambic_plugin import GoogleProject

GOOGLE_GROUP_TEMPLATE_TYPE = "NOQ::GoogleWorkspace::Group"


class GroupMember(BaseModel, ExpiryModel):
    email: str
    expand: bool = Field(
        False,
        description="Expand the group into the members of the group. This is useful for nested groups.",
    )
    role: GroupMemberRole = GroupMemberRole.MEMBER
    type: GroupMemberType = GroupMemberType.USER
    status: GroupMemberStatus = GroupMemberStatus.ACTIVE
    subscription: GroupMemberSubscription = GroupMemberSubscription.EACH_EMAIL

    @property
    def resource_type(self):
        return "google:group:member"

    @property
    def resource_id(self):
        return self.email


class GroupProperties(BaseModel):
    name: str
    domain: str
    email: str
    description: str
    welcome_message: Optional[str]
    members: List[GroupMember]
    who_can_invite: WhoCanInvite = "ALL_MANAGERS_CAN_INVITE"
    who_can_join: WhoCanJoin = "CAN_REQUEST_TO_JOIN"
    who_can_post_message: WhoCanPostMessage = "NONE_CAN_POST"
    who_can_view_group: WhoCanViewGroup = "ALL_MANAGERS_CAN_VIEW"
    who_can_view_membership: WhoCanViewMembership = "ALL_MANAGERS_CAN_VIEW"
    iambic_managed: IambicManaged = IambicManaged.UNDEFINED
    extra: Any = Field(None, description=("Extra attributes to store"))

    @classmethod
    def iambic_specific_knowledge(cls) -> set[str]:
        return {"extra", "metadata_commented_dict"}

    @property
    def resource_type(self):
        return "google:group:template"

    @property
    def resource_id(self):
        return self.email

    @validator("members")
    def sort_groups(cls, v: list[GroupMember]):
        sorted_v = sorted(v, key=lambda member: member.email)
        return sorted_v


class GoogleWorkspaceGroupTemplate(GoogleTemplate, ExpiryModel):
    template_type = GOOGLE_GROUP_TEMPLATE_TYPE
    owner: Optional[str] = Field(None, description="Owner of the group")
    properties: GroupProperties

    def apply_resource_dict(self, google_project: GoogleProject):
        return {
            "name": self.properties.name,
            "email": self.properties.email,
            "description": self.properties.description,
            "members": self.properties.members,
        }

    async def _apply_to_account(
        self, google_project: GoogleProject
    ) -> AccountChangeDetails:
        proposed_group = self.apply_resource_dict(google_project)
        change_details = AccountChangeDetails(
            account=self.properties.domain,
            resource_id=self.properties.email,
            resource_type=self.properties.resource_type,
            new_value=proposed_group,  # TODO fix
            proposed_changes=[],
        )

        log_params = dict(
            resource_type=self.properties.resource_type,
            resource_id=self.properties.email,
            account=str(self.properties.domain),
        )

        current_group = await get_group(
            self.properties.email, self.properties.domain, google_project
        )
        if current_group:
            change_details.current_value = current_group

            if ctx.command == Command.CONFIG_DISCOVERY:
                # Don't overwrite a resource during config discovery
                change_details.new_value = {}
                return change_details

        group_exists = bool(current_group)

        tasks = []

        await self.remove_expired_resources()

        if not group_exists:
            if self.deleted:
                log.info(
                    "Resource is marked for deletion, but does not exist in the cloud. Skipping.",
                )
                return change_details
            change_details.extend_changes(
                [
                    ProposedChange(
                        change_type=ProposedChangeType.CREATE,
                        resource_id=self.properties.email,
                        resource_type=self.properties.resource_type,
                    )
                ]
            )
            log_str = "New resource found in code."
            if not ctx.execute:
                log.info(log_str, **log_params)
                # Exit now because apply functions won't work if resource doesn't exist
                return change_details

            log_str = f"{log_str} Creating resource..."
            log.info(log_str, **log_params)

            await create_group(
                id=self.properties.email,
                domain=self.properties.domain,
                email=self.properties.email,
                name=self.properties.name,
                description=self.properties.description,
                google_project=google_project,
            )
            group_get_attempt = 0
            while not current_group and group_get_attempt < 5:
                # handle fetching group too fast
                group_get_attempt = group_get_attempt + 1
                current_group = await get_group(
                    self.properties.email, self.properties.domain, google_project
                )
                if not current_group:
                    await asyncio.sleep(1)

            if current_group:
                change_details.current_value = current_group

        # TODO: Support group expansion
        tasks.extend(
            [
                update_group_domain(
                    current_group.properties.domain,
                    self.properties.domain,
                    log_params,
                ),
                update_group_email(
                    current_group.properties.email,
                    self.properties.email,
                    self.properties.domain,
                    google_project,
                    log_params,
                ),
                update_group_name(
                    self.properties.email,
                    current_group.properties.name,
                    self.properties.name,
                    self.properties.domain,
                    google_project,
                    log_params,
                ),
                update_group_description(
                    self.properties.email,
                    current_group.properties.description,
                    self.properties.description,
                    self.properties.domain,
                    google_project,
                    log_params,
                ),
                update_group_members(
                    self.properties.email,
                    current_group.properties.members,
                    [
                        member
                        for member in self.properties.members
                        if not member.deleted
                    ],
                    self.properties.domain,
                    google_project,
                    log_params,
                ),
                maybe_delete_group(
                    self,
                    google_project,
                    log_params,
                ),
            ]
        )

        changes_made = await asyncio.gather(*tasks)
        if any(changes_made):
            change_details.extend_changes(list(chain.from_iterable(changes_made)))

        if ctx.execute:
            log.debug(
                "Successfully finished execution for resource",
                changes_made=bool(change_details.proposed_changes),
                **log_params,
            )
            if self.deleted:
                self.delete()
            self.write()
        else:
            log.debug(
                "Successfully finished scanning for drift for resource",
                requires_changes=bool(change_details.proposed_changes),
                **log_params,
            )

        return change_details

    @property
    def resource_type(self):
        return "google:group"

    @property
    def default_file_path(self):
        file_name = f"{self.properties.email.split('@')[0]}.yaml"
        return f"resources/google/groups/{self.properties.domain}/{file_name}"

    def _is_iambic_import_only(self, google_project: GoogleProject):
        return (
            google_project.iambic_managed == IambicManaged.IMPORT_ONLY
            or self.iambic_managed == IambicManaged.IMPORT_ONLY
        )


async def get_group_template(service, group, domain) -> GoogleWorkspaceGroupTemplate:
    members = await get_group_members(service, group)

    file_name = f"{group['email'].split('@')[0]}.yaml"
    return GoogleWorkspaceGroupTemplate(
        file_path=f"resources/google/groups/{domain}/{file_name}",
        properties=dict(
            domain=domain,
            name=group["name"],
            email=group["email"],
            description=group["description"],
            members=members,
        ),
    )
