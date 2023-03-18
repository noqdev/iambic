from __future__ import annotations

import asyncio
from unittest import IsolatedAsyncioTestCase

import dateparser
from functional_tests.aws.user.utils import generate_user_template_from_base
from functional_tests.conftest import IAMBIC_TEST_DETAILS

from iambic.core import noq_json as json
from iambic.core.context import ctx
from iambic.plugins.v0_1_0.aws.iam.models import PermissionBoundary
from iambic.plugins.v0_1_0.aws.iam.policy.models import ManagedPolicyRef, PolicyDocument
from iambic.plugins.v0_1_0.aws.iam.user.utils import get_user_across_accounts
from iambic.plugins.v0_1_0.aws.models import Tag


class UpdateUserTestCase(IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = asyncio.run(
            generate_user_template_from_base(IAMBIC_TEST_DETAILS.template_dir_path)
        )
        cls.user_name = cls.template.properties.user_name
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

    # tag None string value is not acceptable
    async def test_update_tag_with_bad_input(self):
        self.template.properties.path = "/engineering/"  # good input
        self.template.properties.tags = [Tag(key="*", value="")]  # bad input
        template_change_details = await self.template.apply(
            IAMBIC_TEST_DETAILS.config.aws, ctx
        )

        self.assertGreater(
            len(template_change_details.proposed_changes),
            0,
            f"No proposed changes: {json.dumps(template_change_details.dict())}",
        )
        self.assertGreater(
            len(template_change_details.exceptions_seen),
            0,
            f"No exceptions seen: {json.dumps(template_change_details.dict())}",
        )

    async def test_update_permission_boundary(self):
        view_policy_arn = "arn:aws:iam::aws:policy/job-function/ViewOnlyAccess"
        self.template.properties.permissions_boundary = PermissionBoundary(
            policy_arn=view_policy_arn
        )
        await self.template.apply(IAMBIC_TEST_DETAILS.config.aws, ctx)

        account_user_mapping = await get_user_across_accounts(
            IAMBIC_TEST_DETAILS.config.aws.accounts, self.user_name, False
        )

        # Check description was updated across all accounts the role is on
        for account_id, user in account_user_mapping.items():
            if user:
                self.assertEqual(
                    self.template.properties.permissions_boundary.policy_arn,
                    user["PermissionsBoundary"]["PermissionsBoundaryArn"],
                    f"{account_id} has invalid permission boundary for role {self.user_name}",
                )

    async def test_update_managed_policies(self):
        if self.template.properties.managed_policies:
            self.template.properties.managed_policies = []
            await self.template.apply(IAMBIC_TEST_DETAILS.config.aws, ctx)

            account_user_mapping = await get_user_across_accounts(
                IAMBIC_TEST_DETAILS.config.aws.accounts,
                self.user_name,
            )

            for account_id, user in account_user_mapping.items():
                if user:
                    self.assertFalse(
                        bool(user["ManagedPolicies"]),
                        f"{account_id} still has managed policies "
                        f"{user['ManagedPolicies']} attached to it for user {self.user_name}",
                    )

        policy_arn = "arn:aws:iam::aws:policy/job-function/ViewOnlyAccess"
        self.template.properties.managed_policies = [
            ManagedPolicyRef(policy_arn=policy_arn)
        ]
        await self.template.apply(IAMBIC_TEST_DETAILS.config.aws, ctx)

        account_user_mapping = await get_user_across_accounts(
            IAMBIC_TEST_DETAILS.config.aws.accounts,
            self.user_name,
        )

        for account_id, user in account_user_mapping.items():
            if user:
                self.assertIn(
                    policy_arn,
                    [policy["PolicyArn"] for policy in user["ManagedPolicies"]],
                    f"{account_id} missing managed policy for user {self.user_name}",
                )

        self.template.properties.managed_policies = []
        await self.template.apply(IAMBIC_TEST_DETAILS.config.aws, ctx)

        account_user_mapping = await get_user_across_accounts(
            IAMBIC_TEST_DETAILS.config.aws.accounts,
            self.user_name,
        )

        for account_id, user in account_user_mapping.items():
            if user:
                self.assertFalse(
                    bool(user["ManagedPolicies"]),
                    f"{account_id} still has managed policies "
                    f"{user['ManagedPolicies']} attached to it for user {self.user_name}",
                )

    async def test_create_update_user_all_accounts(self):
        self.template.included_accounts = ["*"]
        self.template.excluded_accounts = []

        await self.template.apply(IAMBIC_TEST_DETAILS.config.aws, ctx)

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

        self.template.properties.inline_policies.append(
            PolicyDocument(
                included_accounts=[user_account_ids[0], user_account_ids[1]],
                expires_at="tomorrow",
                policy_name="test_policy",
                statement=[
                    {
                        "action": ["s3:NotARealAction"],
                        "effect": "Deny",
                        "resource": ["*"],
                        "expires_at": "tomorrow",
                        "included_accounts": [user_account_ids[0]],
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
