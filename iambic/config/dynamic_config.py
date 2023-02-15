from __future__ import annotations

import asyncio
import importlib
import itertools
import os
from collections import defaultdict
from enum import Enum
from typing import List, Optional, Union

from pydantic import BaseModel, Field
from pydantic import create_model as create_pydantic_model

from iambic.core.context import ctx
from iambic.core.iambic_plugin import ProviderPlugin
from iambic.core.logger import log
from iambic.core.models import BaseTemplate, TemplateChangeDetails
from iambic.core.utils import sort_dict, yaml
from iambic.plugins import aws


def load_plugins(paths: list[str]) -> List[tuple[ProviderPlugin, BaseModel]]:
    """
    Load all plugins from the given paths.
    This will search recursively for all files ending in iambic_plugin.py
    It will retrieve the variable IAMBIC_PLUGIN set in the iambic_plugin module.

    :param paths: A list of paths to search for plugins.
    :return: A list of tuples containing the plugin and the plugin config model.
    """
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

    log.debug("Loading discovered plugins", discovered_plugin_count=len(plugins))
    return plugins


class ExtendsConfigKey(Enum):
    AWS_SECRETS_MANAGER = "AWS_SECRETS_MANAGER"
    LOCAL_FILE = "LOCAL_FILE"


class ExtendsConfig(BaseModel):
    key: ExtendsConfigKey
    value: str
    assume_role_arn: Optional[str]
    external_id: Optional[str]


