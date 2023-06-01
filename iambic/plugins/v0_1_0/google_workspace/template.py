from __future__ import annotations

from iambic.core.template import TemplateMixin
from iambic.plugins.v0_1_0.google_workspace.group.models import (
    GoogleWorkspaceGroupTemplate,
)


class GoogleWorkspaceTemplateMixin(TemplateMixin):
    templates = [
        GoogleWorkspaceGroupTemplate,
    ]
