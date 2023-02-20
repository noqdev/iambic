from __future__ import annotations

from pydantic import BaseModel as PydanticBaseModel


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
