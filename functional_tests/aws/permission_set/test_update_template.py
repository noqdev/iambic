from __future__ import annotations

import asyncio
from time import sleep
from unittest import IsolatedAsyncioTestCase

from functional_tests.aws.permission_set.utils import (
    generate_permission_set_template_from_base,
)
from functional_tests.conftest import IAMBIC_TEST_DETAILS
from iambic.core import noq_json as json
from iambic.plugins.v0_1_0.aws.identity_center.permission_set.models import (
    PermissionSetAccess,
)
from iambic.plugins.v0_1_0.aws.identity_center.permission_set.utils import (
    get_permission_set_users_and_groups_as_access_rules,
)

EXAMPLE_GROUP = "iambic_test_group"  # this already exist in target cloud resource
EXAMPLE_USER = (
    "iambic_test_user@iambic.org"  # this already exist in target cloud resource
)


class UpdatePermissionSetTestCase(IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = asyncio.run(
            generate_permission_set_template_from_base(
                IAMBIC_TEST_DETAILS.template_dir_path
            )
        )
        asyncio.run(cls.template.apply(IAMBIC_TEST_DETAILS.config.aws))
        sleep(5)
        asyncio.run(
            IAMBIC_TEST_DETAILS.identity_center_account.set_identity_center_details(
                batch_size=5
            )
        )

    @classmethod
    def tearDownClass(cls):
        sleep(5)
        cls.template.deleted = True
        asyncio.run(cls.template.apply(IAMBIC_TEST_DETAILS.config.aws))
        sleep(5)
        asyncio.run(
            IAMBIC_TEST_DETAILS.identity_center_account.set_identity_center_details(
                batch_size=5
            )
        )

    async def test_update_description(self):
        self.template.properties.description = "Updated description"
        await self.template.apply(IAMBIC_TEST_DETAILS.config.aws)
        await IAMBIC_TEST_DETAILS.identity_center_account.set_identity_center_details(
            batch_size=5
        )

        self.assertEqual(
            self.template.properties.description,
            IAMBIC_TEST_DETAILS.identity_center_account.identity_center_details.permission_set_map[
                self.template.identifier
            ][
                "Description"
            ],
        )

    async def test_account_assignment(self):
        self.template.access_rules = [
            PermissionSetAccess(users=[EXAMPLE_USER], groups=[EXAMPLE_GROUP])
        ]
        await self.template.apply(IAMBIC_TEST_DETAILS.config.aws)
        await IAMBIC_TEST_DETAILS.identity_center_account.set_identity_center_details(
            batch_size=5
        )

        # test assignment

        identity_center_client = await IAMBIC_TEST_DETAILS.identity_center_account.get_boto3_client(
            "sso-admin",
            region_name=IAMBIC_TEST_DETAILS.identity_center_account.identity_center_details.region_name,
        )
        permission_set_arn = IAMBIC_TEST_DETAILS.identity_center_account.identity_center_details.permission_set_map[
            self.template.identifier
        ][
            "PermissionSetArn"
        ]
        cloud_access_rules = await get_permission_set_users_and_groups_as_access_rules(
            identity_center_client,
            IAMBIC_TEST_DETAILS.identity_center_account.identity_center_details.instance_arn,
            permission_set_arn,
            IAMBIC_TEST_DETAILS.identity_center_account.identity_center_details.user_map,
            IAMBIC_TEST_DETAILS.identity_center_account.identity_center_details.group_map,
            IAMBIC_TEST_DETAILS.identity_center_account.identity_center_details.org_account_map,
        )
        assert len(cloud_access_rules) > 0

        # test un-assignment
        self.template.access_rules = []
        await self.template.apply(IAMBIC_TEST_DETAILS.config.aws)
        cloud_access_rules = await get_permission_set_users_and_groups_as_access_rules(
            identity_center_client,
            IAMBIC_TEST_DETAILS.identity_center_account.identity_center_details.instance_arn,
            permission_set_arn,
            IAMBIC_TEST_DETAILS.identity_center_account.identity_center_details.user_map,
            IAMBIC_TEST_DETAILS.identity_center_account.identity_center_details.group_map,
            IAMBIC_TEST_DETAILS.identity_center_account.identity_center_details.org_account_map,
        )
        assert len(cloud_access_rules) == 0


class UpdatePermissionSetTestCaseWithBadInput(IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = asyncio.run(
            generate_permission_set_template_from_base(
                IAMBIC_TEST_DETAILS.template_dir_path
            )
        )
        asyncio.run(cls.template.apply(IAMBIC_TEST_DETAILS.config.aws))
        sleep(5)
        asyncio.run(
            IAMBIC_TEST_DETAILS.identity_center_account.set_identity_center_details(
                batch_size=5
            )
        )

    @classmethod
    def tearDownClass(cls):
        sleep(5)
        asyncio.run(
            IAMBIC_TEST_DETAILS.identity_center_account.set_identity_center_details(
                batch_size=5
            )
        )
        cls.template.deleted = True
        asyncio.run(cls.template.apply(IAMBIC_TEST_DETAILS.config.aws))

    async def test_update_description(self):
        self.template.properties.description = ""  # this does not trigger error because default validation only happens during creation
        template_change_details = await self.template.apply(
            IAMBIC_TEST_DETAILS.config.aws
        )
        self.assertEqual(
            len(template_change_details.exceptions_seen),
            1,
            json.dumps(template_change_details.dict()),
        )
