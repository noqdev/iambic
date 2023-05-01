from __future__ import annotations

import asyncio

from iambic.core.logger import log
from iambic.core.parser import load_templates
from iambic.core.utils import remove_expired_resources


async def flag_expired_resources(template_paths: list[str]):
    # Warning: The dynamic config must be loaded before this is called.
    #   This is done using iambic.config.dynamic_config.load_config(config_path)
    log.info("Scanning for expired resources")
    templates = await asyncio.gather(
        *[
            remove_expired_resources(
                template, template.resource_type, template.resource_id
            )
            for template in load_templates(template_paths)
        ]
    )

    for template in templates:
        template.write(exclude_none=True, exclude_unset=True, exclude_defaults=True)

    log.info("Expired resource scan complete.")
