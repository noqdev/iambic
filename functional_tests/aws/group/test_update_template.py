from __future__ import annotations

import asyncio
from unittest import IsolatedAsyncioTestCase

import dateparser

from functional_tests.aws.group.utils import generate_group_template_from_base
from functional_tests.conftest import IAMBIC_TEST_DETAILS
from iambic.core.context import ctx
from iambic.plugins.v0_1_0.aws.iam.group.utils import get_group_across_accounts
from iambic.plugins.v0_1_0.aws.iam.policy.models import ManagedPolicyRef, PolicyDocument


class UpdateGroupTestCase(IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = asyncio.run(
            generate_group_template_from_base(IAMBIC_TEST_DETAILS.template_dir_path)
        )
        cls.group_name = cls.template.properties.group_name
        cls.all_account_ids = [
            account.account_id for account in IAMBIC_TEST_DETAILS.config.aws.accounts
        ]
        # Only include the template in half the accounts
        # Make the accounts explicit so it's easier to validate account scoped tests
        cls.template.included_accounts = cls.all_account_ids[
            : len(cls.all_account_ids) // 2
        ]
        asyncio.run(cls.template.apply(IAMBIC_TEST_DETAILS.config.aws, ctx))

    @classmethod
    def tearDownClass(cls):
        cls.template.deleted = True
        asyncio.run(cls.template.apply(IAMBIC_TEST_DETAILS.config.aws, ctx))

    async def test_update_managed_policies(self):
        if self.template.properties.managed_policies:
            self.template.properties.managed_policies = []
            await self.template.apply(IAMBIC_TEST_DETAILS.config.aws, ctx)

            account_group_mapping = await get_group_across_accounts(
                IAMBIC_TEST_DETAILS.config.aws.accounts,
                self.group_name,
            )

            for account_id, group in account_group_mapping.items():
                if group:
                    self.assertFalse(
                        bool(group["ManagedPolicies"]),
                        f"{account_id} still has managed policies "
                        f"{group['ManagedPolicies']} attached to it for group {self.group_name}",
                    )

        policy_arn = "arn:aws:iam::aws:policy/job-function/ViewOnlyAccess"
        self.template.properties.managed_policies = [
            ManagedPolicyRef(policy_arn=policy_arn)
        ]
        await self.template.apply(IAMBIC_TEST_DETAILS.config.aws, ctx)

        account_group_mapping = await get_group_across_accounts(
            IAMBIC_TEST_DETAILS.config.aws.accounts,
            self.group_name,
        )

        for account_id, group in account_group_mapping.items():
            if group:
                self.assertIn(
                    policy_arn,
                    [policy["PolicyArn"] for policy in group["ManagedPolicies"]],
                    f"{account_id} missing managed policy for group {self.group_name}",
                )

        self.template.properties.managed_policies = []
        await self.template.apply(IAMBIC_TEST_DETAILS.config.aws, ctx)

        account_group_mapping = await get_group_across_accounts(
            IAMBIC_TEST_DETAILS.config.aws.accounts,
            self.group_name,
        )

        for account_id, group in account_group_mapping.items():
            if group:
                self.assertFalse(
                    bool(group["ManagedPolicies"]),
                    f"{account_id} still has managed policies "
                    f"{group['ManagedPolicies']} attached to it for group {self.group_name}",
                )

    async def test_create_update_group_all_accounts(self):
        self.template.included_accounts = ["*"]
        self.template.excluded_accounts = []

        await self.template.apply(IAMBIC_TEST_DETAILS.config.aws, ctx)

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

        self.template.properties.inline_policies.append(
            PolicyDocument(
                included_accounts=[group_account_ids[0], group_account_ids[1]],
                expires_at="tomorrow",
                policy_name="test_policy",
                statement=[
                    {
                        "action": ["s3:NotARealAction"],
                        "effect": "Deny",
                        "resource": ["*"],
                        "expires_at": "tomorrow",
                        "included_accounts": [group_account_ids[0]],
                    },
                    {
                        "action": ["s3:AlsoNotARealAction"],
                        "effect": "Deny",
                        "resource": ["*"],
                        "expires_at": "tomorrow",
                    },
                ],
            )
        )
        r = await self.template.apply(IAMBIC_TEST_DETAILS.config.aws, ctx)
        self.assertEqual(len(r.proposed_changes), 2)

        # Set expiration
        self.template.properties.inline_policies[1].statement[
            0
        ].expires_at = dateparser.parse(
            "yesterday", settings={"TIMEZONE": "UTC", "RETURN_AS_TIMEZONE_AWARE": True}
        )
        r = await self.template.apply(IAMBIC_TEST_DETAILS.config.aws, ctx)
        self.assertEqual(len(r.proposed_changes), 1)
