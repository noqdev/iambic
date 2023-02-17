from __future__ import annotations

from typing import Any

import msal
from pydantic import BaseModel, Field

from iambic.core.iambic_plugin import ProviderPlugin
from iambic.plugins.v0_1_0 import PLUGIN_VERSION
from iambic.plugins.v0_1_0.azure_ad.handlers import import_azure_ad_resources, load


class AzureADOrganization(BaseModel):
    idp_name: str
    tenant_id: str
    client_id: str
    client_secret: str
    request_timeout: int = 60
    client: Any = None

    class Config:
        arbitrary_types_allowed = True

    async def get_azure_ad_client(self):
        if not self.client:
            # initialize the client here
            self.client = msal.ConfidentialClientApplication(
                self.client_id,
                authority=f"https://login.microsoftonline.com/{self.tenant_id}",
                client_credential=self.client_secret,
            )
        return self.client


class AzureADConfig(BaseModel):
    organizations: list[AzureADOrganization] = Field(
        description="A list of Azure Active Directory organizations."
    )


IAMBIC_PLUGIN = ProviderPlugin(
    config_name="azure_ad",
    version=PLUGIN_VERSION,
    provider_config=AzureADConfig,
    requires_secret=True,
    async_import_callable=import_azure_ad_resources,
    async_load_callable=load,
)
