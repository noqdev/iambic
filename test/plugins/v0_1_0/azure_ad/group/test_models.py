from __future__ import annotations

import os
import shutil
import tempfile
from random import randint
from test.plugins.v0_1_0.azure_ad.test_utils import (  # noqa: F401 # intentional for mocks
    MockAzureADOrganization,
    azure_ad_organization,
)
from test.plugins.v0_1_0.azure_ad.user.test_models import (  # noqa: F401 # intentional for mocks
    mock_user,
    mock_user_fs,
)

import pytest

from iambic.core.models import ProposedChangeType
from iambic.plugins.v0_1_0.azure_ad.group.models import (
    AzureActiveDirectoryGroupTemplate as GroupTemplate,
)
from iambic.plugins.v0_1_0.azure_ad.group.models import (
    GroupTemplateProperties,
    Member,
    MemberDataType,
)
from iambic.plugins.v0_1_0.azure_ad.iambic_plugin import AzureADConfig
from iambic.plugins.v0_1_0.azure_ad.user.models import (
    AzureActiveDirectoryUserTemplate as UserTemplate,
)

TEST_TEMPLATE_DIR = "azure_ad"
TEST_TEMPLATE_PATH = "azure_ad/azure_ad_user.yaml"


@pytest.fixture
def mock_group_fs():
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


@pytest.fixture
def mock_group(
    mock_group_fs,  # noqa: F811 # intentional for mocks
    azure_ad_organization: MockAzureADOrganization,  # noqa: F811 # intentional for mocks
) -> GroupTemplate:
    test_template_path, temp_templates_directory = mock_group_fs
    group_suffix = randint(0, 100000)
    group_name = f"group{group_suffix}"
    group_properties = GroupTemplateProperties(
        name=group_name,
        mail_nickname=group_name,
        description="Group Description",
        mail_enabled=True,
        security_enabled=True,
        group_types=[],
    )
    template = GroupTemplate(
        idp_name=azure_ad_organization.idp_name,
        file_path=test_template_path,
        properties=group_properties,
    )
    template.write()
    return template


@pytest.mark.asyncio
async def test_apply_create_group(
    mock_group_fs,  # noqa: F811 # intentional for mocks
    azure_ad_organization: MockAzureADOrganization,  # noqa: F811 # intentional for mocks
    mock_group: GroupTemplate,  # noqa: F811 # intentional for mocks
):
    azure_ad_config = AzureADConfig(organizations=[azure_ad_organization])
    template_change_details = await mock_group.apply(azure_ad_config)
    assert (
        template_change_details.proposed_changes[0].proposed_changes[0].change_type
        == ProposedChangeType.CREATE
    )
    assert bool(
        azure_ad_organization.request_data["groups"].get(mock_group.properties.group_id)
    )


@pytest.mark.asyncio
async def test_apply_create_group_with_user_member(
    mock_group_fs,  # noqa: F811 # intentional for mocks
    mock_user_fs,  # noqa: F811 # intentional for mocks
    azure_ad_organization: MockAzureADOrganization,  # noqa: F811 # intentional for mocks
    mock_group: GroupTemplate,  # noqa: F811 # intentional for mocks
    mock_user: UserTemplate,  # noqa: F811 # intentional for mocks
):
    azure_ad_config = AzureADConfig(organizations=[azure_ad_organization])
    await mock_user.apply(azure_ad_config)

    user = mock_user.properties
    mock_group.properties.members = [
        Member(id=user.user_id, name=user.username, data_type=MemberDataType.USER)
    ]
    mock_group.write()

    template_change_details = await mock_group.apply(azure_ad_config)
    assert (
        template_change_details.proposed_changes[0].proposed_changes[0].change_type
        == ProposedChangeType.CREATE
    )
    assert bool(
        azure_ad_organization.request_data["groups"].get(mock_group.properties.group_id)
    )
    members = azure_ad_organization.request_data["groups"][
        mock_group.properties.group_id
    ]["members"]
    assert len(members) == 1
    assert members[0]["id"] == user.user_id


