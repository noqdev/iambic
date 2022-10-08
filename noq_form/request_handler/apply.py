import asyncio
import os

from noq_form.config.models import Config
from noq_form.core.context import ctx
from noq_form.core.logger import log
from noq_form.core.parser import load_templates
from noq_form.core.utils import remove_expired_resources, yaml


async def apply_changes(config: Config, template_paths: list[str]) -> bool:
    changes_made = await asyncio.gather(
        *[template.apply_all(config) for template in load_templates(template_paths)]
    )
    changes_made = any(changes_made)
    if ctx.execute and changes_made:
        log.info("Finished applying changes.")
    elif not ctx.execute:
        log.info("Finished scanning for changes.")
    else:
        log.info("No changes found.")

    return changes_made


async def flag_expired_resources(template_paths: list[str]):
    log.info("Scanning for expired resources")
    templates = await asyncio.gather(
        *[
            remove_expired_resources(
                template, template.resource_type, template.resource_name
            )
            for template in load_templates(template_paths)
        ]
    )

    for template in templates:
        with open(
            os.path.join(os.path.dirname(__file__), template.file_path), "w"
        ) as f:
            f.write(yaml.dump(template.dict(exclude_none=True, exclude_unset=True)))

    log.info("Expired resource scan complete.")
