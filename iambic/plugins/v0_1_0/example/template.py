from __future__ import annotations

from iambic.core.template import TemplateMixin
from iambic.plugins.v0_1_0.example.local_database.models import (
    ExampleLocalDatabaseTemplate,
)
from iambic.plugins.v0_1_0.example.local_file.models import (
    ExampleLocalFileMultiAccountTemplate,
    ExampleLocalFileTemplate,
)


class ExampleTemplateMixin(TemplateMixin):
    templates = [
        ExampleLocalFileTemplate,
        ExampleLocalFileMultiAccountTemplate,
        ExampleLocalDatabaseTemplate,
    ]
