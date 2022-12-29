import asyncio

from iambic.aws.sso.permission_set.utils import generate_permission_set_map
from iambic.aws.utils import remove_expired_resources
from iambic.config.models import Config
from iambic.core.context import ExecutionContext
from iambic.core.logger import log
from iambic.core.models import TemplateChangeDetails
from iambic.core.parser import load_templates


async def apply_changes(
    config: Config, template_paths: list[str], context: ExecutionContext
) -> list[TemplateChangeDetails]:

    templates = load_templates(template_paths)
    await generate_permission_set_map(config.aws_accounts, templates)

    template_changes = await asyncio.gather(
        *[template.apply(config, context) for template in templates]
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
        template.write(exclude_none=True, exclude_unset=True, exclude_defaults=True)

    log.info("Expired resource scan complete.")
