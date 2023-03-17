from __future__ import annotations

from collections import defaultdict, namedtuple

import pytest

import iambic.plugins.v0_1_0.okta.models
import okta.models
from iambic.core.context import ExecutionContext
from iambic.core.models import ProposedChangeType
from iambic.plugins.v0_1_0.okta.iambic_plugin import OktaOrganization
from iambic.plugins.v0_1_0.okta.user.models import (
    OktaUserTemplate,
    OktaUserTemplateProperties,
)
from iambic.plugins.v0_1_0.okta.user.utils import (  # update_user_attribute,
    change_user_status,
    create_user,
    get_user,
    maybe_deprovision_user,
    update_user_profile,
)
from okta.errors.okta_api_error import OktaAPIError

ResponseDetails = namedtuple("ResponseDetails", ["status", "headers"])


class FakeOktaClient:
    def __init__(self):
        # state management
        self.auto_increment_id = 0
        self.username_to_user = {}
        # user_id is a string
        self.user_id_to_user = {}

    async def get_user(self, *args, **kwargs):
        login = args[0]
        if login in self.username_to_user:
            user = self.username_to_user[login]
            return (user, ResponseDetails(status=200, headers={}), defaultdict(list))
        elif login in self.user_id_to_user:
            user = self.user_id_to_user[login]
            return (user, ResponseDetails(status=200, headers={}), defaultdict(list))
        else:
            error_dict = defaultdict(list)
            error_dict["errorCode"] = "E0000007"
            response = ResponseDetails(status=400, headers={})
            return (
                None,
                response,
                OktaAPIError("https//example.okta.com/", response, error_dict),
            )

    async def create_user(self, config: dict):
        login = config["profile"]["login"]

        if login in self.username_to_user:
            error_dict = defaultdict(list)
            error_dict["errorCode"] = "E0000007"
            response = ResponseDetails(status=400, headers={})
            return (
                None,
                response,
                OktaAPIError("https//example.okta.com/", response, error_dict),
            )
        else:
            user = okta.models.User(config)
            user.profile = okta.models.user_profile.UserProfile(config["profile"])
            user.login = config["profile"]["login"]
            user.id = self.auto_increment_id
            user.status = okta.models.UserStatus.ACTIVE
            self.auto_increment_id += 1
            self.username_to_user[user.login] = user
            self.user_id_to_user[f"{user.id}"] = user
            return (user, ResponseDetails(status=200, headers={}), defaultdict(list))

    async def update_user(self, user_id, properties: dict):
        login = user_id
        if login in self.user_id_to_user:
            user = okta.models.User()
            if isinstance(properties, okta.models.User):
                input_user: okta.models.User = properties
                user.profile = input_user.profile
            else:
                if "status" in properties:
                    user.status = properties["status"]
                user.profile = okta.models.user_profile.UserProfile(properties)
                user.profile.login = login
                user.id = user_id
            return (user, ResponseDetails(status=200, headers={}), defaultdict(list))
        else:
            error_dict = defaultdict(list)
            error_dict["errorCode"] = "E0000007"
            response = ResponseDetails(status=400, headers={})
            return (
                None,
                response,
                OktaAPIError("https//example.okta.com/", response, error_dict),
            )

    async def deactivate_or_delete_user(self, user_id):
        user = self.user_id_to_user[user_id]
        del self.username_to_user[user.profile.login]
        del self.user_id_to_user[f"{user.id}"]
        return (ResponseDetails(status=200, headers={}), defaultdict(list))


@pytest.fixture
def mock_okta_organization() -> OktaOrganization:
    idp_name = "example.org"
    okta_organization = OktaOrganization(
        idp_name=idp_name,
        org_url="https://example.org.okta.com/",
        api_token="fake_token",
    )
    okta_organization.client = FakeOktaClient()
    return okta_organization


@pytest.mark.asyncio
async def test_get_user_by_username(mock_okta_organization: OktaOrganization):

    # Have to create user before getting it
    username = "example_username"
    idp_name = "example.org"
    user_properties = OktaUserTemplateProperties(
        username=username, idp_name=idp_name, profile={"login": username}
    )
    template = OktaUserTemplate(file_path="example", properties=user_properties)
    context = ExecutionContext()
    context.eval_only = False
    okta_user = await create_user(template, mock_okta_organization, context)

    # Test the get_user method
    okta_user = await get_user(username, None, mock_okta_organization)
    assert okta_user.username == username


@pytest.mark.asyncio
async def test_get_user_by_user_id(mock_okta_organization: OktaOrganization):

    # Have to create user before getting it
    username = "example_username"
    idp_name = "example.org"
    user_properties = OktaUserTemplateProperties(
        username=username, idp_name=idp_name, profile={"login": username}
    )
    template = OktaUserTemplate(file_path="example", properties=user_properties)
    context = ExecutionContext()
    context.eval_only = False
    okta_user = await create_user(template, mock_okta_organization, context)

    # Test the get_user method
    okta_user = await get_user(username, okta_user.user_id, mock_okta_organization)
    assert okta_user.user_id == okta_user.user_id


