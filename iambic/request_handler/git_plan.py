from __future__ import annotations

from iambic.core.context import ExecutionContext
from iambic.core.models import TemplateChangeDetails
from iambic.request_handler.git_apply import apply_git_changes


async def plan_git_changes(
    config_path: str, repo_dir: str
) -> list[TemplateChangeDetails]:
    """Retrieves files added/updated/or removed when comparing the current branch to master

    Works by taking the diff and adding implied changes to the templates that were modified.
    These are the changes and this function detects:
        Deleting a file
        Removing 1 or more aws_accounts from included_accounts
        Adding 1 or more aws_accounts to excluded_accounts

    :param config_path:
    :param repo_dir:
    :return:
    """
    eval_only_ctx = ExecutionContext()
    eval_only_ctx.eval_only = True
    return await apply_git_changes(config_path, repo_dir, context=eval_only_ctx)
