from __future__ import annotations

import os
from unittest import IsolatedAsyncioTestCase

from functional_tests.aws.group.utils import generate_group_template_from_base
from functional_tests.conftest import IAMBIC_TEST_DETAILS
from iambic.core.context import ctx
from iambic.plugins.v0_1_0.aws.event_bridge.models import GroupMessageDetails
from iambic.plugins.v0_1_0.aws.iam.group.models import GroupTemplate
from iambic.plugins.v0_1_0.aws.iam.group.template_generation import (
    generate_aws_group_templates,
)


class PartialImportGroupTestCase(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.template = await generate_group_template_from_base(
            IAMBIC_TEST_DETAILS.template_dir_path
        )
        self.group_name = self.template.properties.group_name
        self.all_account_ids = [
            account.account_id for account in IAMBIC_TEST_DETAILS.config.aws.accounts
        ]

    async def asyncTearDown(self):
        self.template.deleted = True
        await self.template.apply(IAMBIC_TEST_DETAILS.config.aws, ctx)

    async def test_delete_group_template(self):
        included_account = self.all_account_ids[0]
        self.template.included_accounts = [included_account]
        self.template.excluded_accounts = []
        self.template.write()

        self.assertTrue(os.path.exists(self.template.file_path))

        await generate_aws_group_templates(
            IAMBIC_TEST_DETAILS.config.aws,
            IAMBIC_TEST_DETAILS.template_dir_path,
            [
                GroupMessageDetails(
                    account_id=included_account,
                    group_name=self.template.properties.group_name,
                    delete=True,
                )
            ],
        )

        self.assertFalse(os.path.exists(self.template.file_path))

    async def test_delete_group_from_one_account(self):
        deleted_account = self.all_account_ids[0]
        self.template.included_accounts = ["*"]
        self.template.excluded_accounts = []
        self.template.write()

        # Create on all accounts except 1
        self.template.excluded_accounts = [deleted_account]

        # Confirm the change is only in memory and not on the file system
        file_sys_template = GroupTemplate.load(self.template.file_path)
        self.assertNotIn(deleted_account, file_sys_template.excluded_accounts)

        # Create the policy on all accounts except 1
        await self.template.apply(IAMBIC_TEST_DETAILS.config.aws, ctx)

        # Refresh the template
        await generate_aws_group_templates(
            IAMBIC_TEST_DETAILS.config.aws,
            IAMBIC_TEST_DETAILS.template_dir_path,
            [
                GroupMessageDetails(
                    account_id=deleted_account,
                    group_name=self.template.properties.group_name,
                    delete=True,
                )
            ],
        )

        file_sys_template = GroupTemplate.load(self.template.file_path)
        self.assertEqual(file_sys_template.included_accounts, ["*"])
        self.assertEqual(file_sys_template.excluded_accounts, [deleted_account])
