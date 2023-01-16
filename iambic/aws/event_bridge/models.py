from __future__ import annotations

from sqlmodel import SQLModel


class PermissionSetMessageDetails(SQLModel):
    account_id: str
    instance_arn: str
    permission_set_arn: str


class ManagedPolicyMessageDetails(SQLModel):
    account_id: str
    policy_path: str
    policy_name: str
    delete: bool


class RoleMessageDetails(SQLModel):
    account_id: str
    role_name: str
    delete: bool
