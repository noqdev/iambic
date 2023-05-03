from __future__ import annotations

from typing import Any, Optional

from okta.client import Client as OktaClient
from pydantic import BaseModel, Extra, Field, SecretStr, validator

from iambic.core.iambic_enum import IambicManaged
from iambic.core.iambic_plugin import ProviderPlugin
from iambic.plugins.v0_1_0 import PLUGIN_VERSION
from iambic.plugins.v0_1_0.okta.app.models import OktaAppTemplate
from iambic.plugins.v0_1_0.okta.group.models import OktaGroupTemplate
from iambic.plugins.v0_1_0.okta.handlers import import_okta_resources, load
from iambic.plugins.v0_1_0.okta.user.models import OktaUserTemplate


class OktaOrganization(BaseModel):
    idp_name: str
    org_url: str
    api_token: SecretStr
    request_timeout: int = 60
    client: Any = None  # OktaClient
    iambic_managed: Optional[IambicManaged] = Field(
        IambicManaged.UNDEFINED,
        description="Controls the directionality of iambic changes",
    )

    class Config:
        arbitrary_types_allowed = True
        extra = Extra.forbid

    async def get_okta_client(self) -> OktaClient:
        if not self.client:
            self.client = OktaClient(
                {
                    "orgUrl": self.org_url,
                    "token": self.api_token.get_secret_value(),
                    "requestTimeout": self.request_timeout,
                    "rateLimit": {"maxRetries": 0},
                }
            )
        return self.client


class OktaConfig(BaseModel):
    organizations: list[OktaOrganization] = Field(
        description="A list of Okta organizations."
    )

    @validator(
        "organizations", allow_reuse=True
    )  # the need of allow_reuse is possibly related to how we handle inheritance
    def validate_okta_organizations(cls, orgs: list[OktaOrganization]):
        idp_name_set = set()
        for org in orgs:
            if org.idp_name in idp_name_set:
                raise ValueError(
                    f"idp_name must be unique within organizations: {org.idp_name}"
                )
            else:
                idp_name_set.add(org.idp_name)
        return orgs

    def get_organization(self, idp_name: str) -> OktaOrganization:
        for o in self.organizations:
            if o.idp_name == idp_name:
                return o
        raise Exception(f"Could not find organization for IDP {idp_name}")


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
