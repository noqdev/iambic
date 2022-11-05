from iambic.aws.iam.policy.models import ManagedPolicyTemplate
from iambic.aws.iam.role.models import RoleTemplate
from iambic.google.group.models import GroupTemplate

TEMPLATES = [RoleTemplate, GroupTemplate, ManagedPolicyTemplate]
TEMPLATE_TYPE_MAP = {
    template.__fields__["template_type"].default: template for template in TEMPLATES
}
