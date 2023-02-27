from __future__ import annotations

import datetime
import os
import time

from functional_tests.conftest import IAMBIC_TEST_DETAILS
from iambic.core.iambic_enum import IambicManaged
from iambic.core.parser import load_templates
from iambic.main import run_force_apply


def test_okta_user():
    temp_config_filename = IAMBIC_TEST_DETAILS.config_path
    temp_templates_directory = IAMBIC_TEST_DETAILS.template_dir_path

    iambic_functional_test_user_yaml = """template_type: NOQ::Okta::User
properties:
  username: iambic_functional_test_user
  idp_name: development
  profile:
    firstName: iambic
    lastName: functional_test_user
    email: iambic_functional_test_user@example.com
    login: iambic_functional_test_user@example.com
  status: active
"""
    test_user_fp = os.path.join(
        temp_templates_directory,
        "resources/okta/development/users/iambic_functional_test_user.yaml",
    )

    with open(test_user_fp, "w") as temp_file:
        temp_file.write(iambic_functional_test_user_yaml)

    # Create user
    run_force_apply(
        temp_config_filename,
        [test_user_fp],
        temp_templates_directory,
    )

    # Test Reading Template
    user_template = load_templates([test_user_fp])[0]
    assert user_template.properties.username == "iambic_functional_test_user"

    # Test Updating Template
    user_template.properties.profile["firstName"] = "TestNameChange"
    user_template.write()
    # Sleep to give profile time to propagate
    time.sleep(30)
    run_force_apply(
        temp_config_filename,
        [test_user_fp],
        temp_templates_directory,
    )
    user_template = load_templates([test_user_fp])[0]
    assert user_template.properties.profile["firstName"] == "TestNameChange"

    # set the template to import_only
    proposed_changes_yaml_path = "{0}/proposed_changes.yaml".format(os.getcwd())
    if os.path.isfile(proposed_changes_yaml_path):
        os.remove(proposed_changes_yaml_path)
    else:
        assert (
            False  # Previous changes are not being written out to proposed_changes.yaml
        )
    user_template.iambic_managed = IambicManaged.IMPORT_ONLY
    orig_first_name = user_template.properties.profile["firstName"]
    user_template.properties.profile["firstName"] = "shouldNotWork"
    user_template.write()
    run_force_apply(
        temp_config_filename,
        [test_user_fp],
        temp_templates_directory,
    )
    if os.path.isfile(proposed_changes_yaml_path):
        assert os.path.getsize(proposed_changes_yaml_path) == 0
    else:
        # this is acceptable as well because there are no changes to be made.
        pass
    user_template.iambic_managed = IambicManaged.UNDEFINED
    user_template.properties.profile["firstName"] = orig_first_name
    user_template.write()

    run_force_apply(
        temp_config_filename,
        [test_user_fp],
        temp_templates_directory,
    )

    user_template = load_templates([test_user_fp])[0]
    # Expire user
    user_template.expires_at = datetime.datetime.now(
        datetime.timezone.utc
    ) - datetime.timedelta(days=1)
    user_template.write()
    run_force_apply(
        temp_config_filename,
        [test_user_fp],
        temp_templates_directory,
    )
    user_template = load_templates([test_user_fp])[0]
    assert user_template.deleted is True
    # Needed to really delete the user and file
    user_template.force_delete = True
    user_template.write()
    run_force_apply(
        temp_config_filename,
        [test_user_fp],
        temp_templates_directory,
    )
