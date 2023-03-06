from __future__ import annotations

from typing import TYPE_CHECKING

from slack_bolt import AsyncApp

if TYPE_CHECKING:
    from iambic.plugins.v0_1_0.slack.self_service_provider_plugin import SlackConfig


async def get_app(config: SlackConfig) -> AsyncApp:
    app = AsyncApp(token=config.slack_token)
    return app
