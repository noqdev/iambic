from __future__ import annotations

import datetime
import os
import random
import time

from functional_tests.conftest import IAMBIC_TEST_DETAILS

from iambic.core.iambic_enum import IambicManaged
from iambic.core.parser import load_templates
from iambic.main import run_apply


def test_okta_user():
    temp_templates_directory = IAMBIC_TEST_DETAILS.template_dir_path
    username = f"iambic_functional_test_user_{random.randint(0, 1000000)}"
    iambic_functional_test_user_yaml = f"""template_type: NOQ::Okta::User
idp_name: development
properties:
  username: {username}
  profile:
    firstName: iambic
    lastName: {username}
    email: {username}@example.com
    login: {username}@example.com
  status: active
"""
    test_user_fp = os.path.join(
        temp_templates_directory,
        f"resources/okta/user/development/{username}.yaml",
    )
    os.makedirs(
        os.path.join(
            temp_templates_directory,
            "resources/okta/user/development/",
        ),
        exist_ok=True,
    )
    with open(test_user_fp, "w") as temp_file:
        temp_file.write(iambic_functional_test_user_yaml)

    # Create user
    run_apply(IAMBIC_TEST_DETAILS.config, [test_user_fp])

    # Test Reading Template
    user_template = load_templates(
        [test_user_fp], IAMBIC_TEST_DETAILS.config.okta.template_map
    )[0]
    assert user_template.properties.username == username

    # Test Updating Template
    user_template.properties.profile["firstName"] = "TestNameChange"
    user_template.write()
    # Sleep to give profile time to propagate
    time.sleep(30)
    run_apply(IAMBIC_TEST_DETAILS.config, [test_user_fp])
    user_template = load_templates(
        [test_user_fp], IAMBIC_TEST_DETAILS.config.okta.template_map
    )[0]
    assert user_template.properties.profile["firstName"] == "TestNameChange"

    # set the template to import_only
    proposed_changes_path = "{0}/proposed_changes.json".format(os.getcwd())
    if os.path.isfile(proposed_changes_path):
        os.remove(proposed_changes_path)
    else:
        assert (
            False  # Previous changes are not being written out to proposed_changes.yaml
        )
    user_template.iambic_managed = IambicManaged.IMPORT_ONLY
    orig_first_name = user_template.properties.profile["firstName"]
    user_template.properties.profile["firstName"] = "shouldNotWork"
    user_template.write()
    run_apply(IAMBIC_TEST_DETAILS.config, [test_user_fp])
    if os.path.isfile(proposed_changes_path):
        assert os.path.getsize(proposed_changes_path) == 2  # {} is 2 bytes
    else:
        # this is acceptable as well because there are no changes to be made.
        pass
    user_template.iambic_managed = IambicManaged.UNDEFINED
    user_template.properties.profile["firstName"] = orig_first_name
    user_template.write()

    run_apply(IAMBIC_TEST_DETAILS.config, [test_user_fp])

    user_template = load_templates(
        [test_user_fp], IAMBIC_TEST_DETAILS.config.okta.template_map
    )[0]
    # Expire user
    user_template.expires_at = datetime.datetime.now(
        datetime.timezone.utc
    ) - datetime.timedelta(days=1)
    user_template.write()
    run_apply(IAMBIC_TEST_DETAILS.config, [test_user_fp])
    user_template = load_templates(
        [test_user_fp], IAMBIC_TEST_DETAILS.config.okta.template_map
    )[0]
    assert user_template.deleted is True
    # Needed to really delete the user and file
    user_template.force_delete = True
    user_template.write()
    run_apply(IAMBIC_TEST_DETAILS.config, [test_user_fp])
