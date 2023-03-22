# from __future__ import annotations
#
# import datetime
# import os
# import random
# import time
#
# from functional_tests.conftest import IAMBIC_TEST_DETAILS
# from iambic.core.iambic_enum import IambicManaged
# from iambic.core.parser import load_templates
# from iambic.main import run_apply
#
#
# def test_azure_ad_user():
#     temp_templates_directory = IAMBIC_TEST_DETAILS.template_dir_path
#     user_suffix = str(random.randint(0, 1000000))
#     username = f"iambic_functional_test_user_{user_suffix}@noq.dev"
#     iambic_functional_test_user_yaml = f"""template_type: NOQ::AzureAD::User
# idp_name: noq_dev
# properties:
#   display_name: Functional Test User {user_suffix}
#   given_name: Fnc Test {user_suffix}
#   username: {username}
# """
#     test_user_fp = os.path.join(
#         temp_templates_directory,
#         f"resources/azure_ad/user/noq_dev/{username}.yaml",
#     )
#
#     with open(test_user_fp, "w") as temp_file:
#         temp_file.write(iambic_functional_test_user_yaml)
#
#     # Create user
#     run_apply(IAMBIC_TEST_DETAILS.config, [test_user_fp])
#
#     # Test Reading Template
#     user_template = load_templates([test_user_fp])[0]
#     assert user_template.properties.username == username
#
#     # Test Updating Template
#     user_template.properties.display_name = "TestNameChange"
#     user_template.write()
#     # Sleep to give profile time to propagate
#     time.sleep(30)
#     run_apply(IAMBIC_TEST_DETAILS.config, [test_user_fp])
#     user_template = load_templates([test_user_fp])[0]
#     assert user_template.properties.display_name == "TestNameChange"
#
#     # set the template to import_only
#     proposed_changes_yaml_path = "{0}/proposed_changes.yaml".format(os.getcwd())
#     if os.path.isfile(proposed_changes_yaml_path):
#         os.remove(proposed_changes_yaml_path)
#     else:
#         assert (
#             False  # Previous changes are not being written out to proposed_changes.yaml
#         )
#     user_template.iambic_managed = IambicManaged.IMPORT_ONLY
#     orig_first_name = user_template.properties.display_name
#     user_template.properties.display_name = "shouldNotWork"
#     user_template.write()
#     run_apply(IAMBIC_TEST_DETAILS.config, [test_user_fp])
#     if os.path.isfile(proposed_changes_yaml_path):
#         assert os.path.getsize(proposed_changes_yaml_path) == 0
#     else:
#         # this is acceptable as well because there are no changes to be made.
#         pass
#     user_template.iambic_managed = IambicManaged.UNDEFINED
#     user_template.properties.display_name = orig_first_name
#     user_template.write()
#
#     run_apply(IAMBIC_TEST_DETAILS.config, [test_user_fp])
#
#     user_template = load_templates([test_user_fp])[0]
#     # Expire user
#     user_template.expires_at = datetime.datetime.now(
#         datetime.timezone.utc
#     ) - datetime.timedelta(days=1)
#     user_template.write()
#     run_apply(IAMBIC_TEST_DETAILS.config, [test_user_fp])
#     user_template = load_templates([test_user_fp])[0]
#     assert user_template.deleted is True
#     # Needed to really delete the user and file
#     user_template.deleted = True
#     user_template.write()
#     run_apply(IAMBIC_TEST_DETAILS.config, [test_user_fp])
