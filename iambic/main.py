from __future__ import annotations

import asyncio
import os
import pathlib
import sys
import uuid
import warnings

import click

from iambic.config.dynamic_config import Config, init_plugins, load_config
from iambic.config.utils import (
    check_and_update_resource_limit,
    resolve_config_template_path,
)
from iambic.config.wizard import ConfigurationWizard
from iambic.core.context import ctx
from iambic.core.git import clone_git_repos
from iambic.core.iambic_enum import Command
from iambic.core.logger import log
from iambic.core.models import ExecutionMessage, TemplateChangeDetails
from iambic.core.parser import load_templates
from iambic.core.utils import gather_templates, init_writable_directory, yaml
from iambic.request_handler.expire_resources import flag_expired_resources
from iambic.request_handler.git_apply import apply_git_changes
from iambic.request_handler.git_plan import plan_git_changes

warnings.filterwarnings("ignore", category=FutureWarning, module="botocore.client")

os.environ.setdefault("IAMBIC_REPO_DIR", str(pathlib.Path.cwd()))


def output_proposed_changes(
    template_changes: list[TemplateChangeDetails], output_path: str = None
):
    if output_path is None:
        output_path = "proposed_changes.yaml"
    if template_changes:
        log.info(f"A detailed summary of changes has been saved to {output_path}")

        with open(output_path, "w") as f:
            f.write(
                yaml.dump(
                    [template_change.dict() for template_change in template_changes],
                )
            )


@click.group()
def cli():
    ...


@cli.command()
@click.argument(
    "templates",
    required=False,
    envvar="IAMBIC_TEMPLATE_PATH",
    type=click.Path(exists=True),
    nargs=-1,
)
@click.option(
    "--repo-dir",
    "-d",
    "repo_dir",
    required=False,
    type=click.Path(exists=True),
    default=os.getenv("IAMBIC_REPO_DIR"),
    help="The repo directory containing the templates. Example: ~/iambic-templates",
)
def expire(templates: list[str], repo_dir: str):
    run_expire(templates, repo_dir=repo_dir)


def run_expire(templates: list[str], repo_dir: str = str(pathlib.Path.cwd())):
    config_path = asyncio.run(resolve_config_template_path(repo_dir))
    # load_config is required to populate known templates
    asyncio.run(load_config(config_path))

    if not templates:
        templates = asyncio.run(gather_templates(repo_dir))

    asyncio.run(flag_expired_resources(templates))


@cli.command()
@click.option(
    "--repo-dir",
    "-d",
    "repo_dir",
    required=False,
    type=click.Path(exists=True),
    help="The repo directory containing the templates. Example: ~/iambic-templates",
)
def detect(repo_dir: str):
    run_detect(repo_dir)


def run_detect(repo_dir: str):
    config_path = asyncio.run(resolve_config_template_path(repo_dir))
    config = asyncio.run(load_config(config_path))
    asyncio.run(config.run_detect_changes(repo_dir))


@cli.command()
@click.option(
    "--repo_dir",
    "-d",
    "repo_dir",
    required=True,
    type=click.Path(exists=True),
    default=os.getenv("IAMBIC_REPO_DIR"),
    help="The repo base directory that should contain the templates. Example: ~/iambic/templates",
)
def clone_repos(repo_dir: str):
    run_clone_repos(repo_dir=repo_dir)


def run_clone_repos(repo_dir: str = str(pathlib.Path.cwd())):
    config_path = asyncio.run(resolve_config_template_path(repo_dir))
    config = asyncio.run(load_config(config_path))
    asyncio.run(clone_git_repos(config, repo_dir))


