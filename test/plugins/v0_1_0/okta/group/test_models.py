from __future__ import annotations

import os
import shutil
import tempfile
from test.plugins.v0_1_0.okta.test_utils import (  # noqa: F401 # intentional for mocks
    mock_okta_organization,
)

import pytest

from iambic.core.models import ProposedChangeType
from iambic.plugins.v0_1_0.okta.group.models import (
    OktaGroupTemplate,
    OktaGroupTemplateProperties,
)
from iambic.plugins.v0_1_0.okta.iambic_plugin import OktaConfig


def test_members_sorting():
    members = [
        {"username": "user_1@example.org"},
        {"username": "user_2@example.org"},
    ]
    properties_1 = OktaGroupTemplateProperties(
        name="example_group",
        idp_name="example.org",
        group_id="example.org-example_group",
        members=members,
    )
    members_1 = properties_1.members
    members_2 = list(reversed(members_1))
    assert members_1 != members_2  # because we reverse the list
    properties_1.members = members_2
    assert (
        properties_1.members == members_2
    )  # double check the list is reversed because validation doesn't happen after creation
    properties_1.validate_model_afterward()
    assert properties_1.members == members_1


TEST_TEMPLATE_DIR = "okta"
TEST_TEMPLATE_PATH = "okta/okta_group.yaml"


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
async def test_apply_create_group(
    mock_fs, mock_okta_organization  # noqa: F811 # intentional for mocks
):
    test_template_path, temp_templates_directory = mock_fs
    idp_name = "example.org"
    group_properties = OktaGroupTemplateProperties(
        name="example_group",
        idp_name=idp_name,
        description="example description",
    )
    template = OktaGroupTemplate(
        file_path=test_template_path, properties=group_properties
    )
    template.write()
    okta_config = OktaConfig(organizations=[mock_okta_organization])
    template_change_details = await template.apply(okta_config)
    assert (
        template_change_details.proposed_changes[0].proposed_changes[0].change_type
        == ProposedChangeType.CREATE
    )
