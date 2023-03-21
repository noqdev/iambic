from __future__ import annotations

import json
from collections import defaultdict, namedtuple
from test.plugins.v0_1_0.okta.fake_okta_client import FakeOktaClient

import okta.models
import pytest
from okta.errors.okta_api_error import OktaAPIError

from iambic.core.exceptions import RateLimitException
from iambic.plugins.v0_1_0.okta.exceptions import UserProfileNotUpdatableYet
from iambic.plugins.v0_1_0.okta.iambic_plugin import OktaOrganization
from iambic.plugins.v0_1_0.okta.utils import generate_user_profile, handle_okta_fn


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
async def test_generate_user_profile():

    user = okta.models.User()
    user.profile = okta.models.user_profile.UserProfile()
    user.profile.login = "example_user"

    profile_dict = await generate_user_profile(user)
    # no none value should be in the returned dictionary
    assert [v for v in profile_dict.values() if v is None] == []
    assert profile_dict["login"] == "example_user"


@pytest.mark.asyncio
async def test_handle_okta_fn_normal_flow():
    async def sample_fn(*args, **kwargs):
        return ("sample_response", None)

    args = ["hello", "world"]
    kwargs = {"keyword_1": "keyword_1"}
    response = await handle_okta_fn(sample_fn, *args, **kwargs)
    assert response == ("sample_response", None)


ResponseDetails = namedtuple("ResponseDetails", ["status", "headers"])


@pytest.mark.asyncio
async def test_handle_okta_fn_rate_limit():
    async def sample_fn(*args, **kwargs):
        response_body = defaultdict(list)
        response_body["errorCode"] = "E0000047"
        response_body["errorSummary"] = "summary"
        okta_api_error = OktaAPIError(
            "https://fake-url.com",
            ResponseDetails(status=500, headers={}),
            response_body,
        )
        return ("sample_response", okta_api_error)

    args = ["hello", "world"]
    kwargs = {"keyword_1": "keyword_1"}
    with pytest.raises(RateLimitException, match="summary"):
        await handle_okta_fn(sample_fn, *args, **kwargs)


@pytest.mark.asyncio
async def test_handle_okta_fn_user_not_provisioned():
    async def sample_fn(*args, **kwargs):
        response_body = defaultdict(list)
        response_body["errorCode"] = "E0000112"
        response_body["errorSummary"] = "summary"
        okta_api_error = OktaAPIError(
            "https://fake-url.com",
            ResponseDetails(status=500, headers={}),
            response_body,
        )
        return ("sample_response", okta_api_error)

    args = ["hello", "world"]
    kwargs = {"keyword_1": "keyword_1"}
    with pytest.raises(
        UserProfileNotUpdatableYet,
        match="Unable to update profile, user is not fully provisioned",
    ):
        await handle_okta_fn(sample_fn, *args, **kwargs)


@pytest.mark.asyncio
async def test_handle_okta_fn_generic_json_error():

    json_error_string = json.dumps({"errorCode": "E0000047"})

    async def sample_fn(*args, **kwargs):
        response_body = defaultdict(list)
        response_body["errorCode"] = "E0000047"
        response_body["errorSummary"] = "summary"
        return ("sample_response", json_error_string)

    args = ["hello", "world"]
    kwargs = {"keyword_1": "keyword_1"}
    with pytest.raises(RateLimitException, match=json_error_string):
        await handle_okta_fn(sample_fn, *args, **kwargs)
