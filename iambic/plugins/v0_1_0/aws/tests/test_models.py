from __future__ import annotations

import unittest

import pytest
from pydantic import ValidationError

from iambic.plugins.v0_1_0.aws.iam.models import MaxSessionDuration, Path
from iambic.plugins.v0_1_0.aws.iam.role.models import AwsIamRoleTemplate, RoleProperties
from iambic.plugins.v0_1_0.aws.iambic_plugin import AWSConfig
from iambic.plugins.v0_1_0.aws.models import AWSAccount, Description, Partition


def test_unique_account_id():
    with pytest.raises(ValidationError, match=r"1 validation error for AWSConfig.*"):
        AWSConfig(
            accounts=[
                AWSAccount(account_id="123456789012", account_name="account1"),
                AWSAccount(account_id="123456789012", account_name="account2"),
            ]
        )


def test_unique_account_name():
    with pytest.raises(ValidationError, match=r"1 validation error for AWSConfig.*"):
        AWSConfig(
            accounts=[
                AWSAccount(account_id="123456789012", account_name="account1"),
                AWSAccount(account_id="234567890123", account_name="account1"),
            ]
        )


def test_unique_account_id_and_name():
    with pytest.raises(ValidationError, match=r"1 validation error for AWSAccount.*"):
        AWSConfig(
            accounts=[
                AWSAccount(account_id="123456789012"),
                AWSAccount(account_id="123456789012"),
            ]
        )


def test_valid_config():
    config = AWSConfig(
        accounts=[
            AWSAccount(account_id="123456789012", account_name="account1"),
            AWSAccount(account_id="234567890123", account_name="account2"),
        ]
    )
    assert config.validate(config)


class TestBaseModel(unittest.TestCase):
    def setUp(self):
        properties = RoleProperties(
            role_name="test_role",
            description=[
                Description(
                    included_accounts=["test_account"],
                    description="test_account role description",
                ),
                Description(
                    included_accounts=["not_test_account"],
                    description="not_test_account role description",
                ),
            ],
            max_session_duration=[
                MaxSessionDuration(
                    included_accounts=["test_account"], max_session_duration=3600
                ),
                MaxSessionDuration(
                    included_accounts=["not_test_account"], max_session_duration=600
                ),
            ],
            path=[Path(file_path="/")],
        )
        self.role_template = AwsIamRoleTemplate(
            identifier="test_role",
            file_path="/tmp/test_role.yaml",
            properties=properties,
        )

    def test_get_attribute_val_for_account(self):
        aws_account = AWSAccount(
            account_id="123456789012",
            account_name="test_account",
            partition=Partition.AWS,
        )

        result = self.role_template.get_attribute_val_for_account(
            aws_account, "properties.role_name"
        )
        self.assertEqual(result, "test_role")

        result = self.role_template.get_attribute_val_for_account(
            aws_account, "properties.description"
        )
        self.assertEqual(result, [{"Description": "test_account role description"}])

        result = self.role_template.get_attribute_val_for_account(
            aws_account, "properties.max_session_duration"
        )
        self.assertEqual(result, [{"MaxSessionDuration": 3600}])
