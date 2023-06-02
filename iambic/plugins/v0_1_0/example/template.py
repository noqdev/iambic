from __future__ import annotations

from iambic.core.template import ConfigMixin
from iambic.plugins.v0_1_0.example.local_database.models import (
    ExampleLocalDatabaseTemplate,
)
from iambic.plugins.v0_1_0.example.local_file.models import (
    ExampleLocalFileMultiAccountTemplate,
    ExampleLocalFileTemplate,
)


class ExampleConfigMixin(ConfigMixin):
    templates = [
        ExampleLocalFileTemplate,
        ExampleLocalFileMultiAccountTemplate,
        ExampleLocalDatabaseTemplate,
    ]
