from __future__ import annotations

import datetime
import os

from functional_tests.conftest import IAMBIC_TEST_DETAILS
from iambic.core.parser import load_templates
from iambic.main import run_apply


def test_google():
    iambic_functional_test_group_yaml = """template_type: NOQ::Google::Group
properties:
  name: iambic_functional_test_temp_group
  description: 'This is a temporary group created by the iambic functional test suite.'
  domain: iambic.org
  email: iambic_test_group@iambic.org
  members:
    - email: curtis@iambic.org
      role: OWNER
    - email: iambic_test_user_1@iambic.org
    - email: iambic_test_user_2@iambic.org
"""
    test_group_fp = os.path.join(
        IAMBIC_TEST_DETAILS.template_dir_path,
        "resources/google/iambic.org/groups/iambic_test_group.yaml",
    )

    with open(test_group_fp, "w") as temp_file:
        temp_file.write(iambic_functional_test_group_yaml)

    # Create group
    run_apply(
        True,
        IAMBIC_TEST_DETAILS.config_path,
        [test_group_fp],
        IAMBIC_TEST_DETAILS.template_dir_path,
    )

    # Test Reading Template
    group_template = load_templates([test_group_fp])[0]
    assert group_template.properties.members[2].email == "iambic_test_user_2@iambic.org"

    # Expire `fakeuser@example.com`
    group_template.properties.members[2].expires_at = datetime.datetime.now(
        datetime.timezone.utc
    ) - datetime.timedelta(days=1)
    # Set `iambic_test_user_1@iambic.org` to expire tomorrow
    group_template.properties.members[1].expires_at = datetime.datetime.now(
        datetime.timezone.utc
    ) + datetime.timedelta(days=1)
    # Write new template, apply, and confirm access removed
    group_template.write()
    run_apply(
        True,
        IAMBIC_TEST_DETAILS.config_path,
        [test_group_fp],
        IAMBIC_TEST_DETAILS.template_dir_path,
    )
    group_template = load_templates([test_group_fp])[0]
    assert len(group_template.properties.members) == 2
    # Set expiry for the entire group
    group_template.expires_at = datetime.datetime.now() - datetime.timedelta(days=1)
    group_template.write()
    run_apply(
        True,
        IAMBIC_TEST_DETAILS.config_path,
        [test_group_fp],
        IAMBIC_TEST_DETAILS.template_dir_path,
    )

    group_template = load_templates([test_group_fp])[0]
    assert group_template.deleted is True
