from __future__ import annotations

import os
import random
import uuid

from functional_tests.conftest import IAMBIC_TEST_DETAILS
from iambic.core.iambic_enum import Command
from iambic.core.models import ExecutionMessage
from iambic.plugins.v0_1_0.azure_ad.group.models import (
    AzureActiveDirectoryGroupTemplate,
)
from iambic.plugins.v0_1_0.azure_ad.group.template_generation import (
    collect_org_groups,
    generate_group_templates,
)


def generate_group_template() -> AzureActiveDirectoryGroupTemplate:
    group_dir = os.path.join(
        IAMBIC_TEST_DETAILS.template_dir_path,
        "resources/azure_ad/group/noq_dev",
    )
    os.makedirs(group_dir, exist_ok=True)
    identifier = str(random.randint(0, 10000))
    file_path = os.path.join(group_dir, f"iambic_functional_test_{identifier}.yaml")
    group_template = f"""
template_type: NOQ::AzureAD::Group
idp_name: noq_dev
properties:
  name: Fn Test Group {identifier}
  description: This is the group for running functional tests
  group_types:
    - Unified
  mail_enabled: true
  mail_nickname: fn_test_group_{identifier}
  security_enabled: false
"""
    with open(file_path, "w") as f:
        f.write(group_template)
    group_template = AzureActiveDirectoryGroupTemplate.load(file_path)

    return group_template


async def group_full_import():
    exe_message = ExecutionMessage(
        execution_id=str(uuid.uuid4()), command=Command.IMPORT, provider_type="aws"
    )
    await collect_org_groups(
        exe_message,
        IAMBIC_TEST_DETAILS.config.azure_ad,
    )
    await generate_group_templates(
        exe_message,
        IAMBIC_TEST_DETAILS.config.aws,
        IAMBIC_TEST_DETAILS.template_dir_path,
    )
