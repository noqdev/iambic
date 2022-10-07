from noq_form.aws.iam.role.models import MultiAccountRoleTemplate

TEMPLATES = [MultiAccountRoleTemplate]
TEMPLATE_TYPE_MAP = {
    template.__fields__["template_type"].default: template for template in TEMPLATES
}
