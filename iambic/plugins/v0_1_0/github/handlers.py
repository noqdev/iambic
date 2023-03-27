from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from iambic.plugins.v0_1_0.github.iambic_plugin import GithubConfig


async def load(config: GithubConfig) -> GithubConfig:
    import iambic.plugins.v0_1_0.github.github

    iambic.plugins.v0_1_0.github.github.COMMIT_MESSAGE_USER_NAME = (
        config.commit_message_user_name
    )
    iambic.plugins.v0_1_0.github.github.COMMIT_MESSAGE_USER_EMAIL = (
        config.commit_message_user_email
    )
    iambic.plugins.v0_1_0.github.github.COMMIT_MESSAGE_FOR_DETECT = (
        config.commit_message_for_detect
    )
    iambic.plugins.v0_1_0.github.github.COMMIT_MESSAGE_FOR_IMPORT = (
        config.commit_message_for_import
    )
    iambic.plugins.v0_1_0.github.github.COMMIT_MESSAGE_FOR_EXPIRE = (
        config.commit_message_for_expire
    )
    iambic.plugins.v0_1_0.github.github.COMMIT_MESSAGE_FOR_GIT_APPLY_ABSOLUTE_TIME = (
        config.commit_message_for_git_apply
    )

    return config


# This is not managing Github cloud resources today.
# It exists to comply with plugin interface. Github Plugin
# today provides GithubApp integrations for iambic templates
async def import_github_resources(
    config: GithubConfig, base_output_dir: str, messages: list = None
):
    tasks = []
    await asyncio.gather(*tasks)
