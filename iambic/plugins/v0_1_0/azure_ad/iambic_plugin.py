from __future__ import annotations

import asyncio
from typing import Any

import aiohttp
import msal
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
    access_token: str = ""

    class Config:
        arbitrary_types_allowed = True

    async def set_azure_access_token(self):
        if not self.access_token:
            # initialize the client here
            self.client = msal.ConfidentialClientApplication(
                self.client_id,
                authority=f"https://login.microsoftonline.com/{self.tenant_id}",
                client_credential=self.client_secret,
            )
            token_result = self.client.acquire_token_for_client(
                ["https://graph.microsoft.com/.default"]
            )
            if "access_token" in token_result:
                self.access_token = token_result["access_token"]
            else:
                raise Exception("Access token was not successfully acquired")
        return self.access_token

    async def make_request(self, endpoint, params=None):
        await self.set_azure_access_token()
        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }
            url = f"https://graph.microsoft.com/v1.0/{endpoint}"
            while url:
                async with session.get(url, headers=headers, params=params) as resp:
                    if resp.status == 429:
                        # Handle rate limit exceeded error
                        retry_after = int(resp.headers.get("Retry-After", 1))
                        await asyncio.sleep(retry_after)
                        continue
                    data = await resp.json()
                    if resp.status >= 400:
                        # Handle other errors
                        error_message = data.get("error", {}).get(
                            "message", "Unknown error"
                        )
                        raise Exception(f"{resp.status}: {error_message}")
                    if "@odata.nextLink" in data:
                        # Handle pagination
                        url = data["@odata.nextLink"]
                        params = (
                            None  # Clear params since they only apply to the first page
                        )
                    else:
                        url = None
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
