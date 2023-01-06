import os
import pytest
from tempfile import TemporaryDirectory
from iambic.aws.models import AWSAccount, BaseAWSOrgRule
from iambic.config.models import AWSConfig, AWSOrganization, Config
from iambic.core.iambic_enum import IambicManaged


@pytest.fixture
def config(request):
    def fin():
        TEST_CLEANUP = os.getenv("IAMBIC_TEST_CLEANUP", False)
        temp_config_folder.cleanup()
    request.addfinalizer(fin)
    temp_config_folder = TemporaryDirectory(prefix="iambic_test")
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
        secrets={},
        role_access_tag="noq-authorized",
        variables=[],
        slack_app="",
        sqs={},
        slack={},
        repo_path=temp_config_folder,
    )
    return test_config


@pytest.mark.asyncio
async def test_load_store_templated_config(config):
    config.test_canary = True
    config.store_template([config.repo_dir], "test_repo")
    test_config = Config.load_template(config.repo_dir)
    assert test_config.test_canary is True
