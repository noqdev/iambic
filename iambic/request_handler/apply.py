import asyncio

from iambic.aws.utils import remove_expired_resources
from iambic.config.models import Config
from iambic.core.context import ExecutionContext
from iambic.core.logger import log
from iambic.core.models import TemplateChangeDetails
from iambic.core.parser import load_templates
from iambic.core.utils import yaml


async def apply_changes(
    config: Config, template_paths: list[str], context: ExecutionContext
) -> list[TemplateChangeDetails]:
    template_changes = await asyncio.gather(
        *[
            template.apply(config, context)
            for template in load_templates(template_paths)
        ]
    )
    template_changes = [
        template_change
        for template_change in template_changes
        if template_change.proposed_changes
    ]

    if context.execute and template_changes:
        log.info("Finished applying changes.")
    elif not context.execute:
        log.info("Finished scanning for changes.")
    else:
        log.info("No changes found.")

    return template_changes


async def flag_expired_resources(template_paths: list[str]):
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
        with open(template.file_path, "w") as f:
            f.write(yaml.dump(template.dict(exclude_none=True, exclude_unset=True)))

    log.info("Expired resource scan complete.")
