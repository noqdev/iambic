from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import time
from enum import Enum

from iambic.config.dynamic_config import load_config
from iambic.config.utils import resolve_config_template_path
from iambic.core.models import BaseModel
from iambic.main import run_clone_repos, run_detect, run_git_apply, run_git_plan

REPO_BASE_PATH = os.path.expanduser("~/.iambic/repos/")
PLAN_OUTPUT_PATH = os.environ.get("PLAN_OUTPUT_PATH", None)
FROM_SHA = os.environ.get("FROM_SHA", None)
TO_SHA = os.environ.get("TO_SHA", None)


def init_repo_base_path():
    # Have to be careful when setting REPO_BASE_PATH because lambda execution
    # environment can be very straight on only /tmp is writable

    if os.environ.get("AWS_LAMBDA_FUNCTION_NAME", False):
        temp_templates_directory = tempfile.mkdtemp(prefix="lambda")
        REPO_BASE_PATH = f"{temp_templates_directory}/.iambic/repos/"
    else:
        REPO_BASE_PATH = os.path.expanduser("~/.iambic/repos/")

    this_module = sys.modules[__name__]
    setattr(this_module, "REPO_BASE_PATH", REPO_BASE_PATH)
    os.makedirs(os.path.dirname(REPO_BASE_PATH), exist_ok=True)


def init_plan_output_path():
    # Have to be careful when setting REPO_BASE_PATH because lambda execution
    # environment can be very straight on only /tmp is writable

    if os.environ.get("AWS_LAMBDA_FUNCTION_NAME", False):
        temp_templates_directory = tempfile.mkdtemp(prefix="lambda")
        PLAN_OUTPUT_PATH = f"{temp_templates_directory}/proposed_changes.yaml"
    else:
        PLAN_OUTPUT_PATH = os.environ.get("PLAN_OUTPUT_PATH", None)

    this_module = sys.modules[__name__]
    setattr(this_module, "PLAN_OUTPUT_PATH", PLAN_OUTPUT_PATH)


class LambdaCommand(Enum):
    # `import` is reserved in Python. So we just prepend `run_` to everything.
    run_import = "import"
    run_plan = "plan"
    run_apply = "apply"
    run_detect = "detect"
    run_git_apply = "git_apply"
    run_git_plan = "git_plan"
    run_clone_git_repos = "clone_git_repos"


class LambdaContext(BaseModel):
    command: str


def handler(event, context):
    return run_handler(event, context)


def run_handler(event=None, context=None):
    """
    Default handler for AWS Lambda.
    It is split out from the actual handler, so we can also run via IDE run configurations
    """
    if not context:
        context = {"command": "import"}
    lambda_context = LambdaContext(**context)

    if lambda_context.command == LambdaCommand.run_import.value:
        config_path = asyncio.run(resolve_config_template_path(REPO_BASE_PATH))
        config = asyncio.run(load_config(config_path))
        return asyncio.run(config.run_import(REPO_BASE_PATH))
    elif lambda_context.command == LambdaCommand.run_detect.value:
        return run_detect(REPO_BASE_PATH)
    elif lambda_context.command == LambdaCommand.run_apply.value:
        return run_git_apply(
            False,
            FROM_SHA,
            TO_SHA,
            repo_dir=REPO_BASE_PATH,
            output_path=PLAN_OUTPUT_PATH,
        )
    elif lambda_context.command == LambdaCommand.run_plan.value:
        return run_git_plan(PLAN_OUTPUT_PATH, repo_dir=REPO_BASE_PATH)
    elif lambda_context.command == LambdaCommand.run_git_apply.value:
        return run_git_apply(
            False,
            FROM_SHA,
            TO_SHA,
            repo_dir=REPO_BASE_PATH,
            output_path=PLAN_OUTPUT_PATH,
        )
    elif lambda_context.command == LambdaCommand.run_git_plan.value:
        return run_git_plan(PLAN_OUTPUT_PATH, repo_dir=REPO_BASE_PATH)
    elif lambda_context.command == LambdaCommand.run_clone_git_repos.value:
        return run_clone_repos(REPO_BASE_PATH)
    else:
        raise NotImplementedError(f"Unknown command {lambda_context.command}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise Exception("You must pass a command")
    command = sys.argv[1]

    init_repo_base_path()
    init_plan_output_path()

    # `schedule` is just for development and demo purposes
    if command == "schedule":
        while True:
            run_handler(None, {"command": "clone_git_repos"})
            run_handler(None, {"command": "apply"})
            time.sleep(1)
    else:
        run_handler(None, {"command": command})
