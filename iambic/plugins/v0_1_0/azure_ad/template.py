from __future__ import annotations

from iambic.core.template import ConfigMixin
from iambic.plugins.v0_1_0.azure_ad.group.models import (
    AzureActiveDirectoryGroupTemplate,
)
from iambic.plugins.v0_1_0.azure_ad.user.models import AzureActiveDirectoryUserTemplate


class AzureAdConfigMixin(ConfigMixin):
    templates = [AzureActiveDirectoryGroupTemplate, AzureActiveDirectoryUserTemplate]
