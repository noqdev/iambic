from __future__ import annotations

import datetime
import os
import shutil
import tempfile

from iambic.core.parser import load_templates
from iambic.main import run_apply, run_import

os.environ["AWS_PROFILE"] = "staging/IambicHubRole"
os.environ["TESTING"] = "true"

okta_config = """
extends:
  - key: AWS_SECRETS_MANAGER
    value: arn:aws:secretsmanager:us-west-2:759357822767:secret:test/okta-only-secret-4XZ2TL
    assume_role_arn: arn:aws:iam::759357822767:role/IambicSpokeRole
"""


def test_okta():
    fd, temp_config_filename = tempfile.mkstemp(
        prefix="iambic_test_temp_config_filename"
    )
    temp_templates_directory = tempfile.mkdtemp(
        prefix="iambic_test_temp_templates_directory"
    )
    with open(temp_config_filename, "w") as temp_file:
        temp_file.write(okta_config)

    run_import(
        [temp_config_filename],
        temp_templates_directory,
    )

    iambic_functional_test_group_yaml = """template_type: NOQ::Okta::Group
properties:
  name: iambic_functional_test_group
  idp_name: development
  description: This is a test group created by the Iambic functional test suite.
  members:
    - username: curtis@noq.dev
    - username: steven@noq.dev
    - username: will@noq.dev
"""
    test_group_fp = os.path.join(
        temp_templates_directory,
        "okta/groups/development/iambic_functional_test_group.yaml",
    )

    with open(test_group_fp, "w") as temp_file:
        temp_file.write(iambic_functional_test_group_yaml)

    # Create group
    run_apply(
        True,
        temp_config_filename,
        [test_group_fp],
        temp_templates_directory,
    )

    # Test Reading Template
    group_template = load_templates([test_group_fp])[0]
    assert group_template.properties.members[2].username == "will@noq.dev"

    # Expire `fakeuser@example.com`
    group_template.properties.members[
        2
    ].expires_at = datetime.datetime.now() - datetime.timedelta(days=1)
    # Set `steven@noq.dev` to expire tomorrow
    group_template.properties.members[
        1
    ].expires_at = datetime.datetime.now() + datetime.timedelta(days=1)
    # Write new template, apply, and confirm access removed
    group_template.write()
    run_apply(
        True,
        temp_config_filename,
        [test_group_fp],
        temp_templates_directory,
    )
    group_template = load_templates([test_group_fp])[0]
    assert len(group_template.properties.members) == 2
    # Set expiry for the entire group
    group_template.expires_at = datetime.datetime.now() - datetime.timedelta(days=1)
    group_template.write()
    run_apply(
        True,
        temp_config_filename,
        [test_group_fp],
        temp_templates_directory,
    )

    group_template = load_templates([test_group_fp])[0]
    assert group_template.deleted is True
    os.close(fd)
    os.unlink(temp_config_filename)
    shutil.rmtree(temp_templates_directory)
