from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel as PydanticBaseModel
from pydantic import Field


class ProviderClassDefinition(PydanticBaseModel):
    config_name: str = Field(
        description="The name of the provider configuration in the iambic config file."
        "Exists under the overall ProviderPlugin config_name space."
    )
    provider_class: Any = Field(
        "The class of the provider. "
        "This is used to instantiate the provider and assign it to the config as the attr config_name."
    )
    supports_multiple: bool = Field(
        default=True,
        description="Whether or not the provider supports multiple instances of the provider class.",
    )
    required: bool = Field(
        default=True,
        description="Whether or not the provider is required to be defined in the config.",
    )


class ProviderPlugin(PydanticBaseModel):
    config_name: str = Field(
        description="The name of the provider configuration in the iambic config file."
    )
    requires_secret: bool = Field(
        default=False,
        description="Whether or not the provider requires a secret to be passed in.",
    )
    child_definition: ProviderClassDefinition = Field(
        description="The child provider class definition. An example of this would be an AWS account."
    )
    parent_definition: Optional[ProviderClassDefinition] = Field(
        description="The parent provider class definition. "
        "An example of this would be an AWS Organization."
        "Not all providers have the concept of a parent so this is an optional field."
    )
    provider_config: Optional[Any] = Field(
        description="The Pydantic model that is attached to the Config.",
        default=PydanticBaseModel,
    )
    async_load_callable: Any = Field(
        description="The function that is called to load any dynamic metadata used by the provider."
        "For example, assigning default session info to an AWS account or decoding a secret."
        "This function must accept the following parameters: config: Config"
        "The chanes must be made to the config object directly and must return the config",
    )
    async_import_callable: Any = Field(
        description="The function that should be called to import resources across all templates for this provider."
        "This function must accept the following parameters: "
        "config: Config, base_output_dir: str, messages: list = None",
    )
    templates: list = Field(
        description="The list of templates that should be used for this provider.",
    )
