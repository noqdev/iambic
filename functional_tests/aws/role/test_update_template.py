from __future__ import annotations

import asyncio
from unittest import IsolatedAsyncioTestCase

import dateparser

from functional_tests.aws.role.utils import generate_role_template_from_base
from functional_tests.conftest import IAMBIC_TEST_DETAILS
from iambic.core.context import ctx
from iambic.plugins.v0_1_0.aws.iam.policy.models import ManagedPolicyRef, PolicyDocument
from iambic.plugins.v0_1_0.aws.iam.role.utils import get_role_across_accounts
from iambic.plugins.v0_1_0.aws.models import Tag


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
        asyncio.run(cls.template.apply(IAMBIC_TEST_DETAILS.config.aws, ctx))

    @classmethod
    def tearDownClass(cls):
        cls.template.deleted = True
        asyncio.run(cls.template.apply(IAMBIC_TEST_DETAILS.config.aws, ctx))

    async def test_update_tag(self):
        self.template.properties.tags = [Tag(key="test", value="")]
        await self.template.apply(IAMBIC_TEST_DETAILS.config.aws, ctx)

        account_role_mapping = await get_role_across_accounts(
            IAMBIC_TEST_DETAILS.config.aws.accounts, self.role_name, False
        )

        # Check description was updated across all accounts the role is on
        for account_id, role in account_role_mapping.items():
            if role:
                self.assertEqual(
                    self.template.properties.tags[0].key,
                    role["Tags"][0]["Key"],
                    f"{account_id} has invalid tag key for role {self.role_name}",
                )
                self.assertEqual(
                    self.template.properties.tags[0].value,
                    role["Tags"][0]["Value"],
                    f"{account_id} has invalid tag key for role {self.role_name}",
                )

    async def test_update_description(self):
        self.template.properties.description = "Updated description"
        await self.template.apply(IAMBIC_TEST_DETAILS.config.aws, ctx)

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
            await self.template.apply(IAMBIC_TEST_DETAILS.config.aws, ctx)

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
        await self.template.apply(IAMBIC_TEST_DETAILS.config.aws, ctx)

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
        await self.template.apply(IAMBIC_TEST_DETAILS.config.aws, ctx)

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

    async def test_create_update_role_all_accounts(self):
        self.template.included_accounts = ["*"]
        self.template.excluded_accounts = []

        await self.template.apply(IAMBIC_TEST_DETAILS.config.aws, ctx)

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

        self.template.properties.inline_policies.append(
            PolicyDocument(
                included_accounts=[role_account_ids[0], role_account_ids[1]],
                expires_at="tomorrow",
                policy_name="test_policy",
                statement=[
                    {
                        "action": ["s3:NotARealAction"],
                        "effect": "Deny",
                        "resource": ["*"],
                        "expires_at": "tomorrow",
                        "included_accounts": [role_account_ids[0]],
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
