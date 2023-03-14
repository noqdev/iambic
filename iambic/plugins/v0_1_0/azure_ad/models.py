from __future__ import annotations

import asyncio
from typing import Any, Union

import aiohttp
import msal
from pydantic import BaseModel

from iambic.core.iambic_enum import IambicManaged


class AzureADOrganization(BaseModel):
    idp_name: str
    tenant_id: str
    client_id: str
    client_secret: str
    request_timeout: int = 60
    client: Any = None
    access_token: str = ""
    iambic_managed: IambicManaged = IambicManaged.DISABLED

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

    async def _make_request(
        self, request_type: str, endpoint: str, **kwargs
    ) -> Union[dict, list, None]:
        await self.set_azure_access_token()

        response = []
        is_list = bool(request_type == "list")
        if is_list:
            request_type = "get"

        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            }
            url = f"https://graph.microsoft.com/v1.0/{endpoint}"
            while url:
                async with getattr(session, request_type)(
                    url, headers=headers, **kwargs
                ) as resp:
                    if resp.status == 429:
                        # Handle rate limit exceeded error
                        retry_after = int(resp.headers.get("Retry-After", "1"))
                        await asyncio.sleep(retry_after)
                        continue

                    resp.raise_for_status()

                    try:
                        data = await resp.json()
                    except aiohttp.ContentTypeError:
                        return

                    if is_list:
                        response.extend(data["value"])
                        if "@odata.nextLink" in data:
                            url = data["@odata.nextLink"]
                            kwargs.pop(
                                "params", None
                            )  # Clear params since they only apply to the first page
                        else:
                            return response
                    else:
                        return data

    async def post(self, endpoint, **kwargs):
        return await self._make_request("post", endpoint, **kwargs)

    async def get(self, endpoint, **kwargs):
        return await self._make_request("get", endpoint, **kwargs)

    async def list(self, endpoint, **kwargs):
        return await self._make_request("list", endpoint, **kwargs)

    async def patch(self, endpoint, **kwargs):
        return await self._make_request("patch", endpoint, **kwargs)

    async def delete(self, endpoint, **kwargs):
        return await self._make_request("delete", endpoint, **kwargs)
