from __future__ import annotations

from test.plugins.v0_1_0.okta.test_utils import (  # noqa: F401 # intentional for mocks
    mock_okta_organization,
)

import okta.models
import pytest

from iambic.core.context import ctx
import iambic.plugins.v0_1_0.okta.models
from iambic.core.models import ProposedChangeType
from iambic.plugins.v0_1_0.okta.iambic_plugin import OktaOrganization
from iambic.plugins.v0_1_0.okta.user.models import OktaUserTemplate, UserProperties
from iambic.plugins.v0_1_0.okta.user.utils import (
    change_user_status,
    create_user,
    get_user,
    maybe_deprovision_user,
    update_user_profile,
    update_user_status,
)
from iambic.plugins.v0_1_0.okta.models import UserStatus


@pytest.mark.asyncio
async def test_get_user_by_username(
    mock_okta_organization: OktaOrganization,  # noqa: F811 # intentional for mocks
):
    # Have to create user before getting it
    username = "example_username"
    idp_name = "example.org"
    user_properties = UserProperties(username=username, profile={"login": username})
    template = OktaUserTemplate(
        file_path="example", idp_name=idp_name, properties=user_properties
    )
    okta_user = await create_user(
        template,
        mock_okta_organization,
    )

    # Test the get_user method
    okta_user = await get_user(username, None, mock_okta_organization)
    assert okta_user.username == username


@pytest.mark.asyncio
async def test_get_user_by_user_id(
    mock_okta_organization: OktaOrganization,  # noqa: F811 # intentional for mocks
):
    # Have to create user before getting it
    username = "example_username"
    idp_name = "example.org"
    user_properties = UserProperties(username=username, profile={"login": username})
    template = OktaUserTemplate(
        file_path="example", idp_name=idp_name, properties=user_properties
    )
    init_okta_user = await create_user(template, mock_okta_organization)

    # Test the get_user method
    okta_user = await get_user(username, init_okta_user.user_id, mock_okta_organization)
    assert init_okta_user.user_id == okta_user.user_id


@pytest.mark.asyncio
async def test_create_user(
    mock_okta_organization: OktaOrganization,  # noqa: F811 # intentional for mocks
):
    username = "example_username"
    idp_name = "example.org"
    user_properties = UserProperties(username=username, profile={"login": username})
    template = OktaUserTemplate(
        file_path="example", idp_name=idp_name, properties=user_properties
    )
    okta_user = await create_user(
        template,
        mock_okta_organization,
    )
    assert okta_user.username == username


@pytest.mark.asyncio
async def test_change_user_status(
    mock_okta_organization: OktaOrganization,  # noqa: F811 # intentional for mocks
):
    # Have to create user before getting it
    username = "example_username"
    idp_name = "example.org"
    user_properties = UserProperties(username=username, profile={"login": username})
    template = OktaUserTemplate(
        file_path="example", idp_name=idp_name, properties=user_properties
    )
    okta_user = await create_user(
        template,
        mock_okta_organization,
    )

    input_user = iambic.plugins.v0_1_0.okta.models.User(
        idp_name=idp_name,
        username=username,
        user_id=okta_user.user_id,
        status="suspended",
        profile={},
    )
    proposed_changes = await change_user_status(
        input_user,
        okta.models.UserStatus.ACTIVE,
        mock_okta_organization,
    )
    assert proposed_changes[0].change_type == ProposedChangeType.UPDATE
    assert proposed_changes[0].resource_type == input_user.resource_type
    assert proposed_changes[0].resource_id == input_user.user_id
    assert proposed_changes[0].attribute == "status"
    assert proposed_changes[0].new_value == okta.models.UserStatus.ACTIVE
    assert input_user.status == okta.models.UserStatus.ACTIVE


@pytest.mark.asyncio
async def test_update_user_profile(
    mock_okta_organization: OktaOrganization,  # noqa: F811 # intentional for mocks
):
    # Have to create user before getting it
    username = "example_username"
    idp_name = "example.org"
    user_properties = UserProperties(username=username, profile={"login": username})
    template = OktaUserTemplate(
        file_path="example", idp_name=idp_name, properties=user_properties
    )
    okta_user = await create_user(
        template,
        mock_okta_organization,
    )

    proposed_user = UserProperties(username=username, profile={})
    input_user = iambic.plugins.v0_1_0.okta.models.User(
        idp_name=idp_name,
        username=username,
        user_id=okta_user.user_id,
        status="suspended",
        profile={},
    )
    input_profile = {"nickname": "example"}
    proposed_changes = await update_user_profile(
        proposed_user,
        input_user,
        input_profile,
        mock_okta_organization,
        {},
    )
    assert proposed_changes[0].change_type == ProposedChangeType.UPDATE
    assert proposed_changes[0].resource_type == input_user.resource_type
    assert proposed_changes[0].resource_id == input_user.user_id
    assert proposed_changes[0].attribute == "profile"
    assert proposed_changes[0].change_summary == {
        "current_profile": input_user.profile,
        "new_profile": input_profile,
    }


