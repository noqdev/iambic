from __future__ import annotations

import asyncio
import pathlib
import warnings

import click

from iambic.config.models import Config
from iambic.config.utils import multi_config_loader, resolve_config_template_path
from iambic.config.wizard import ConfigurationWizard
from iambic.core.context import ctx
from iambic.core.git import clone_git_repos
from iambic.core.logger import log
from iambic.core.models import TemplateChangeDetails
from iambic.core.utils import gather_templates, yaml
from iambic.request_handler.apply import apply_changes, flag_expired_resources
from iambic.request_handler.detect import detect_changes
from iambic.request_handler.generate import generate_templates
from iambic.request_handler.git_apply import apply_git_changes
from iambic.request_handler.git_plan import plan_git_changes

warnings.filterwarnings("ignore", category=FutureWarning, module="botocore.client")


def output_proposed_changes(
    template_changes: list[TemplateChangeDetails], output_path: str = None
):
    if output_path is None:
        output_path = "proposed_changes.yaml"
    if template_changes:
        log.info(f"A detailed summary of descriptions was saved to {output_path}")

        with open(output_path, "w") as f:
            f.write(
                yaml.dump(
                    [template_change.dict() for template_change in template_changes],
                )
            )


@click.group()
def cli():
    ...


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
    default=str(pathlib.Path.cwd()),
    help="The repo directory containing the templates. Example: ~/noq-templates",
)
def plan(templates: list[str], repo_dir: str):
    run_plan(templates, repo_dir=repo_dir)


def run_plan(
    templates: list[str], repo_dir: str = str(pathlib.Path.cwd())
):
    if not templates:
        templates = asyncio.run(gather_templates(repo_dir))

    asyncio.run(flag_expired_resources(templates))
    config_path = asyncio.run(resolve_config_template_path(repo_dir))
    config = Config.load(config_path)
    asyncio.run(config.setup_aws_accounts())
    ctx.eval_only = True
    output_proposed_changes(asyncio.run(apply_changes(config, templates, ctx)))


@click.option(
    "--repo-dir",
    "-d",
    "repo_dir",
    required=False,
    type=click.Path(exists=True),
    help="The repo directory containing the templates. Example: ~/noq-templates",
)
def detect(repo_dir: str):
    run_detect(repo_dir)


def run_detect(repo_dir: str):
    config_path = asyncio.run(resolve_config_template_path(repo_dir))
    config = Config.load(config_path)
    asyncio.run(config.setup_aws_accounts())
    asyncio.run(detect_changes(config, repo_dir or str(pathlib.Path.cwd())))


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
    config = Config.load(config_path)
    asyncio.run(config.setup_aws_accounts())
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
    default=str(pathlib.Path.cwd()),
    help="The repo directory containing the templates. Example: ~/noq-templates",
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
    config = Config.load(config_path)
    asyncio.run(config.setup_aws_accounts())
    ctx.eval_only = not force

    template_changes = asyncio.run(apply_changes(config, templates, ctx))
    output_proposed_changes(template_changes)

    if ctx.eval_only and template_changes and click.confirm("Proceed?"):
        ctx.eval_only = False
        asyncio.run(apply_changes(config, templates, ctx))
    asyncio.run(detect_changes(config, repo_dir))


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
    default=str(pathlib.Path.cwd()),
    help="The repo directory containing the templates. Example: ~/noq-templates",
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
def git_apply(
    config_path: str, repo_dir: str, allow_dirty: bool, from_sha: str, to_sha: str
):
    run_git_apply(config_path, allow_dirty, from_sha, to_sha, repo_dir=repo_dir)


def run_git_apply(
    config_path: str,
    allow_dirty: bool,
    from_sha: str,
    to_sha: str,
    repo_dir: str = str(pathlib.Path.cwd()),
):
    template_changes = asyncio.run(
        apply_git_changes(
            config_path,
            repo_dir or str(pathlib.Path.cwd()),
            allow_dirty=allow_dirty,
            from_sha=from_sha,
            to_sha=to_sha,
        )
    )
    output_proposed_changes(template_changes)


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
    help="The location to output the plan Example: ./proposed_changes.json",
)
@click.option(
    "--repo-dir",
    "-d",
    "repo_dir",
    required=False,
    type=click.Path(exists=True),
    default=str(pathlib.Path.cwd()),
    help="The repo directory containing the templates. Example: ~/noq-templates",
)
def git_plan(config_path: str, plan_output: str, repo_dir: str):
    run_git_plan(config_path, plan_output, repo_dir=repo_dir)


def run_git_plan(
    config_path: str,
    output_path: str,
    repo_dir: str = str(pathlib.Path.cwd()),
):
    template_changes = asyncio.run(plan_git_changes(config_path, repo_dir))
    output_proposed_changes(template_changes, output_path=output_path)


@cli.command(name="import")
@click.option(
    "--repo-dir",
    "-d",
    "repo_dir",
    required=False,
    type=click.Path(exists=True),
    default=str(pathlib.Path.cwd()),
    help="The repo directory containing the templates. Example: ~/noq-templates",
)
def import_(repo_dir: str):
    config_path = asyncio.run(resolve_config_template_path(repo_dir))
    run_import([config_path], repo_dir=repo_dir)


def run_import(config_paths: list[str], repo_dir: str = str(pathlib.Path.cwd())):
    if not config_paths or config_paths == [None]:
        config_paths = [asyncio.run(resolve_config_template_path(repo_dir))]
    configs = asyncio.run(multi_config_loader(config_paths))
    asyncio.run(generate_templates(configs, repo_dir or str(pathlib.Path.cwd())))


@cli.command()
@click.option(
    "--repo-dir",
    "-d",
    "repo_dir",
    required=False,
    type=click.Path(exists=True),
    help="The repo directory. Example: ~/noq-templates",
)
def setup(repo_dir: str):
    ConfigurationWizard(repo_dir or str(pathlib.Path.cwd())).run()


if __name__ == "__main__":
    cli()
