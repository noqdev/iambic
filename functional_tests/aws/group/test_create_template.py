from __future__ import annotations

from unittest import IsolatedAsyncioTestCase

from functional_tests.aws.group.utils import generate_group_template_from_base
from functional_tests.aws.user.utils import get_modifiable_user
from functional_tests.conftest import IAMBIC_TEST_DETAILS

from iambic.output.text import screen_render_resource_changes
from iambic.plugins.v0_1_0.aws.iam.group.utils import get_group_across_accounts
from iambic.plugins.v0_1_0.aws.iam.user.utils import get_user_groups
from iambic.plugins.v0_1_0.aws.utils import boto_crud_call


class CreateGroupTestCase(IsolatedAsyncioTestCase):
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
        await self.template.apply(
            IAMBIC_TEST_DETAILS.config.aws,
        )

    async def test_create_group_all_accounts(self):
        self.template.included_accounts = ["*"]
        self.template.excluded_accounts = []

        changes = await self.template.apply(
            IAMBIC_TEST_DETAILS.config.aws,
        )
        screen_render_resource_changes([changes])

        account_group_mapping = await get_group_across_accounts(
            IAMBIC_TEST_DETAILS.config.aws.accounts, self.group_name, False
        )
        group_account_ids = [
            account_id for account_id, group in account_group_mapping.items() if group
        ]

        for account_id in group_account_ids:
            self.assertIn(
                account_id,
                self.all_account_ids,
                f"{account_id} not found for group {self.group_name}",
            )

    async def test_create_group_on_single_account(self):
        included_account = self.all_account_ids[0]
        self.template.included_accounts = [included_account]
        self.template.excluded_accounts = []

        changes = await self.template.apply(
            IAMBIC_TEST_DETAILS.config.aws,
        )
        screen_render_resource_changes([changes])

        account_group_mapping = await get_group_across_accounts(
            IAMBIC_TEST_DETAILS.config.aws.accounts, self.group_name, False
        )
        group_account_ids = [
            account_id for account_id, group in account_group_mapping.items() if group
        ]
        self.assertIn(
            included_account,
            group_account_ids,
            f"{included_account} not found for group {self.group_name}",
        )
        self.assertEqual(len(group_account_ids), 1)

    async def test_create_group_and_attach_to_user(self):
        included_account = self.all_account_ids[0]
        aws_account = [
            aws_account
            for aws_account in IAMBIC_TEST_DETAILS.config.aws.accounts
            if aws_account.account_id == included_account
        ][0]
        iam_client = await aws_account.get_boto3_client("iam")

        self.template.included_accounts = [included_account]
        self.template.excluded_accounts = []
        changes = await self.template.apply(
            IAMBIC_TEST_DETAILS.config.aws,
        )
        screen_render_resource_changes([changes])

        user = await get_modifiable_user(iam_client)
        user_name = user["UserName"]
        await boto_crud_call(
            iam_client.add_user_to_group, UserName=user_name, GroupName=self.group_name
        )

        user_groups = await get_user_groups(user_name, iam_client)
        self.assertIn(self.group_name, list(user_groups.keys()))
