from __future__ import annotations

import os
import shutil
import tempfile
from test.plugins.v0_1_0.aws.iam.policy.test_utils import (  # noqa: F401 # intentional for mocks
    EXAMPLE_POLICY_DOCUMENT,
)
from test.plugins.v0_1_0.aws.organizations.scp.test_utils import (
    EXAMPLE_ACCOUNT_EMAIL,
    EXAMPLE_ACCOUNT_NAME,
    EXAMPLE_ORGANIZATIONAL_UNIT_NAME,
    EXAMPLE_POLICY_DESCRIPTION,
    EXAMPLE_POLICY_NAME,
)

import boto3
import pytest
from moto import mock_organizations, mock_sts
from moto.organizations.models import FakePolicy

import iambic
from iambic.core.iambic_enum import Command
from iambic.core.models import ExecutionMessage
from iambic.plugins.v0_1_0.aws.iambic_plugin import AWSConfig
from iambic.plugins.v0_1_0.aws.models import AWSAccount, AWSOrganization

TEST_TEMPLATE_DIR = "resources/aws/organizations/scp"
TEST_TEMPLATE_PATH = f"{TEST_TEMPLATE_DIR}/example_policy.yaml"


@pytest.fixture
def mock_fs():
    temp_templates_directory = tempfile.mkdtemp(
        prefix="iambic_test_temp_templates_directory"
    )

    try:
        os.makedirs(f"{temp_templates_directory}/{TEST_TEMPLATE_DIR}")

        test_template_path = f"{temp_templates_directory}/{TEST_TEMPLATE_PATH}"
        with open(test_template_path, "w") as f:
            f.write("")

        setattr(iambic.core.utils, "__WRITABLE_DIRECTORY__", temp_templates_directory)

        yield test_template_path, temp_templates_directory
    finally:
        try:
            shutil.rmtree(temp_templates_directory)
        except Exception as e:
            print(e)


@pytest.fixture
def mock_execution_message():
    def factory():
        message = ExecutionMessage(
            execution_id="fake_execution_id",
            command=Command.IMPORT,
        )  # type: ignore
        return message

    return factory


@pytest.fixture
def mock_aws_account():
    account = AWSAccount(
        account_id="123456789012",
        account_name="example_account",
        hub_role_arn="arn:aws:iam::123456789012:role/example-hub-role",
        spoke_role_arn="arn:aws:iam::123456789012:role/example-spoke-role",
    )  # type: ignore

    return account


@pytest.fixture
def mock_aws_organization():
    account = AWSOrganization(
        org_name="main-organization",
        org_id="123456789012"[::-1],
        org_account_id="123456789012",
        hub_role_arn="arn:aws:iam::123456789012:role/example-hub-role",
    )  # type: ignore
    return account  # type: ignore


@pytest.fixture
def mock_aws_config(mock_aws_account, mock_aws_organization):
    def factory():
        account = mock_aws_account
        org = mock_aws_organization

        config = AWSConfig(
            accounts=[mock_aws_account],
            organizations=[mock_aws_organization],
        )  # type: ignore

        account.set_account_organization_details(org, config)

        return config

    return factory


@pytest.fixture
def mock_organizations_client():
    with mock_organizations(), mock_sts():
        client = boto3.client("organizations")
        org = client.create_organization(FeatureSet="ALL")["Organization"]
        root = client.list_roots()["Roots"][0]
        account = client.create_account(
            AccountName=EXAMPLE_ACCOUNT_NAME,
            Email=EXAMPLE_ACCOUNT_EMAIL,
        )["CreateAccountStatus"]
        org_unit = client.create_organizational_unit(
            ParentId=root["Id"], Name=EXAMPLE_ORGANIZATIONAL_UNIT_NAME
        )["OrganizationalUnit"]

        _current_init = FakePolicy.__init__

        def new_init(self, organization, **kwargs):
            # CHECK pull request https://github.com/getmoto/moto/pull/6338
            self.tags = kwargs.get("Tags", {})
            _current_init(self, organization, **kwargs)

        FakePolicy.__init__ = new_init

        policy = client.create_policy(
            Content=EXAMPLE_POLICY_DOCUMENT,
            Description=EXAMPLE_POLICY_DESCRIPTION,
            Name=EXAMPLE_POLICY_NAME,
            Type="SERVICE_CONTROL_POLICY",
        )["Policy"]["PolicySummary"]

        yield client, [org, root, account, org_unit, policy]
