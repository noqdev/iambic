from __future__ import annotations

import os
import shutil
import tempfile
from test.plugins.v0_1_0.okta.app.test_utils import (  # noqa: F401 # intentional for mocks
    mock_application,
)
from test.plugins.v0_1_0.okta.test_utils import (  # noqa: F401 # intentional for mocks
    mock_okta_organization,
)

import pytest

from iambic.core.models import ProposedChangeType
from iambic.plugins.v0_1_0.okta.app.models import (
    OktaAppTemplate,
    OktaAppTemplateProperties,
)
from iambic.plugins.v0_1_0.okta.iambic_plugin import OktaConfig, OktaOrganization
from iambic.plugins.v0_1_0.okta.models import App, Assignment, Group


def test_members_sorting():
    assignments = [
        {"user": "user_1@example.org"},
        {"group": "group@example.org"},
    ]
    properties_1 = OktaAppTemplateProperties(
        name="example_app",
        idp_name="example.org",
        id="example.org-example_app",
        assignments=assignments,
    )
    assignments_1 = properties_1.assignments
    assignments_2 = list(reversed(assignments_1))
    assert assignments_1 != assignments_2  # because we reverse the list
    properties_1.assignments = assignments_2
    assert (
        properties_1.assignments == assignments_2
    )  # double check the list is reversed because validation doesn't happen after creation
    properties_1.validate_model_afterward()
    assert properties_1.assignments == assignments_1


TEST_TEMPLATE_DIR = "okta"
TEST_TEMPLATE_PATH = "okta/okta_app.yaml"


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
async def test_apply_app_assignment(
    mock_fs: tuple[str, str],
    mock_application: tuple[  # noqa: F811 # intentional for mocks
        OktaOrganization, Group, None, App
    ],  # noqa: F811 # intentional for mocks
):
    test_template_path, temp_templates_directory = mock_fs
    okta_organization, okta_group, okta_app, _ = mock_application
    app_properties = OktaAppTemplateProperties(
        id=okta_app.id,
        name=okta_app.name,
        idp_name=okta_app.idp_name,
        assignments=[Assignment(group=okta_group.name)],
    )
    template = OktaAppTemplate(file_path=test_template_path, properties=app_properties)
    template.write()
    okta_config = OktaConfig(organizations=[okta_organization])
    template_change_details = await template.apply(okta_config)
    assert (
        template_change_details.proposed_changes[0].proposed_changes[0].change_type
        == ProposedChangeType.ATTACH
    )
