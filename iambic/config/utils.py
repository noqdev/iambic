from __future__ import annotations

import asyncio

from iambic.config.models import Config


async def multi_config_loader(config_paths: list[str]) -> list[Config]:
    """Load multiple config files into a list of Config objects."""
    configs = []
    for config_path in config_paths:
        config = Config.load(config_path)
        configs.append(config)

    await asyncio.gather(*[config.setup_aws_accounts() for config in configs])

    identity_center_detail_set_tasks = []
    for config in configs:
        if config.aws and config.aws.accounts:
            identity_center_detail_set_tasks.extend(
                [account.set_identity_center_details() for account in config.aws.accounts]
            )
    await asyncio.gather(*identity_center_detail_set_tasks)

    return configs
