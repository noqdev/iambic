from __future__ import annotations

import asyncio
from unittest import IsolatedAsyncioTestCase

import dateparser

from functional_tests.aws.role.utils import generate_role_template_from_base
from functional_tests.conftest import IAMBIC_TEST_DETAILS
from iambic.output.text import screen_render_resource_changes
from iambic.plugins.v0_1_0.aws.iam.policy.models import ManagedPolicyRef, PolicyDocument
from iambic.plugins.v0_1_0.aws.iam.role.models import (
    AwsIamRoleTemplate,
    PermissionBoundary,
)
from iambic.plugins.v0_1_0.aws.iam.role.utils import get_role_across_accounts
from iambic.plugins.v0_1_0.aws.models import Tag
from iambic.request_handler.expire_resources import flag_expired_resources


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
        asyncio.run(cls.template.apply(IAMBIC_TEST_DETAILS.config.aws))

    @classmethod
    def tearDownClass(cls):
        cls.template.deleted = True
        asyncio.run(cls.template.apply(IAMBIC_TEST_DETAILS.config.aws))

    # empty tag string value is a valid input
    async def test_update_tag_with_empty_string(self):
        self.template.properties.tags = [Tag(key="test", value="")]
        changes = await self.template.apply(IAMBIC_TEST_DETAILS.config.aws)
        screen_render_resource_changes([changes])

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

    # tag None string value is not acceptable
    async def test_update_tag_with_bad_input(self):
        self.template.properties.description = "{0}_bad_input".format(
            self.template.properties.description
        )  # good input
        self.template.properties.tags = [Tag(key="*", value="")]  # bad input
        try:
            template_change_details = await self.template.apply(
                IAMBIC_TEST_DETAILS.config.aws
            )
            screen_render_resource_changes([template_change_details])
        except Exception as e:
            # because it should still crash
            # FIXME check assert here
            print(e)

        assert len(template_change_details.proposed_changes) > 0
        assert len(template_change_details.exceptions_seen) > 0

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

        # Check tags was NOT updated across all accounts the role is on
        for account_id, role in account_role_mapping.items():
            if role:
                self.assertNotIn(
                    "Tags",
                    role,
                    f"{account_id} should not have tags for role {self.role_name}",
                )

    async def test_update_description(self):
        self.template.properties.description = "Updated description"
        changes = await self.template.apply(IAMBIC_TEST_DETAILS.config.aws)
        screen_render_resource_changes([changes])

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

    async def test_update_permission_boundary(self):
        view_policy_arn = "arn:aws:iam::aws:policy/job-function/ViewOnlyAccess"
        self.template.properties.permissions_boundary = PermissionBoundary(
            policy_arn=view_policy_arn
        )
        changes = await self.template.apply(IAMBIC_TEST_DETAILS.config.aws)
        screen_render_resource_changes([changes])

        account_role_mapping = await get_role_across_accounts(
            IAMBIC_TEST_DETAILS.config.aws.accounts, self.role_name, False
        )

        # Check description was updated across all accounts the role is on
        for account_id, role in account_role_mapping.items():
            if role:
                self.assertEqual(
                    self.template.properties.permissions_boundary.policy_arn,
                    role["PermissionsBoundary"]["PermissionsBoundaryArn"],
                    f"{account_id} has invalid permission boundary for role {self.role_name}",
                )

    async def test_update_managed_policies(self):
        if self.template.properties.managed_policies:
            self.template.properties.managed_policies = []
            changes = await self.template.apply(IAMBIC_TEST_DETAILS.config.aws)
            screen_render_resource_changes([changes])

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
        await self.template.apply(IAMBIC_TEST_DETAILS.config.aws)

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
        changes = await self.template.apply(IAMBIC_TEST_DETAILS.config.aws)
        screen_render_resource_changes([changes])

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
        template_changes = await self.template.apply(IAMBIC_TEST_DETAILS.config.aws)
        screen_render_resource_changes([template_changes])
        self.assertEqual(len(template_changes.proposed_changes), 2)

        # Set expiration
        self.template.properties.inline_policies[1].statement[
            0
        ].expires_at = dateparser.parse(
            "yesterday", settings={"TIMEZONE": "UTC", "RETURN_AS_TIMEZONE_AWARE": True}
        )
        self.template.write()
        await flag_expired_resources([self.template.file_path])
        template = AwsIamRoleTemplate.load(self.template.file_path)

        template_changes = await template.apply(IAMBIC_TEST_DETAILS.config.aws)
        screen_render_resource_changes([template_changes])
        self.assertEqual(len(template_changes.proposed_changes), 1)

    async def test_replace_max_size_inline_policy(self):
        # Check that replacing policies won't fail due to size limits
        policy_statement = [
            {
                "action": [f"s3:NotARealAction{x}" for x in range(350)],
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
