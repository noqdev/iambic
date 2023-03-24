from __future__ import annotations

from unittest import IsolatedAsyncioTestCase

from functional_tests.azure_ad.user.utils import generate_user_template
from functional_tests.conftest import IAMBIC_TEST_DETAILS

from iambic.core.context import ctx
from iambic.plugins.v0_1_0.azure_ad.user.utils import get_user


class CreateUserTestCase(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.template = generate_user_template()
        self.username = self.template.properties.username
        self.org = IAMBIC_TEST_DETAILS.config.azure_ad.organizations[0]

    async def asyncTearDown(self):
        self.template.deleted = True
        await self.template.apply(IAMBIC_TEST_DETAILS.config.azure_ad, ctx)

    async def test_create_user(self):
        changes = await self.template.apply(IAMBIC_TEST_DETAILS.config.azure_ad, ctx)
        self.assertEqual(len(changes.exceptions_seen), 0, changes.exceptions_seen)

        try:
            user = await get_user(self.org, username=self.username)
        except Exception as err:
            self.fail(f"User was not created but no exceptions in changes: {err}")

        self.assertEqual(user.username, self.username)
