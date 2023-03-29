from __future__ import annotations

import os.path
from unittest import IsolatedAsyncioTestCase

from functional_tests.aws.managed_policy.utils import (
    generate_managed_policy_template_from_base,
    managed_policy_full_import,
)
from functional_tests.conftest import IAMBIC_TEST_DETAILS
from iambic.output.text import screen_render_resource_changes
from iambic.plugins.v0_1_0.aws.event_bridge.models import ManagedPolicyMessageDetails
from iambic.plugins.v0_1_0.aws.iam.policy.models import AwsIamManagedPolicyTemplate


class PartialImportManagedPolicyTestCase(IsolatedAsyncioTestCase):
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
        await self.template.apply(IAMBIC_TEST_DETAILS.config.aws)

    async def test_update_managed_policy_attribute(self):
        initial_description = "This was created by a functional test."
        updated_description = "Updated description."

        included_account = self.all_account_ids[0]
        self.template.included_accounts = [included_account]
        self.template.excluded_accounts = []
        self.template.properties.description = initial_description
        self.template.write()

        self.template.properties.description = updated_description
        changes = await self.template.apply(IAMBIC_TEST_DETAILS.config.aws)
        screen_render_resource_changes([changes])

        file_sys_template = AwsIamManagedPolicyTemplate.load(self.template.file_path)
        self.assertEqual(file_sys_template.properties.description, initial_description)

        await managed_policy_full_import(
            [
                ManagedPolicyMessageDetails(
                    account_id=included_account,
                    policy_path=self.template.properties.path,
                    policy_name=self.template.properties.policy_name,
                    delete=False,
                )
            ]
        )

        file_sys_template = AwsIamManagedPolicyTemplate.load(self.template.file_path)
        self.assertEqual(file_sys_template.properties.description, updated_description)

    async def test_delete_managed_policy_template(self):
        included_account = self.all_account_ids[0]
        self.template.included_accounts = [included_account]
        self.template.excluded_accounts = []
        self.template.write()

        self.assertTrue(os.path.exists(self.template.file_path))

        await managed_policy_full_import(
            [
                ManagedPolicyMessageDetails(
                    account_id=included_account,
                    policy_path=self.template.properties.path,
                    policy_name=self.template.properties.policy_name,
                    delete=True,
                )
            ]
        )
        self.assertFalse(os.path.exists(self.template.file_path))

    async def test_delete_managed_policy_from_one_account(self):
        deleted_account = self.all_account_ids[0]
        deleted_account_obj = [
            aws_account
            for aws_account in IAMBIC_TEST_DETAILS.config.aws.accounts
            if aws_account.account_id == deleted_account
        ][0]
        self.template.included_accounts = ["*"]
        self.template.excluded_accounts = []
        self.template.write()

        # Create on all accounts except 1
        self.template.excluded_accounts = [deleted_account]

        # Confirm the change is only in memory and not on the file system
        file_sys_template = AwsIamManagedPolicyTemplate.load(self.template.file_path)
        self.assertNotIn(deleted_account, file_sys_template.excluded_accounts)

        # Create the policy on all accounts except 1
        changes = await self.template.apply(IAMBIC_TEST_DETAILS.config.aws)
        screen_render_resource_changes([changes])

        # Refresh the template
        await managed_policy_full_import(
            [
                ManagedPolicyMessageDetails(
                    account_id=deleted_account,
                    policy_path=self.template.properties.path,
                    policy_name=self.template.properties.policy_name,
                    delete=True,
                )
            ]
        )

        file_sys_template = AwsIamManagedPolicyTemplate.load(self.template.file_path)
        self.assertEqual(file_sys_template.included_accounts, ["*"])
        self.assertEqual(
            file_sys_template.excluded_accounts, [deleted_account_obj.account_name]
        )
