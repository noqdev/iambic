from __future__ import annotations

from typing import Type

from iambic.core.models import BaseTemplate
from iambic.core.template import TemplateMixin
from iambic.plugins.v0_1_0.aws.iam.group.models import AwsIamGroupTemplate
from iambic.plugins.v0_1_0.aws.iam.policy.models import AwsIamManagedPolicyTemplate
from iambic.plugins.v0_1_0.aws.iam.role.models import AwsIamRoleTemplate
from iambic.plugins.v0_1_0.aws.iam.user.models import AwsIamUserTemplate
from iambic.plugins.v0_1_0.aws.identity_center.permission_set.models import (
    AwsIdentityCenterPermissionSetTemplate,
)
from iambic.plugins.v0_1_0.aws.organizations.scp.models import AwsScpPolicyTemplate


class AwsTemplateMixin(TemplateMixin):
    templates: list[Type[BaseTemplate]] = [
        AwsIdentityCenterPermissionSetTemplate,
        AwsIamGroupTemplate,
        AwsIamRoleTemplate,
        AwsIamUserTemplate,
        AwsIamManagedPolicyTemplate,
        AwsScpPolicyTemplate,
    ]
