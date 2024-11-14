from __future__ import annotations

from unittest import IsolatedAsyncioTestCase

from functional_tests.conftest import IAMBIC_TEST_DETAILS

from iambic.core.models import ProposedChangeType
from iambic.plugins.v0_1_0.aws.models import Tag
from iambic.plugins.v0_1_0.aws.organizations.scp.models import (
    AwsScpPolicyTemplate,
    PolicyTargetProperties,
)
from iambic.plugins.v0_1_0.aws.organizations.scp.template_generation import (
    get_template_dir,
)

from .utils import generate_policy_template


class CreatePolicyTestCase(IsolatedAsyncioTestCase):
    templates: list[AwsScpPolicyTemplate] = []

    async def asyncSetUp(self):
        self.policy_dir = get_template_dir(IAMBIC_TEST_DETAILS.template_dir_path)

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
        for template in self.templates:
            template.deleted = True
            await template.apply(IAMBIC_TEST_DETAILS.config.aws)

    async def test_create_template(self):
        client = self.org_client
        policy_template = await generate_policy_template(
            IAMBIC_TEST_DETAILS.template_dir_path,
            self.org_account,
        )  # type: ignore

        policy_template.write()

        changes = await policy_template.apply(IAMBIC_TEST_DETAILS.config.aws)

        self.check_no_exception_seen(changes)

        policy_template = AwsScpPolicyTemplate.load(str(policy_template.file_path))

        policy = (
            client.describe_policy(PolicyId=policy_template.properties.policy_id)
            .get("Policy")
            .get("PolicySummary")
        )

        self.check_policy_changes(policy_template, policy)

        self.templates.append(policy_template)

    async def test_create_template_with_targets(self):
        client = self.org_client
        policy_template = await generate_policy_template(
            IAMBIC_TEST_DETAILS.template_dir_path,
            self.org_account,
        )  # type: ignore

        if not policy_template.properties.targets:
            policy_template.properties.targets = PolicyTargetProperties()  # type: ignore

        policy_template.properties.targets.accounts += [
            account.account_id for account in self.accounts
        ]

        policy_template.write()

        changes = await policy_template.apply(IAMBIC_TEST_DETAILS.config.aws)

        self.check_no_exception_seen(changes)

        policy_template = AwsScpPolicyTemplate.load(str(policy_template.file_path))

        policy = (
            client.describe_policy(PolicyId=policy_template.properties.policy_id)
            .get("Policy")
            .get("PolicySummary")
        )

        self.check_policy_changes(policy_template, policy)
        self.check_targets(policy_template, IAMBIC_TEST_DETAILS.config.aws.accounts)

        self.templates.append(policy_template)

    async def test_create_template_with_tags_and_targets(self):
        client = self.org_client
        policy_template = await generate_policy_template(
            IAMBIC_TEST_DETAILS.template_dir_path,
            self.org_account,
        )  # type: ignore

        if not policy_template.properties.targets:
            policy_template.properties.targets = PolicyTargetProperties()  # type: ignore

        policy_template.properties.targets.accounts += [
            account.account_id for account in self.accounts
        ]

        if not policy_template.properties.tags:
            policy_template.properties.tags = []

        policy_template.properties.tags += [
            Tag(key="created_by", value="functional_test")  # type: ignore
        ]

        policy_template.write()

        changes = await policy_template.apply(IAMBIC_TEST_DETAILS.config.aws)

        self.check_no_exception_seen(changes)

        policy_template = AwsScpPolicyTemplate.load(str(policy_template.file_path))

        policy = (
            client.describe_policy(PolicyId=policy_template.properties.policy_id)
            .get("Policy")
            .get("PolicySummary")
        )

        self.check_policy_changes(policy_template, policy)
        self.check_targets(policy_template, IAMBIC_TEST_DETAILS.config.aws.accounts)
        self.check_tags(policy_template)

        self.templates.append(policy_template)

    def check_policy_changes(self, policy_template, policy):
        self.assertEquals(policy.get("Name"), policy_template.properties.policy_name)
        self.assertEquals(
            policy.get("Description"), policy_template.properties.description
        )

    def check_no_exception_seen(self, changes):
        self.assertEquals(len(changes.exceptions_seen), 0)
        self.assertEquals(
            changes.proposed_changes[0].proposed_changes[0].change_type,
            ProposedChangeType.CREATE,
        )

    def check_targets(self, template, accounts):
        account_ids = sorted([account.account_id for account in self.accounts])

        targets = self.org_client.list_targets_for_policy(
            PolicyId=template.properties.policy_id
        ).get("Targets")

        self.assertEquals(
            sorted([target.get("TargetId") for target in targets]), account_ids
        )

    def check_tags(self, template):
        listed_tags = self.org_client.list_tags_for_resource(
            ResourceId=template.properties.policy_id
        ).get("Tags")

        self.assertIn("created_by", [tag.get("Key") for tag in listed_tags])