@pytest.mark.asyncio
async def test_apply_delete_group(
    mock_group_fs,  # noqa: F811 # intentional for mocks
    azure_ad_organization: MockAzureADOrganization,  # noqa: F811 # intentional for mocks
    mock_group: GroupTemplate,  # noqa: F811 # intentional for mocks
):
    azure_ad_config = AzureADConfig(organizations=[azure_ad_organization])
    await mock_group.apply(azure_ad_config)
    assert bool(
        azure_ad_organization.request_data["groups"].get(mock_group.properties.group_id)
    )

    # Now delete it
    mock_group.deleted = True
    mock_group.write()
    await mock_group.apply(azure_ad_config)
    assert not bool(
        azure_ad_organization.request_data["groups"].get(mock_group.properties.group_id)
    )


@pytest.mark.asyncio
async def test_apply_update_group(
    mock_group_fs,  # noqa: F811 # intentional for mocks
    azure_ad_organization: MockAzureADOrganization,  # noqa: F811 # intentional for mocks
    mock_group: GroupTemplate,  # noqa: F811 # intentional for mocks
):
    azure_ad_config = AzureADConfig(organizations=[azure_ad_organization])
    await mock_group.apply(azure_ad_config)
    assert bool(
        azure_ad_organization.request_data["groups"].get(mock_group.properties.group_id)
    )

    # Now update it
    mock_group.properties.description = "New Description"
    mock_group.write()
    template_change_details = await mock_group.apply(azure_ad_config)
    assert (
        template_change_details.proposed_changes[0].proposed_changes[0].change_type
        == ProposedChangeType.UPDATE
    )
    group_data = azure_ad_organization.request_data["groups"].get(
        mock_group.properties.group_id
    )
    assert group_data["description"] == mock_group.properties.description


@pytest.mark.asyncio
async def test_apply_update_group_with_new_user_member(
    mock_group_fs,  # noqa: F811 # intentional for mocks
    mock_user_fs,  # noqa: F811 # intentional for mocks
    azure_ad_organization: MockAzureADOrganization,  # noqa: F811 # intentional for mocks
    mock_group: GroupTemplate,  # noqa: F811 # intentional for mocks
    mock_user: UserTemplate,  # noqa: F811 # intentional for mocks
):
    azure_ad_config = AzureADConfig(organizations=[azure_ad_organization])
    await mock_user.apply(azure_ad_config)
    user = mock_user.properties

    await mock_group.apply(azure_ad_config)
    assert bool(
        azure_ad_organization.request_data["groups"].get(mock_group.properties.group_id)
    )
    members = azure_ad_organization.request_data["groups"][
        mock_group.properties.group_id
    ]["members"]
    assert len(members) == 0

    # Now add the user member
    mock_group.properties.members = [
        Member(id=user.user_id, name=user.username, data_type=MemberDataType.USER)
    ]
    mock_group.write()
    await mock_group.apply(azure_ad_config)
    members = azure_ad_organization.request_data["groups"][
        mock_group.properties.group_id
    ]["members"]
    assert len(members) == 1
    assert members[0]["id"] == user.user_id


@pytest.mark.asyncio
async def test_apply_update_group_with_user_member_removal(
    mock_group_fs,  # noqa: F811 # intentional for mocks
    mock_user_fs,  # noqa: F811 # intentional for mocks
    azure_ad_organization: MockAzureADOrganization,  # noqa: F811 # intentional for mocks
    mock_group: GroupTemplate,  # noqa: F811 # intentional for mocks
    mock_user: UserTemplate,  # noqa: F811 # intentional for mocks
):
    azure_ad_config = AzureADConfig(organizations=[azure_ad_organization])
    await mock_user.apply(azure_ad_config)

    user = mock_user.properties
    mock_group.properties.members = [
        Member(id=user.user_id, name=user.username, data_type=MemberDataType.USER)
    ]
    mock_group.write()

    template_change_details = await mock_group.apply(azure_ad_config)
    assert (
        template_change_details.proposed_changes[0].proposed_changes[0].change_type
        == ProposedChangeType.CREATE
    )
    assert bool(
        azure_ad_organization.request_data["groups"].get(mock_group.properties.group_id)
    )
    members = azure_ad_organization.request_data["groups"][
        mock_group.properties.group_id
    ]["members"]
    assert len(members) == 1
    assert members[0]["id"] == user.user_id

    # Now remove the user member
    mock_group.properties.members = []
    mock_group.write()
    template_change_details = await mock_group.apply(azure_ad_config)
    assert (
        template_change_details.proposed_changes[0].proposed_changes[0].change_type
        == ProposedChangeType.DETACH
    )
    members = azure_ad_organization.request_data["groups"][
        mock_group.properties.group_id
    ]["members"]
    assert len(members) == 0
