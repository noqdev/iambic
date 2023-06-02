from __future__ import annotations

from iambic.core.template import ConfigMixin
from iambic.plugins.v0_1_0.google_workspace.group.models import (
    GoogleWorkspaceGroupTemplate,
)


class GoogleWorkspaceConfigMixin(ConfigMixin):
    templates = [
        GoogleWorkspaceGroupTemplate,
    ]
