from __future__ import annotations

from typing import Optional

from pydantic import Field, constr

from iambic.core.models import ExpiryModel
from iambic.plugins.v0_1_0.aws.models import ARN_RE, AccessModel


class Path(AccessModel):
    file_path: str = Field(..., hidden_from_schema=True)

    @property
    def resource_type(self) -> str:
        return "iam:path"

    @property
    def resource_id(self) -> str:
        return self.file_path


class MaxSessionDuration(AccessModel):
    max_session_duration: int

    @property
    def resource_type(self) -> str:
        return "iam:max_session_duration"

    @property
    def resource_id(self) -> str:
        return str(self.max_session_duration)


class PermissionBoundary(ExpiryModel, AccessModel):
    # alias allows easily deserialize from boto3 response
    policy_arn: constr(regex=ARN_RE) = Field(alias="permissions_boundary_arn")

    # permissions_boundary_type to make it easy to deserialize from boto3 response
    # we won't actually serialize it back
    permissions_boundary_type: Optional[str] = Field(exclude=True)

    @property
    def resource_type(self):
        return "aws:iam:permission_boundary"

    @property
    def resource_id(self):
        return self.policy_arn
