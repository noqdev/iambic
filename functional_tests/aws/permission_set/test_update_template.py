from __future__ import annotations

import asyncio
from time import sleep
from unittest import IsolatedAsyncioTestCase

from functional_tests.aws.permission_set.utils import (
    generate_permission_set_template_from_base,
)
from functional_tests.conftest import IAMBIC_TEST_DETAILS
from iambic.core.context import ctx


class UpdatePermissionSetTestCase(IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = asyncio.run(
            generate_permission_set_template_from_base(
                IAMBIC_TEST_DETAILS.template_dir_path
            )
        )
        asyncio.run(cls.template.apply(IAMBIC_TEST_DETAILS.config.aws, ctx))
        sleep(5)
        asyncio.run(
            IAMBIC_TEST_DETAILS.identity_center_account.set_identity_center_details()
        )

    @classmethod
    def tearDownClass(cls):
        sleep(5)
        asyncio.run(
            IAMBIC_TEST_DETAILS.identity_center_account.set_identity_center_details()
        )
        cls.template.deleted = True
        asyncio.run(cls.template.apply(IAMBIC_TEST_DETAILS.config.aws, ctx))

    async def test_update_description(self):
        self.template.properties.description = "Updated description"
        await self.template.apply(IAMBIC_TEST_DETAILS.config.aws, ctx)
        await IAMBIC_TEST_DETAILS.identity_center_account.set_identity_center_details()

        self.assertEqual(
            self.template.properties.description,
            IAMBIC_TEST_DETAILS.identity_center_account.identity_center_details.permission_set_map[
                self.template.identifier
            ][
                "Description"
            ],
        )


class UpdatePermissionSetTestCaseWithBadInput(IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = asyncio.run(
            generate_permission_set_template_from_base(
                IAMBIC_TEST_DETAILS.template_dir_path
            )
        )
        asyncio.run(cls.template.apply(IAMBIC_TEST_DETAILS.config.aws, ctx))
        sleep(5)
        asyncio.run(
            IAMBIC_TEST_DETAILS.identity_center_account.set_identity_center_details()
        )

    @classmethod
    def tearDownClass(cls):
        sleep(5)
        asyncio.run(
            IAMBIC_TEST_DETAILS.identity_center_account.set_identity_center_details()
        )
        cls.template.deleted = True
        asyncio.run(cls.template.apply(IAMBIC_TEST_DETAILS.config.aws, ctx))

    async def test_update_description(self):
        self.template.properties.description = ""  # this does not trigger error because default validation only happens during creation
        template_change_details = await self.template.apply(
            IAMBIC_TEST_DETAILS.config.aws, ctx
        )
        self.assertEqual(len(template_change_details.exceptions_seen), 1)
