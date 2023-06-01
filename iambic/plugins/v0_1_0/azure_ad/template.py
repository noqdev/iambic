from __future__ import annotations

from iambic.core.template import TemplateMixin
from iambic.plugins.v0_1_0.azure_ad.group.models import (
    AzureActiveDirectoryGroupTemplate,
)
from iambic.plugins.v0_1_0.azure_ad.user.models import AzureActiveDirectoryUserTemplate


class AzureAdTemplateMixin(TemplateMixin):
    templates = [AzureActiveDirectoryGroupTemplate, AzureActiveDirectoryUserTemplate]
