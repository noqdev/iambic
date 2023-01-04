from __future__ import annotations

import asyncio

from iambic.aws.identity_center.permission_set.utils import generate_permission_set_map
from iambic.config.models import Config
from iambic.core.context import ExecutionContext, ctx
from iambic.core.git import (
    create_templates_for_deleted_files,
    create_templates_for_modified_files,
    retrieve_git_changes,
)
from iambic.core.logger import log
from iambic.core.models import TemplateChangeDetails
from iambic.core.parser import load_templates


async def apply_git_changes(
    config_path: str,
    repo_dir: str,
    context: ExecutionContext = None,
    allow_dirty: bool = False,
    from_sha: str = None,
    to_sha: str = None,
) -> list[TemplateChangeDetails]:
    """Retrieves files added/updated/or removed when comparing the current branch to master

    Works by taking the diff and adding implied changes to the templates that were modified.
    These are the changes and this function detects:
        Deleting a file
        Removing 1 or more aws_accounts from included_accounts
        Adding 1 or more aws_accounts to excluded_accounts

    :param config_path:
    :param repo_dir:
    :param context:
    :param allow_dirty:
    :param from_sha:
    :param to_sha:
    :return:
    """
    if context is None:
        context = ctx

    config = Config.load(config_path)
    await config.setup_aws_accounts()
    file_changes = await retrieve_git_changes(
        repo_dir, allow_dirty=allow_dirty, from_sha=from_sha, to_sha=to_sha
    )
    if (
        not file_changes["new_files"]
        and not file_changes["modified_files"]
        and not file_changes["deleted_files"]
    ):
        log.info("No changes found.")
        return []

    templates = load_templates(
        [git_diff.path for git_diff in file_changes["new_files"]]
    )
    templates.extend(create_templates_for_deleted_files(file_changes["deleted_files"]))
    templates.extend(
        create_templates_for_modified_files(config, file_changes["modified_files"])
    )

    if config.aws and config.aws.accounts:
        await generate_permission_set_map(config.aws.accounts, templates)

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
