from __future__ import annotations

import datetime
import os

from functional_tests.conftest import IAMBIC_TEST_DETAILS
from iambic.core.models import ProposedChangeType
from iambic.core.parser import load_templates
from iambic.main import run_apply
from iambic.plugins.v0_1_0.google_workspace.group.models import (
    GoogleWorkspaceGroupTemplate,
    GroupMember,
)


def test_google():
    iambic_functional_test_group_yaml = """template_type: NOQ::GoogleWorkspace::Group
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
    test_group_path = os.path.join(
        IAMBIC_TEST_DETAILS.template_dir_path,
        "resources/google_workspace/groups/iambic.org",
    )
    test_group_fp = os.path.join(test_group_path, "iambic_test_group.yaml")
    os.makedirs(test_group_path, exist_ok=True)

    with open(test_group_fp, "w") as temp_file:
        temp_file.write(iambic_functional_test_group_yaml)

    # Create group
    run_apply(IAMBIC_TEST_DETAILS.config, [test_group_fp])

    # Test Reading Template
    group_template: GoogleWorkspaceGroupTemplate = load_templates([test_group_fp])[0]
    assert group_template.properties.members[2].email == "iambic_test_user_2@iambic.org"

    # Test attach members
    new_group_member = GroupMember(email="iambic_test_user_3@iambic.org")
    group_template.properties.members.append(new_group_member)
    group_template.write()
    template_changes = run_apply(IAMBIC_TEST_DETAILS.config, [test_group_fp])
    proposed_change = template_changes[0].proposed_changes[0].proposed_changes[0]
    assert proposed_change.change_type == ProposedChangeType.ATTACH
    assert proposed_change.resource_id == "iambic_test_group@iambic.org"
    assert proposed_change.resource_type == "google:group:template"

    # Test detach members
    group_template.properties.members.remove(new_group_member)
    group_template.write()
    template_changes = run_apply(IAMBIC_TEST_DETAILS.config, [test_group_fp])
    proposed_change = template_changes[0].proposed_changes[0].proposed_changes[0]
    assert proposed_change.change_type == ProposedChangeType.DETACH
    assert proposed_change.resource_id == "iambic_test_group@iambic.org"
    assert proposed_change.resource_type == "google:group:template"

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
    run_apply(IAMBIC_TEST_DETAILS.config, [test_group_fp])
    group_template = load_templates([test_group_fp])[0]
    assert len(group_template.properties.members) == 2
    # Set expiry for the entire group
    group_template.expires_at = datetime.datetime.now() - datetime.timedelta(days=1)
    group_template.write()
    run_apply(IAMBIC_TEST_DETAILS.config, [test_group_fp])

    group_template = load_templates([test_group_fp])[0]
    assert group_template.deleted is True
