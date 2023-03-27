from __future__ import annotations

import datetime
import os

from functional_tests.conftest import IAMBIC_TEST_DETAILS

from iambic.core.iambic_enum import IambicManaged
from iambic.core.parser import load_templates
from iambic.main import run_apply


def test_okta_group():
    iambic_functional_test_group_yaml = """template_type: NOQ::Okta::Group
idp_name: development
properties:
  name: iambic_functional_test_group
  description: This is a test group created by the Iambic functional test suite.
  members:
    - username: user1@example.com
    - username: user2@example.com
    - username: user3@example.com
"""
    test_group_path = os.path.join(
        IAMBIC_TEST_DETAILS.template_dir_path,
        "resources/okta/group/development",
    )
    test_group_fp = os.path.join(test_group_path, "iambic_functional_test_group.yaml")
    os.makedirs(test_group_path, exist_ok=True)

    with open(test_group_fp, "w") as temp_file:
        temp_file.write(iambic_functional_test_group_yaml)

    # Create group
    run_apply(IAMBIC_TEST_DETAILS.config, [test_group_fp])

    # Test Reading Template
    group_template = load_templates([test_group_fp])[0]
    assert group_template.properties.members[2].username == "user3@example.com"

    # Expire `user3@example.com`
    group_template.properties.members[2].expires_at = datetime.datetime.now(
        datetime.timezone.utc
    ) - datetime.timedelta(days=1)
    # Set `user2@example.com` to expire tomorrow
    group_template.properties.members[1].expires_at = datetime.datetime.now(
        datetime.timezone.utc
    ) + datetime.timedelta(days=1)
    # Write new template, apply, and confirm access removed
    group_template.write()
    run_apply(IAMBIC_TEST_DETAILS.config, [test_group_fp])
    group_template = load_templates([test_group_fp])[0]
    assert len(group_template.properties.members) == 2

    # set the template to import_only
    proposed_changes_path = "{0}/proposed_changes.json".format(os.getcwd())
    if os.path.isfile(proposed_changes_path):
        os.remove(proposed_changes_path)
    else:
        assert (
            False  # Previous changes are not being written out to proposed_changes.yaml
        )
    group_template.iambic_managed = IambicManaged.IMPORT_ONLY
    orig_username = group_template.properties.members[0].username
    group_template.properties.members[
        0
    ].username = "this_user_should_not_exist@example.com"
    group_template.write()
    run_apply(IAMBIC_TEST_DETAILS.config, [test_group_fp])
    if os.path.isfile(proposed_changes_path):
        assert os.path.getsize(proposed_changes_path) == 2
    else:
        # this is acceptable as well because there are no changes to be made.
        pass
    group_template.iambic_managed = IambicManaged.UNDEFINED
    group_template.properties.members[0].username = orig_username
    group_template.write()

    # Set expiry for the entire group
    group_template.expires_at = "yesterday"
    group_template.write()
    run_apply(IAMBIC_TEST_DETAILS.config, [test_group_fp])

    group_template = load_templates([test_group_fp])[0]
    assert group_template.deleted is True

    # make sure we turn relative time -> absolute time EN-1645
    assert group_template.expires_at != "yesterday"
    assert isinstance(group_template.expires_at, datetime.datetime)
