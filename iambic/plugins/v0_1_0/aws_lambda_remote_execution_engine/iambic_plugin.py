from __future__ import annotations

from pydantic import BaseModel

from iambic.core.iambic_plugin import ProviderPlugin
from iambic.plugins.v0_1_0 import PLUGIN_VERSION
from iambic.plugins.v0_1_0.aws_lambda_remote_execution_engine.handlers import (
    import_lambda_resources,
    load,
)


class AWSLambdaRemoteExecutionEngineConfig(BaseModel):
    pass


IAMBIC_PLUGIN = ProviderPlugin(
    config_name="aws_lambda_remote_execution_engine",
    version=PLUGIN_VERSION,
    provider_config=AWSLambdaRemoteExecutionEngineConfig,
    requires_secret=False,
    async_import_callable=import_lambda_resources,
    async_load_callable=load,
    templates=[],
)