@cli.command()
@click.option(
    "--repo-dir",
    "-d",
    "repo_dir",
    required=False,
    type=click.Path(exists=True),
    default=os.getenv("IAMBIC_REPO_DIR"),
    help="The repo directory containing the templates. Example: ~/iambic-templates",
)
@click.option(
    "--force",
    "-f",
    is_flag=True,
    show_default=True,
    help="Apply changes without asking for permission?",
)
@click.argument(
    "templates",
    required=True,
    envvar="IAMBIC_TEMPLATE_PATH",
    type=click.Path(exists=True),
    nargs=-1,
)
@click.option(
    "--allow-dirty",
    is_flag=True,
    hidden=True,
    help="Allow applying changes from a dirty git repo",
)
@click.option(
    "--from-sha",
    "from_sha",
    hidden=True,
    required=False,
    type=str,
    help="The from_sha to calculate diff",
)
@click.option(
    "--to-sha",
    "to_sha",
    hidden=True,
    required=False,
    type=str,
    help="The to_sha to calculate diff",
)
@click.option(
    "--plan-output",
    "-o",
    "plan_output",
    type=click.Path(exists=True),
    help="The location to output the plan Example: ./proposed_changes.yaml",
)
def apply(
    repo_dir: str,
    force: bool,
    templates: list[str],
    allow_dirty: bool,
    from_sha: str,
    to_sha: str,
    plan_output: str,
):
    try:
        if from_sha:
            assert to_sha, "to_sha is required when from_sha is provided"
            assert (
                not templates
            ), "templates cannot be provided when from_sha is provided"
            run_git_apply(
                allow_dirty,
                from_sha,
                to_sha,
                repo_dir=repo_dir,
                output_path=plan_output,
            )
        else:
            assert templates, "templates is a required argument"
            assert not to_sha, "to_sha is not supported with templates"
            assert not from_sha, "from_sha is not supported with templates"
            ctx.eval_only = not force
            config_path = asyncio.run(resolve_config_template_path(repo_dir))
            config = asyncio.run(load_config(config_path))
            run_apply(config, templates)
    except AssertionError as err:
        log.error("Invalid arguments", error=repr(err))


def run_apply(config: Config, templates: list[str]) -> list[TemplateChangeDetails]:
    template_changes = []
    exe_message = ExecutionMessage(
        execution_id=str(uuid.uuid4()), command=Command.APPLY
    )
    templates = load_templates(templates)
    asyncio.run(flag_expired_resources([template.file_path for template in templates]))
    template_changes = asyncio.run(config.run_apply(exe_message, templates))
    output_proposed_changes(template_changes)

    if ctx.eval_only and template_changes and click.confirm("Proceed?"):
        ctx.eval_only = False
        template_changes = asyncio.run(config.run_apply(exe_message, templates))
    # This was here before, but I don't think it's needed. Leaving it here for now to see if anything breaks.
    # asyncio.run(config.run_detect_changes(repo_dir))
    return template_changes


def run_git_apply(
    allow_dirty: bool,
    from_sha: str,
    to_sha: str,
    repo_dir: str = str(pathlib.Path.cwd()),
    output_path: str = None,
) -> list[TemplateChangeDetails]:
    ctx.eval_only = False
    config_path = asyncio.run(resolve_config_template_path(repo_dir))

    template_changes = asyncio.run(
        apply_git_changes(
            config_path,
            repo_dir,
            allow_dirty=allow_dirty,
            from_sha=from_sha,
            to_sha=to_sha,
        )
    )
    output_proposed_changes(template_changes, output_path=output_path)
    exceptions = [
        change.exceptions_seen for change in template_changes if change.exceptions_seen
    ]
    # figure out a way to log the useful information
    if exceptions:
        log.error(
            "exceptions encountered. some operations failed. read proposed_changes for details."
        )
        raise SystemExit(1)
    return template_changes


@cli.command()
@click.argument(
    "templates",
    required=False,
    envvar="IAMBIC_TEMPLATE_PATH",
    type=click.Path(exists=True),
    nargs=-1,
)
@click.option(
    "--plan-output",
    "-o",
    "plan_output",
    hidden=True,
    type=click.Path(exists=True),
    help="The location to output the plan Example: ./proposed_changes.yaml",
)
@click.option(
    "--repo-dir",
    "-d",
    "repo_dir",
    required=False,
    type=click.Path(exists=True),
    default=os.getenv("IAMBIC_REPO_DIR"),
    help="The repo directory containing the templates. Example: ~/iambic-templates",
)
@click.option(
    "--git-aware",
    is_flag=True,
    hidden=True,
)
def plan(templates: list, plan_output: str, repo_dir: str, git_aware: bool):
    if git_aware:
        run_git_plan(plan_output, repo_dir=repo_dir)
    else:
        if not templates:
            log.error("Invalid arguments", error="templates is a required argument")
            raise sys.exit(1)
        run_plan(templates, repo_dir=repo_dir)


