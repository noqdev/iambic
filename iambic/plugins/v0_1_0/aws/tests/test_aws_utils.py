from __future__ import annotations

from unittest import IsolatedAsyncioTestCase, mock
from unittest.mock import MagicMock

import boto3
from botocore.exceptions import ClientError
from botocore.stub import Stubber
from moto import mock_s3

from iambic.core.iambic_enum import IambicManaged
from iambic.plugins.v0_1_0.aws.iambic_plugin import AWSConfig
from iambic.plugins.v0_1_0.aws.models import AWSAccount
from iambic.plugins.v0_1_0.aws.utils import (
    boto3_retry,
    create_assume_role_session,
    get_aws_account_map,
)


async def async_noop(*args, **kwargs):
    pass


class TestAWSUtils(IsolatedAsyncioTestCase):
    # Test the boto3_retry function with retries
    async def test_boto3_retry_with_error(self):
        # Create a mock S3 bucket
        with mock_s3():
            s3_client = boto3.client("s3", region_name="us-east-1")
            s3_client.create_bucket(Bucket="test-bucket")

            # Use botocore stubber to mock the s3.head_bucket function
            with Stubber(s3_client) as stubber:
                expected_params = {"Bucket": "test-bucket"}

                # Add the exception response and the successful response to the stubber
                stubber.add_client_error(
                    "head_bucket",
                    expected_params={"Bucket": "test-bucket"},
                    service_error_code="NoSuchBucket",
                    service_message="The specified bucket does not exist",
                    http_status_code=400,
                )
                stubber.add_response(
                    "head_bucket", service_response={}, expected_params=expected_params
                )

                # Patch asyncio.sleep to avoid waiting during tests
                with mock.patch("asyncio.sleep", new=async_noop):

                    @boto3_retry
                    async def mock_boto3_function(bucket_name):
                        return s3_client.head_bucket(Bucket=bucket_name)

                    with self.assertRaises(ClientError):
                        await mock_boto3_function("test-bucket")

    # Test the boto3_retry function without retries
    async def test_boto3_retry_without_retries(self):
        # Create a mock S3 bucket
        with mock_s3():
            s3 = boto3.client("s3", region_name="us-east-1")
            s3.create_bucket(Bucket="test-bucket")

            @boto3_retry
            async def mock_boto3_function(bucket_name):
                return s3.head_bucket(Bucket=bucket_name)

            # Test the original boto3 function
            result = await mock_boto3_function("test-bucket")
            self.assertEqual(result["ResponseMetadata"]["HTTPStatusCode"], 200)

    async def test_boto3_retry_with_throttling(self):
        # Create a mock S3 bucket
        with mock_s3():
            s3_client = boto3.client("s3", region_name="us-east-1")
            s3_client.create_bucket(Bucket="test-bucket")

            # Use botocore stubber to mock the s3.head_bucket function
            with Stubber(s3_client) as stubber:
                # Add the throttling exception and the successful response to the stubber
                for i in range(10):
                    stubber.add_client_error(
                        "head_bucket",
                        expected_params={"Bucket": "test-bucket"},
                        service_error_code="Throttling",
                        service_message="Rate exceeded",
                        http_status_code=429,
                    )

                # Patch asyncio.sleep to avoid waiting during tests
                with mock.patch("asyncio.sleep", new=async_noop):

                    @boto3_retry
                    async def mock_boto3_function(bucket_name):
                        return s3_client.head_bucket(Bucket=bucket_name)

                    with self.assertRaises(
                        ClientError
                    ):  # We expect a Throttline error to be raised
                        await mock_boto3_function("test-bucket")


