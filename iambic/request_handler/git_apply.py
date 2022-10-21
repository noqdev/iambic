import asyncio

from iambic.config.models import Config
from iambic.core.context import ctx
from iambic.core.git import (
    create_templates_for_deleted_files,
    create_templates_for_modified_files,
    retrieve_git_changes,
)
from iambic.core.logger import log
from iambic.core.parser import load_templates


async def apply_git_changes(config_path: str, repo_dir: str):
    """Retrieves files added/updated/or removed when comparing the current branch to master

    Works by taking the diff and adding implied changes to the templates that were modified.
    These are the changes and this function detects:
        Deleting a file
        Removing 1 or more accounts from included_accounts
        Adding 1 or more accounts to excluded_accounts

    :param config_path:
    :param repo_dir:
    :return:
    """
    config = Config.load(config_path)
    config.set_account_defaults()
    file_changes = await retrieve_git_changes(repo_dir)
    if (
        not file_changes["new_files"]
        and not file_changes["modified_files"]
        and not file_changes["deleted_files"]
    ):
        log.info("No changes found.")
        return

    templates = load_templates(
        [git_diff.path for git_diff in file_changes["new_files"]]
    )
    templates.extend(create_templates_for_deleted_files(file_changes["deleted_files"]))
    templates.extend(
        create_templates_for_modified_files(config, file_changes["modified_files"])
    )

    changes_made = await asyncio.gather(
        *[template.apply_all(config) for template in templates]
    )
    changes_made = any(changes_made)
    if ctx.execute and changes_made:
        log.info("Finished applying changes.")
    elif not ctx.execute:
        log.info("Finished scanning for changes.")
    else:
        log.info("No changes found.")
