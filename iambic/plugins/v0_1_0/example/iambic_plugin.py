from __future__ import annotations

from pydantic import BaseModel

from iambic.core.iambic_plugin import ProviderPlugin
from iambic.plugins.v0_1_0 import PLUGIN_VERSION
from iambic.plugins.v0_1_0.example.handlers import import_example_resources, load
from iambic.plugins.v0_1_0.example.local_database.models import (
    ExampleLocalDatabaseTemplate,
)
from iambic.plugins.v0_1_0.example.local_file.models import (
    ExampleLocalFileMultiAccountTemplate,
    ExampleLocalFileTemplate,
)


class ExampleConfig(BaseModel):
    pass


IAMBIC_PLUGIN = ProviderPlugin(
    config_name="example",
    version=PLUGIN_VERSION,
    provider_config=ExampleConfig,
    requires_secret=True,
    async_import_callable=import_example_resources,
    async_load_callable=load,
    templates=[
        ExampleLocalFileTemplate,
        ExampleLocalFileMultiAccountTemplate,
        ExampleLocalDatabaseTemplate,
    ],
)