class TestUpdateUserStatus:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "transition",
        [
            (UserStatus.provisioned, UserStatus.deprovisioned),
            (UserStatus.active, UserStatus.deprovisioned),
            (UserStatus.suspended, UserStatus.active),
            (UserStatus.active, UserStatus.suspended),
            (UserStatus.staged, UserStatus.active),
            (UserStatus.deprovisioned, UserStatus.active),
            (UserStatus.staged, UserStatus.provisioned),
            (UserStatus.deprovisioned, UserStatus.provisioned),
            (UserStatus.provisioned, UserStatus.active),
            (UserStatus.locked_out, UserStatus.active),
            (UserStatus.provisioned, UserStatus.recovery),
            (UserStatus.provisioned, UserStatus.password_expired),
        ],
    )
    async def test_update_user_status(
        self,
        mock_okta_organization: OktaOrganization,  # noqa: F811 # intentional for mocks
        mock_ctx,
        transition,
    ):
        # Have to create user before getting it
        username = "example_username"
        idp_name = "example.org"
        user_properties = UserProperties(
            username=username,
            profile={"login": username},
            status=transition[0].value,
        )  # type: ignore
        template = OktaUserTemplate(
            file_path="example", idp_name=idp_name, properties=user_properties
        )  # type: ignore

        okta_user = await create_user(
            template,
            mock_okta_organization,
        )
        okta_user.status = transition[0]

        mock_ctx(eval_only=True)
        proposed_changes = await update_user_status(
            okta_user,
            transition[1].value,
            mock_okta_organization,
            {},
        )

        print(proposed_changes)
        assert proposed_changes[0].change_type == ProposedChangeType.UPDATE
        assert proposed_changes[0].resource_type == okta_user.resource_type
        assert proposed_changes[0].resource_id == okta_user.user_id
        assert proposed_changes[0].attribute == "status"
        assert proposed_changes[0].change_summary == {
            "current_status": transition[0].value,
            "proposed_status": transition[1].value,
        }

    @pytest.mark.asyncio
    async def test_update_user_status_when_deleted(
        self,
        mock_okta_organization: OktaOrganization,  # noqa: F811 # intentional for mocks
        mock_ctx,
    ):

        username = "example_username"
        idp_name = "example.org"
        user_properties = UserProperties(
            username=username,
            profile={"login": username},
            status=UserStatus.deprovisioned.value,
        )  # type: ignore

        template = OktaUserTemplate(
            file_path="example",
            idp_name=idp_name,
            properties=user_properties,
            deleted=True,
        )  # type: ignore

        okta_user = await create_user(
            template,
            mock_okta_organization,
        )
        okta_user.deleted = True

        mock_ctx(eval_only=True)
        proposed_changes = await update_user_status(
            okta_user,
            UserStatus.provisioned.value,
            mock_okta_organization,
            {},
        )

        assert proposed_changes == []


@pytest.mark.asyncio
async def test_maybe_deprovision_user(
    mock_okta_organization: OktaOrganization,  # noqa: F811 # intentional for mocks
):
    # Have to create user before getting it
    username = "example_username"
    idp_name = "example.org"
    user_properties = UserProperties(username=username, profile={"login": username})
    template = OktaUserTemplate(
        file_path="example", idp_name=idp_name, properties=user_properties
    )
    okta_user = await create_user(
        template,
        mock_okta_organization,
    )

    input_user = iambic.plugins.v0_1_0.okta.models.User(
        idp_name=idp_name,
        username=username,
        user_id=okta_user.user_id,
        status="suspended",
        profile={},
    )
    proposed_changes = await maybe_deprovision_user(
        True,
        input_user,
        mock_okta_organization,
        {},
    )
    assert proposed_changes[0].change_type == ProposedChangeType.DELETE
    assert proposed_changes[0].resource_type == input_user.resource_type
    assert proposed_changes[0].resource_id == input_user.user_id
    assert proposed_changes[0].attribute == "user"
    assert proposed_changes[0].change_summary == {
        "user": input_user.username,
    }
