from __future__ import annotations

import os
import pytest
import shutil
import tempfile

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
      sso_account:
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


class IambicTestPaths:
    config_path: str = None
    template_dir_path: str = None


IAMBIC_TEST_PATHS = IambicTestPaths()


@pytest.fixture(scope="session", autouse=True)
def generate_templates_fixture(request):
    log.info("Generating templates for testing")

    fd, IAMBIC_TEST_PATHS.config_path = tempfile.mkstemp(
        prefix="iambic_test_temp_config_filename",
        suffix=".yaml"
    )
    IAMBIC_TEST_PATHS.template_dir_path = tempfile.mkdtemp(
        prefix="iambic_test_temp_templates_directory"
    )
    with open(IAMBIC_TEST_PATHS.config_path, "w") as temp_file:
        temp_file.write(all_config)

    run_import(
        [IAMBIC_TEST_PATHS.config_path],
        IAMBIC_TEST_PATHS.template_dir_path,
    )

    log.info("Finished generating templates for testing")

    def teardown():
        log.info(
            "Removing temp files",
            template_dir=IAMBIC_TEST_PATHS.template_dir_path,
            config_file=IAMBIC_TEST_PATHS.config_path
        )
        os.close(fd)
        os.unlink(IAMBIC_TEST_PATHS.config_path)
        shutil.rmtree(IAMBIC_TEST_PATHS.template_dir_path)

    request.addfinalizer(teardown)
