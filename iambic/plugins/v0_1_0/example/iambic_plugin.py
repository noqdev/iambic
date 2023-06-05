from __future__ import annotations

from pydantic import BaseModel

from iambic.core.iambic_plugin import ProviderPlugin
from iambic.core.models import ConfigMixin
from iambic.plugins.v0_1_0 import PLUGIN_VERSION
from iambic.plugins.v0_1_0.example.handlers import import_example_resources, load


def get_example_templates():
    from iambic.plugins.v0_1_0.example.local_database.models import (
        ExampleLocalDatabaseTemplate,
    )
    from iambic.plugins.v0_1_0.example.local_file.models import (
        ExampleLocalFileMultiAccountTemplate,
        ExampleLocalFileTemplate,
    )

    return [
        ExampleLocalFileTemplate,
        ExampleLocalFileMultiAccountTemplate,
        ExampleLocalDatabaseTemplate,
    ]


class ExampleConfig(ConfigMixin, BaseModel):
    @property
    def templates(self):
        return get_example_templates()


IAMBIC_PLUGIN = ProviderPlugin(
    config_name="example",
    version=PLUGIN_VERSION,
    provider_config=ExampleConfig,
    requires_secret=True,
    async_import_callable=import_example_resources,
    async_load_callable=load,
    templates=get_example_templates(),
)
