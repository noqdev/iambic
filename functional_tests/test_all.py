from __future__ import annotations

import os
import shutil
import tempfile

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
      assume_role_arns:
        - arn: 'arn:aws:iam::259868150464:role/IambicSpokeRole'
      org_name: 'staging'
      account_rules:
        - included_accounts:
            - '*'
          enabled: true
          read_only: false
      default_rule:
        enabled: true
        read_only: false
"""


def test_import():
    fd, temp_config_filename = tempfile.mkstemp(
        prefix="iambic_test_temp_config_filename"
    )
    temp_templates_directory = tempfile.mkdtemp(
        prefix="iambic_test_temp_templates_directory"
    )
    with open(temp_config_filename, "w") as temp_file:
        temp_file.write(all_config)

    run_import(
        [temp_config_filename],
        temp_templates_directory,
    )

    os.close(fd)
    os.unlink(temp_config_filename)
    shutil.rmtree(temp_templates_directory)
