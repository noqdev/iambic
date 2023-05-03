import pytest
from pydantic import SecretStr

from iambic.core.iambic_enum import IambicManaged
from iambic.plugins.v0_1_0.azure_ad.models import AzureADOrganization


@pytest.mark.parametrize("exclude", [None, {"other"}])
def test_organization_to_dict(exclude):
    organization = AzureADOrganization(
        idp_name="idp_name",
        tenant_id="tenant_id",
        client_id="client_id",
        client_secret=SecretStr("client_secret"),
    )  # type: ignore

    assert organization.dict(exclude=exclude) == dict(
        idp_name="idp_name",
        tenant_id="tenant_id",
        client_id="client_id",
        client_secret=SecretStr("client_secret"),
        request_timeout=60,
        iambic_managed=IambicManaged.UNDEFINED,
        require_user_mfa_on_create=False,
    )  # type: ignore
