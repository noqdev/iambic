from __future__ import annotations

import pytest
from iambic.plugins.v0_1_0.aws.iambic_plugin import AWSConfig
from iambic.plugins.v0_1_0.aws.models import AWSAccount
from pydantic import ValidationError


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
