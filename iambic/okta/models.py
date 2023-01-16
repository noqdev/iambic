from __future__ import annotations

from enum import Enum
from typing import Any, List, Optional, Union

from pydantic import Field

from iambic.core.models import BaseModel, ExpiryModel

# Reference: https://www.guidodiepen.nl/2019/02/implementing-a-simple-plugin-framework-in-python/


class IdentityProvider(BaseModel):
    name: str


class UserStatus(Enum):
    active = "active"
    provisioned = "provisioned"
    deprovisioned = "deprovisioned"
    recovery = "recovery"


class User(BaseModel, ExpiryModel):
    idp_name: str
    username: str
    user_id: Optional[str]
    domain: Optional[str]
    fullname: Optional[str]
    status: Optional[UserStatus]
    created: Optional[str]
    updated: Optional[str]
    groups: Optional[List[str]]
    background_check_status: Optional[bool]
    extra: Any = Field(None, description=("Extra attributes to store"))


class GroupAttributes(BaseModel):
    requestable: bool = Field(
        False, description="Whether end-users can request access to group"
    )
    manager_approval_required: bool = Field(
        False, description="Whether a manager needs to approve access to the group"
    )
    approval_chain: List[Union[User, str]] = Field(
        [],
        description="A list of users or groups that need to approve access to the group",
    )
    self_approval_groups: List[str] = Field(
        [],
        description=(
            "If the user is a member of a self-approval group, their request to the group "
            "will be automatically approved"
        ),
    )
    allow_bulk_add_and_remove: bool = Field(
        True,
        description=(
            "Controls whether administrators can automatically approve access to the group"
        ),
    )
    background_check_required: bool = Field(
        False,
        description=("Whether a background check is required to be added to the group"),
    )
    allow_contractors: bool = Field(
        False,
        description=("Whether contractors are allowed to be members of the group"),
    )
    allow_third_party: bool = Field(
        False,
        description=(
            "Whether third-party users are allowed to be a member of the group"
        ),
    )
    emails_to_notify_on_new_members: List[str] = Field(
        [],
        description=(
            "A list of e-mail addresses to notify when new users are added to the group."
        ),
    )


class Group(BaseModel):
    name: str = Field(..., description="Name of the group")
    owner: Optional[str] = Field(None, description="Owner of the group")
    idp_name: str = Field(
        ...,
        description="Name of the tenant's identity provider that's associated with the group",
    )
    group_id: Optional[str] = Field(
        ..., description="Unique Group ID for the group. Usually it's {idp-name}-{name}"
    )
    description: Optional[str] = Field(None, description="Description of the group")
    attributes: GroupAttributes = Field(
        ...,
        description=(
            "Protected attributes that tell us whether the group is requester, where approvals should be routed, etc."
        ),
    )
    extra: Any = Field(None, description=("Extra attributes to store"))
    members: List[User] = Field([], description="Users in the group")

    @property
    def resource_type(self) -> str:
        return "okta:group"


class ActionStatus(Enum):
    success = "success"
    error = "error"


class ActionResponse(BaseModel):
    status: Optional[ActionStatus] = None
    errors: Optional[List[str]] = None
    data: Any = None


class GroupRequestStatus(Enum):
    pending = "pending"
    approved = "approved"
    cancelled = "cancelled"
    rejected = "rejected"


class LastUpdated(BaseModel):
    user: User
    time: int
    comment: str


class GroupRequest(BaseModel):
    request_id: str
    request_url: str
    tenant: str
    users: List[User]
    groups: List[Group]
    requester: User
    justification: str
    expires: Optional[int] = None
    status: GroupRequestStatus
    created_time: int
    last_updated: List[LastUpdated]
    last_updated_time: int
    last_updated_by: User
    reviewer_comments: Optional[str]


class GroupRequests(BaseModel):
    requests: List[GroupRequest]


class GroupRequestsTable(BaseModel):
    User: str
    Group: str
    Requester: str
    Justification: str
    Expires: Optional[str]
    Status: str
    Last_Updated: str
