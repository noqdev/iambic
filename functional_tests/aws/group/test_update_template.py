from __future__ import annotations

import asyncio
from unittest import IsolatedAsyncioTestCase

import dateparser
from functional_tests.aws.group.utils import generate_group_template_from_base
from functional_tests.conftest import IAMBIC_TEST_DETAILS

from iambic.output.text import screen_render_resource_changes
from iambic.plugins.v0_1_0.aws.iam.group.models import AwsIamGroupTemplate
from iambic.plugins.v0_1_0.aws.iam.group.utils import get_group_across_accounts
from iambic.plugins.v0_1_0.aws.iam.policy.models import ManagedPolicyRef, PolicyDocument
from iambic.request_handler.expire_resources import flag_expired_resources


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
        asyncio.run(cls.template.apply(IAMBIC_TEST_DETAILS.config.aws))

    @classmethod
    def tearDownClass(cls):
        cls.template.deleted = True
        asyncio.run(cls.template.apply(IAMBIC_TEST_DETAILS.config.aws))

    async def test_update_managed_policies(self):
        if self.template.properties.managed_policies:
            self.template.properties.managed_policies = []
            await self.template.apply(IAMBIC_TEST_DETAILS.config.aws)

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
        changes = await self.template.apply(IAMBIC_TEST_DETAILS.config.aws)
        screen_render_resource_changes([changes])

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
        changes = await self.template.apply(IAMBIC_TEST_DETAILS.config.aws)
        screen_render_resource_changes([changes])

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

        await self.template.apply(IAMBIC_TEST_DETAILS.config.aws)

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
        template_changes = await self.template.apply(IAMBIC_TEST_DETAILS.config.aws)
        screen_render_resource_changes(([template_changes]))
        self.assertEqual(len(template_changes.proposed_changes), 2)

        # Set expiration
        self.template.properties.inline_policies[1].statement[
            0
        ].expires_at = dateparser.parse(
            "yesterday", settings={"TIMEZONE": "UTC", "RETURN_AS_TIMEZONE_AWARE": True}
        )
        self.template.write()
        await flag_expired_resources(
            [self.template.file_path], IAMBIC_TEST_DETAILS.config.aws.template_map
        )
        template = AwsIamGroupTemplate.load(self.template.file_path)

        template_changes = await template.apply(IAMBIC_TEST_DETAILS.config.aws)
        screen_render_resource_changes(([template_changes]))
        self.assertEqual(len(template_changes.proposed_changes), 1)

    async def test_replace_max_size_inline_policy(self):
        # Check that replacing policies won't fail due to size limits
        policy_statement = [
            {
                "action": [f"s3:NotARealAction{x}" for x in range(175)],
                "effect": "Deny",
                "resource": ["*"],
            },
        ]

        self.template.properties.inline_policies.append(
            PolicyDocument(policy_name="init_policy", statement=policy_statement)
        )
        results = await self.template.apply(IAMBIC_TEST_DETAILS.config.aws)
        self.assertFalse(bool(results.exceptions_seen))
        self.assertTrue(bool(results.proposed_changes))

        self.template.properties.inline_policies = [
            PolicyDocument(policy_name="replace_policy", statement=policy_statement)
        ]
        results = await self.template.apply(IAMBIC_TEST_DETAILS.config.aws)
        self.assertFalse(bool(results.exceptions_seen))


class UpdateGroupBadInputTestCase(IsolatedAsyncioTestCase):
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
        asyncio.run(cls.template.apply(IAMBIC_TEST_DETAILS.config.aws))

    @classmethod
    def tearDownClass(cls):
        cls.template.deleted = True
        asyncio.run(cls.template.apply(IAMBIC_TEST_DETAILS.config.aws))

    async def test_bad_input(self):
        self.template.included_accounts = ["*"]
        self.template.excluded_accounts = []

        await self.template.apply(IAMBIC_TEST_DETAILS.config.aws)

        account_group_mapping = await get_group_across_accounts(
            IAMBIC_TEST_DETAILS.config.aws.accounts, self.group_name, False
        )
        group_account_ids = [
            account_id for account_id, group in account_group_mapping.items() if group
        ]

        self.template.properties.inline_policies.append(
            PolicyDocument(
                included_accounts=[group_account_ids[0], group_account_ids[1]],
                expires_at="tomorrow",
                policy_name="test_policy",
                statement=[
                    {
                        "action": ["s3:NotARealAction"],
                        "effect": "BAD_INPUT",
                        "resource": ["*"],
                        "expires_at": "tomorrow",
                        "included_accounts": [group_account_ids[0]],
                    },
                    {
                        "action": ["s3:AlsoNotARealAction"],
                        "effect": "BAD_INPUT",
                        "resource": ["*"],
                        "expires_at": "tomorrow",
                    },
                ],
            )
        )
        r = await self.template.apply(IAMBIC_TEST_DETAILS.config.aws)
        screen_render_resource_changes(([r]))
        self.assertEqual(len(r.exceptions_seen), 2)
