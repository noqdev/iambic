from __future__ import annotations

import os
import pathlib
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest

from iambic.config.dynamic_config import Config
from iambic.config.utils import check_and_update_resource_limit
from iambic.core.iambic_enum import IambicManaged
from iambic.plugins.v0_1_0.aws.iambic_plugin import AWSConfig
from iambic.plugins.v0_1_0.aws.models import (
    AWSAccount,
    AWSOrganization,
    BaseAWSOrgRule,
    get_hub_role_arn,
    get_spoke_role_arn,
)


@pytest.fixture
def repo_path(request):
    def fin():
        TEST_CLEANUP = os.getenv("IAMBIC_TEST_CLEANUP", True)
        if TEST_CLEANUP:
            temp_config_folder.cleanup()

    request.addfinalizer(fin)
    temp_config_folder = TemporaryDirectory(prefix="iambic_test")
    return pathlib.Path(temp_config_folder.name)


@pytest.fixture
def config(repo_path):
    account_id = "123456789012"
    aws_config = AWSConfig(
        organizations=[
            AWSOrganization(
                org_id="test_org_uuid",
                org_name="test_org_name",
                default_rule=BaseAWSOrgRule(),
                account_rules=[],
                hub_role_arn=get_hub_role_arn(account_id),
                org_account_id=account_id,
            ),
        ],
        accounts=[
            AWSAccount(
                account_id=account_id,
                org_id="test_org_uuid",
                account_name="test_account_name",
                role_access_tag="",
                iambic_managed=IambicManaged.READ_AND_WRITE,
                spoke_role_arn=get_spoke_role_arn(account_id),
            ),
        ],
        min_accounts_required_for_wildcard_included_accounts=2,
    )
    test_config = Config(
        aws=aws_config,
        google_projects=[],
        okta_organizations=[],
        extends=[],
        secrets={
            "git": {
                "repositories": [
                    {
                        "name": repo_path.name,
                        "uri": "http://test_repo_uri",
                    },
                ]
            }
        },
        role_access_tag="noq-authorized",
        variables=[],
        slack_app="",
        sqs={},
        slack={},
        version="0.0.0",
        file_path=f"{repo_path}/cool_location.yaml",
    )
    return test_config


@patch("resource.setrlimit")
@patch("resource.getrlimit")
@patch("resource.RLIMIT_NOFILE")
def test_check_and_update_resource_limit(
    mock_rlimit, mock_getrlimit, mock_setrlimit, config
):
    mock_rlimit.value = 7
    mock_getrlimit.return_value = (1024, 4096)
    mock_setrlimit.return_value = None
    check_and_update_resource_limit(config)
    mock_setrlimit.assert_called_once_with(
        mock_rlimit, (config.core.minimum_ulimit, 4096)
    )
