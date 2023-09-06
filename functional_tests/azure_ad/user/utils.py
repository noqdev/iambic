from __future__ import annotations

import os
import random

from functional_tests.conftest import IAMBIC_TEST_DETAILS
from iambic.plugins.v0_1_0.azure_ad.user.models import AzureActiveDirectoryUserTemplate


def generate_user_template() -> AzureActiveDirectoryUserTemplate:
    user_dir = os.path.join(
        IAMBIC_TEST_DETAILS.template_dir_path,
        "resources/azure_ad/user/iambic",
    )
    os.makedirs(user_dir, exist_ok=True)
    identifier = str(random.randint(0, 10000))
    file_path = os.path.join(user_dir, f"iambic_functional_test_{identifier}.yaml")
    # Note: iambicorg.onmicrosoft.com suffix is due to the azure ad setup
    username = f"iambic_functional_test_user_{identifier}@iambicorg.onmicrosoft.com"
    user_template = f"""
template_type: NOQ::AzureAD::User
idp_name: iambic
properties:
  display_name: Functional Test User {identifier}
  given_name: Fnc Test {identifier}
  username: {username}
"""
    with open(file_path, "w") as f:
        f.write(user_template)
    user_template = AzureActiveDirectoryUserTemplate.load(file_path)

    return user_template
