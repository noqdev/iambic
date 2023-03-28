from __future__ import annotations

import asyncio
import uuid
from unittest import IsolatedAsyncioTestCase

from functional_tests.aws.permission_set.utils import (
    attach_access_rule,
    generate_permission_set_template_from_base,
)
from functional_tests.conftest import IAMBIC_TEST_DETAILS
from iambic.config.dynamic_config import load_config
from iambic.core.iambic_enum import Command
from iambic.core.models import ExecutionMessage


class CreatePermissionSetTestCase(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.template = await generate_permission_set_template_from_base(
            IAMBIC_TEST_DETAILS.template_dir_path
        )

    async def asyncTearDown(self):
        await asyncio.sleep(5)
        await IAMBIC_TEST_DETAILS.identity_center_account.set_identity_center_details()
        self.template.deleted = True
        await self.template.apply(IAMBIC_TEST_DETAILS.config.aws)

    async def test_create_permission_set(self):
        await self.template.apply(IAMBIC_TEST_DETAILS.config.aws)
        await IAMBIC_TEST_DETAILS.identity_center_account.set_identity_center_details()

        self.assertIn(
            self.template.identifier,
            IAMBIC_TEST_DETAILS.identity_center_account.identity_center_details.permission_set_map,
        )

    async def test_create_permission_set_with_account_assignment(self):
        self.template = attach_access_rule(
            self.template, IAMBIC_TEST_DETAILS.identity_center_account
        )
        await self.template.apply(IAMBIC_TEST_DETAILS.config.aws)
        await IAMBIC_TEST_DETAILS.identity_center_account.set_identity_center_details()

        self.assertIn(
            self.template.identifier,
            IAMBIC_TEST_DETAILS.identity_center_account.identity_center_details.permission_set_map,
        )

        # TODO: Validate account assignments with response of get_permission_set_users_and_groups

    # the config discovery tests are here because there are cloud dependency in functional tests that
    # remove resources in-flight. (because we now run functional tests in parallel)
    async def test_aws_account_name_updated(self):
        exe_message = ExecutionMessage(
            execution_id=str(uuid.uuid4()),
            command=Command.CONFIG_DISCOVERY,
            provider_type="aws",
        )
        config = await load_config(IAMBIC_TEST_DETAILS.config_path)
        original_name = config.aws.accounts[0].account_name
        new_name = "new_name"
        config.aws.accounts[0].account_name = new_name

        await config.run_discover_upstream_config_changes(
            exe_message, IAMBIC_TEST_DETAILS.template_dir_path
        )

        account_names = [account.account_name for account in config.aws.accounts]
        self.assertIn(original_name, account_names)
        self.assertNotIn(new_name, account_names)

    async def test_aws_account_discovered(self):
        config = await load_config(IAMBIC_TEST_DETAILS.config_path)
        original_aws_count = len(config.aws.accounts)
        removed_account = config.aws.accounts[-1]
        config.aws.accounts.pop(-1)
        exe_message = ExecutionMessage(
            execution_id=str(uuid.uuid4()),
            command=Command.CONFIG_DISCOVERY,
            provider_type="aws",
        )

        await config.run_discover_upstream_config_changes(
            exe_message, IAMBIC_TEST_DETAILS.template_dir_path
        )
        self.assertEqual(len(config.aws.accounts), original_aws_count)
        self.assertIn(
            removed_account.account_id,
            [account.account_id for account in config.aws.accounts],
        )
