from __future__ import annotations

import asyncio
import os
import pathlib
import warnings
from typing import Optional

import click

from iambic.config.dynamic_config import init_plugins, load_config
from iambic.config.utils import (
    check_and_update_resource_limit,
    resolve_config_template_path,
)
from iambic.config.wizard import ConfigurationWizard
from iambic.core.context import ctx
from iambic.core.git import clone_git_repos
from iambic.core.logger import log
from iambic.core.models import TemplateChangeDetails
from iambic.core.parser import load_templates
from iambic.core.utils import gather_templates, yaml
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
@click.option(
    "--template",
    "-t",
    "templates",
    required=False,
    multiple=True,
    type=click.Path(exists=True),
    help="The template file path(s) to apply. Example: ./resources/aws/roles/engineering.yaml",
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
def plan(templates: list[str], repo_dir: str):
    run_plan(templates, repo_dir=repo_dir)


def run_plan(templates: list[str], repo_dir: str = str(pathlib.Path.cwd())):
    if not templates:
        templates = asyncio.run(gather_templates(repo_dir))

    config_path = asyncio.run(resolve_config_template_path(repo_dir))
    config = asyncio.run(load_config(config_path))

    asyncio.run(flag_expired_resources(templates))
    ctx.eval_only = True
    output_proposed_changes(asyncio.run(config.run_apply(load_templates(templates))))


@cli.command()
@click.option(
    "--template",
    "-t",
    "templates",
    required=False,
    multiple=True,
    type=click.Path(exists=True),
    help="The template file path(s) to expire. Example: ./aws/roles/engineering.yaml",
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
    default=str(pathlib.Path.cwd()),
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
    "--force",
    "-f",
    is_flag=True,
    show_default=True,
    help="Apply changes without asking for permission?",
)
@click.option(
    "--config",
    "-c",
    "config_path",
    type=click.Path(exists=True),
    help="The config.yaml file path to apply. Example: ./prod/config.yaml",
)
@click.option(
    "--template",
    "-t",
    "templates",
    required=False,
    multiple=True,
    type=click.Path(exists=True),
    help="The template file path(s) to apply. Example: ./aws/roles/engineering.yaml",
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
def apply(force: bool, config_path: str, templates: list[str], repo_dir: str):
    run_apply(force, config_path, templates, repo_dir=repo_dir)


def run_apply(
    force: bool,
    config_path: str,
    templates: list[str],
    repo_dir: str = str(pathlib.Path.cwd()),
):
    if not templates:
        templates = asyncio.run(gather_templates(repo_dir))
    if not config_path:
        config_path = asyncio.run(resolve_config_template_path(repo_dir))
    config = asyncio.run(load_config(config_path))
    ctx.eval_only = not force

    templates = load_templates(templates)
    asyncio.run(flag_expired_resources([template.file_path for template in templates]))
    template_changes = asyncio.run(config.run_apply(templates))
    output_proposed_changes(template_changes)

    if ctx.eval_only and template_changes and click.confirm("Proceed?"):
        ctx.eval_only = False
        asyncio.run(config.run_apply(templates))
    # This was here before, but I don't think it's needed. Leaving it here for now to see if anything breaks.
    # asyncio.run(config.run_detect_changes(repo_dir))


@cli.command(name="git-apply")
@click.option(
    "--config",
    "-c",
    "config_path",
    type=click.Path(exists=True),
    help="The config.yaml file path to apply. Example: ./prod/config.yaml",
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
    "--allow-dirty",
    is_flag=True,
    show_default=True,
    help="Allow applying changes from a dirty git repo",
)
@click.option(
    "--from-sha",
    "from_sha",
    required=False,
    type=str,
    help="The from_sha to calculate diff",
)
@click.option(
    "--to-sha",
    "to_sha",
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
def git_apply(
    config_path: str,
    repo_dir: str,
    allow_dirty: bool,
    from_sha: str,
    to_sha: str,
    plan_output: str,
):
    run_git_apply(
        config_path,
        allow_dirty,
        from_sha,
        to_sha,
        repo_dir=repo_dir,
        output_path=plan_output,
    )


def run_git_apply(
    config_path: str,
    allow_dirty: bool,
    from_sha: str,
    to_sha: str,
    repo_dir: str = str(pathlib.Path.cwd()),
    output_path: str = None,
):

    ctx.eval_only = False
    config_path = asyncio.run(resolve_config_template_path(repo_dir))
    asyncio.run(load_config(config_path))

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


@cli.command()
@click.option(
    "--config",
    "-c",
    "config_path",
    type=click.Path(exists=True),
    help="The config.yaml file path to apply. Example: ./prod/config.yaml",
)
@click.option(
    "--plan-output",
    "-o",
    "plan_output",
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
def git_plan(config_path: str, plan_output: str, repo_dir: str):
    run_git_plan(config_path, plan_output, repo_dir=repo_dir)


def run_git_plan(
    config_path: str,
    output_path: str,
    repo_dir: str = str(pathlib.Path.cwd()),
):
    ctx.eval_only = True
    config_path = asyncio.run(resolve_config_template_path(repo_dir))
    config = asyncio.run(load_config(config_path))
    check_and_update_resource_limit(config)
    template_changes = asyncio.run(plan_git_changes(config_path, repo_dir))
    output_proposed_changes(template_changes, output_path=output_path)


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
    asyncio.run(config.run_discover_upstream_config_changes(repo_dir))


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
    run_import(repo_dir=repo_dir)


def run_import(
    repo_dir: str = str(pathlib.Path.cwd()), config_path: Optional[str] = None
):
    if not config_path:
        config_path = asyncio.run(resolve_config_template_path(repo_dir))
    config = asyncio.run(load_config(config_path))
    check_and_update_resource_limit(config)
    asyncio.run(config.run_import(repo_dir))


@cli.command()
@click.option(
    "--template",
    "-t",
    "templates",
    required=False,
    multiple=True,
    type=click.Path(exists=True),
    help="The template file path(s) to expire. Example: ./aws/roles/engineering.yaml",
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
    ConfigurationWizard(repo_dir).run()


if __name__ == "__main__":
    cli()