class TestCreateAssumeRoleSession(IsolatedAsyncioTestCase):
    async def test_create_assume_role_session(self):
        # Set up parameters
        assume_role_arn = "arn:aws:iam::123456789012:role/TestRole"
        region_name = "us-east-1"
        external_id = "test-external-id"
        session_name = "iambic"

        # Mock boto3 session
        boto3_session = MagicMock()

        # Mock the STS client
        sts_client = boto3.client("sts", region_name=region_name)
        boto3_session.client.return_value = sts_client

        # Set up STS response
        expected_credentials = {
            "AccessKeyId": "ACCESS_KEY_ID_123456",
            "SecretAccessKey": "SECRET_KEY",
            "SessionToken": "SESSION_TOKEN",
            "Expiration": "2022-01-01T00:00:00Z",
        }
        sts_response = {
            "AssumedRoleUser": {
                "AssumedRoleId": "AROATESTID:TestRole",
                "Arn": "arn:aws:sts::123456789012:assumed-role/TestRole/{}".format(
                    session_name
                ),
            },
            "Credentials": expected_credentials,
            "PackedPolicySize": 123,
        }

        # Use botocore stubber to mock the sts.assume_role function
        with Stubber(sts_client) as stubber:
            stubber.add_response(
                "assume_role",
                service_response=sts_response,
                expected_params={
                    "RoleArn": assume_role_arn,
                    "RoleSessionName": session_name,
                    "ExternalId": external_id,
                },
            )

            # Call the create_assume_role_session function
            assumed_session = await create_assume_role_session(
                boto3_session, assume_role_arn, region_name, external_id, session_name
            )

            actual_creds = assumed_session.get_credentials().get_frozen_credentials()

            # Check if the returned session has the correct credentials
            self.assertEqual(
                actual_creds.access_key,
                expected_credentials["AccessKeyId"],
            )

            self.assertEqual(
                actual_creds.secret_key,
                expected_credentials["SecretAccessKey"],
            )

            self.assertEqual(
                actual_creds.token,
                expected_credentials["SessionToken"],
            )

    async def test_create_assume_role_session_exception(self):
        # Set up parameters
        assume_role_arn = "arn:aws:iam::123456789012:role/TestRole"
        region_name = "us-east-1"
        external_id = "test-external-id"
        session_name = "iambic"

        # Mock boto3 session
        boto3_session = MagicMock()

        # Mock the STS client
        sts_client = boto3.client("sts", region_name=region_name)
        boto3_session.client.return_value = sts_client

        # Use botocore stubber to mock the sts.assume_role function and raise an exception
        with Stubber(sts_client) as stubber:
            stubber.add_client_error(
                "assume_role",
                service_error_code="AccessDenied",
                service_message="Access Denied",
                http_status_code=400,
                expected_params={
                    "RoleArn": assume_role_arn,
                    "RoleSessionName": session_name,
                    "ExternalId": external_id,
                },
            )

            # Call the create_assume_role_session function and expect an exception
            with self.assertRaises(ClientError):
                await create_assume_role_session(
                    boto3_session,
                    assume_role_arn,
                    region_name,
                    external_id,
                    session_name,
                )


class TestGetAWSAccountMap(IsolatedAsyncioTestCase):
    async def test_get_aws_account_map(self):
        # Create example AWSConfig
        accounts = [
            AWSAccount(
                account_id="123456789012",
                iambic_managed=IambicManaged.READ_AND_WRITE,
                account_name="test_account_2",
            ),
            AWSAccount(
                account_id="223456789012",
                iambic_managed=IambicManaged.READ_AND_WRITE,
                account_name="test_account_3",
            ),
            AWSAccount(
                account_id="323456789012",
                iambic_managed=IambicManaged.READ_AND_WRITE,
                account_name="test_account_4",
            ),
            AWSAccount(
                account_id="423456789012",
                iambic_managed=IambicManaged.READ_AND_WRITE,
                account_name="test_account_5",
            ),
        ]
        config = AWSConfig(accounts=accounts)

        # Call the get_aws_account_map function
        account_map = await get_aws_account_map(config)

        # Check if the returned account map is correct
        self.assertEqual(len(account_map), len(accounts))
        for account in accounts:
            self.assertIn(account.account_id, account_map)
            self.assertEqual(account_map[account.account_id], account)

    async def test_get_aws_account_map_iambic_managed_disabled(self):
        # Create example AWSConfig
        accounts = [
            AWSAccount(
                account_id="123456789012",
                iambic_managed=IambicManaged.READ_AND_WRITE,
                account_name="test_account_2",
            ),
            AWSAccount(
                account_id="223456789012",
                iambic_managed=IambicManaged.DISABLED,
                account_name="test_account_3",
            ),
            AWSAccount(
                account_id="323456789012",
                iambic_managed=IambicManaged.READ_AND_WRITE,
                account_name="test_account_4",
            ),
            AWSAccount(
                account_id="423456789012",
                iambic_managed=IambicManaged.READ_AND_WRITE,
                account_name="test_account_5",
            ),
        ]
        config = AWSConfig(accounts=accounts)

        # Call the get_aws_account_map function
        account_map = await get_aws_account_map(config)

        # Check if the returned account map is correct
        self.assertEqual(len(account_map), len(accounts) - 1)
        for account in accounts:
            if account.iambic_managed != IambicManaged.DISABLED:
                self.assertIn(account.account_id, account_map)
                self.assertEqual(account_map[account.account_id], account)

    async def test_get_aws_account_map_duplicate_account_id(self):
        # Create example AWSConfig
        accounts = [
            AWSAccount(
                account_id="123456789012",
                iambic_managed=IambicManaged.READ_AND_WRITE,
                account_name="test_account_2",
            ),
            AWSAccount(
                account_id="123456789012",
                iambic_managed=IambicManaged.READ_AND_WRITE,
                account_name="test_account_2_duplicate",
            ),
            AWSAccount(
                account_id="223456789012",
                iambic_managed=IambicManaged.READ_AND_WRITE,
                account_name="test_account_3",
            ),
            AWSAccount(
                account_id="323456789012",
                iambic_managed=IambicManaged.READ_AND_WRITE,
                account_name="test_account_4",
            ),
            AWSAccount(
                account_id="423456789012",
                iambic_managed=IambicManaged.READ_AND_WRITE,
                account_name="test_account_5",
            ),
        ]
        config = AWSConfig()
        config.accounts = accounts

        # Call the get_aws_account_map function and check for ValueError due to duplicate account_id
        with self.assertRaises(ValueError):
            await get_aws_account_map(config)
