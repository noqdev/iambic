from __future__ import annotations

from pydantic import BaseModel, Field

from iambic.core.iambic_plugin import ProviderPlugin
from iambic.plugins.v0_1_0 import PLUGIN_VERSION
from iambic.plugins.v0_1_0.azure_ad.group.models import GroupTemplate
from iambic.plugins.v0_1_0.azure_ad.handlers import import_azure_ad_resources, load
from iambic.plugins.v0_1_0.azure_ad.models import AzureADOrganization
from iambic.plugins.v0_1_0.azure_ad.user.models import UserTemplate


class AzureADConfig(BaseModel):
    organizations: list[AzureADOrganization] = Field(
        description="A list of Azure Active Directory organizations."
    )

    def get_organization(self, idp_name: str) -> AzureADOrganization:
        for o in self.organizations:
            if o.idp_name == idp_name:
                return o
        raise Exception(f"Could not find organization for IDP {idp_name}")


IAMBIC_PLUGIN = ProviderPlugin(
    config_name="azure_ad",
    version=PLUGIN_VERSION,
    provider_config=AzureADConfig,
    async_import_callable=import_azure_ad_resources,
    async_load_callable=load,
    requires_secret=True,
    templates=[GroupTemplate, UserTemplate],
)