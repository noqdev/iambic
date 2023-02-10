from __future__ import annotations

import importlib
import os
from typing import Any, List, Optional

from pydantic import BaseModel, Field
from pydantic import create_model as create_pydantic_model

from iambic import aws
from iambic.core.iambic_plugin import ProviderPlugin
from iambic.core.logger import log
from iambic.core.utils import yaml


def generate_plugin_config_model(
    plugin: ProviderPlugin,
) -> tuple[ProviderPlugin, BaseModel]:
    config_attrs = {}
    for provider_def in [plugin.child_definition, plugin.parent_definition]:
        if provider_def:
            if provider_def.supports_multiple:
                field_def = (
                    list[provider_def.provider_class],
                    ... if provider_def.required else None,
                )
            else:
                field_def = (
                    provider_def.provider_class,
                    ... if provider_def.required else None,
                )
            config_attrs[provider_def.config_name] = field_def

    plugin_config_model = create_pydantic_model(
        f"Dynamic{plugin.config_name.upper()}Config",
        __base__=plugin.provider_config,
        **config_attrs,
    )
    return plugin, plugin_config_model


def load_plugins(paths: list[str]) -> List[tuple[ProviderPlugin, BaseModel]]:
    plugins = []
    for path in paths:
        for root, dirs, files in os.walk(path):
            for file in files:
                if file.endswith("iambic_plugin.py"):
                    module_name, _ = os.path.splitext(file)
                    module_path = os.path.join(root, file)
                    module = importlib.machinery.SourceFileLoader(
                        module_name, module_path
                    ).load_module()
                    if iambic_plugin := getattr(module, "IAMBIC_PLUGIN"):
                        plugins.append(iambic_plugin)
                    else:
                        log.error(
                            "Could not find the IAMBIC_PLUGIN variable",
                            plugin_file_path=file,
                        )

    return [generate_plugin_config_model(plugin) for plugin in plugins]


class Config(BaseModel):
    plugin_paths: Optional[list[str]] = Field(
        default=[
            aws.__path__[0],
        ],
        description="The paths to the plugins that should be loaded.",
    )
    plugin_load_callables: Optional[list[Any]] = Field(
        description="Used by the dynamic config loader."
    )
    plugin_import_callables: Optional[list[Any]] = Field(
        description="Used by the dynamic config loader."
    )
    plugin_templates: Optional[list[str]] = Field(
        description="Used by the dynamic config loader."
    )

    async def run_import(self, output_dir: str, messages: list = None):
        # It's the responsibility of the provider to handle throttling.
        await asyncio.gather(
            *[
                _import(self, output_dir, messages)
                for _import in self.plugin_import_callables
            ]
        )

    async def run_load(self):
        # Sync to prevent issues updating the config
        for _load in self.plugin_load_callables:
            await _load(self)


async def load_config(config_path: str):
    base_config = Config()
    all_plugins = load_plugins(base_config.plugin_paths)
    config_fields = dict(
        plugin_load_callables=(list, ...),
        plugin_import_callables=(list, ...),
        plugin_templates=(list, ...),
    )
    plugin_templates = []
    plugin_load_callables = []
    plugin_import_callables = []
    for plugin, plugin_config_model in all_plugins:
        config_fields[plugin.config_name] = (plugin_config_model, None)
        plugin_templates.extend(plugin.templates)
        plugin_load_callables.append(plugin.async_load_callable)
        plugin_import_callables.append(plugin.async_import_callable)

    dynamic_config = create_pydantic_model(
        "DynamicConfig", __base__=Config, **config_fields
    )
    config = dynamic_config(
        plugin_import_callables=plugin_import_callables,
        plugin_load_callables=plugin_load_callables,
        plugin_templates=plugin_templates,
        **yaml.load(open(config_path)),
    )
    await config.run_load()
    return config


if __name__ == "__main__":
    import asyncio

    os.environ["AWS_PROFILE"] = "iambic_test_org_account/IambicHubRole"
    local_config = asyncio.run(load_config("__local_config.yaml"))
    print(local_config)
