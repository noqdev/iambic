from __future__ import annotations

from iambic.aws.iam.group.models import GroupTemplate as AWSGroupTemplate
from iambic.aws.iam.policy.models import ManagedPolicyTemplate
from iambic.aws.iam.role.models import RoleTemplate
from iambic.aws.iam.user.models import UserTemplate
from iambic.aws.identity_center.permission_set.models import (
    AWSIdentityCenterPermissionSetTemplate,
)
from iambic.google.group.models import GroupTemplate as GoogleGroupTemplate
from iambic.okta.app.models import OktaAppTemplate
from iambic.okta.group.models import OktaGroupTemplate
from iambic.okta.user.models import OktaUserTemplate

TEMPLATES = [
    AWSGroupTemplate,
    AWSIdentityCenterPermissionSetTemplate,
    RoleTemplate,
    UserTemplate,
    GoogleGroupTemplate,
    OktaGroupTemplate,
    OktaAppTemplate,
    OktaUserTemplate,
    ManagedPolicyTemplate,
]
TEMPLATE_TYPE_MAP = {
    template.__fields__["template_type"].default: template for template in TEMPLATES
}
