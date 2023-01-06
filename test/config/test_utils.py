import os
import pathlib
import asynctest
import pytest
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock
from iambic.aws.models import AWSAccount, BaseAWSOrgRule
from iambic.config.models import AWSConfig, AWSOrganization, Config
from iambic.config.utils import load_template, store_template
import iambic.core.git
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
                    repo_path.name
                ]
            }
        },
        role_access_tag="noq-authorized",
        variables=[],
        slack_app="",
        sqs={},
        slack={},
    )
    return test_config


# @pytest.mark.asyncio
# async def test_load_store_templated_config(mocker, config, repo_path):
#     config.slack_app = "test_canary"
#     main_or_master_result = AsyncMock(return_value="main")
#     mocker.patch("iambic.core.git.main_or_master", side_effect=main_or_master_result)
#     clone_git_repos_result = AsyncMock(return_value={"test_repo": {}})
#     with mocker.patch("iambic.core.git.clone_git_repos", side_effect=clone_git_repos_result):
#         await store_template(config, repo_path, "test_repo")
#         assert iambic.core.git.clone_git_repos.called()
#         assert iambic.core.git.main_or_master.called()
#     test_config = await load_template(repo_path)
#     assert test_config.slack_app == "test_canary"

@pytest.mark.asyncio
async def test_load_store_templated_config(mocker, config, repo_path):
    config.slack_app = "test_canary"
    with asynctest.patch("iambic.config.utils.main_or_master", return_value="main"):
        with asynctest.patch("iambic.config.utils.clone_git_repos", return_value={"test_repo": MagicMock()}):
            await store_template(config, repo_path, "test_repo")
    test_config = await load_template(repo_path)
    assert test_config.slack_app == "test_canary"
