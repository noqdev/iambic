from __future__ import annotations

import asyncio
import importlib
import itertools
import os
import subprocess
from collections import defaultdict
from enum import Enum
from pathlib import Path
from typing import List, Optional, Union
from uuid import uuid4

import ujson as json
from pydantic import BaseModel, Field
from pydantic import create_model as create_pydantic_model

import iambic.plugins.v0_1_0.github
from iambic.core.context import ctx
from iambic.core.exceptions import MultipleSecretsNotAcceptedException
from iambic.core.iambic_plugin import ProviderPlugin
from iambic.core.logger import log
from iambic.core.models import BaseTemplate, ExecutionMessage, TemplateChangeDetails
from iambic.core.utils import sort_dict, yaml
from iambic.plugins.v0_1_0 import PLUGIN_VERSION, aws, azure_ad, google_workspace, okta

CURRENT_IAMBIC_VERSION = "1"


class CoreConfig(BaseModel):
    minimum_ulimit: int = 64000


class PluginType(Enum):
    DIRECTORY_PATH = "DIRECTORY_PATH"
    # GIT = "GIT"


class ExtendsConfigKey(Enum):
    AWS_SECRETS_MANAGER = "AWS_SECRETS_MANAGER"
    LOCAL_FILE = "LOCAL_FILE"


class PluginDefinition(BaseModel):
    type: PluginType
    location: str = Field(
        description="The location of the plugin. "
        "For a DIRECTORY_PATH, this is the path to the plugin. "
        "For a GIT plugin, this is the git url."
    )
    version: str


