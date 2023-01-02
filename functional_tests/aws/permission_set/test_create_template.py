from __future__ import annotations

import asyncio
from unittest import IsolatedAsyncioTestCase

from functional_tests.aws.permission_set.utils import (
    attach_access_rule,
    generate_permission_set_template_from_base,
)
from functional_tests.conftest import IAMBIC_TEST_DETAILS
from iambic.core.context import ctx


class CreatePermissionSetTestCase(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.template = await generate_permission_set_template_from_base(
            IAMBIC_TEST_DETAILS.template_dir_path
        )

    async def asyncTearDown(self):
        await asyncio.sleep(5)
        await IAMBIC_TEST_DETAILS.sso_account.set_sso_details()
        self.template.deleted = True
        await self.template.apply(IAMBIC_TEST_DETAILS.config, ctx)

    async def test_create_permission_set(self):
        await self.template.apply(IAMBIC_TEST_DETAILS.config, ctx)
        await IAMBIC_TEST_DETAILS.sso_account.set_sso_details()

        self.assertIn(
            self.template.identifier,
            IAMBIC_TEST_DETAILS.sso_account.sso_details.permission_set_map,
        )

    async def test_create_permission_set_with_account_assignment(self):
        self.template = attach_access_rule(
            self.template, IAMBIC_TEST_DETAILS.sso_account
        )
        await self.template.apply(IAMBIC_TEST_DETAILS.config, ctx)
        await IAMBIC_TEST_DETAILS.sso_account.set_sso_details()

        self.assertIn(
            self.template.identifier,
            IAMBIC_TEST_DETAILS.sso_account.sso_details.permission_set_map,
        )

        # TODO: Validate account assignments with response of get_permission_set_users_and_groups
