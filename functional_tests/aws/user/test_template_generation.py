from __future__ import annotations

import os
from unittest import IsolatedAsyncioTestCase

from functional_tests.aws.user.utils import generate_user_template_from_base
from functional_tests.conftest import IAMBIC_TEST_DETAILS
from iambic.core.context import ctx
from iambic.plugins.aws.event_bridge.models import UserMessageDetails
from iambic.plugins.aws.iam.user.models import UserTemplate
from iambic.plugins.aws.iam.user.template_generation import generate_aws_user_templates


class PartialImportUserTestCase(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.template = await generate_user_template_from_base(
            IAMBIC_TEST_DETAILS.template_dir_path
        )
        self.user_name = self.template.properties.user_name
        self.all_account_ids = [
            account.account_id for account in IAMBIC_TEST_DETAILS.config.aws.accounts
        ]

    async def asyncTearDown(self):
        self.template.deleted = True
        await self.template.apply(IAMBIC_TEST_DETAILS.config.aws, ctx)

    async def test_delete_user_template(self):
        included_account = self.all_account_ids[0]
        self.template.included_accounts = [included_account]
        self.template.excluded_accounts = []
        self.template.write()

        self.assertTrue(os.path.exists(self.template.file_path))

        await generate_aws_user_templates(
            IAMBIC_TEST_DETAILS.config.aws,
            IAMBIC_TEST_DETAILS.template_dir_path,
            [
                UserMessageDetails(
                    account_id=included_account,
                    user_name=self.template.properties.user_name,
                    delete=True,
                )
            ],
        )

        self.assertFalse(os.path.exists(self.template.file_path))

    async def test_delete_user_from_one_account(self):
        deleted_account = self.all_account_ids[0]
        self.template.included_accounts = ["*"]
        self.template.excluded_accounts = []
        self.template.write()

        # Create on all accounts except 1
        self.template.excluded_accounts = [deleted_account]

        # Confirm the change is only in memory and not on the file system
        file_sys_template = UserTemplate.load(self.template.file_path)
        self.assertNotIn(deleted_account, file_sys_template.excluded_accounts)

        # Create the policy on all accounts except 1
        await self.template.apply(IAMBIC_TEST_DETAILS.config.aws, ctx)

        # Refresh the template
        await generate_aws_user_templates(
            IAMBIC_TEST_DETAILS.config.aws,
            IAMBIC_TEST_DETAILS.template_dir_path,
            [
                UserMessageDetails(
                    account_id=deleted_account,
                    user_name=self.template.properties.user_name,
                    delete=True,
                )
            ],
        )

        file_sys_template = UserTemplate.load(self.template.file_path)
        self.assertEqual(file_sys_template.included_accounts, ["*"])
        self.assertEqual(file_sys_template.excluded_accounts, [deleted_account])