def load_plugins(
    plugin_defs: list[PluginDefinition],
) -> List[tuple[ProviderPlugin, BaseModel]]:
    """
    Load all plugins from the given paths.
    This will search recursively for all files ending in iambic_plugin.py
    It will retrieve the variable IAMBIC_PLUGIN set in the iambic_plugin module.

    :param plugin_defs: A list of PluginDefinition instances to load.
    :return: A list of tuples containing the plugin and the plugin config model.
    """
    plugins = []
    for plugin_def in plugin_defs:
        if plugin_def.type == PluginType.DIRECTORY_PATH:
            for root, dirs, files in os.walk(plugin_def.location):
                for file in files:
                    if file == "iambic_plugin.py":
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
        # TODO: Add git support here.
        #  Would work by trying to find the cloned repo in a defined dir

    log.debug("Loading discovered plugins", discovered_plugin_count=len(plugins))
    return plugins


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
    plugins: Optional[list[PluginDefinition]] = Field(
        default=[
            PluginDefinition(
                type=PluginType.DIRECTORY_PATH,
                location=aws.__path__[0],
                version=PLUGIN_VERSION,
            ),
            PluginDefinition(
                type=PluginType.DIRECTORY_PATH,
                location=google_workspace.__path__[0],
                version=PLUGIN_VERSION,
            ),
            PluginDefinition(
                type=PluginType.DIRECTORY_PATH,
                location=okta.__path__[0],
                version=PLUGIN_VERSION,
            ),
            PluginDefinition(
                type=PluginType.DIRECTORY_PATH,
                location=iambic.plugins.v0_1_0.github.__path__[0],
                version=PLUGIN_VERSION,
            ),
            PluginDefinition(
                type=PluginType.DIRECTORY_PATH,
                location=azure_ad.__path__[0],
                version=PLUGIN_VERSION,
            ),
        ],
        description="The plugins used by your IAMbic template repo.",
    )
    extends: List[ExtendsConfig] = []
    secrets: Optional[dict] = Field(
        description="Secrets should only be used in memory and never serialized out",
        exclude=True,
        default={},
    )
    plugin_instances: Optional[list[ProviderPlugin]] = Field(
        description="A list of the plugin instances parsed as part of the plugin paths.",
        exclude=True,
    )
    core: Optional[CoreConfig] = Field(
        CoreConfig(),
        description="Core configuration options for iambic.",
    )

    class Config:
        arbitrary_types_allowed = True

    def get_config_plugin(self, plugin: ProviderPlugin):
        return getattr(self, plugin.config_name)

    def set_config_plugin(self, plugin: ProviderPlugin, config: BaseModel):
        setattr(self, plugin.config_name, config)

    @property
    def configured_plugins(self):
        return [
            plugin for plugin in self.plugin_instances if self.get_config_plugin(plugin)
        ]

    async def set_config_secrets(self):
        if self.extends:
            if len(self.extends) > 1:
                raise MultipleSecretsNotAcceptedException()

            extend = self.extends[0]
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
                        for plugin in self.plugin_instances
                        if plugin.async_decode_secret_callable
                    ]
                )
                for decoded_secret in decoded_secret_responses:
                    if decoded_secret:
                        if "secrets" not in decoded_secret:
                            decoded_secret = dict(secrets=decoded_secret)
                        else:
                            for k, v in decoded_secret.items():
                                if k != "secrets":
                                    decoded_secret["secrets"][k] = v

                        for k, v in decoded_secret.get("secrets", {}).items():
                            if k in decoded_secret:
                                log.warning(
                                    "Secret key already exists. "
                                    "This means it was defined in multiple secrets"
                                    " or multiple times in the same secret.",
                                    key=k,
                                )
                            self.secrets.setdefault(k, v)

    async def run_import(
        self,
        exe_message: ExecutionMessage,
        output_dir: str,
    ):
        ctx.command = exe_message.parent_command
        # It's the responsibility of the provider to handle throttling.
        if exe_message.provider_type:
            plugin = [
                plugin
                for plugin in self.configured_plugins
                if plugin.config_name == exe_message.provider_type
            ][0]
            await plugin.async_import_callable(
                exe_message, self.get_config_plugin(plugin), output_dir
            )
        else:
            tasks = []
            for plugin in self.configured_plugins:
                task_message = exe_message.copy()
                task_message.provider_type = plugin.config_name
                tasks.append(
                    plugin.async_import_callable(
                        task_message, self.get_config_plugin(plugin), output_dir
                    )
                )

            await asyncio.gather(*tasks)

    async def run_apply(
        self, exe_message: ExecutionMessage, templates: list[BaseTemplate]
    ) -> list[TemplateChangeDetails]:
        # It's the responsibility of the provider to handle throttling.
        # Build a map of a plugin's template types to the plugin
        ctx.command = exe_message.parent_command
        template_provider_map = {}
        for plugin in self.plugin_instances:
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
        for plugin in self.plugin_instances:
            if (
                exe_message.provider_type
                and plugin.config_name != exe_message.provider_type
            ):
                continue

            if templates := plugin_templates.get(plugin.config_name):
                if plugin_config := self.get_config_plugin(plugin):
                    task_message = exe_message.copy()
                    task_message.provider_type = plugin.config_name
                    tasks.append(
                        plugin.async_apply_callable(
                            task_message, plugin_config, templates
                        )
                    )
                else:
                    log.warning(
                        "Templates discovered for a plugin not defined in the config file.",
                        missing_config=plugin.config_name,
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
                for plugin in self.configured_plugins
                if plugin.async_detect_changes_callable
            ]
        )
        if run_import_as_fallback:
            await asyncio.gather(
                *[
                    plugin.async_import_callable(
                        self.get_config_plugin(plugin), repo_dir
                    )
                    for plugin in self.configured_plugins
                    if not plugin.async_detect_changes_callable
                ]
            )

        if change_str_list := [
            change_str for change_str in change_str_list if change_str
        ]:
            return "\n".join(change_str_list)

    async def run_discover_upstream_config_changes(
        self, exe_message: ExecutionMessage, repo_dir: str
    ):
        ctx.command = exe_message.parent_command
        tasks = []
        for plugin in self.configured_plugins:
            if plugin.async_discover_upstream_config_changes_callable:
                task_message = exe_message.copy()
                task_message.provider_type = plugin.config_name
                tasks.append(
                    plugin.async_discover_upstream_config_changes_callable(
                        task_message, self.get_config_plugin(plugin), repo_dir
                    )
                )

        if tasks:
            log.info("Scanning for upstream changes to config attributes.")
            await asyncio.gather(*tasks)

        log.info("Finished scanning for upstream changes to config attributes.")
        self.write()

    async def configure_plugins(self):
        """
        Called to set plugin metadata that is generated at run-time.
        """

        # Sync to prevent issues updating the config
        for plugin in self.configured_plugins:
            if not plugin.requires_secret:
                await plugin.async_load_callable(self.get_config_plugin(plugin))

        await self.set_config_secrets()

        for plugin in self.plugin_instances:
            if plugin.requires_secret:
                if provider_config_dict := self.secrets.get(plugin.config_name):
                    try:
                        setattr(
                            self,
                            plugin.config_name,
                            plugin.provider_config(
                                **json.loads(json.dumps(provider_config_dict))
                            ),
                        )
                        await plugin.async_load_callable(self.get_config_plugin(plugin))
                    except Exception as err:
                        log.critical(
                            "Failed to configure plugin.",
                            err=err,
                            plugin=plugin.config_name,
                        )
                        raise

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
        required_exclude = {"secrets", "file_path", "plugin_instances"}

        if self.plugin_instances:
            for plugin in self.plugin_instances:
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


