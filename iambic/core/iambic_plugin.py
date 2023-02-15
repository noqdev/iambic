from __future__ import annotations

import asyncio
from typing import Any, Optional

from pydantic import BaseModel as PydanticBaseModel
from pydantic import Field

from iambic.core.context import ctx
from iambic.core.models import BaseTemplate, TemplateChangeDetails


async def default_apply_callable(
    config, templates: list[BaseTemplate]
) -> list[TemplateChangeDetails]:
    """
    The default apply callable for the IambicPlugin class.

    :param config: The plugin's config object.
    :param templates: The list of templates to apply.
    """
    template_changes = await asyncio.gather(
        *[template.apply(config, ctx) for template in templates]
    )

    return [
        template_change
        for template_change in template_changes
        if template_change.proposed_changes
    ]


class ProviderPlugin(PydanticBaseModel):
    config_name: str = Field(
        description="The name of the provider configuration in the iambic config file."
    )
    requires_secret: bool = Field(
        default=False,
        description="Whether or not the provider requires a secret to be passed in.",
    )
    provider_config: Any = Field(
        description="The Pydantic model that is attached to the Config."
        "This will contain the provider specific configuration."
        "These are things like the AWSAccount model, OktaOrganization or GoogleProject."
    )
    async_load_callable: Any = Field(
        description="The function that is called to load any dynamic metadata used by the provider."
        "For example, assigning default session info to an AWS account or decoding a secret."
        "This function must accept the param (config: ProviderConfig)."
        "The changes must be made to the config object directly and must return the config",
    )
    async_import_callable: Any = Field(
        description="The function that called to import resources across all templates for this provider."
        "This function must accept the params: (config: ProviderConfig, base_output_dir: str, messages: list = None)"
    )
    async_apply_callable: Any = Field(
        description="The function that called to apply resources across all templates for this provider."
        "This function must accept the params: (config: ProviderConfig, templates: list[BaseTemplate])."
        "It must return a list[TemplateChangeDetails].",
        default=default_apply_callable,
    )
    async_detect_changes_callable: Optional[Any] = Field(
        description="(OPTIONAL) The function that called to detect changes across all templates for this provider."
        "This is optional and if not provided will fallback to the async_import_callable."
        "The function is called more frequently than the import_callable."
        "It is used as a drift detection tool."
        "For example, the default AWS plugin supports an SQS queue containing cloudtrail events."
        "This function must accept the params: (config: ProviderConfig, repo_dir: str)"
        "It must return a str containing the detected changes.",
    )
    async_decode_secret_callable: Optional[Any] = Field(
        description="(OPTIONAL) The function that called to decode a secret."
        "Check extend.key before attempting to decode."
        "This function must accept the params (config: ProviderConfig, extend: ExtendsConfig)"
        "It must return the decoded secret as a dict."
    )
    async_discover_upstream_config_changes_callable: Optional[Any] = Field(
        description="(OPTIONAL) The function that called to discover upstream config changes."
        "An example of this would be a new account being added to an AWS Organization,"
        "or a change to AWS account's name or tags."
        "This function must accept the params: (config: ProviderConfig, repo_dir: str)"
    )
    templates: list = Field(
        description="The list of templates used for this provider.",
    )
