from __future__ import annotations

import pytest
from iambic.config.dynamic_config import Config
from iambic.plugins.v0_1_0.aws.iambic_plugin import AWSConfig
from iambic.plugins.v0_1_0.aws.models import (
    AWSIdentityCenter,
    AWSOrgAccountRule,
    AWSOrganization,
    BaseAWSOrgRule,
)
from pydantic import ValidationError


@pytest.fixture
def config_file_path(tmpdir):
    file_path = tmpdir.join("config.yml")
    file_path.write("version: '1'\n")
    return str(file_path)


def test_load(config_file_path):
    config = Config.load(config_file_path)
    assert config.version == "1"


def test_combine_extended_configs(config_file_path):
    config = Config.load(config_file_path)
    assert hasattr(config, "version")
    assert getattr(config, "version") == "1"


def test_aws_config_instantiate_with_organizations():
    organizations = [
        AWSOrganization(
            org_id="o-123456789",
            org_account_id="123456789012",
            identity_center=AWSIdentityCenter(
                account_id="123456789012", region="us-west-2"
            ),
            default_rule=BaseAWSOrgRule(enabled=True),
            account_rules=[AWSOrgAccountRule(account_id="123456789012")],
            hub_role_arn="arn:aws:iam::123456789012:role/hub_role",
        )
    ]
    config = AWSConfig(organizations=organizations)
    assert config.organizations == organizations


def test_aws_config_raises_error_for_multiple_configured():
    organizations = [
        AWSOrganization(
            org_id="o-123456789",
            org_account_id="123456789012",
            identity_center=AWSIdentityCenter(
                account_id="123456789012", region="us-west-2"
            ),
            default_rule=BaseAWSOrgRule(enabled=True),
            account_rules=[AWSOrgAccountRule(account_id="123456789012")],
            hub_role_arn="arn:aws:iam::123456789012:role/hub_role",
        ),
        AWSOrganization(
            org_id="o-234567891",
            org_account_id="234567890123",
            identity_center=AWSIdentityCenter(
                account_id="234567890123", region="us-west-2"
            ),
            default_rule=BaseAWSOrgRule(enabled=True),
            account_rules=[AWSOrgAccountRule(account_id="234567890123")],
            hub_role_arn="arn:aws:iam::234567890123:role/hub_role",
        ),
    ]
    with pytest.raises(ValidationError) as e:
        AWSConfig(organizations=organizations)
    assert str(e.value) == (
        "1 validation error for AWSConfig\norganizations\n  Only one AWS "
        "Organization is supported at this time. (type=value_error)"
    )