@pytest.mark.asyncio
async def test_create_user(mock_okta_organization: OktaOrganization):
    username = "example_username"
    idp_name = "example.org"
    user_properties = OktaUserTemplateProperties(
        username=username, idp_name=idp_name, profile={"login": username}
    )
    template = OktaUserTemplate(file_path="example", properties=user_properties)
    context = ExecutionContext()
    context.eval_only = False
    okta_user = await create_user(template, mock_okta_organization, context)
    assert okta_user.username == username


@pytest.mark.asyncio
async def test_change_user_status(mock_okta_organization: OktaOrganization):

    # Have to create user before getting it
    username = "example_username"
    idp_name = "example.org"
    user_properties = OktaUserTemplateProperties(
        username=username, idp_name=idp_name, profile={"login": username}
    )
    template = OktaUserTemplate(file_path="example", properties=user_properties)
    context = ExecutionContext()
    context.eval_only = False
    okta_user = await create_user(template, mock_okta_organization, context)

    input_user = iambic.plugins.v0_1_0.okta.models.User(
        idp_name=idp_name,
        username=username,
        user_id=okta_user.user_id,
        status="suspended",
        profile={},
    )
    context = ExecutionContext()
    context.eval_only = False
    proposed_changes = await change_user_status(
        input_user, okta.models.UserStatus.ACTIVE, mock_okta_organization, context
    )
    assert proposed_changes[0].change_type == ProposedChangeType.UPDATE
    assert proposed_changes[0].resource_type == input_user.resource_type
    assert proposed_changes[0].resource_id == input_user.user_id
    assert proposed_changes[0].attribute == "status"
    assert proposed_changes[0].new_value == okta.models.UserStatus.ACTIVE
    assert input_user.status == okta.models.UserStatus.ACTIVE


@pytest.mark.asyncio
async def test_update_user_profile(mock_okta_organization: OktaOrganization):

    # Have to create user before getting it
    username = "example_username"
    idp_name = "example.org"
    user_properties = OktaUserTemplateProperties(
        username=username, idp_name=idp_name, profile={"login": username}
    )
    template = OktaUserTemplate(file_path="example", properties=user_properties)
    context = ExecutionContext()
    context.eval_only = False
    okta_user = await create_user(template, mock_okta_organization, context)

    proposed_user = OktaUserTemplateProperties(
        username=username, idp_name=idp_name, profile={}
    )
    input_user = iambic.plugins.v0_1_0.okta.models.User(
        idp_name=idp_name,
        username=username,
        user_id=okta_user.user_id,
        status="suspended",
        profile={},
    )
    input_profile = {"nickname": "example"}
    context = ExecutionContext()
    context.eval_only = False
    proposed_changes = await update_user_profile(
        proposed_user, input_user, input_profile, mock_okta_organization, {}, context
    )
    assert proposed_changes[0].change_type == ProposedChangeType.UPDATE
    assert proposed_changes[0].resource_type == input_user.resource_type
    assert proposed_changes[0].resource_id == input_user.user_id
    assert proposed_changes[0].attribute == "profile"
    assert proposed_changes[0].change_summary == {
        "current_profile": input_user.profile,
        "new_profile": input_profile,
    }


# @pytest.mark.asyncio
# async def test_update_user_attribute(mock_okta_organization: OktaOrganization):
#     username = "example_username"
#     user_id = "example_user_id"
#     idp_name = "example.org"
#     proposed_user = OktaUserTemplateProperties(username=username, idp_name=idp_name, profile={})
#     input_user = iambic.plugins.v0_1_0.okta.models.User(idp_name=idp_name, username=username, user_id=user_id, status="suspended", profile={})
#     input_profile = {"nickname": "example"}
#     context= ExecutionContext()
#     context.eval_only = False
#     input_attribute_name = "fullname"
#     input_attribute_value = "John Doe"
#     proposed_changes = await update_user_attribute(input_user, input_attribute_value, input_attribute_name, mock_okta_organization, {}, context)
#     assert proposed_changes[0].change_type == ProposedChangeType.UPDATE
#     assert proposed_changes[0].resource_type == input_user.resource_type
#     assert proposed_changes[0].resource_id == input_user.user_id
#     assert proposed_changes[0].attribute == input_attribute_name
#     assert proposed_changes[0].new_value == input_attribute_value


@pytest.mark.asyncio
async def test_maybe_deprovision_user(mock_okta_organization: OktaOrganization):

    # Have to create user before getting it
    username = "example_username"
    idp_name = "example.org"
    user_properties = OktaUserTemplateProperties(
        username=username, idp_name=idp_name, profile={"login": username}
    )
    template = OktaUserTemplate(file_path="example", properties=user_properties)
    context = ExecutionContext()
    context.eval_only = False
    okta_user = await create_user(template, mock_okta_organization, context)

    input_user = iambic.plugins.v0_1_0.okta.models.User(
        idp_name=idp_name,
        username=username,
        user_id=okta_user.user_id,
        status="suspended",
        profile={},
    )
    context = ExecutionContext()
    context.eval_only = False
    proposed_changes = await maybe_deprovision_user(
        True, input_user, mock_okta_organization, {}, context
    )
    assert proposed_changes[0].change_type == ProposedChangeType.DELETE
    assert proposed_changes[0].resource_type == input_user.resource_type
    assert proposed_changes[0].resource_id == input_user.user_id
    assert proposed_changes[0].attribute == "user"
    assert proposed_changes[0].change_summary == {
        "user": input_user.username,
    }
