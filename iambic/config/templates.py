from iambic.aws.iam.role.models import RoleTemplate
from iambic.google.group.models import GroupTemplate

TEMPLATES = [RoleTemplate, GroupTemplate]
TEMPLATE_TYPE_MAP = {
    template.__fields__["template_type"].default: template for template in TEMPLATES
}
