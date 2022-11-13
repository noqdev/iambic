from iambic.aws.accounts.models import AWSAccountTemplate
from iambic.aws.iam.policy.models import ManagedPolicyTemplate
from iambic.aws.iam.role.models import RoleTemplate
from iambic.aws.organizations.models import AWSOrganizationTemplate
from iambic.google.group.models import GroupTemplate

TEMPLATES = [
    RoleTemplate,
    AWSAccountTemplate,
    AWSOrganizationTemplate,
    GroupTemplate,
    ManagedPolicyTemplate,
]
TEMPLATE_TYPE_MAP = {
    template.__fields__["template_type"].default: template for template in TEMPLATES
}
