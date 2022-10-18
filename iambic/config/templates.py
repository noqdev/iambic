from iambic.aws.iam.role.models import RoleTemplate
from iambic.google.models import GroupTemplate

TEMPLATES = [RoleTemplate, GroupTemplate]
TEMPLATE_TYPE_MAP = {
    template.__fields__["template_type"].default: template for template in TEMPLATES
}
