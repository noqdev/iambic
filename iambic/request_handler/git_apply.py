from __future__ import annotations

import itertools
import os.path
import uuid
from io import StringIO

from deepdiff import DeepDiff
from git import Repo

from iambic.config.dynamic_config import load_config
from iambic.core.git import (
    create_templates_for_deleted_files,
    create_templates_for_modified_files,
    retrieve_git_changes,
)
from iambic.core.iambic_enum import Command
from iambic.core.logger import log
from iambic.core.models import (
    BaseTemplate,
    ExecutionMessage,
    ProposedChange,
    ProposedChangeType,
    TemplateChangeDetails,
)
from iambic.core.parser import load_templates
from iambic.core.utils import yaml
from iambic.request_handler.expire_resources import flag_expired_resources


async def apply_git_changes(
    config_path: str,
    repo_dir: str,
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

    config = await load_config(config_path)
    file_changes = await retrieve_git_changes(
        repo_dir,
        config.template_map,
        allow_dirty=allow_dirty,
        from_sha=from_sha,
        to_sha=to_sha,
    )
    if (
        not file_changes["new_files"]
        and not file_changes["modified_files"]
        and not file_changes["deleted_files"]
    ):
        log.info("No changes found.")
        return []

    exe_message = ExecutionMessage(
        execution_id=str(uuid.uuid4()), command=Command.APPLY
    )
    new_templates = load_templates(
        [git_diff.path for git_diff in file_changes["new_files"]],
        config.template_map,
    )

    deleted_templates = create_templates_for_deleted_files(
        file_changes["deleted_files"],
        config.template_map,
    )

    modified_templates_doubles = create_templates_for_modified_files(
        config,
        file_changes["modified_files"],
    )

    # You can only flag expired resources on new/modified-templates
    await flag_expired_resources(
        [
            template.file_path
            for template in itertools.chain(new_templates, modified_templates_doubles)
            if os.path.exists(template.file_path)
        ],
        config.template_map,
    )

    template_changes = await config.run_apply(
        exe_message,
        itertools.chain(new_templates, deleted_templates, modified_templates_doubles),
    )

    # Crutch to compute metadata changes
    metadata_changes = compute_metadata_changes(config, file_changes["modified_files"])
    template_changes.extend(metadata_changes)

    # note modified_templates_exist_in_repo has different entries from create_templates_for_modified_files because
    # create_templates_for_modified_files actually has two template instance per a single modified file
    modified_templates_exist_in_repo = load_templates(
        [git_diff.path for git_diff in file_changes["modified_files"]],
        config.template_map,
    )
    commit_deleted_templates(
        repo_dir, modified_templates_exist_in_repo, template_changes
    )

    return template_changes


def compute_metadata_changes(config, modified_files):
    changes = []
    for git_diff in modified_files:
        old_template_dict = yaml.load(StringIO(git_diff.content))
        template_type_string = old_template_dict["template_type"]
        template_cls = config.template_map.get(template_type_string, None)

        if template_cls is None:
            # well the case is the previous version is an unknown config type now.
            # this is typically the config file
            log_params = {"template_type": template_type_string}
            log.warning(
                "template_type is not registered among template_map", **log_params
            )
            continue

        old_template = template_cls(file_path=git_diff.path, **old_template_dict)
        new_template = load_templates([git_diff.path], config.template_map)[0]

        if template_type_string != "NOQ::AWS::IAM::Role":
            continue

        new_access_rules = getattr(new_template, "access_rules", [])
        old_access_rules = getattr(old_template, "access_rules", [])
        diff = DeepDiff(
            old_access_rules,
            new_access_rules,
            ignore_order=True,
            report_repetition=True,
        )
        if diff:
            propose_change = ProposedChange(
                change_type=ProposedChangeType.UPDATE,
                attribute="access_rules",
                resource_id=new_template.resource_id,
                resource_type=new_template.resource_type,
                change_summary=diff,
            )
            template_change_details = TemplateChangeDetails(
                resource_id=new_template.resource_id,
                resource_type=new_template.template_type,
                template_path=new_template.file_path,
                proposed_changes=[propose_change],
            )
            changes.append(template_change_details)

    return changes


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
