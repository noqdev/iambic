from __future__ import annotations

import os
import pathlib
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock

import asynctest
import pytest

from iambic.aws.models import AWSAccount, BaseAWSOrgRule
from iambic.config.models import AWSConfig, AWSOrganization, Config
from iambic.config.utils import load_template, store_template
from iambic.core.iambic_enum import IambicManaged


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
    aws_config = AWSConfig(
        organizations=[
            AWSOrganization(
                org_id="test_org_uuid",
                org_name="test_org_name",
                default_rule=BaseAWSOrgRule(),
                account_rules=[],
            ),
        ],
        accounts=[
            AWSAccount(
                account_id="123456789012",
                org_id="test_org_uuid",
                account_name="test_account_name",
                role_access_tag="",
                iambic_managed=IambicManaged.READ_AND_WRITE,
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
        file_path="cool_location.yaml",
    )
    return test_config


@pytest.mark.asyncio
@asynctest.patch(
    "iambic.config.utils.clone_git_repos", return_value={"test_repo": MagicMock()}
)
@asynctest.patch("iambic.config.utils.get_origin_head", return_value="main")
@asynctest.patch("iambic.config.utils.Repo", return_value=MagicMock())
# Notice: the order of fixtures is important; asynctest patches always come first in reverse order
# And then the pytest fixtures
async def test_load_store_templated_config(
    repo, origin_head, test_repo, mocker, config, repo_path
):
    config.slack_app = "test_canary"
    await store_template(config, repo_path, "test_repo")
    test_config = await load_template(repo_path)
    assert test_config.slack_app == "test_canary"
