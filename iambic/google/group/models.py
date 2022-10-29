from typing import List, Optional

from pydantic import Field

from iambic.aws.models import ExpiryModel
from iambic.config.models import GoogleProject
from iambic.core.models import AccountChangeDetails
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


class GroupMember(ExpiryModel):
    email: str
    expand: bool = Field(
        False,
        description="Expand the group into the members of the group. This is useful for nested groups.",
    )
    role: GroupMemberRole = GroupMemberRole.MEMBER
    type: GroupMemberType = GroupMemberType.USER
    status: GroupMemberStatus = GroupMemberStatus.ACTIVE
    subscription: GroupMemberSubscription = GroupMemberSubscription.EACH_EMAIL


class GroupTemplate(GoogleTemplate):
    template_type = "NOQ::Google::GroupTemplate"
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

    async def _apply_to_account(
        self, google_account: GoogleProject
    ) -> AccountChangeDetails:
        raise NotImplementedError

    def resource_type(self):
        return "google:group"

    def resource_id(self):
        return self.name
