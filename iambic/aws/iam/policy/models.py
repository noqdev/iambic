from typing import List, Optional, Union

from pydantic import Field

from iambic.config.models import AccountConfig
from iambic.core.models import AccessModel, BaseModel, ExpiryModel


class ManagedPolicy(AccessModel, ExpiryModel):
    policy_arn: str

    @property
    def resource_type(self):
        return "Managed Policy"

    @property
    def resource_name(self):
        return self.policy_arn


class Principal(BaseModel):
    aws: Optional[Union[str | list[str]]] = None
    service: Optional[Union[str | list[str]]] = None
    canonical_user: Optional[Union[str | list[str]]] = None
    federated: Optional[Union[str | list[str]]] = None

    def _apply_resource_dict(self, account_config: AccountConfig = None) -> dict:
        resource_dict = super(Principal, self)._apply_resource_dict(account_config)
        if aws_val := resource_dict.pop('aws', resource_dict.pop('Aws', None)):
            resource_dict["AWS"] = aws_val
        return resource_dict


class ConditionalStatement(BaseModel):
    for_all_values: Optional[bool] = None
    for_any_values: Optional[bool] = None


class Condition(BaseModel):
    """TODO: Finish this.

    I put in a pin it because it became obvious this will be a large undertaking.
    The problem stems from the way conditions are structured.

    Take string_equals: Optional[dict] = None for example
    For this one attribute it also requires the following:
        for_all_values__string_equals
        for_any_values__string_equals
        for_all_values__string_equals__if_exists
        for_any_values__string_equals__if_exists
    On top of that we still need to add clarity on what the supported keys are.

    For more info on conditions:
    https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_elements_condition.html

    """
    # Key = service/resource_type
    # Value = resource_value | list[resource_value]

    # String conditionals
    string_equals: Optional[dict] = None
    string_not_equals: Optional[dict] = None
    string_equals_ignore_case: Optional[dict] = None
    string_like: Optional[dict] = None
    string_not_like: Optional[dict] = None

    # Numeric Conditionals
    numeric_equals: Optional[dict] = None
    numeric_not_equals: Optional[dict] = None
    numeric_less_than: Optional[dict] = None
    numeric_less_than_equals: Optional[dict] = None
    numeric_greater_than: Optional[dict] = None
    numeric_greater_than_equals: Optional[dict] = None

    # Date Conditionals
    date_equals: Optional[dict] = None
    date_not_equals: Optional[dict] = None
    date_less_than: Optional[dict] = None
    date_less_than_equals: Optional[dict] = None
    date_greater_than: Optional[dict] = None
    date_greater_than_equals: Optional[dict] = None

    # IP Addr Conditionals
    ip_address: Optional[dict] = None
    not_ip_address: Optional[dict] = None

    # ARN Conditionals
    arn_equals: Optional[dict] = None
    arn_like: Optional[dict] = None
    arn_not_equals: Optional[dict] = None
    arn_not_like: Optional[dict] = None

    # Null Conditional
    null: Optional[dict] = None

    # Boolean conditional
    bool: Optional[dict] = None


class PolicyStatement(AccessModel, ExpiryModel):
    effect: str = Field(..., description="Allow | Deny")
    principal: Optional[Union[Principal | str]] = None
    not_principal: Optional[Union[Principal | str]] = None
    action: Optional[Union[List[str] | str]] = None
    not_action: Optional[Union[List[str] | str]] = None
    resource: Optional[Union[List[str] | str]] = None
    not_resource: Optional[Union[List[str] | str]] = None
    condition: Optional[dict] = None
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
