from __future__ import annotations

import asyncio
import os
import shutil
import tempfile

import pytest

from iambic.config.dynamic_config import Config, load_config
from iambic.core.context import ctx
from iambic.core.logger import log
from iambic.plugins.v0_1_0.aws.models import AWSAccount

if not os.environ.get("GITHUB_ACTIONS", None):
    # We will select a particular AWS_PROFILE to run on developer local machine
    # Github action runner will use temporary creds in the environment
    # If you are public developer, this probably won't work for you since
    # functional test requires particular cloud resources for testing.
    os.environ["AWS_PROFILE"] = "iambic_test_org_account/IambicHubRole"

os.environ["TESTING"] = "true"
FUNCTIONAL_TEST_TEMPLATE_DIR = os.getenv("FUNCTIONAL_TEST_TEMPLATE_DIR", None)

all_config = """
template_type: NOQ::Core::Config
version: '1'

extends:
  - key: AWS_SECRETS_MANAGER
    value: arn:aws:secretsmanager:us-west-2:442632209887:secret:dev/iambic_itest_secrets_v2-Ctmonc
    assume_role_arn: arn:aws:iam::442632209887:role/IambicSpokeRole
  - key: AWS_SECRETS_MANAGER
    value: arn:aws:secretsmanager:us-west-2:442632209887:secret:dev/github-token-iambic-templates-itest
    assume_role_arn: arn:aws:iam::442632209887:role/IambicSpokeRole

aws:
  organizations:
    - org_id: 'o-8t0mt0ybdd'
      hub_role_arn: 'arn:aws:iam::580605962305:role/IambicHubRole'
      org_name: 'iambic_test_org_account'
      org_account_id: '580605962305'
      identity_center:
        region: 'us-east-1'
      account_rules:
        - included_accounts:
            - '*'
          enabled: true
          iambic_managed: read_and_write
      default_rule:
        enabled: true
        iambic_managed: read_and_write
  accounts:
    - account_id: '192455039954'
      account_name: iambic_test_spoke_account_2
      iambic_managed: read_and_write
      org_id: o-8t0mt0ybdd
      spoke_role_arn: arn:aws:iam::192455039954:role/IambicSpokeRole
    - account_id: '333972133479'
      account_name: iambic_test_spoke_account_3
      iambic_managed: read_and_write
      org_id: o-8t0mt0ybdd
      spoke_role_arn: arn:aws:iam::333972133479:role/IambicSpokeRole
    - account_id: '580605962305'
      account_name: iambic_test_org_account
      iambic_managed: read_and_write
      org_id: o-8t0mt0ybdd
      spoke_role_arn: arn:aws:iam::580605962305:role/IambicSpokeRole
    - account_id: '442632209887'
      account_name: iambic_test_spoke_account_1
      iambic_managed: read_and_write
      org_id: o-8t0mt0ybdd
      spoke_role_arn: arn:aws:iam::442632209887:role/IambicSpokeRole
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

    if FUNCTIONAL_TEST_TEMPLATE_DIR:
        IAMBIC_TEST_DETAILS.template_dir_path = FUNCTIONAL_TEST_TEMPLATE_DIR
    else:
        IAMBIC_TEST_DETAILS.template_dir_path = tempfile.mkdtemp(
            prefix="iambic_test_temp_templates_directory"
        )

    with open(IAMBIC_TEST_DETAILS.config_path, "w") as temp_file:
        temp_file.write(all_config)

    log.info("Setting up config for testing")
    IAMBIC_TEST_DETAILS.config = asyncio.run(
        load_config(IAMBIC_TEST_DETAILS.config_path)
    )

    if not FUNCTIONAL_TEST_TEMPLATE_DIR:
        asyncio.run(
            IAMBIC_TEST_DETAILS.config.run_import(IAMBIC_TEST_DETAILS.template_dir_path)
        )
        log.info("Finished generating templates for testing")

    for aws_account in IAMBIC_TEST_DETAILS.config.aws.accounts:
        if aws_account.identity_center_details:
            IAMBIC_TEST_DETAILS.identity_center_account = aws_account
            asyncio.run(aws_account.set_identity_center_details())
            break

    log.info("Config setup complete")

    def teardown():
        log_params = {
            "config_path": IAMBIC_TEST_DETAILS.config_path,
        }
        if not FUNCTIONAL_TEST_TEMPLATE_DIR:
            log_params["template_dir_path"] = IAMBIC_TEST_DETAILS.template_dir_path
        log.info("Removing temp files", **log_params)
        os.close(fd)
        os.unlink(IAMBIC_TEST_DETAILS.config_path)

        if not FUNCTIONAL_TEST_TEMPLATE_DIR:
            shutil.rmtree(IAMBIC_TEST_DETAILS.template_dir_path)

    request.addfinalizer(teardown)
