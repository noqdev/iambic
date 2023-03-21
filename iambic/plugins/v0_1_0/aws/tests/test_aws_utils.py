from __future__ import annotations

from unittest import IsolatedAsyncioTestCase, mock

import boto3
from botocore.exceptions import ClientError
from botocore.stub import Stubber
from moto import mock_s3

from iambic.plugins.v0_1_0.aws.utils import boto3_retry


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
