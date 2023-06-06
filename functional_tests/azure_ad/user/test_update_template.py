from __future__ import annotations

import asyncio
from unittest import IsolatedAsyncioTestCase

from functional_tests.azure_ad.user.utils import generate_user_template
from functional_tests.conftest import IAMBIC_TEST_DETAILS

from iambic.plugins.v0_1_0.azure_ad.user.utils import get_user


class UpdateUserTestCase(IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = generate_user_template()
        cls.username = cls.template.properties.username
        cls.org = IAMBIC_TEST_DETAILS.config.azure_ad.organizations[0]
        asyncio.run(cls.template.apply(IAMBIC_TEST_DETAILS.config.azure_ad))

    @classmethod
    def tearDownClass(cls):
        cls.template.deleted = True
        asyncio.run(cls.template.apply(IAMBIC_TEST_DETAILS.config.azure_ad))

    async def test_update_given_name(self):
        self.template.properties.given_name = "Updated Given Name"
        await self.template.apply(IAMBIC_TEST_DETAILS.config.azure_ad)

        try:
            user = await get_user(self.org, username=self.username)
        except Exception as err:
            self.fail(f"Unable to retrieve User: {err}")

        self.assertEqual(
            self.template.properties.given_name,
            user.given_name,
            "given_name was not updated",
        )
