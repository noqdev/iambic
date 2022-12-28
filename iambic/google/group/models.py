from __future__ import annotations

import asyncio
from itertools import chain
from typing import List, Optional

from pydantic import Field

from iambic.config.models import GoogleProject
from iambic.core.context import ExecutionContext
from iambic.core.logger import log
from iambic.core.models import (
    AccountChangeDetails,
    BaseModel,
    ExpiryModel,
    ProposedChange,
    ProposedChangeType,
)
from iambic.google.group.utils import (
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
from iambic.google.models import (
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

# TODO: Okta Applications and User/Group -> Application assignments


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


class GroupTemplateProperties(BaseModel):
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
    read_only: bool = False

    @property
    def resource_type(self):
        return "google:group:template"

    @property
    def resource_id(self):
        return self.email


# TODO: Support deleting Google Groups if expired
class GroupTemplate(GoogleTemplate, ExpiryModel):
    template_type = "NOQ::Google::Group"
    properties: GroupTemplateProperties

    def apply_resource_dict(
        self, google_project: GoogleProject, context: ExecutionContext
    ):
        return {
            "name": self.properties.name,
            "email": self.properties.email,
            "description": self.properties.description,
            "members": self.properties.members,
        }

    async def _apply_to_account(
        self, google_project: GoogleProject, context: ExecutionContext
    ) -> AccountChangeDetails:
        proposed_group = self.apply_resource_dict(google_project, context)
        change_details = AccountChangeDetails(
            account=self.properties.domain,
            resource_id=self.properties.email,
            new_value=proposed_group,  # TODO fix
            proposed_changes=[],
        )

        log_params = dict(
            resource_type=self.properties.resource_type,
            resource_id=self.properties.email,
            account=str(self.properties.domain),
        )
        # read_only = self._is_read_only(google_project)

        current_group = await get_group(
            self.properties.email, self.properties.domain, google_project
        )
        if current_group:
            change_details.current_value = current_group

        group_exists = bool(current_group)

        tasks = []

        await self.remove_expired_resources(context)

        if not group_exists and not self.deleted:
            change_details.proposed_changes.append(
                ProposedChange(
                    change_type=ProposedChangeType.CREATE,
                    resource_id=self.properties.email,
                    resource_type=self.properties.resource_type,
                )
            )
            log_str = "New resource found in code."
            if not context.execute:
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
            current_group = await get_group(
                self.properties.email, self.properties.domain, google_project
            )
            if current_group:
                change_details.current_value = current_group

        # TODO: Support group expansion
        tasks.extend(
            [
                update_group_domain(
                    current_group.properties.domain,
                    self.properties.domain,
                    log_params,
                    context,
                ),
                update_group_email(
                    current_group.properties.email,
                    self.properties.email,
                    self.properties.domain,
                    google_project,
                    log_params,
                    context,
                ),
                update_group_name(
                    self.properties.email,
                    current_group.properties.name,
                    self.properties.name,
                    self.properties.domain,
                    google_project,
                    log_params,
                    context,
                ),
                update_group_description(
                    self.properties.email,
                    current_group.properties.description,
                    self.properties.description,
                    self.properties.domain,
                    google_project,
                    log_params,
                    context,
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
                    context,
                ),
            ]
        )

        changes_made = await asyncio.gather(*tasks)
        deletion_change = await maybe_delete_group(
            self,
            google_project,
            log_params,
            context,
        )
        changes_made.extend(deletion_change)
        if any(changes_made):
            change_details.proposed_changes.extend(
                list(chain.from_iterable(changes_made))
            )

        if context.execute:
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

    def _is_read_only(self, google_project: GoogleProject):
        return google_project.read_only or self.read_only


async def get_group_template(service, group, domain) -> GroupTemplate:
    members = await get_group_members(service, group)

    file_name = f"{group['email'].split('@')[0]}.yaml"
    return GroupTemplate(
        file_path=f"google/groups/{domain}/{file_name}",
        properties=dict(
            domain=domain,
            name=group["name"],
            email=group["email"],
            description=group["description"],
            members=members,
        ),
    )
