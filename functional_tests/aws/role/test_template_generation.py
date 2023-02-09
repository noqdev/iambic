from __future__ import annotations

import os
from unittest import IsolatedAsyncioTestCase

from functional_tests.aws.role.utils import generate_role_template_from_base
from functional_tests.conftest import IAMBIC_TEST_DETAILS
from iambic.aws.event_bridge.models import RoleMessageDetails
from iambic.aws.iam.role.models import RoleTemplate
from iambic.aws.iam.role.template_generation import generate_aws_role_templates
from iambic.core.context import ctx


class PartialImportRoleTestCase(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.template = await generate_role_template_from_base(
            IAMBIC_TEST_DETAILS.template_dir_path
        )
        self.role_name = self.template.properties.role_name
        self.all_account_ids = [
            account.account_id for account in IAMBIC_TEST_DETAILS.config.aws.accounts
        ]

    async def asyncTearDown(self):
        self.template.deleted = True
        await self.template.apply(IAMBIC_TEST_DETAILS.config, ctx)

    async def test_update_role_attribute(self):
        initial_description = "This was created by a functional test."
        updated_description = "Updated description."

        included_account = self.all_account_ids[0]
        self.template.included_accounts = [included_account]
        self.template.excluded_accounts = []
        self.template.properties.description = initial_description
        self.template.write()

        self.template.properties.description = updated_description

        # Confirm change was only in memory
        file_sys_template = RoleTemplate.load(self.template.file_path)
        self.assertEqual(file_sys_template.properties.description, initial_description)

        await self.template.apply(IAMBIC_TEST_DETAILS.config, ctx)

        await generate_aws_role_templates(
            [IAMBIC_TEST_DETAILS.config],
            IAMBIC_TEST_DETAILS.template_dir_path,
            [
                RoleMessageDetails(
                    account_id=included_account,
                    role_name=self.template.properties.role_name,
                    delete=False,
                )
            ],
        )

        file_sys_template = RoleTemplate.load(self.template.file_path)
        self.assertEqual(file_sys_template.properties.description, updated_description)

    async def test_delete_role_template(self):
        included_account = self.all_account_ids[0]
        self.template.included_accounts = [included_account]
        self.template.excluded_accounts = []
        self.template.write()

        self.assertTrue(os.path.exists(self.template.file_path))

        await generate_aws_role_templates(
            [IAMBIC_TEST_DETAILS.config],
            IAMBIC_TEST_DETAILS.template_dir_path,
            [
                RoleMessageDetails(
                    account_id=included_account,
                    role_name=self.template.properties.role_name,
                    delete=True,
                )
            ],
        )

        self.assertFalse(os.path.exists(self.template.file_path))

    async def test_delete_role_from_one_account(self):
        deleted_account = self.all_account_ids[0]
        self.template.included_accounts = ["*"]
        self.template.excluded_accounts = []
        self.template.write()

        # Create on all accounts except 1
        self.template.excluded_accounts = [deleted_account]

        # Confirm the change is only in memory and not on the file system
        file_sys_template = RoleTemplate.load(self.template.file_path)
        self.assertNotIn(deleted_account, file_sys_template.excluded_accounts)

        # Create the policy on all accounts except 1
        await self.template.apply(IAMBIC_TEST_DETAILS.config, ctx)

        # Refresh the template
        await generate_aws_role_templates(
            [IAMBIC_TEST_DETAILS.config],
            IAMBIC_TEST_DETAILS.template_dir_path,
            [
                RoleMessageDetails(
                    account_id=deleted_account,
                    role_name=self.template.properties.role_name,
                    delete=True,
                )
            ],
        )

        file_sys_template = RoleTemplate.load(self.template.file_path)
        self.assertEqual(file_sys_template.included_accounts, ["*"])
        self.assertEqual(file_sys_template.excluded_accounts, [deleted_account])
