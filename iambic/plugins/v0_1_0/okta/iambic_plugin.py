from __future__ import annotations

from typing import Any

from iambic.core.iambic_plugin import ProviderPlugin
from iambic.plugins.v0_1_0 import PLUGIN_VERSION
from iambic.plugins.v0_1_0.okta.app.models import OktaAppTemplate
from iambic.plugins.v0_1_0.okta.group.models import OktaGroupTemplate
from iambic.plugins.v0_1_0.okta.handlers import import_okta_resources, load
from iambic.plugins.v0_1_0.okta.user.models import OktaUserTemplate
from pydantic import BaseModel, Field

from okta.client import Client as OktaClient


class OktaOrganization(BaseModel):
    idp_name: str
    org_url: str
    api_token: str
    request_timeout: int = 60
    client: Any = None  # OktaClient

    class Config:
        arbitrary_types_allowed = True

    async def get_okta_client(self):
        if not self.client:
            self.client = OktaClient(
                {
                    "orgUrl": self.org_url,
                    "token": self.api_token,
                    "requestTimeout": self.request_timeout,
                    "rateLimit": {"maxRetries": 0},
                }
            )
        return self.client


class OktaConfig(BaseModel):
    organizations: list[OktaOrganization] = Field(
        description="A list of Okta organizations."
    )


IAMBIC_PLUGIN = ProviderPlugin(
    config_name="okta",
    version=PLUGIN_VERSION,
    provider_config=OktaConfig,
    requires_secret=True,
    async_import_callable=import_okta_resources,
    async_load_callable=load,
    templates=[
        OktaAppTemplate,
        OktaGroupTemplate,
        OktaUserTemplate,
    ],
)
