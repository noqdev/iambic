from __future__ import annotations

from unittest import IsolatedAsyncioTestCase

from functional_tests.aws.managed_policy.utils import (
    generate_managed_policy_template_from_base,
)
from functional_tests.aws.role.utils import get_modifiable_role
from functional_tests.conftest import IAMBIC_TEST_DETAILS
from iambic.aws.iam.policy.utils import (
    get_managed_policy_across_accounts,
    get_managed_policy_attachments,
)
from iambic.core.context import ctx
from iambic.core.utils import aio_wrapper


class CreateManagedPolicyTestCase(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.template = await generate_managed_policy_template_from_base(
            IAMBIC_TEST_DETAILS.template_dir_path
        )
        self.policy_name = self.template.properties.policy_name
        self.path = self.template.properties.path
        self.all_account_ids = [
            account.account_id for account in IAMBIC_TEST_DETAILS.config.aws.accounts
        ]

    async def asyncTearDown(self):
        self.template.deleted = True
        await self.template.apply(IAMBIC_TEST_DETAILS.config, ctx)

    async def test_create_managed_policy_all_accounts(self):
        self.template.included_accounts = ["*"]
        self.template.excluded_accounts = []

        await self.template.apply(IAMBIC_TEST_DETAILS.config, ctx)

        account_mp_mapping = await get_managed_policy_across_accounts(
            IAMBIC_TEST_DETAILS.config.aws.accounts, self.path, self.policy_name
        )
        mp_account_ids = [
            account_id for account_id, mp in account_mp_mapping.items() if mp
        ]

        for account_id in mp_account_ids:
            self.assertIn(
                account_id,
                self.all_account_ids,
                f"{account_id} not found for managed policy {self.policy_name}",
            )

    async def test_create_managed_policy_on_single_account(self):
        included_account = self.all_account_ids[0]
        self.template.included_accounts = [included_account]
        self.template.excluded_accounts = []

        await self.template.apply(IAMBIC_TEST_DETAILS.config, ctx)

        account_mp_mapping = await get_managed_policy_across_accounts(
            IAMBIC_TEST_DETAILS.config.aws.accounts, self.path, self.policy_name
        )
        mp_account_ids = [
            account_id for account_id, mp in account_mp_mapping.items() if mp
        ]
        self.assertIn(
            included_account,
            mp_account_ids,
            f"{included_account} not found for role {self.policy_name}",
        )
        self.assertEqual(len(mp_account_ids), 1)

    async def test_create_managed_policy_and_attach_to_role(self):
        included_account = self.all_account_ids[0]
        aws_account = [
            aws_account
            for aws_account in IAMBIC_TEST_DETAILS.config.aws.accounts
            if aws_account.account_id == included_account
        ][0]
        iam_client = await aws_account.get_boto3_client("iam")

        self.template.included_accounts = [included_account]
        self.template.excluded_accounts = []
        await self.template.apply(IAMBIC_TEST_DETAILS.config, ctx)

        role = await get_modifiable_role(iam_client)
        role_name = role["RoleName"]
        policy_arn = self.template.get_arn_for_account(aws_account)

        await aio_wrapper(
            iam_client.attach_role_policy, RoleName=role_name, PolicyArn=policy_arn
        )

        policy_attachments = await get_managed_policy_attachments(
            iam_client, policy_arn
        )
        attached_roles = [
            attachment["RoleName"] for attachment in policy_attachments["PolicyRoles"]
        ]

        self.assertIn(
            role_name,
            attached_roles,
            f"{role_name} not found in attached roles {attached_roles} for policy {self.policy_name}",
        )
