from __future__ import annotations

import asyncio
import secrets
import uuid
from unittest import IsolatedAsyncioTestCase

import dateparser

from functional_tests.aws.user.utils import generate_user_template_from_base
from functional_tests.conftest import IAMBIC_TEST_DETAILS
from iambic.core import noq_json as json
from iambic.core.iambic_enum import Command
from iambic.core.logger import log
from iambic.core.models import ExecutionMessage
from iambic.core.template_generation import (
    get_existing_template_map,
    templatize_resource,
)
from iambic.output.text import screen_render_resource_changes
from iambic.plugins.v0_1_0.aws.event_bridge.models import UserMessageDetails
from iambic.plugins.v0_1_0.aws.iam.models import PermissionBoundary
from iambic.plugins.v0_1_0.aws.iam.policy.models import ManagedPolicyRef, PolicyDocument
from iambic.plugins.v0_1_0.aws.iam.user.models import (
    AWS_IAM_USER_TEMPLATE_TYPE,
    AwsIamUserTemplate,
)
from iambic.plugins.v0_1_0.aws.iam.user.template_generation import (
    collect_aws_users,
    generate_aws_user_templates,
)
from iambic.plugins.v0_1_0.aws.iam.user.utils import get_user_across_accounts
from iambic.plugins.v0_1_0.aws.models import AWSAccount, Tag
from iambic.plugins.v0_1_0.aws.utils import boto_crud_call, get_aws_account_map
from iambic.request_handler.expire_resources import flag_expired_resources


