from __future__ import annotations

import asyncio
import os
import shutil
import tempfile

import pytest

from iambic.aws.models import AWSAccount
from iambic.config.models import Config
from iambic.core.context import ctx
from iambic.core.logger import log
from iambic.main import run_import

os.environ["AWS_PROFILE"] = "staging/IambicHubRole"
os.environ["TESTING"] = "true"

all_config = """
extends:
  - key: AWS_SECRETS_MANAGER
    value: arn:aws:secretsmanager:us-west-2:759357822767:secret:dev/google-MmAS1o
    assume_role_arn: arn:aws:iam::759357822767:role/IambicSpokeRole

aws:
  organizations:
    - org_id: 'o-yfdp0r70sq'
      assume_role_arn: 'arn:aws:iam::259868150464:role/IambicSpokeRole'
      org_name: 'staging'
      identity_center_account:
        account_id: '259868150464'
        region: 'us-east-1'
      account_rules:
        - included_accounts:
            - '*'
          enabled: true
          read_only: false
      default_rule:
        enabled: true
        read_only: false
"""


class IambicTestDetails:
    config_path: str = None
    template_dir_path: str = None
    config: Config = None
    identity_center_account: AWSAccount = None


IAMBIC_TEST_DETAILS = IambicTestDetails()


@pytest.fixture(scope="session", autouse=True)
def generate_templates_fixture(request):
    log.info("Generating templates for testing")
    ctx.eval_only = False

    fd, IAMBIC_TEST_DETAILS.config_path = tempfile.mkstemp(
        prefix="iambic_test_temp_config_filename", suffix=".yaml"
    )
    IAMBIC_TEST_DETAILS.template_dir_path = tempfile.mkdtemp(
        prefix="iambic_test_temp_templates_directory"
    )

    with open(IAMBIC_TEST_DETAILS.config_path, "w") as temp_file:
        temp_file.write(all_config)

    run_import(
        [IAMBIC_TEST_DETAILS.config_path],
        IAMBIC_TEST_DETAILS.template_dir_path,
    )

    log.info("Finished generating templates for testing")
    log.info("Setting up config for testing")

    IAMBIC_TEST_DETAILS.config = Config.load(IAMBIC_TEST_DETAILS.config_path)
    asyncio.run(IAMBIC_TEST_DETAILS.config.setup_aws_accounts())

    for aws_account in IAMBIC_TEST_DETAILS.config.aws.accounts:
        if aws_account.identity_center_details:
            IAMBIC_TEST_DETAILS.identity_center_account = aws_account
            asyncio.run(aws_account.set_identity_center_details())
            break

    log.info("Config setup complete")

    def teardown():
        log.info(
            "Removing temp files",
            template_dir=IAMBIC_TEST_DETAILS.template_dir_path,
            config_file=IAMBIC_TEST_DETAILS.config_path,
        )
        os.close(fd)
        os.unlink(IAMBIC_TEST_DETAILS.config_path)
        shutil.rmtree(IAMBIC_TEST_DETAILS.template_dir_path)

    request.addfinalizer(teardown)
