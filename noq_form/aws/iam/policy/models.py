from typing import List, Optional, Union

from pydantic import Field

from noq_form.core.models import AccessModel, ExpiryModel


class ManagedPolicy(AccessModel, ExpiryModel):
    policy_arn: str

    @property
    def resource_type(self):
        return "Managed Policy"

    @property
    def resource_name(self):
        return self.policy_arn


class PolicyStatement(AccessModel, ExpiryModel):
    effect: str = Field(..., description="Allow | Deny")
    principal: Optional[dict] = None
    not_principal: Optional[dict] = None
    action: Optional[Union[List[str] | str]] = None
    not_action: Optional[Union[List[str] | str]] = None
    resource: Optional[Union[List[str] | str]] = None
    not_resource: Optional[Union[List[str] | str]] = None
    sid: Optional[str] = None  # Fix constr(regex=r"^[a-zA-Z0-9]*")

    @property
    def resource_type(self):
        return "Policy Statement"

    @property
    def resource_name(self):
        return self.sid


class AssumeRolePolicyDocument(AccessModel):
    version: Optional[str] = None
    statement: Optional[List[PolicyStatement]] = None


class PolicyDocument(AccessModel, ExpiryModel):
    policy_name: str
    version: Optional[str] = None
    statement: Optional[List[PolicyStatement]] = None

    @property
    def resource_type(self):
        return "Policy Document"

    @property
    def resource_name(self):
        return self.policy_name
