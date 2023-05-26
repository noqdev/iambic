from __future__ import annotations

from typing import Optional

from pydantic import BaseModel as PydanticBaseModel
from pydantic import Field


class PermissionSetMessageDetails(PydanticBaseModel):
    account_id: str
    instance_arn: str
    permission_set_arn: str


class ManagedPolicyMessageDetails(PydanticBaseModel):
    account_id: str
    policy_path: str
    policy_name: str
    delete: bool


class RoleMessageDetails(PydanticBaseModel):
    account_id: str
    role_name: str
    delete: bool


class GroupMessageDetails(PydanticBaseModel):
    account_id: str
    group_name: str
    delete: bool


class UserMessageDetails(PydanticBaseModel):
    account_id: str
    user_name: str
    delete: bool


class SCPMessageDetails(PydanticBaseModel):
    account_id: str
    policy_id: str
    delete: bool
    event: str = Field(
        ...,
        description="One of: CreatePolicy, DeletePolicy, UpdatePolicy, AttachPolicy, DetachPolicy, TagResource, UntagResource",
    )

    @staticmethod
    def tag_event(event, source) -> bool:
        """Returns True if the event is a tag/untag event related to SCPs"""
        return (
            event in ["TagResource", "UntagResource"]
            and source == "organizations.amazonaws.com"
        )

    @staticmethod
    def get_policy_id(request_params, response_elements) -> Optional[str]:
        """Returns the policy ID from the request parameters or response elements (last one if it is a CreatePolicy event)"""
        return (request_params and request_params.get("policyId", None)) or (
            response_elements
            and response_elements.get("policy", {})
            .get("policySummary", {})
            .get("id", None)
        )