class Config(BaseTemplate):
    template_type: str = "NOQ::Core::Config"
    version: str = Field(
        description="Do not change! The version of iambic this repo is compatible with.",
    )
    plugin_paths: Optional[list[str]] = Field(
        default=[
            aws.__path__[0],
        ],
        description="The paths to the plugins that should be loaded.",
    )
    extends: List[ExtendsConfig] = []
    secrets: Optional[dict] = Field(
        description="Secrets should only be used in memory and never serialized out",
        exclude=True,
        default={},
    )
    plugins: Optional[list[ProviderPlugin]] = Field(
        description="A list of the plugin instances parsed as part of the plugin paths.",
        exclude=True,
    )

    class Config:
        arbitrary_types_allowed = True

    def get_config_plugin(self, plugin: ProviderPlugin):
        return getattr(self, plugin.config_name)

    def set_config_plugin(self, plugin: ProviderPlugin, config: BaseModel):
        setattr(self, plugin.config_name, config)

    async def set_config_secrets(self):
        if self.extends:
            for extend in self.extends:
                if extend.key == ExtendsConfigKey.LOCAL_FILE:
                    dir_path = os.path.dirname(self.file_path)
                    extend_path = os.path.join(dir_path, extend.value)
                    with open(extend_path, "r") as ymlfile:
                        extend_config = yaml.load(ymlfile)
                    for k, v in extend_config.items():
                        if not getattr(self, k, None):
                            setattr(self, k, v)
                else:
                    decoded_secret_responses: list[dict] = await asyncio.gather(
                        *[
                            plugin.async_decode_secret_callable(
                                self.get_config_plugin(plugin), extend
                            )
                            for plugin in self.plugins
                            if plugin.async_decode_secret_callable
                        ]
                    )
                    for decoded_secret in decoded_secret_responses:
                        if decoded_secret:
                            for k, v in decoded_secret.items():
                                if not getattr(self, k, None):
                                    setattr(self, k, v)
                            break

    async def run_import(self, output_dir: str, messages: list = None):
        # It's the responsibility of the provider to handle throttling.
        await asyncio.gather(
            *[
                plugin.async_import_callable(
                    self.get_config_plugin(plugin), output_dir, messages
                )
                for plugin in self.plugins
            ]
        )

    async def run_apply(
        self, templates: list[BaseTemplate]
    ) -> list[TemplateChangeDetails]:
        # It's the responsibility of the provider to handle throttling.
        # Build a map of a plugin's template types to the plugin
        template_provider_map = {}
        for plugin in self.plugins:
            for template in plugin.templates:
                template_provider_map[
                    template.__fields__["template_type"].default
                ] = plugin.config_name

        # Create a map of the templates to apply to the template's plugin
        plugin_templates = defaultdict(list)
        for template in templates:
            provider = template_provider_map[template.template_type]
            plugin_templates[provider].append(template)

        tasks = []
        for plugin in self.plugins:
            if templates := plugin_templates.get(plugin.config_name):
                tasks.append(
                    plugin.async_apply_callable(
                        self.get_config_plugin(plugin), templates
                    )
                )

        # Retrieve template changes across plugins and flatten responses
        template_changes = await asyncio.gather(*tasks)
        template_changes = list(itertools.chain.from_iterable(template_changes))

        if ctx.execute and template_changes:
            log.info("Finished applying changes.")
        elif not ctx.execute:
            log.info("Finished scanning for changes.")
        else:
            log.info("No changes found.")

        return template_changes

    async def run_detect_changes(
        self, repo_dir: str, run_import_as_fallback: bool = False
    ) -> Union[str, None]:
        change_str_list = await asyncio.gather(
            *[
                plugin.async_detect_changes_callable(
                    self.get_config_plugin(plugin), repo_dir
                )
                for plugin in self.plugins
                if plugin.async_detect_changes_callable
            ]
        )
        if run_import_as_fallback:
            await asyncio.gather(
                *[
                    plugin.async_import_callable(
                        self.get_config_plugin(plugin), repo_dir
                    )
                    for plugin in self.plugins
                    if not plugin.async_detect_changes_callable
                ]
            )

        if change_str_list := [
            change_str for change_str in change_str_list if change_str
        ]:
            return "\n".join(change_str_list)

    async def run_discover_upstream_config_changes(self, repo_dir: str):
        await asyncio.gather(
            *[
                plugin.async_discover_upstream_config_changes_callable(
                    self.get_config_plugin(plugin), repo_dir
                )
                for plugin in self.plugins
                if plugin.async_discover_upstream_config_changes_callable
            ]
        )
        self.write()

    async def configure_plugins(self):
        """
        Called to set plugin metadata that is generated at run-time.
        """

        # Sync to prevent issues updating the config
        for plugin in self.plugins:
            if not plugin.requires_secret:
                await plugin.async_load_callable(self.get_config_plugin(plugin))

        await self.set_config_secrets()

        for plugin in self.plugins:
            if plugin.requires_secret:
                if provider_config_dict := self.secrets.get(plugin.config_name):
                    setattr(
                        self,
                        plugin.config_name,
                        plugin.provider_config(**provider_config_dict),
                    )
                    await plugin.async_load_callable(self.get_config_plugin(plugin))

    def dict(
        self,
        *,
        include: Optional[
            Union["AbstractSetIntStr", "MappingIntStrAny"]  # noqa
        ] = None,
        exclude: Optional[
            Union["AbstractSetIntStr", "MappingIntStrAny"]  # noqa
        ] = None,
        by_alias: bool = False,
        skip_defaults: Optional[bool] = None,
        exclude_unset: bool = True,
        exclude_defaults: bool = False,
        exclude_none: bool = True,
    ) -> "DictStrAny":  # noqa
        required_exclude = {
            "secrets",
            "file_path",
        }
        for plugin in self.plugins:
            if plugin.requires_secret:
                required_exclude.add(plugin.config_name)

        if exclude:
            exclude.update(required_exclude)
        else:
            exclude = required_exclude

        return super().dict(
            include=include,
            exclude=exclude,
            by_alias=by_alias,
            skip_defaults=skip_defaults,
            exclude_unset=exclude_unset,
            exclude_defaults=exclude_defaults,
            exclude_none=exclude_none,
        )

    def write(self, exclude_none=True, exclude_unset=False, exclude_defaults=True):
        input_dict = self.dict(
            exclude_none=exclude_none,
            exclude_unset=exclude_unset,
            exclude_defaults=exclude_defaults,
        )
        sorted_input_dict = sort_dict(
            input_dict,
            [
                "template_type",
                "version",
            ],
        )

        file_path = os.path.expanduser(self.file_path)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w") as f:
            f.write(yaml.dump(sorted_input_dict))

        log.info("Config successfully written", config_location=file_path)


async def load_config(config_path: str) -> Config:
    """
    Load the configuration from the specified file path.

    Only use this function to retrieve the configuration object.
    Do not try to instantiate directly.
    Should be called as soon as possible in the application.
    This function is responsible for:
    - Loading the configuration file
    - Loading the plugins
    - Creating the dynamic configuration object using the loaded plugins
    - Setting runtime metadata for the plugins
    - Retrieving secrets which are used to set certain plugins
    - Setting list of templates on the TEMPLATE global variable

    Parameters:
    - config_path (str): The file path of the configuration file.

    Returns:
    - Config: The configuration object created from the specified file.
    """
    from iambic.config.templates import TEMPLATES

    config_dict = yaml.load(open(config_path))
    base_config = Config(file_path=config_path, **config_dict)
    all_plugins = load_plugins(base_config.plugin_paths)
    config_fields = {}
    for plugin in all_plugins:
        config_fields[plugin.config_name] = (plugin.provider_config, None)

    dynamic_config = create_pydantic_model(
        "DynamicConfig", __base__=Config, **config_fields
    )
    config = dynamic_config(plugins=all_plugins, file_path=config_path, **config_dict)
    await config.configure_plugins()

    TEMPLATES.set_templates(
        list(
            itertools.chain.from_iterable(
                [plugin.templates for plugin in config.plugins]
            )
        )
    )
    return config
