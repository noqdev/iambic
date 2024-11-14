from __future__ import annotations

import random
from unittest import IsolatedAsyncioTestCase

from functional_tests.conftest import IAMBIC_TEST_DETAILS

from iambic.plugins.v0_1_0.aws.models import Tag
from iambic.plugins.v0_1_0.aws.organizations.scp.models import PolicyTargetProperties

from .utils import generate_scp_policy_template_from_base


class UpdatePolicyTestCase(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.template = await generate_scp_policy_template_from_base(
            IAMBIC_TEST_DETAILS.template_dir_path, create_policy=True
        )
        self.policy_name = self.template.properties.policy_name
        self.path = self.template.properties.path
        self.all_account_ids = [
            account.account_id for account in IAMBIC_TEST_DETAILS.config.aws.accounts
        ]

        self.org_account = next(
            filter(
                lambda acc: acc.organization_account,
                IAMBIC_TEST_DETAILS.config.aws.accounts,
            )
        )

        self.org_client = await self.org_account.get_boto3_client("organizations")

        self.accounts = [
            acc
            for acc in IAMBIC_TEST_DETAILS.config.aws.accounts
            if acc.organization_account is False
        ]

    async def asyncTearDown(self):
        self.template.deleted = True
        await self.template.apply(IAMBIC_TEST_DETAILS.config.aws)

    async def test_update_policy_without_attachments(self):
        changes = await self.template.apply(IAMBIC_TEST_DETAILS.config.aws)
        self.assertEquals(len(changes.exceptions_seen), 0)
        current_policy = self.org_client.describe_policy(
            PolicyId=self.template.properties.policy_id
        )
        self.assertEquals(
            current_policy.get("Policy").get("PolicySummary").get("Name"),
            self.template.properties.policy_name,
        )
        self.assertEquals(
            current_policy.get("Policy").get("PolicySummary").get("Name"),
            self.template.identifier,
        )

    async def test_update_policy_with_targets(self):
        account = self.attach_account()

        changes = await self.template.apply(IAMBIC_TEST_DETAILS.config.aws)

        self.assertEquals(
            len(changes.exceptions_seen), 0, f"failed due to {changes.exceptions_seen}"
        )

        self.check_attach_accounts(account)

        # detach policy from account
        self.detach_account(account)

        changes = await self.template.apply(IAMBIC_TEST_DETAILS.config.aws)
        self.assertEquals(len(changes.exceptions_seen), 0)

        self.check_detach_account(account)

    async def test_update_policy_with_tags(self):
        tags = self.attach_tags()

        changes = await self.template.apply(IAMBIC_TEST_DETAILS.config.aws)

        self.assertEquals(len(changes.exceptions_seen), 0)

        self.check_attach_tags(tags)

        self.detach_tags(tags)

        changes = await self.template.apply(IAMBIC_TEST_DETAILS.config.aws)

        self.assertEquals(len(changes.exceptions_seen), 0)

        self.check_detach_tags(tags)

    async def test_update_policy_with_attachments(self):
        tags = self.attach_tags()
        account = self.attach_account()

        changes = await self.template.apply(IAMBIC_TEST_DETAILS.config.aws)

        self.assertEquals(len(changes.exceptions_seen), 0)

        self.check_attach_tags(tags)
        self.check_attach_accounts(account)

        self.detach_tags(tags)
        self.detach_account(account)

        changes = await self.template.apply(IAMBIC_TEST_DETAILS.config.aws)

        self.assertEquals(len(changes.exceptions_seen), 0)

        self.check_detach_tags(tags)
        self.check_detach_account(account)

    def check_detach_account(self, account):
        targets = self.org_client.list_targets_for_policy(
            PolicyId=self.template.properties.policy_id
        ).get("Targets")
        self.assertNotIn(
            account.account_id, [target.get("TargetId") for target in targets]
        )

    def detach_account(self, account):
        self.template.properties.targets.accounts.remove(account.account_id)

    def check_attach_accounts(self, account):
        targets = self.org_client.list_targets_for_policy(
            PolicyId=self.template.properties.policy_id
        ).get("Targets")

        self.assertIn(
            account.account_id, [target.get("TargetId") for target in targets]
        )

    def attach_account(self):
        account = random.choice(self.accounts)

        if not self.template.properties.targets:
            self.template.properties.targets = PolicyTargetProperties()

        self.template.properties.targets.accounts.append(account.account_id)
        return account

    def check_detach_tags(self, tags):
        listed_tags = self.org_client.list_tags_for_resource(
            ResourceId=self.template.properties.policy_id
        ).get("Tags")

        self.assertNotIn(tags[0].key, [tag.get("Key") for tag in listed_tags])

    def detach_tags(self, tags):
        self.template.properties.tags = [
            tag for tag in self.template.properties.tags if tag.key not in tags[0].key
        ]

    def check_attach_tags(self, tags):
        listed_tags = self.org_client.list_tags_for_resource(
            ResourceId=self.template.properties.policy_id
        ).get("Tags")

        self.assertIn(tags[0].key, [tag.get("Key") for tag in listed_tags])

    def attach_tags(self):
        tags = [
            Tag(key="functional_test_tag", value="value"),  # type: ignore
        ]

        self.template.properties.tags = tags
        return tags
