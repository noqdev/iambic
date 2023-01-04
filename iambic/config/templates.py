from __future__ import annotations

from iambic.aws.iam.policy.models import ManagedPolicyTemplate
from iambic.aws.iam.role.models import RoleTemplate
from iambic.aws.identity_center.permission_set.models import AWSIdentityCenterPermissionSetTemplate
from iambic.google.group.models import GroupTemplate
from iambic.okta.group.models import OktaGroupTemplate

TEMPLATES = [
    AWSIdentityCenterPermissionSetTemplate,
    RoleTemplate,
    GroupTemplate,
    OktaGroupTemplate,
    ManagedPolicyTemplate,
]
TEMPLATE_TYPE_MAP = {
    template.__fields__["template_type"].default: template for template in TEMPLATES
}
