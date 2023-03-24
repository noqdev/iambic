from __future__ import annotations

from unittest import IsolatedAsyncioTestCase

from functional_tests.azure_ad.group.utils import generate_group_template
from functional_tests.conftest import IAMBIC_TEST_DETAILS
from iambic.core.context import ctx
from iambic.plugins.v0_1_0.azure_ad.group.utils import get_group


class CreateGroupTestCase(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.template = generate_group_template()
        self.group_name = self.template.properties.name
        self.org = IAMBIC_TEST_DETAILS.config.azure_ad.organizations[0]

    async def asyncTearDown(self):
        self.template.deleted = True
        await self.template.apply(IAMBIC_TEST_DETAILS.config.azure_ad, ctx)

    async def test_create_ms_365_group(self):
        await self.template.apply(IAMBIC_TEST_DETAILS.config.azure_ad, ctx)

        try:
            group = await get_group(self.org, group_name=self.group_name)
        except Exception as err:
            self.fail(f"Group was not created: {err}")

        group_members = [member.name for member in group.members]
        for member in self.template.properties.members:
            self.assertIn(member.name, group_members)

    async def test_create_security_group(self):
        self.template.properties.mail_enabled = False
        self.template.properties.members = []
        self.template.properties.group_types = []
        self.template.properties.security_enabled = True
        self.template.write(exclude_unset=False)

        changes = await self.template.apply(IAMBIC_TEST_DETAILS.config.azure_ad, ctx)
        self.assertEqual(len(changes.exceptions_seen), 0, changes.exceptions_seen)

        try:
            await get_group(self.org, group_name=self.group_name)
        except Exception as err:
            self.fail(f"Group was not created: {err}")

    async def test_attempt_create_mail_enabled_security_group(self):
        self.template.properties.group_types = []
        self.template.properties.security_enabled = True
        self.template.write(exclude_unset=False)

        changes = await self.template.apply(IAMBIC_TEST_DETAILS.config.azure_ad, ctx)
        self.assertGreaterEqual(len(changes.exceptions_seen), 1)

        # Should not exist
        with self.assertRaises(Exception):
            await get_group(self.org, group_name=self.group_name)
