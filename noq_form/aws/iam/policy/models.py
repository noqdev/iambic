from typing import List, Optional, Union

from pydantic import Field

from noq_form.config.models import AccountConfig
from noq_form.core.models import AccessModel, BaseModel, ExpiryModel


class ManagedPolicy(AccessModel, ExpiryModel):
    policy_arn: str

    @property
    def resource_type(self):
        return "Managed Policy"

    @property
    def resource_name(self):
        return self.policy_arn


class Principal(BaseModel):
    aws: str

    def _apply_resource_dict(self, account_config: AccountConfig = None) -> dict:
        return {"AWS": self.aws}


class Condition(BaseModel):
    # Key = service/resource_type
    # Value = resource_value | list[resource_value]
    string_equals: Optional[dict] = None
    string_not_equals: Optional[dict] = None
    string_equals_ignore_case: Optional[dict] = None
    string_like: Optional[dict] = None
    string_not_like: Optional[dict] = None


class PolicyStatement(AccessModel, ExpiryModel):
    effect: str = Field(..., description="Allow | Deny")
    principal: Optional[Principal] = None
    not_principal: Optional[Principal] = None
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
