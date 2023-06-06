from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from unittest import IsolatedAsyncioTestCase

from functional_tests.aws.organizations.scp.utils import generate_policy_template
from functional_tests.conftest import IAMBIC_TEST_DETAILS

from iambic.core.models import ProposedChangeType
from iambic.core.utils import remove_expired_resources
from iambic.plugins.v0_1_0.aws.organizations.scp.models import AwsScpPolicyTemplate
from iambic.plugins.v0_1_0.aws.organizations.scp.template_generation import (
    get_template_dir,
)


class ExpirationPolicyTestCase(IsolatedAsyncioTestCase):
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

    async def test_expire_policy_template(self):
        template = await generate_policy_template(
            IAMBIC_TEST_DETAILS.template_dir_path,
            self.org_account,
        )  #

        template.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
        template.write()

        self.assertFalse(template.deleted)
        await remove_expired_resources(
            template, template.resource_type, template.resource_id
        )
        self.assertTrue(template.deleted)

    async def test_delete_policy(self):
        template = await generate_policy_template(
            IAMBIC_TEST_DETAILS.template_dir_path,
            self.org_account,
        )  #

        template.write()

        changes = await template.apply(IAMBIC_TEST_DETAILS.config.aws)

        template.deleted = True
        template.write()

        changes = await template.apply(IAMBIC_TEST_DETAILS.config.aws)

        self.assertFalse(changes.proposed_changes[0].exceptions_seen)
        self.assertFalse(os.path.exists(template.file_path))

        self.assertEquals(
            changes.proposed_changes[0].proposed_changes[0].change_type,
            ProposedChangeType.DELETE,
        )