def run_git_plan(
    output_path: str,
    repo_dir: str = str(pathlib.Path.cwd()),
) -> list[TemplateChangeDetails]:
    ctx.eval_only = True
    config_path = asyncio.run(resolve_config_template_path(repo_dir))
    config = asyncio.run(load_config(config_path))
    check_and_update_resource_limit(config)
    template_changes = asyncio.run(plan_git_changes(config_path, repo_dir))
    output_proposed_changes(template_changes, output_path=output_path)
    return template_changes


def run_plan(templates: list[str], repo_dir: str = str(pathlib.Path.cwd())):
    if not templates:
        templates = asyncio.run(gather_templates(repo_dir))

    config_path = asyncio.run(resolve_config_template_path(repo_dir))
    config = asyncio.run(load_config(config_path))
    exe_message = ExecutionMessage(
        execution_id=str(uuid.uuid4()), command=Command.APPLY
    )
    asyncio.run(flag_expired_resources(templates))
    ctx.eval_only = True
    output_proposed_changes(
        asyncio.run(config.run_apply(exe_message, load_templates(templates)))
    )


@cli.command()
@click.option(
    "--repo-dir",
    "-d",
    "repo_dir",
    required=False,
    type=click.Path(exists=True),
    default=os.getenv("IAMBIC_REPO_DIR"),
    help="The repo directory containing the templates. Example: ~/iambic-templates",
)
def config_discovery(repo_dir: str):
    config_path = asyncio.run(resolve_config_template_path(repo_dir))
    config = asyncio.run(load_config(config_path))
    exe_message = ExecutionMessage(
        execution_id=str(uuid.uuid4()), command=Command.CONFIG_DISCOVERY
    )
    asyncio.run(config.run_discover_upstream_config_changes(exe_message, repo_dir))


@cli.command(name="import")
@click.option(
    "--repo-dir",
    "-d",
    "repo_dir",
    required=False,
    type=click.Path(exists=True),
    default=os.getenv("IAMBIC_REPO_DIR"),
    help="The repo directory containing the templates. Example: ~/iambic-templates",
)
def import_(repo_dir: str):
    config_path = asyncio.run(resolve_config_template_path(repo_dir))
    config = asyncio.run(load_config(config_path))
    check_and_update_resource_limit(config)
    exe_message = ExecutionMessage(
        execution_id=str(uuid.uuid4()), command=Command.IMPORT
    )
    asyncio.run(config.run_import(exe_message, repo_dir))


@cli.command()
@click.argument(
    "templates",
    required=False,
    envvar="IAMBIC_TEMPLATE_PATH",
    type=click.Path(exists=True),
    nargs=-1,
)
@click.option(
    "--repo-dir",
    "-d",
    "repo_dir",
    required=False,
    type=click.Path(exists=True),
    default=os.getenv("IAMBIC_REPO_DIR"),
    help="The repo directory containing the templates. Example: ~/iambic-templates",
)
def lint(templates: list[str], repo_dir: str):
    ctx.eval_only = True
    config_path = asyncio.run(resolve_config_template_path(repo_dir))
    asyncio.run(load_config(config_path, configure_plugins=False))

    if not templates:
        templates = asyncio.run(gather_templates(repo_dir))

    templates = load_templates(templates, False)
    log.info("Formatting templates.")
    for template in templates:
        template.write()


@cli.command(name="init")
@click.option(
    "--repo-dir",
    "-d",
    "repo_dir",
    required=False,
    type=click.Path(exists=True),
    default=os.getenv("IAMBIC_REPO_DIR"),
    help="The repo directory. Example: ~/iambic-templates",
)
def init_plugins_cmd(repo_dir: str):
    config_path = asyncio.run(resolve_config_template_path(repo_dir))
    asyncio.run(init_plugins(config_path))


@cli.command()
@click.option(
    "--repo-dir",
    "-d",
    "repo_dir",
    required=False,
    type=click.Path(exists=True),
    default=os.getenv("IAMBIC_REPO_DIR"),
    help="The repo directory. Example: ~/iambic-templates",
)
def setup(repo_dir: str):
    ctx.command = Command.APPLY
    ConfigurationWizard(repo_dir).run()


if __name__ == "__main__":
    init_writable_directory()
    cli()
