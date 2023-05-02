from __future__ import annotations

import random
import uuid

from functional_tests.conftest import IAMBIC_TEST_DETAILS
from iambic.core.iambic_enum import Command
from iambic.core.logger import log
from iambic.core.models import ExecutionMessage
from iambic.core.template_generation import get_existing_template_map
from iambic.core.utils import gather_templates
from iambic.plugins.v0_1_0.aws.identity_center.permission_set.models import (
    AWS_IDENTITY_CENTER_PERMISSION_SET_TEMPLATE_TYPE,
    AwsIdentityCenterPermissionSetTemplate,
    PermissionSetAccess,
    PermissionSetProperties,
)
from iambic.plugins.v0_1_0.aws.identity_center.permission_set.template_generation import (
    collect_aws_permission_sets,
    generate_aws_permission_set_templates,
    get_template_dir,
)
from iambic.plugins.v0_1_0.aws.models import AWSAccount


def attach_access_rule(
    permission_set_template: AwsIdentityCenterPermissionSetTemplate,
    aws_account: AWSAccount,
    exclude_accounts: int = 0,
) -> AwsIdentityCenterPermissionSetTemplate:
    users = [
        details["UserName"]
        for details in aws_account.identity_center_details.user_map.values()
    ]
    groups = [
        details["DisplayName"]
        for details in aws_account.identity_center_details.user_map.values()
    ]
    org_accounts = list(aws_account.identity_center_details.org_account_map.values())
    if exclude_accounts:
        exclude_accounts = min(exclude_accounts, len(org_accounts) - 1)

    excluded_accounts = [] if not exclude_accounts else org_accounts[exclude_accounts:]
    include_accounts = random.randint(0, len(org_accounts) - exclude_accounts)
    if include_accounts == len(org_accounts) - 1:
        included_accounts = ["*"]
    else:
        included_accounts = org_accounts[:include_accounts]

    permission_set_template.access_rules.append(
        PermissionSetAccess(
            users=users[: random.randint(1, len(users))],
            groups=users[: random.randint(1, len(groups))],
            excluded_accounts=excluded_accounts,
            included_accounts=included_accounts,
        )
    )

    return permission_set_template


async def generate_permission_set_template_from_base(
    repo_dir: str,
    extra_salt: str = "",
) -> AwsIdentityCenterPermissionSetTemplate:
    permission_sets = await gather_templates(
        repo_dir, AWS_IDENTITY_CENTER_PERMISSION_SET_TEMPLATE_TYPE
    )
    permission_set_dir = get_template_dir(repo_dir)
    permission_set_template = AwsIdentityCenterPermissionSetTemplate.load(
        random.choice(permission_sets)
    )
    log.info(
        "Using permission set as base",
        permission_set=permission_set_template.identifier,
    )

    permission_set_template.identifier = (
        f"iambic_test_{extra_salt}{random.randint(0, 10000)}"
    )
    permission_set_template.file_path = (
        f"{permission_set_dir}/{permission_set_template.identifier}.yaml"
    )

    permission_set_template.properties.name = permission_set_template.identifier
    permission_set_template.properties.description = (
        "This was created by a functional test."
    )

    permission_set_template.write(exclude_unset=False)
    return permission_set_template


async def generate_permission_set_template(
    repo_dir: str,
    noise: str = "",
) -> AwsIdentityCenterPermissionSetTemplate:
    permission_set_dir = get_template_dir(repo_dir)
    identifier = f"iambic_test_{noise}{random.randint(0, 10000)}"
    file_path = f"{permission_set_dir}/{identifier}.yaml"
    properties = PermissionSetProperties(
        name=identifier, description="This was created by a functional test."
    )
    permission_set_template = AwsIdentityCenterPermissionSetTemplate(
        identifier=identifier, properties=properties, file_path=file_path
    )
    permission_set_template.write()
    return permission_set_template


async def permission_set_full_import(detect_messages: list = None):
    exe_message = ExecutionMessage(
        execution_id=str(uuid.uuid4()), command=Command.IMPORT, provider_type="aws"
    )
    identity_center_template_map = await get_existing_template_map(
        repo_dir=IAMBIC_TEST_DETAILS.template_dir_path,
        template_type="AWS::IdentityCenter.*",
        nested=True,
    )
    await collect_aws_permission_sets(
        exe_message,
        IAMBIC_TEST_DETAILS.config.aws,
        identity_center_template_map,
        detect_messages,
    )
    await generate_aws_permission_set_templates(
        exe_message,
        IAMBIC_TEST_DETAILS.config.aws,
        IAMBIC_TEST_DETAILS.template_dir_path,
        identity_center_template_map,
        detect_messages,
    )
