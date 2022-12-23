from iambic.aws.iam.policy.models import ManagedPolicyTemplate
from iambic.aws.iam.role.models import RoleTemplate
from iambic.aws.sso.permission_set.models import AWSSSOPermissionSetTemplate
from iambic.google.group.models import GroupTemplate
from iambic.okta.group.models import OktaGroupTemplate

TEMPLATES = [
    RoleTemplate,
    GroupTemplate,
    OktaGroupTemplate,
    ManagedPolicyTemplate,
    AWSSSOPermissionSetTemplate,
]
TEMPLATE_TYPE_MAP = {
    template.__fields__["template_type"].default: template for template in TEMPLATES
}
