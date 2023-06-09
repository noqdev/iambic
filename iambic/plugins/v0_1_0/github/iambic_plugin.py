from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from iambic.core.iambic_plugin import ProviderPlugin
from iambic.plugins.v0_1_0 import PLUGIN_VERSION
from iambic.plugins.v0_1_0.github.handlers import import_github_resources, load

DEFAULT_ALLOWED_BOT_APPROVER = None


class GithubBotApprover(BaseModel):
    login: str = Field(
        ...,
        description="login for allowed bot approver",
    )
    es256_pub_key: str = Field(
        ...,
        description="ES256 Pub Key for allowed bot approver",
    )


class GithubConfig(BaseModel):
    commit_message_user_name: str = Field(
        default="Iambic Automation", description="Commit message user name"
    )
    commit_message_user_email: str = Field(
        default="iambic-automation@iambic.org", description="Commit message user email"
    )
    commit_message_for_detect: str = Field(
        default="Import changes from detect operation",
        description="Commit message to use during changes through detect operations",
    )
    commit_message_for_import: str = Field(
        default="Import changes from import operation",
        description="Commit message to use during changes through import operations",
    )
    commit_message_for_expire: str = Field(
        default="Periodic Expiration",
        description="Commit message to use during changes through expire operations",
    )
    commit_message_for_git_apply: str = Field(
        default="Replace relative time with absolute time",
        description="Commit message to use during changes through git-apply",
    )
    allowed_bot_approvers: Optional[list[GithubBotApprover]] = Field(
        default=[],
        description="list of allowed bot approver",
    )


IAMBIC_PLUGIN = ProviderPlugin(
    config_name="github",
    version=PLUGIN_VERSION,
    provider_config=GithubConfig,
    requires_secret=False,
    async_import_callable=import_github_resources,
    async_load_callable=load,
    templates=[],
)
