from __future__ import annotations

import asyncio
from unittest import IsolatedAsyncioTestCase

from functional_tests.aws.role.utils import generate_role_template_from_base
from functional_tests.conftest import IAMBIC_TEST_DETAILS
from iambic.aws.iam.policy.models import ManagedPolicyRef
from iambic.aws.iam.role.utils import get_role_across_accounts
from iambic.core.context import ctx


class UpdateRoleTestCase(IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = asyncio.run(
            generate_role_template_from_base(IAMBIC_TEST_DETAILS.template_dir_path)
        )
        cls.role_name = cls.template.properties.role_name
        cls.all_account_ids = [
            account.account_id for account in IAMBIC_TEST_DETAILS.config.aws.accounts
        ]
        # Only include the template in half the accounts
        # Make the accounts explicit so it's easier to validate account scoped tests
        cls.template.included_accounts = cls.all_account_ids[
            : len(cls.all_account_ids) // 2
        ]
        asyncio.run(cls.template.apply(IAMBIC_TEST_DETAILS.config, ctx))

    @classmethod
    def tearDownClass(cls):
        cls.template.deleted = True
        asyncio.run(cls.template.apply(IAMBIC_TEST_DETAILS.config, ctx))

    async def test_update_description(self):
        self.template.properties.description = "Updated description"
        await self.template.apply(IAMBIC_TEST_DETAILS.config, ctx)

        account_role_mapping = await get_role_across_accounts(
            IAMBIC_TEST_DETAILS.config.aws.accounts, self.role_name, False
        )

        # Check description was updated across all accounts the role is on
        for account_id, role in account_role_mapping.items():
            if role:
                self.assertEqual(
                    self.template.properties.description,
                    role["Description"],
                    f"{account_id} has invalid description for role {self.role_name}",
                )

    async def test_update_managed_policies(self):
        if self.template.properties.managed_policies:
            self.template.properties.managed_policies = []
            await self.template.apply(IAMBIC_TEST_DETAILS.config, ctx)

            account_role_mapping = await get_role_across_accounts(
                IAMBIC_TEST_DETAILS.config.aws.accounts,
                self.role_name,
            )

            for account_id, role in account_role_mapping.items():
                if role:
                    self.assertFalse(
                        bool(role["ManagedPolicies"]),
                        f"{account_id} still has managed policies "
                        f"{role['ManagedPolicies']} attached to it for role {self.role_name}",
                    )

        policy_arn = "arn:aws:iam::aws:policy/job-function/ViewOnlyAccess"
        self.template.properties.managed_policies = [
            ManagedPolicyRef(policy_arn=policy_arn)
        ]
        await self.template.apply(IAMBIC_TEST_DETAILS.config, ctx)

        account_role_mapping = await get_role_across_accounts(
            IAMBIC_TEST_DETAILS.config.aws.accounts,
            self.role_name,
        )

        for account_id, role in account_role_mapping.items():
            if role:
                self.assertIn(
                    policy_arn,
                    [policy["PolicyArn"] for policy in role["ManagedPolicies"]],
                    f"{account_id} missing managed policy for role {self.role_name}",
                )

        self.template.properties.managed_policies = []
        await self.template.apply(IAMBIC_TEST_DETAILS.config, ctx)

        account_role_mapping = await get_role_across_accounts(
            IAMBIC_TEST_DETAILS.config.aws.accounts,
            self.role_name,
        )

        for account_id, role in account_role_mapping.items():
            if role:
                self.assertFalse(
                    bool(role["ManagedPolicies"]),
                    f"{account_id} still has managed policies "
                    f"{role['ManagedPolicies']} attached to it for role {self.role_name}",
                )
