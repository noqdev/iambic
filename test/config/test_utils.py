from __future__ import annotations

import os
import pathlib
import resource
from tempfile import TemporaryDirectory

import pytest

from iambic.config.dynamic_config import Config
from iambic.config.utils import (
    check_and_update_resource_limit,
    resolve_config_template_path,
)
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
        variables=[],
        slack_app="",
        sqs={},
        slack={},
        version="0.0.0",
        file_path=f"{repo_path}/cool_location.yaml",
    )
    return test_config


def test_check_and_update_resource_limit(config):
    cur_soft_limit, cur_hard_limit = resource.getrlimit(resource.RLIMIT_NOFILE)
    assert cur_soft_limit != 0
    config.core.minimum_ulimit = cur_soft_limit * 2
    check_and_update_resource_limit(config)
    new_soft_limit, new_hard_limit = resource.getrlimit(resource.RLIMIT_NOFILE)
    assert new_soft_limit == config.core.minimum_ulimit
    # restore original value
    resource.setrlimit(resource.RLIMIT_NOFILE, (cur_soft_limit, cur_hard_limit))


@pytest.mark.asyncio
async def test_resolve_config_template_path(test_config_path_two_accounts_plus_org):
    test_config_path = pathlib.Path(test_config_path_two_accounts_plus_org).parent
    config_path = await resolve_config_template_path(test_config_path)
    assert config_path == test_config_path / "configuration.yaml"


@pytest.mark.asyncio
async def test_resolve_config_template_path_too_many_exception(
    test_config_path_two_accounts_plus_org,
):
    test_config_path = pathlib.Path(test_config_path_two_accounts_plus_org).parent
    (test_config_path / "configuration.yaml").write_text(
        "template_type: NOQ::Core::Config\n"
    )
    (test_config_path / "configuration2.yaml").write_text(
        "template_type: NOQ::Core::Config\n"
    )
    with pytest.raises(RuntimeError):
        await resolve_config_template_path(test_config_path)


@pytest.mark.asyncio
async def test_resolve_config_template_path_no_config_exception(tmpdir):
    with pytest.raises(RuntimeError):
        await resolve_config_template_path(pathlib.Path(tmpdir))
