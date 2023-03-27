from __future__ import annotations

import os
import shutil
import tempfile
from test.plugins.v0_1_0.okta.user.test_utils import (  # noqa: F401 # intentional for mocks
    mock_okta_organization,
)

import pytest

from iambic.core.models import ProposedChangeType
from iambic.plugins.v0_1_0.okta.iambic_plugin import OktaConfig
from iambic.plugins.v0_1_0.okta.user.models import OktaUserTemplate, UserProperties

TEST_TEMPLATE_DIR = "okta"
TEST_TEMPLATE_PATH = "okta/okta_user.yaml"


@pytest.fixture
def mock_fs():
    temp_templates_directory = tempfile.mkdtemp(
        prefix="iambic_test_temp_templates_directory"
    )

    try:
        os.makedirs(f"{temp_templates_directory}/{TEST_TEMPLATE_DIR}")

        test_template_path = f"{temp_templates_directory}/{TEST_TEMPLATE_PATH}"
        with open(test_template_path, "w") as f:
            f.write("")

        yield test_template_path, temp_templates_directory
    finally:
        try:
            shutil.rmtree(temp_templates_directory)
        except Exception as e:
            print(e)


@pytest.mark.asyncio
async def test_apply_create_user(
    mock_fs, mock_okta_organization  # noqa: F811 # intentional for mocks
):
    test_template_path, temp_templates_directory = mock_fs
    idp_name = "example.org"
    user_properties = UserProperties(
        username="example_user",
        profile={"login": "example_username"},
    )
    template = OktaUserTemplate(
        file_path=test_template_path, idp_name=idp_name, properties=user_properties
    )
    template.write()
    okta_config = OktaConfig(organizations=[mock_okta_organization])
    mock_okta_organization.client.has_no_user = True
    template_change_details = await template.apply(okta_config)
    assert (
        template_change_details.proposed_changes[0].proposed_changes[0].change_type
        == ProposedChangeType.CREATE
    )
