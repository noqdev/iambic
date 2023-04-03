from __future__ import annotations

import asyncio
import datetime
from unittest import IsolatedAsyncioTestCase

from functional_tests.aws.permission_set.utils import generate_permission_set_template
from functional_tests.conftest import IAMBIC_TEST_DETAILS
from iambic.core import noq_json as json
from iambic.core.context import ctx
from iambic.core.models import ProposedChangeType
from iambic.output.text import screen_render_resource_changes
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
    async def asyncSetUp(self):
        self.template = await generate_permission_set_template(
            IAMBIC_TEST_DETAILS.template_dir_path,
            noise="update",
        )

        ctx.eval_only = False
        changes = await self.template.apply(IAMBIC_TEST_DETAILS.config.aws)
        assert changes.exceptions_seen in [None, []]

        # eventual consistency bites
        # after create, it does not mean we can immediate list it
        cur_attempt = 0
        max_attempts = 3
        while cur_attempt < max_attempts:
            cur_attempt += 1
            await IAMBIC_TEST_DETAILS.identity_center_account.set_identity_center_details(
                batch_size=5
            )
            if (
                self.template.identifier
                not in IAMBIC_TEST_DETAILS.identity_center_account.identity_center_details.permission_set_map
            ):
                asyncio.sleep(5)
            else:
                break

        assert (
            self.template.identifier
            in IAMBIC_TEST_DETAILS.identity_center_account.identity_center_details.permission_set_map
        )

    async def asyncTearDown(self):
        self.template.deleted = True
        await self.template.apply(IAMBIC_TEST_DETAILS.config.aws)

    async def test_update_description(self):
        timestamp = datetime.datetime.now().isoformat()
        updated_description = f"{timestamp}"
        assert self.template.properties.description != updated_description
        self.template.properties.description = updated_description
        changes = await self.template.apply(IAMBIC_TEST_DETAILS.config.aws)
        assert (
            changes.proposed_changes[0].proposed_changes[0].change_type
            == ProposedChangeType.UPDATE
        )
        assert changes.exceptions_seen in [None, []]

        identity_center_client = await IAMBIC_TEST_DETAILS.identity_center_account.get_boto3_client(
            "sso-admin",
            region_name=IAMBIC_TEST_DETAILS.identity_center_account.identity_center_details.region_name,
        )
        sso_admin_instance_arn = (
            IAMBIC_TEST_DETAILS.identity_center_account.identity_center_details.instance_arn
        )
        permission_set_arn = IAMBIC_TEST_DETAILS.identity_center_account.identity_center_details.permission_set_map[
            self.template.identifier
        ][
            "PermissionSetArn"
        ]
        response = identity_center_client.describe_permission_set(
            InstanceArn=sso_admin_instance_arn,
            PermissionSetArn=permission_set_arn,
        )

        self.assertEqual(
            self.template.properties.description,
            response["PermissionSet"]["Description"],
        )

        self.template.properties.description = ""  # this does not trigger error because default validation only happens during creation
        template_change_details = await self.template.apply(
            IAMBIC_TEST_DETAILS.config.aws
        )
        screen_render_resource_changes([template_change_details])
        self.assertEqual(
            len(template_change_details.exceptions_seen),
            1,
            json.dumps(template_change_details.dict()),
        )

    async def test_account_assignment(self):
        self.template.access_rules = [
            PermissionSetAccess(users=[EXAMPLE_USER], groups=[EXAMPLE_GROUP])
        ]
        changes = await self.template.apply(IAMBIC_TEST_DETAILS.config.aws)
        assert changes.exceptions_seen in [None, []]

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
        changes = await self.template.apply(IAMBIC_TEST_DETAILS.config.aws)
        screen_render_resource_changes([changes])
        cloud_access_rules = await get_permission_set_users_and_groups_as_access_rules(
            identity_center_client,
            IAMBIC_TEST_DETAILS.identity_center_account.identity_center_details.instance_arn,
            permission_set_arn,
            IAMBIC_TEST_DETAILS.identity_center_account.identity_center_details.user_map,
            IAMBIC_TEST_DETAILS.identity_center_account.identity_center_details.group_map,
            IAMBIC_TEST_DETAILS.identity_center_account.identity_center_details.org_account_map,
        )
        assert len(cloud_access_rules) == 0
