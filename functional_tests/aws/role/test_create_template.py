from __future__ import annotations

from unittest import IsolatedAsyncioTestCase

from functional_tests.aws.role.utils import generate_role_template_from_base
from functional_tests.conftest import IAMBIC_TEST_DETAILS

from iambic.output.text import screen_render_resource_changes
from iambic.plugins.v0_1_0.aws.iam.role.utils import get_role_across_accounts


class CreateRoleTestCase(IsolatedAsyncioTestCase):
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
        await self.template.apply(IAMBIC_TEST_DETAILS.config.aws)

    async def test_create_role_all_accounts(self):
        self.template.included_accounts = ["*"]
        self.template.excluded_accounts = []

        changes = await self.template.apply(IAMBIC_TEST_DETAILS.config.aws)
        screen_render_resource_changes([changes])

        account_role_mapping = await get_role_across_accounts(
            IAMBIC_TEST_DETAILS.config.aws.accounts, self.role_name, False
        )
        role_account_ids = [
            account_id for account_id, role in account_role_mapping.items() if role
        ]

        for account_id in role_account_ids:
            self.assertIn(
                account_id,
                self.all_account_ids,
                f"{account_id} not found for role {self.role_name}",
            )

    async def test_create_role_on_single_account(self):
        included_account = self.all_account_ids[0]
        self.template.included_accounts = [included_account]
        self.template.excluded_accounts = []

        changes = await self.template.apply(IAMBIC_TEST_DETAILS.config.aws)
        screen_render_resource_changes([changes])

        account_role_mapping = await get_role_across_accounts(
            IAMBIC_TEST_DETAILS.config.aws.accounts, self.role_name, False
        )
        role_account_ids = [
            account_id for account_id, role in account_role_mapping.items() if role
        ]
        self.assertIn(
            included_account,
            role_account_ids,
            f"{included_account} not found for role {self.role_name}",
        )
        self.assertEqual(len(role_account_ids), 1)
