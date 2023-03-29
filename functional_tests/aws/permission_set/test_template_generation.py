from __future__ import annotations

import asyncio
import os
from unittest import IsolatedAsyncioTestCase

from functional_tests.aws.permission_set.utils import (
    generate_permission_set_template_from_base,
    permission_set_full_import,
)
from functional_tests.conftest import IAMBIC_TEST_DETAILS

from iambic.plugins.v0_1_0.aws.event_bridge.models import PermissionSetMessageDetails
from iambic.plugins.v0_1_0.aws.identity_center.permission_set.models import (
    AwsIdentityCenterPermissionSetTemplate,
)


class PartialImportPermissionSetTestCase(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.template = await generate_permission_set_template_from_base(
            IAMBIC_TEST_DETAILS.template_dir_path
        )

    async def asyncTearDown(self):
        self.template.deleted = True
        await self.template.apply(IAMBIC_TEST_DETAILS.config.aws)

    async def test_update_permission_set_attribute(self):
        initial_description = "This was created by a functional test."
        updated_description = "Updated description."

        self.template.properties.description = initial_description
        self.template.write()

        self.template.properties.description = updated_description
        # Confirm template on disk has not been updated
        file_sys_template = AwsIdentityCenterPermissionSetTemplate.load(
            self.template.file_path
        )
        self.assertEqual(file_sys_template.properties.description, initial_description)

        await self.template.apply(IAMBIC_TEST_DETAILS.config.aws)
        await asyncio.sleep(5)
        await IAMBIC_TEST_DETAILS.identity_center_account.set_identity_center_details()

        identity_center_account = IAMBIC_TEST_DETAILS.identity_center_account
        identity_center_details = identity_center_account.identity_center_details

        permission_set_properties = identity_center_details.permission_set_map.get(
            self.template.properties.name
        )

        await permission_set_full_import(
            [
                PermissionSetMessageDetails(
                    account_id=identity_center_account.account_id,
                    instance_arn=identity_center_details.instance_arn,
                    permission_set_arn=permission_set_properties.get(
                        "PermissionSetArn"
                    ),
                )
            ]
        )

        file_sys_template = AwsIdentityCenterPermissionSetTemplate.load(
            self.template.file_path
        )
        self.assertEqual(file_sys_template.properties.description, updated_description)

    async def test_delete_permission_set_template(self):
        self.template.write()

        self.assertTrue(os.path.exists(self.template.file_path))

        await permission_set_full_import()

        self.assertFalse(os.path.exists(self.template.file_path))
