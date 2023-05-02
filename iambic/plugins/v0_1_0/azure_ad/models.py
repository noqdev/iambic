from __future__ import annotations

import asyncio
import os
import typing
from typing import TYPE_CHECKING, Any, Optional, Union

import aiohttp
import msal
from pydantic import BaseModel, Field, SecretStr

from iambic.core.context import ctx
from iambic.core.iambic_enum import IambicManaged
from iambic.core.logger import log
from iambic.core.models import BaseTemplate, TemplateChangeDetails

if TYPE_CHECKING:  # pragma: no cover
    from iambic.plugins.v0_1_0.azure_ad.iambic_plugin import AzureADConfig

    MappingIntStrAny = typing.Mapping[int | str, Any]
    AbstractSetIntStr = typing.AbstractSet[int | str]


class AzureADOrganization(BaseModel):
    idp_name: str
    tenant_id: str
    client_id: str
    client_secret: SecretStr
    request_timeout: int = 60
    client: Any = None
    access_token: str = ""
    iambic_managed: IambicManaged = IambicManaged.UNDEFINED
    require_user_mfa_on_create: bool = Field(
        False,
        description="If true, at next sign-in, the user must perform a multi-factor authentication (MFA) "
        "before being forced to change their password.",
    )

    class Config:
        arbitrary_types_allowed = True

    async def set_azure_access_token(self):  # pragma: no cover
        if not self.access_token:
            # initialize the client here
            self.client = msal.ConfidentialClientApplication(
                self.client_id,
                authority=f"https://login.microsoftonline.com/{self.tenant_id}",
                client_credential=self.client_secret.get_secret_value(),
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
    ) -> Union[dict, list, None]:  # pragma: no cover
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

                    if not resp.ok:
                        log.error(
                            "Azure AD request failed",
                            url=url,
                            org=self.idp_name,
                            message=await resp.text(),
                            status_code=resp.status,
                        )
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

    def dict(
        self,
        *,
        include: Optional[Union[AbstractSetIntStr, MappingIntStrAny]] = None,
        exclude: Optional[Union[AbstractSetIntStr, MappingIntStrAny]] = None,
        by_alias: bool = False,
        skip_defaults: Optional[bool] = None,
        exclude_unset: bool = False,
        exclude_defaults: bool = False,
        exclude_none: bool = False,
    ) -> "DictStrAny":  # noqa
        required_exclude = {"access_token", "client"}
        if not exclude:
            exclude = required_exclude
        elif isinstance(exclude, set):
            exclude.update(required_exclude)

        return super().dict(
            include=include,
            exclude=exclude,
            by_alias=by_alias,
            skip_defaults=skip_defaults,
            exclude_unset=exclude_unset,
            exclude_defaults=exclude_defaults,
            exclude_none=exclude_none,
        )


class AzureADTemplate(BaseTemplate):
    idp_name: str = Field(
        ...,
        description="Name of the identity provider that's associated with the resource",
    )

    @property
    def resource_id(self) -> str:
        return self.properties.resource_id

    async def apply(self, config: AzureADConfig) -> TemplateChangeDetails:
        tasks = []
        template_changes = TemplateChangeDetails(
            resource_id=self.resource_id,
            resource_type=self.template_type,
            template_path=self.file_path,
        )
        log_params = dict(
            resource_type=self.resource_type,
            resource_id=self.resource_id,
        )

        if self.iambic_managed == IambicManaged.IMPORT_ONLY:
            log_str = "Resource is marked as import only."
            log.info(log_str, **log_params)
            template_changes.proposed_changes = []
            return template_changes

        for azure_ad_organization in config.organizations:
            if azure_ad_organization.idp_name != self.idp_name:
                continue

            if ctx.execute:
                log_str = "Applying changes to resource."
            else:
                log_str = "Detecting changes for resource."
            log.info(log_str, idp_name=azure_ad_organization.idp_name, **log_params)
            tasks.append(self._apply_to_account(azure_ad_organization))

        account_changes = list(await asyncio.gather(*tasks))
        template_changes.extend_changes(account_changes)

        if template_changes.exceptions_seen:
            cmd_verb = "applying" if ctx.execute else "detecting"
            log.error(
                f"Error encountered when {cmd_verb} resource changes.",
                **log_params,
            )
        elif account_changes and ctx.execute:
            if self.deleted:
                self.delete()
                log.info(
                    "Successfully removed resource from all Azure AD organizations.",
                    **log_params,
                )
            else:
                log.info(
                    "Successfully applied resource changes to all Azure AD organizations.",
                    **log_params,
                )
        elif account_changes:
            log.info(
                "Successfully detected required resource changes on all Azure AD organizations.",
                **log_params,
            )
        else:
            log.debug(
                "No changes detected for resource on any Azure AD organization.",
                **log_params,
            )

        return template_changes

    def set_default_file_path(self, repo_dir: str, file_name: str):
        if not file_name.endswith(".yaml"):
            file_name = f"{file_name}.yaml"

        self.file_path = os.path.expanduser(
            os.path.join(
                repo_dir,
                f"resources/{self.resource_type.replace(':', '/')}/{self.idp_name}/{file_name}",
            )
        )
