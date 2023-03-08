from __future__ import annotations

from typing import Any, Optional

import aiohttp
import msal
from azure.identity.aio import ClientSecretCredential
from kiota_authentication_azure.azure_identity_authentication_provider import (
    AzureIdentityAuthenticationProvider,
)
from msgraph import GraphRequestAdapter, GraphServiceClient
from pydantic import BaseModel, Field

from iambic.core.iambic_plugin import ProviderPlugin
from iambic.core.logger import log
from iambic.core.models import BaseTemplate, TemplateChangeDetails
from iambic.plugins.v0_1_0 import PLUGIN_VERSION
from iambic.plugins.v0_1_0.azure_ad.group.models import AzureADGroupTemplate
from iambic.plugins.v0_1_0.azure_ad.handlers import (
    apply,
    import_azure_ad_resources,
    load,
)


class AzureADOrganization(BaseModel):
    idp_name: str
    tenant_id: str
    client_id: str
    client_secret: str
    request_timeout: int = 60
    client: Any = None
    access_token: Optional[str] = None

    class Config:
        arbitrary_types_allowed = True

    async def get_azure_ad_client(self):
        if not self.client:
            credentials = ClientSecretCredential(
                tenant_id=self.tenant_id,
                client_id=self.client_id,
                client_secret=self.client_secret,
            )
            auth_provider = AzureIdentityAuthenticationProvider(credentials)
            adapter = GraphRequestAdapter(auth_provider)
            self.client = GraphServiceClient(adapter)
        return self.client

    async def make_request(self, endpoint):
        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }
            async with session.get(
                f"https://graph.microsoft.com/v1.0/{endpoint}", headers=headers
            ) as resp:
                data = await resp.json()
                return data


class AzureADConfig(BaseModel):
    organizations: list[AzureADOrganization] = Field(
        description="A list of Azure Active Directory organizations."
    )


IAMBIC_PLUGIN = ProviderPlugin(
    config_name="azure_ad",
    version=PLUGIN_VERSION,
    provider_config=AzureADConfig,
    async_apply_callable=apply,
    async_import_callable=import_azure_ad_resources,
    async_load_callable=load,
    requires_secret=True,
    templates=[AzureADGroupTemplate],
)