class UpdateUserTestCase(IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = asyncio.run(
            generate_user_template_from_base(IAMBIC_TEST_DETAILS.template_dir_path)
        )
        cls.user_name = cls.template.properties.user_name
        cls.all_account_ids = [
            account.account_id for account in IAMBIC_TEST_DETAILS.config.aws.accounts
        ]
        # Only include the template in half the accounts
        # Make the accounts explicit so it's easier to validate account scoped tests
        cls.template.included_accounts = cls.all_account_ids[
            : len(cls.all_account_ids) // 2
        ]
        asyncio.run(cls.template.apply(IAMBIC_TEST_DETAILS.config.aws))

    @classmethod
    def tearDownClass(cls):
        cls.template.deleted = True
        asyncio.run(cls.template.apply(IAMBIC_TEST_DETAILS.config.aws))

    # tag None string value is not acceptable
    async def test_update_tag_with_bad_input(self):
        self.template.properties.path = "/engineering/"  # good input
        self.template.properties.tags = [
            Tag(key="a", value=""),
            Tag(key="a", value=""),
        ]  # bad input because you cannot have repeating tag
        template_change_details = await self.template.apply(
            IAMBIC_TEST_DETAILS.config.aws
        )

        self.assertGreater(
            len(template_change_details.proposed_changes),
            0,
            f"No proposed changes: {json.dumps(template_change_details.dict())}",
        )
        self.assertGreater(
            len(template_change_details.exceptions_seen),
            0,
            f"No exceptions seen: {json.dumps(template_change_details.dict())}",
        )

    async def test_update_permission_boundary(self):
        view_policy_arn = "arn:aws:iam::aws:policy/job-function/ViewOnlyAccess"
        self.template.properties.permissions_boundary = PermissionBoundary(
            policy_arn=view_policy_arn
        )
        await self.template.apply(IAMBIC_TEST_DETAILS.config.aws)

        account_user_mapping = await get_user_across_accounts(
            IAMBIC_TEST_DETAILS.config.aws.accounts, self.user_name, False
        )

        # Check description was updated across all accounts the role is on
        for account_id, user in account_user_mapping.items():
            if user:
                self.assertEqual(
                    self.template.properties.permissions_boundary.policy_arn,
                    user["PermissionsBoundary"]["PermissionsBoundaryArn"],
                    f"{account_id} has invalid permission boundary for role {self.user_name}",
                )

    async def test_update_managed_policies(self):
        if self.template.properties.managed_policies:
            self.template.properties.managed_policies = []
            await self.template.apply(IAMBIC_TEST_DETAILS.config.aws)

            account_user_mapping = await get_user_across_accounts(
                IAMBIC_TEST_DETAILS.config.aws.accounts,
                self.user_name,
            )

            for account_id, user in account_user_mapping.items():
                if user:
                    self.assertFalse(
                        bool(user["ManagedPolicies"]),
                        f"{account_id} still has managed policies "
                        f"{user['ManagedPolicies']} attached to it for user {self.user_name}",
                    )

        policy_arn = "arn:aws:iam::aws:policy/job-function/ViewOnlyAccess"
        self.template.properties.managed_policies = [
            ManagedPolicyRef(policy_arn=policy_arn)
        ]
        await self.template.apply(IAMBIC_TEST_DETAILS.config.aws)

        account_user_mapping = await get_user_across_accounts(
            IAMBIC_TEST_DETAILS.config.aws.accounts,
            self.user_name,
        )

        for account_id, user in account_user_mapping.items():
            if user:
                self.assertIn(
                    policy_arn,
                    [policy["PolicyArn"] for policy in user["ManagedPolicies"]],
                    f"{account_id} missing managed policy for user {self.user_name}",
                )

        self.template.properties.managed_policies = []
        await self.template.apply(IAMBIC_TEST_DETAILS.config.aws)

        account_user_mapping = await get_user_across_accounts(
            IAMBIC_TEST_DETAILS.config.aws.accounts,
            self.user_name,
        )

        for account_id, user in account_user_mapping.items():
            if user:
                self.assertFalse(
                    bool(user["ManagedPolicies"]),
                    f"{account_id} still has managed policies "
                    f"{user['ManagedPolicies']} attached to it for user {self.user_name}",
                )

    async def test_create_update_user_all_accounts(self):
        self.template.included_accounts = ["*"]
        self.template.excluded_accounts = []

        await self.template.apply(IAMBIC_TEST_DETAILS.config.aws)

        account_user_mapping = await get_user_across_accounts(
            IAMBIC_TEST_DETAILS.config.aws.accounts, self.user_name, False
        )
        user_account_ids = [
            account_id for account_id, user in account_user_mapping.items() if user
        ]

        for account_id in user_account_ids:
            self.assertIn(
                account_id,
                self.all_account_ids,
                f"{account_id} not found for user {self.user_name}",
            )

        self.template.properties.inline_policies.append(
            PolicyDocument(
                included_accounts=[user_account_ids[0], user_account_ids[1]],
                expires_at="tomorrow",
                policy_name="test_policy",
                statement=[
                    {
                        "action": ["s3:NotARealAction"],
                        "effect": "Deny",
                        "resource": ["*"],
                        "expires_at": "tomorrow",
                        "included_accounts": [user_account_ids[0]],
                    },
                    {
                        "action": ["s3:AlsoNotARealAction"],
                        "effect": "Deny",
                        "resource": ["*"],
                        "expires_at": "tomorrow",
                    },
                ],
            )
        )
        template_changes = await self.template.apply(IAMBIC_TEST_DETAILS.config.aws)
        screen_render_resource_changes([template_changes])
        self.assertEqual(len(template_changes.proposed_changes), 2)

        # Set expiration
        self.template.properties.inline_policies[1].statement[
            0
        ].expires_at = dateparser.parse(
            "yesterday", settings={"TIMEZONE": "UTC", "RETURN_AS_TIMEZONE_AWARE": True}
        )
        self.template.write()

        await flag_expired_resources(
            [self.template.file_path], IAMBIC_TEST_DETAILS.config.aws.template_map
        )
        template = AwsIamUserTemplate.load(self.template.file_path)

        template_changes = await template.apply(IAMBIC_TEST_DETAILS.config.aws)
        screen_render_resource_changes([template_changes])
        self.assertEqual(len(template_changes.proposed_changes), 1)

    async def test_replace_max_size_inline_policy(self):
        # Check that replacing policies won't fail due to size limits
        policy_statement = [
            {
                "action": [f"s3:NotARealAction{x}" for x in range(75)],
                "effect": "Deny",
                "resource": ["*"],
            },
        ]

        self.template.properties.inline_policies.append(
            PolicyDocument(policy_name="init_policy", statement=policy_statement)
        )
        results = await self.template.apply(IAMBIC_TEST_DETAILS.config.aws)
        self.assertFalse(bool(results.exceptions_seen))
        self.assertTrue(bool(results.proposed_changes))

        self.template.properties.inline_policies = [
            PolicyDocument(policy_name="replace_policy", statement=policy_statement)
        ]
        results = await self.template.apply(IAMBIC_TEST_DETAILS.config.aws)
        self.assertFalse(bool(results.exceptions_seen))


class UpdateUserCredentialTestCase(IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = asyncio.run(
            generate_user_template_from_base(IAMBIC_TEST_DETAILS.template_dir_path)
        )
        cls.template.properties.managed_policies = []
        cls.template.properties.inline_policies = [
            {
                "action": ["*"],
                "effect": "Deny",
                "resource": ["*"],
            }
        ]
        cls.user_name = cls.template.properties.user_name
        cls.all_account_ids = [
            account.account_id for account in IAMBIC_TEST_DETAILS.config.aws.accounts
        ]
        # Only include the template in half the accounts
        # Make the accounts explicit so it's easier to validate account scoped tests
        cls.template.included_accounts = cls.all_account_ids[
            : max(len(cls.all_account_ids) // 2, 2)
        ]
        asyncio.run(cls.template.apply(IAMBIC_TEST_DETAILS.config.aws))
        cls.aws_account_map = asyncio.run(
            get_aws_account_map(IAMBIC_TEST_DETAILS.config.aws)
        )
        cls.included_account_map = {
            account_id: cls.aws_account_map[account_id]
            for account_id in cls.template.included_accounts
        }
        cls.iam_user_template_map = asyncio.run(
            get_existing_template_map(
                repo_dir=IAMBIC_TEST_DETAILS.template_dir_path,
                template_type=AWS_IAM_USER_TEMPLATE_TYPE,
                template_map=IAMBIC_TEST_DETAILS.config.aws.template_map,
                nested=True,
            )
        )

    async def asyncSetUp(self):
        await self.refresh_template()  # Ensure template state is correct

    @classmethod
    def tearDownClass(cls):
        cls.template.deleted = True
        asyncio.run(cls.template.apply(IAMBIC_TEST_DETAILS.config.aws))

    def set_enable_iam_user_credentials(self, enable_iam_user_credentials: bool):
        IAMBIC_TEST_DETAILS.config.aws.enable_iam_user_credentials = (
            enable_iam_user_credentials
        )
        for account in IAMBIC_TEST_DETAILS.config.aws.accounts:
            account.enable_iam_user_credentials = enable_iam_user_credentials

        for account in self.included_account_map.values():
            account.enable_iam_user_credentials = enable_iam_user_credentials

        for account in self.aws_account_map.values():
            account.enable_iam_user_credentials = enable_iam_user_credentials

    async def refresh_template(self):
        # Need to trigger an IAMbic import for the user.
        # It's just the easiest way to try update the template
        aws_account = list(self.included_account_map.values())[0]
        templatized_user_name = templatize_resource(aws_account, self.user_name)
        exe_message = ExecutionMessage(
            execution_id=str(uuid.uuid4()), command=Command.IMPORT, provider_type="aws"
        )
        user_messages = [
            UserMessageDetails(
                account_id=aws_account.account_id,
                user_name=templatized_user_name,
                delete=False,
            )
        ]
        await collect_aws_users(
            exe_message,
            IAMBIC_TEST_DETAILS.config.aws,
            self.iam_user_template_map,
            detect_messages=user_messages,
        )
        await generate_aws_user_templates(
            exe_message,
            IAMBIC_TEST_DETAILS.config.aws,
            IAMBIC_TEST_DETAILS.template_dir_path,
            self.iam_user_template_map,
            detect_messages=user_messages,
        )
        self.template = AwsIamUserTemplate.load(self.template.file_path)

    async def set_user_password(self):
        user_password = secrets.token_urlsafe(nbytes=32)

        async def _update_or_create_user_password(aws_account: AWSAccount):
            client = await aws_account.get_boto3_client("iam")
            boto_kwargs = dict(
                UserName=self.user_name,
                Password=user_password,
                PasswordResetRequired=True,
            )
            try:
                await boto_crud_call(
                    client.update_login_profile,
                    retryable_errors=["EntityTemporarilyUnmodifiableException"],
                    **boto_kwargs,
                )
            except:  # noqa: E722
                try:
                    await boto_crud_call(client.create_login_profile, **boto_kwargs)
                except:  # noqa: E722
                    # to make sure boto_kwargs do not get accidentally print out because
                    # it contains password materials.
                    log.error(
                        "something update_login_profile and create_login_profile crash"
                    )
                    raise RuntimeError(
                        "something update_login_profile and create_login_profile crash"
                    )

        # Really gross but need to avoid EntityTemporarilyUnmodifiable error
        await asyncio.sleep(15)
        await asyncio.gather(
            *[
                _update_or_create_user_password(aws_account)
                for aws_account in self.included_account_map.values()
            ]
        )

        # Really gross but need to avoid EntityTemporarilyUnmodifiable error
        await asyncio.sleep(15)
        await self.refresh_template()

    async def set_user_access_key(self):
        await asyncio.gather(
            *[
                boto_crud_call(
                    (await aws_account.get_boto3_client("iam")).create_access_key,
                    UserName=self.user_name,
                )
                for aws_account in self.included_account_map.values()
            ]
        )

        await asyncio.sleep(15)  # Really gross but need to wait for change to propagate
        await self.refresh_template()

    async def delete_user_access_keys(self):
        async def _delete_user_access_keys(aws_account: AWSAccount):
            client = await aws_account.get_boto3_client("iam")
            access_keys = await boto_crud_call(
                client.list_access_keys, UserName=self.user_name
            )
            await asyncio.gather(
                *[
                    boto_crud_call(
                        client.delete_access_key,
                        UserName=self.user_name,
                        AccessKeyId=access_key["AccessKeyId"],
                    )
                    for access_key in access_keys["AccessKeyMetadata"]
                ]
            )

        await asyncio.gather(
            *[
                _delete_user_access_keys(aws_account)
                for aws_account in self.included_account_map.values()
            ]
        )
        await asyncio.sleep(15)  # Really gross but need to wait for change to propagate

    async def flip_user_access_keys_status(self):
        async def _flip_user_access_keys_status(aws_account: AWSAccount):
            client = await aws_account.get_boto3_client("iam")
            access_keys = await boto_crud_call(
                client.list_access_keys, UserName=self.user_name
            )
            await asyncio.gather(
                *[
                    boto_crud_call(
                        client.update_access_key,
                        UserName=self.user_name,
                        AccessKeyId=access_key["AccessKeyId"],
                        Status="Inactive"
                        if access_key["Status"] == "Active"
                        else "Active",
                    )
                    for access_key in access_keys["AccessKeyMetadata"]
                ]
            )

        await asyncio.gather(
            *[
                _flip_user_access_keys_status(aws_account)
                for aws_account in self.included_account_map.values()
            ]
        )
        await asyncio.sleep(15)  # Really gross but need to wait for change to propagate

    async def test_set_password_disabled(self):
        """
        Test the ability to disable a users password
        """
        self.set_enable_iam_user_credentials(True)
        await self.set_user_password()

        if isinstance(self.template.properties.credentials, list):
            for credential in self.template.properties.credentials:
                credential.password.enabled = False
        else:
            self.template.properties.credentials.password.enabled = False

        template_change_details = await self.template.apply(
            IAMBIC_TEST_DETAILS.config.aws
        )

        self.assertGreater(
            len(template_change_details.proposed_changes),
            0,
            f"No proposed changes detected: {json.dumps(template_change_details.dict())}",
        )
        self.assertEqual(
            len(template_change_details.exceptions_seen),
            0,
            f"Exceptions detected: {json.dumps(template_change_details.dict())}",
        )
        await self.refresh_template()

    async def test_attempt_set_password_enabled(self):
        """
        Verify that if a user attempts to set password to "enabled" an exception will be returned
        """
        self.set_enable_iam_user_credentials(True)
        await self.refresh_template()

        if isinstance(self.template.properties.credentials, list):
            for credential in self.template.properties.credentials:
                credential.password.enabled = False
        else:
            self.template.properties.credentials.password.enabled = False

        template_change_details = await self.template.apply(
            IAMBIC_TEST_DETAILS.config.aws
        )

        self.assertEqual(
            len(template_change_details.exceptions_seen),
            0,
            f"Exceptions detected: {json.dumps(template_change_details.dict())}",
        )

        if isinstance(self.template.properties.credentials, list):
            for credential in self.template.properties.credentials:
                credential.password.enabled = True
        else:
            self.template.properties.credentials.password.enabled = True

        template_change_details = await self.template.apply(
            IAMBIC_TEST_DETAILS.config.aws
        )

        self.assertEqual(
            len(template_change_details.proposed_changes),
            0,
            f"Proposed changes detected: {json.dumps(template_change_details.dict())}",
        )
        self.assertGreater(
            len(template_change_details.exceptions_seen),
            0,
            f"No exceptions detected: {json.dumps(template_change_details.dict())}",
        )
        await self.refresh_template()

    async def test_set_access_key_disabled(self):
        """
        Test the ability to disable a users access key
        """
        self.set_enable_iam_user_credentials(True)

        await self.delete_user_access_keys()
        await self.set_user_access_key()
        expected_changes = 0

        if isinstance(self.template.properties.credentials, list):
            for credential in self.template.properties.credentials:
                for access_key in credential.access_keys:
                    expected_changes += 1
                    access_key.enabled = False
        else:
            for access_key in self.template.properties.credentials.access_keys:
                expected_changes += 1
                access_key.enabled = False

        template_change_details = await self.template.apply(
            IAMBIC_TEST_DETAILS.config.aws
        )

        self.assertEqual(
            len(template_change_details.proposed_changes),
            expected_changes,
            f"Incorrect number of proposed changes: {json.dumps(template_change_details.dict())}",
        )
        self.assertEqual(
            len(template_change_details.exceptions_seen),
            0,
            f"Exceptions detected: {json.dumps(template_change_details.dict())}",
        )
        await self.refresh_template()

    async def test_attempt_set_access_key_enabled(self):
        """
        Verify that if a user attempts to set an access key to "enabled" an exception will be returned
        """
        self.set_enable_iam_user_credentials(True)

        await self.delete_user_access_keys()
        await self.set_user_access_key()
        await self.flip_user_access_keys_status()
        expected_exceptions = 0

        if isinstance(self.template.properties.credentials, list):
            for credential in self.template.properties.credentials:
                expected_exceptions += len(credential.access_keys)
        else:
            expected_exceptions = len(self.template.properties.credentials.access_keys)

        template_change_details = await self.template.apply(
            IAMBIC_TEST_DETAILS.config.aws
        )

        self.assertEqual(
            len(template_change_details.exceptions_seen),
            expected_exceptions,
            f"Incorrect number of exceptions detected: {json.dumps(template_change_details.dict())}",
        )
        await self.refresh_template()

    async def test_ignore_credentials_on_apply_if_disabled(self):
        await self.set_user_password()
        self.set_enable_iam_user_credentials(False)

        if isinstance(self.template.properties.credentials, list):
            for credential in self.template.properties.credentials:
                credential.password.enabled = False
        else:
            self.template.properties.credentials.password.enabled = False

        template_change_details = await self.template.apply(
            IAMBIC_TEST_DETAILS.config.aws
        )

        self.assertEqual(
            len(template_change_details.exceptions_seen),
            0,
            f"Exceptions detected: {json.dumps(template_change_details.dict())}",
        )
        self.set_enable_iam_user_credentials(True)
        await self.refresh_template()

    async def test_ignore_credentials_on_import_if_disabled(self):
        self.set_enable_iam_user_credentials(False)
        await self.refresh_template()
        self.assertIsNone(self.template.properties.credentials)
