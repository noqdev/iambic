from typing import Any

from iambic.core.models import BaseTemplate


class CloudControlBaseTemplate(BaseTemplate):
    template_type: str
    properties: Any