async def load_config(
    config_path: str,
    configure_plugins: bool = True,
    approved_plugins_only: bool = False,
) -> Config:
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
    log.info("Loading config...")
    config_path = str(
        config_path
    )  # Ensure it's a string in case it's a Path for pydantic
    config_dict = yaml.load(open(config_path))
    base_config = Config(file_path=config_path, **config_dict)
    return await process_config(
        base_config, config_path, config_dict, configure_plugins, approved_plugins_only
    )


async def process_config(
    base_config: Config,
    config_path,
    config_dict,
    configure_plugins: bool = True,
    approved_plugins_only: bool = False,
) -> Config:
    from iambic.config.templates import TEMPLATES

    if approved_plugins_only:
        default_plugins = [
            plugin.location for plugin in Config.__fields__["plugins"].default
        ]
        base_config.plugins = [
            plugin
            for plugin in base_config.plugins
            if plugin.location in default_plugins
        ]

    all_plugins = load_plugins(base_config.plugins)
    config_fields = {}
    for plugin in all_plugins:
        config_fields[plugin.config_name] = (plugin.provider_config, None)

    dynamic_config = create_pydantic_model(
        f"DynamicConfig-{uuid4()}", __base__=Config, **config_fields
    )
    config = dynamic_config(
        plugin_instances=all_plugins, file_path=config_path, **config_dict
    )

    if configure_plugins:
        log.info("Setting config metadata...")
        await config.configure_plugins()
        log.info("Plugins loaded successfully...")

    TEMPLATES.set_templates(
        list(
            itertools.chain.from_iterable(
                [plugin.templates for plugin in config.plugin_instances]
            )
        )
    )
    return config


async def init_plugins(config_path: str):
    """
    Download plugins and install plugin dependencies
    """
    config_path = str(
        config_path
    )  # Ensure it's a string in case it's a Path for pydantic
    config_dict = yaml.load(open(config_path))
    config = Config(file_path=config_path, **config_dict)
    errors = defaultdict(dict)

    for plugin in config.plugins:
        if plugin.type == PluginType.DIRECTORY_PATH:
            plugin_path = plugin.location
        # elif plugin.type == PluginType.GIT:
        # Clone repo, set plugin_path

        if "aws" in plugin_path:
            continue

        required_files = ["iambic_plugin.py", "pyproject.toml"]
        for required_file in required_files:
            file_path = Path(os.path.join(plugin_path, required_file))
            if not file_path.is_file():
                errors[plugin.location].setdefault("missing_required_file", []).append(
                    str(file_path)
                )

        if plugin.location in errors:
            continue

        try:
            log.info("Installing plugin dependencies", plugin=plugin.location)
            subprocess.run(
                [
                    "poetry",
                    "install",
                ],
                cwd=plugin_path,
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as err:
            errors[plugin.location]["install_failed"] = dict(error=err.stderr)
        except Exception as err:
            errors[plugin.location]["install_failed"] = dict(error=repr(err))

    if errors:
        log.error("Failed to initialize all plugins", **errors)
