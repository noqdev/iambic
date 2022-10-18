from iambic.aws.iam.role.models import RoleTemplate

TEMPLATES = [RoleTemplate]
TEMPLATE_TYPE_MAP = {
    template.__fields__["template_type"].default: template for template in TEMPLATES
}
