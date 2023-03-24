from __future__ import annotations

import asyncio
from test.plugins.v0_1_0.okta.test_utils import (  # noqa: F401 # intentional for mocks
    mock_okta_organization,
)

import okta.models
import pytest

from iambic.core.models import ProposedChangeType
from iambic.plugins.v0_1_0.okta.app.utils import (
    get_app,
    list_all_apps,
    list_app_group_assignments,
    list_app_user_assignments,
    maybe_delete_app,
    update_app_assignments,
    update_app_name,
)
from iambic.plugins.v0_1_0.okta.group.utils import create_group
from iambic.plugins.v0_1_0.okta.iambic_plugin import OktaOrganization
from iambic.plugins.v0_1_0.okta.models import App, Assignment, Group
from iambic.plugins.v0_1_0.okta.user.models import (
    OktaUserTemplate,
    OktaUserTemplateProperties,
)
from iambic.plugins.v0_1_0.okta.user.utils import create_user


@pytest.fixture
def mock_application(
    mock_okta_organization: OktaOrganization,  # noqa: F811 # intentional for mocks
):
    # Have to create group before getting it
    group_name = "example_groupname"
    idp_name = "example.org"
    description = "example description"
    okta_group = asyncio.run(
        create_group(group_name, idp_name, description, mock_okta_organization)
    )

    # Have to create user before getting it
    username = "example_username"
    idp_name = "example.org"
    user_properties = OktaUserTemplateProperties(
        username=username, idp_name=idp_name, profile={"login": username}
    )
    template = OktaUserTemplate(file_path="example", properties=user_properties)

    okta_user = asyncio.run(create_user(template, mock_okta_organization))

    # Have to create application before getting it
    app_name = "example_application"
    idp_name = "example.org"
    description = "example description"
    okta_app_model = okta.models.Application()
    okta_app_model.name = app_name
    okta_client = asyncio.run(mock_okta_organization.get_okta_client())
    okta_app_model, _, _ = asyncio.run(okta_client.create_application(okta_app_model))

    okta_app = asyncio.run(get_app(mock_okta_organization, str(okta_app_model.id)))

    yield mock_okta_organization, okta_group, okta_app, okta_user


@pytest.mark.asyncio
async def test_list_app_group_assignments_with_zero_assignment(
    mock_application: tuple[OktaOrganization, Group, None, App]
):
    okta_organization, _, okta_app, _ = mock_application
    group_assignment = await list_app_group_assignments(okta_organization, okta_app)
    assert len(group_assignment["group_assignments"]) == 0


@pytest.mark.asyncio
async def test_list_app_group_assignments_with_one_assignment(
    mock_application: tuple[OktaOrganization, Group, None, App]
):
    okta_organization, okta_group, okta_app, _ = mock_application

    # assign group to app
    new_assignments = [Assignment(group=okta_group.name)]
    proposed_changes = await update_app_assignments(
        okta_app,
        new_assignments,
        okta_organization,
        {},
    )
    assert len(proposed_changes) > 0

    group_assignment = await list_app_group_assignments(okta_organization, okta_app)
    assert len(group_assignment["group_assignments"]) == 1
    assign_group_name = group_assignment["group_assignments"][0]
    assert assign_group_name == okta_group.name

    okta_app = await get_app(okta_organization, str(okta_app.id))
    assert len(okta_app.assignments) == 1

    # unassign group to app
    new_assignments = []
    proposed_changes = await update_app_assignments(
        okta_app,
        new_assignments,
        okta_organization,
        {},
    )
    assert len(proposed_changes) > 0


@pytest.mark.asyncio
async def test_list_app_user_assignments_with_zero_assignment(
    mock_application: tuple[OktaOrganization, Group, None, App]
):
    okta_organization, _, okta_app, _ = mock_application
    user_assignment = await list_app_user_assignments(okta_organization, okta_app)
    assert len(user_assignment["user_assignments"]) == 0


@pytest.mark.asyncio
async def test_list_app_user_assignments_with_one_assignment(
    mock_application: tuple[OktaOrganization, Group, None, App]
):
    okta_organization, _, okta_app, okta_user = mock_application

    # assign user to app
    new_assignments = [Assignment(user=okta_user.username)]
    proposed_changes = await update_app_assignments(
        okta_app,
        new_assignments,
        okta_organization,
        {},
    )
    assert len(proposed_changes) > 0

    user_assignment = await list_app_user_assignments(okta_organization, okta_app)
    assert len(user_assignment["user_assignments"]) == 1
    assign_login = user_assignment["user_assignments"][0]
    assert assign_login == okta_user.username

    okta_app = await get_app(okta_organization, str(okta_app.id))
    assert len(okta_app.assignments) == 1

    # unassign group to app
    new_assignments = []
    proposed_changes = await update_app_assignments(
        okta_app,
        new_assignments,
        okta_organization,
        {},
    )
    assert len(proposed_changes) > 0


@pytest.mark.asyncio
async def test_list_all_apps(
    mock_application: tuple[OktaOrganization, Group, None, App]
):
    okta_organization, _, okta_app, _ = mock_application
    apps = await list_all_apps(okta_organization)
    assert len(apps) == 1
    assert apps[0].name == okta_app.name


@pytest.mark.asyncio
async def test_update_app_name(
    mock_application: tuple[OktaOrganization, Group, None, App]
):
    okta_organization, _, okta_app, _ = mock_application
    new_app_name = "new application name"
    await update_app_name(
        okta_app,
        new_app_name,
        okta_organization,
        {},
    )
    okta_app = await get_app(okta_organization, str(okta_app.id))
    assert okta_app.name == new_app_name


@pytest.mark.asyncio
async def test_maybe_delete_app(
    mock_application: tuple[OktaOrganization, Group, None, App]
):
    okta_organization, _, okta_app, _ = mock_application
    proposed_changes = await maybe_delete_app(
        True,
        okta_app,
        okta_organization,
        {},
    )
    assert proposed_changes[0].change_type == ProposedChangeType.DELETE
