from __future__ import annotations

from unittest import IsolatedAsyncioTestCase

from functional_tests.aws.user.utils import generate_user_template_from_base
from functional_tests.conftest import IAMBIC_TEST_DETAILS
from iambic.plugins.v0_1_0.aws.iam.user.utils import get_user_across_accounts


class CreateUserTestCase(IsolatedAsyncioTestCase):
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
        await self.template.apply(IAMBIC_TEST_DETAILS.config.aws)

    async def test_create_user_all_accounts(self):
        self.template.included_accounts = ["*"]
        self.template.excluded_accounts = []

        await self.template.apply(IAMBIC_TEST_DETAILS.config.aws)

        account_user_mapping = await get_user_across_accounts(
            IAMBIC_TEST_DETAILS.config.aws.accounts, self.user_name, False
        )
        user_account_ids = [
            account_id for account_id, user in account_user_mapping.items() if user
        ]

        for account_id in user_account_ids:
            self.assertIn(
                account_id,
                self.all_account_ids,
                f"{account_id} not found for user {self.user_name}",
            )

    async def test_create_user_on_single_account(self):
        included_account = self.all_account_ids[0]
        self.template.included_accounts = [included_account]
        self.template.excluded_accounts = []

        await self.template.apply(IAMBIC_TEST_DETAILS.config.aws)

        account_user_mapping = await get_user_across_accounts(
            IAMBIC_TEST_DETAILS.config.aws.accounts, self.user_name, False
        )
        user_account_ids = [
            account_id for account_id, user in account_user_mapping.items() if user
        ]
        self.assertIn(
            included_account,
            user_account_ids,
            f"{included_account} not found for user {self.user_name}",
        )
        self.assertEqual(len(user_account_ids), 1)
