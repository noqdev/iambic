from __future__ import annotations

import os
import shutil
import tempfile
from random import randint
from test.plugins.v0_1_0.azure_ad.test_utils import MockAzureADOrganization
from test.plugins.v0_1_0.azure_ad.user.test_utils import (  # noqa: F401 # intentional for mocks
    azure_ad_organization,
)

import pytest

from iambic.core.models import ProposedChangeType
from iambic.plugins.v0_1_0.azure_ad.iambic_plugin import AzureADConfig
from iambic.plugins.v0_1_0.azure_ad.user.models import (
    AzureActiveDirectoryUserTemplate as UserTemplate,
)
from iambic.plugins.v0_1_0.azure_ad.user.models import UserTemplateProperties

TEST_TEMPLATE_DIR = "azure_ad"
TEST_TEMPLATE_PATH = "azure_ad/azure_ad_user.yaml"


@pytest.fixture
def mock_user_fs():
    temp_templates_directory = tempfile.mkdtemp(
        prefix="iambic_test_temp_templates_directory"
    )

    try:
        os.makedirs(f"{temp_templates_directory}/{TEST_TEMPLATE_DIR}", exist_ok=True)

        test_template_path = f"{temp_templates_directory}/{TEST_TEMPLATE_PATH}"
        with open(test_template_path, "w") as f:
            f.write("")

        yield test_template_path, temp_templates_directory
    finally:
        try:
            shutil.rmtree(temp_templates_directory)
        except Exception as e:
            print(e)


@pytest.fixture
def mock_user(
    mock_user_fs, azure_ad_organization  # noqa: F811 # intentional for mocks
) -> UserTemplate:
    test_template_path, temp_templates_directory = mock_user_fs
    user_suffix = randint(0, 100000)
    username = f"user{user_suffix}@example.com"
    user_properties = UserTemplateProperties(
        username=username,
        mail_nickname=f"user{user_suffix}",
        display_name=f"user{user_suffix}",
    )
    template = UserTemplate(
        idp_name=azure_ad_organization.idp_name,
        file_path=test_template_path,
        properties=user_properties,
    )
    template.write()
    return template


@pytest.mark.asyncio
async def test_apply_create_user(
    mock_user_fs,
    azure_ad_organization: MockAzureADOrganization,  # noqa: F811 # intentional for mocks
    mock_user: UserTemplate,  # noqa: F811 # intentional for mocks
):
    azure_ad_config = AzureADConfig(organizations=[azure_ad_organization])
    template_change_details = await mock_user.apply(azure_ad_config)
    assert (
        template_change_details.proposed_changes[0].proposed_changes[0].change_type
        == ProposedChangeType.CREATE
    )
    assert bool(
        azure_ad_organization.request_data["users"].get(mock_user.properties.user_id)
    )


@pytest.mark.asyncio
async def test_apply_delete_user(
    mock_user_fs,
    azure_ad_organization: MockAzureADOrganization,  # noqa: F811 # intentional for mocks
    mock_user: UserTemplate,  # noqa: F811 # intentional for mocks
):
    azure_ad_config = AzureADConfig(organizations=[azure_ad_organization])
    await mock_user.apply(azure_ad_config)
    assert bool(
        azure_ad_organization.request_data["users"].get(mock_user.properties.user_id)
    )

    # Now delete it
    mock_user.deleted = True
    mock_user.write()
    await mock_user.apply(azure_ad_config)
    assert not bool(
        azure_ad_organization.request_data["users"].get(mock_user.properties.user_id)
    )


@pytest.mark.asyncio
async def test_apply_update_user(
    mock_user_fs,  # noqa: F811 # intentional for mocks
    azure_ad_organization: MockAzureADOrganization,  # noqa: F811 # intentional for mocks
    mock_user: UserTemplate,  # noqa: F811 # intentional for mocks
):
    azure_ad_config = AzureADConfig(organizations=[azure_ad_organization])
    await mock_user.apply(azure_ad_config)
    assert bool(
        azure_ad_organization.request_data["users"].get(mock_user.properties.user_id)
    )

    # Now update it
    mock_user.properties.display_name = "New Display Name"
    mock_user.write()

    template_change_details = await mock_user.apply(azure_ad_config)
    assert (
        template_change_details.proposed_changes[0].proposed_changes[0].change_type
        == ProposedChangeType.UPDATE
    )
    user_data = azure_ad_organization.request_data["users"].get(
        mock_user.properties.user_id
    )
    assert user_data["displayName"] == mock_user.properties.display_name
