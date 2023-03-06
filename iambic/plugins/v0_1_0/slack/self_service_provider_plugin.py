from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, SecretStr, validator
from slack_bolt import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler

from iambic.core.iambic_plugin import SelfServiceProviderPlugin
from iambic.plugins.v0_1_0.slack import PLUGIN_VERSION

DEFUALT_SCOPES = """app_mentions:read,channels:history,channels:join,channels:read,chat:write,chat:write.public,emoji:read,groups:history,groups:read,groups:write,im:history,im:read,im:write,mpim:history,mpim:read,mpim:write,pins:read,pins:write,reactions:read,reactions:write,users:read,users:read.email,channels:manage,chat:write.customize,dnd:read,files:read,files:write,links:read,links:write,metadata.message:read,usergroups:read,usergroups:write,users.profile:read,users:write""".split(
    ","
)


class SlackConfig(BaseModel):
    scopes: list[str] = Field(
        default=DEFUALT_SCOPES,
        description="The list of scopes to request from Slack.",
    )
    slack_app_token: SecretStr = Field(
        description="The Slack token to use for the Slack API.",
    )
    slack_app: Any = None  # AsyncApp (Slack App)

    class Config:
        arbitrary_types_allowed = True

    async def get_app(self) -> AsyncApp:
        if not self.app:
            self.app = AsyncApp(token=self.slack_app_token)
        return self.app

    async def start_app(self):
        if not self.app:
            self.get_app()
        await AsyncSocketModeHandler(self.app, self.slack_app_token).start


async def self_service_handler():
    pass


IAMBIC_PLUGIN = SelfServiceProviderPlugin(
    config_name="slack",
    version=PLUGIN_VERSION,
    provider_config=SlackConfig,
    async_self_service_callable=self_service_handler,
)
