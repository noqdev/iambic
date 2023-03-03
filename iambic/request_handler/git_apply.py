from __future__ import annotations

from git import Repo

from iambic.config.dynamic_config import load_config
from iambic.core.context import ExecutionContext, ctx
from iambic.core.git import (
    create_templates_for_deleted_files,
    create_templates_for_modified_files,
    retrieve_git_changes,
)
from iambic.core.logger import log
from iambic.core.models import BaseTemplate, TemplateChangeDetails
from iambic.core.parser import load_templates
from iambic.request_handler.expire_resources import flag_expired_resources


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

    config = await load_config(config_path)
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
    await flag_expired_resources([template.file_path for template in templates])
    template_changes = await config.run_apply(templates)

    # note modified_templates has different entries from create_templates_for_modified_files because
    # create_templates_for_modified_files actually has two template instance per a single modified file
    modified_templates = load_templates(
        [git_diff.path for git_diff in file_changes["modified_files"]]
    )
    commit_deleted_templates(repo_dir, modified_templates, template_changes)

    return template_changes


def commit_deleted_templates(
    repo_dir: str, templates: list[BaseTemplate], details: list[TemplateChangeDetails]
):

    repo = Repo(repo_dir)

    # intended to delete
    deleted_template_path_to_template: dict[str, BaseTemplate] = {
        template.file_path: template for template in templates if template.deleted
    }

    for template_detail in details:

        if template_detail.template_path in deleted_template_path_to_template:

            if template_detail.exceptions_seen:
                log_params = {"path": template_detail.template_path}
                log.error(
                    "add_commits_from_delete_templates cannot be deleted due to exceptions in apply",
                    **log_params,
                )
            else:
                deleted_template_path_to_template[
                    template_detail.template_path
                ].delete()

    diff_list = repo.head.commit.diff()
    if len(diff_list) > 0:
        repo.git.commit("-m", "Delete template after successfully delete resources")
