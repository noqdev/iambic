from __future__ import annotations

import os.path
from datetime import datetime, timedelta, timezone
from unittest import IsolatedAsyncioTestCase

from functional_tests.aws.managed_policy.utils import (
    generate_managed_policy_template_from_base,
)
from functional_tests.conftest import IAMBIC_TEST_DETAILS

from iambic.plugins.v0_1_0.aws.iam.policy.models import ManagedPolicyTemplate
from iambic.plugins.v0_1_0.aws.utils import remove_expired_resources


class ManagedPolicyExpirationTestCase(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.template = await generate_managed_policy_template_from_base(
            IAMBIC_TEST_DETAILS.template_dir_path
        )

    async def asyncTearDown(self):
        if os.path.exists(self.template.file_path):
            os.remove(self.template.file_path)

    async def test_expire_managed_policy_statement(self):
        expected_statement_count = len(
            self.template.properties.policy_document.statement
        )
        self.template.properties.policy_document.statement.append(
            self.template.properties.policy_document.statement[0]
        )
        self.template.properties.policy_document.statement[0].expires_at = datetime.now(
            timezone.utc
        ) - timedelta(days=1)
        self.template.write()

        file_sys_template = ManagedPolicyTemplate.load(self.template.file_path)
        self.assertEqual(
            len(file_sys_template.properties.policy_document.statement),
            expected_statement_count + 1,
            "Expired Statement was not added to the template.",
        )

        await remove_expired_resources(
            self.template, self.template.resource_type, self.template.resource_id
        )
        self.template.write()

        file_sys_template = ManagedPolicyTemplate.load(self.template.file_path)
        self.assertEqual(
            len(file_sys_template.properties.policy_document.statement),
            expected_statement_count,
            "Expired Statement was not removed from the template.",
        )

    async def test_expire_managed_policy_template(self):
        self.template.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
        self.template.write()

        self.assertFalse(self.template.deleted)
        await remove_expired_resources(
            self.template, self.template.resource_type, self.template.resource_id
        )
        self.assertTrue(self.template.deleted)
