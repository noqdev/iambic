from __future__ import annotations

import pytest

from iambic.plugins.v0_1_0.okta.iambic_plugin import OktaConfig, OktaOrganization


def test_okta_config():
    okta_org_1 = OktaOrganization(
        idp_name="example.org",
        org_url="https://example.okta.com/",
        api_token="fake-token",
    )

    okta_config = OktaConfig(organizations=[okta_org_1])
    assert okta_config.organizations[0].idp_name == "example.org"


def test_okta_config_with_repeated_idp_name():
    okta_org_1 = OktaOrganization(
        idp_name="example.org",
        org_url="https://example.okta.com/",
        api_token="fake-token",
    )

    okta_org_2 = OktaOrganization(
        idp_name="example.org",
        org_url="https://example.okta.com/",
        api_token="fake-token",
    )

    with pytest.raises(
        ValueError, match="idp_name must be unique within organizations: example.org"
    ):
        _ = OktaConfig(organizations=[okta_org_1, okta_org_2])
