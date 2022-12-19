from typing import Any, Optional

from iambic.aws.cloudcontrol.models import CloudControlBaseTemplate
from iambic.core.models import BaseModel


class AWSSSOInstance(BaseModel):
    arn: str
    region: str
    access_portal_url: str
    identity_store_id: str


class CustomerManagedPolicyReferences(BaseModel):
    path: str
    name: str


class Tags(BaseModel):
    key: str
    value: str


class AWSSSOPermissionSetProperties(BaseModel):
    name: str
    arn: str
    permission_set_arn: str
    customer_managed_policy_references: list[CustomerManagedPolicyReferences]
    session_duration: str
    instance_arn: str
    inline_policy: str
    managed_policies: list[Any]
    tags: Optional[list[Tags]]


class AWSSSOPermissionSetTemplate(CloudControlBaseTemplate):
    template_type: str = "NOQ::AWS::SSO::PermissionSet"
    properties: AWSSSOPermissionSetProperties


async def get_aws_sso_permission_set_template(
    model: AWSSSOPermissionSetProperties,
) -> AWSSSOPermissionSetTemplate:

    file_name = f"{model.name}.yaml"
    return AWSSSOPermissionSetTemplate(
        file_path=f"resources/aws/sso/permission_sets/{file_name}",
        properties=model,
    )
