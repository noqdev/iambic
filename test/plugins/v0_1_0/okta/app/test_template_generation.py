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
import yaml

import iambic.core.utils
from iambic.core.iambic_enum import Command
from iambic.core.models import ExecutionMessage
from iambic.plugins.v0_1_0.okta.app.models import OktaAppTemplate
from iambic.plugins.v0_1_0.okta.app.template_generation import (
    collect_org_apps,
    get_response_dir,
)
from iambic.plugins.v0_1_0.okta.iambic_plugin import OktaConfig, OktaOrganization

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

        setattr(iambic.core.utils, "__WRITABLE_DIRECTORY__", temp_templates_directory)

        yield test_template_path, temp_templates_directory
    finally:
        try:
            shutil.rmtree(temp_templates_directory)
        except Exception as e:
            print(e)


@pytest.mark.asyncio
async def test_collect_org_apps(
    mock_fs: tuple[str, str],
    mock_application: tuple[  # noqa: F811 # intentional for mocks
        OktaOrganization, None, None
    ],  # noqa: F811 # intentional for mocks
):
    test_template_path, temp_templates_directory = mock_fs
    okta_organization, _, okta_app, _ = mock_application
    execution_id = "foo"
    exe_message = ExecutionMessage(
        execution_id=execution_id,
        command=Command.IMPORT,
        provider_id=okta_organization.idp_name,
    )
    okta_config = OktaConfig(organizations=[okta_organization])
    await collect_org_apps(exe_message, okta_config)
    response_dir = get_response_dir(exe_message)
    expected_file_location = f"{response_dir}/{okta_app.name}.yaml"
    assert os.path.exists(expected_file_location)
    with open(expected_file_location, "r") as f:
        yaml_dict = yaml.safe_load(f)
        template = OktaAppTemplate(file_path=expected_file_location, **yaml_dict)
        assert template.properties.name == okta_app.name
