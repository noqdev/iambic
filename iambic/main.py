import asyncio
import pathlib
import warnings

import click

from iambic.config.models import Config
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


@cli.command()
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
    help="The repo directory containing the templates. Example: ~/noq-templates",
)
def plan(config_path: str, templates: list[str], repo_dir: str):
    run_plan(config_path, templates, repo_dir)


def run_plan(config_path: str, templates: list[str], repo_dir: str):
    if not templates:
        templates = asyncio.run(gather_templates(repo_dir or str(pathlib.Path.cwd())))

    asyncio.run(flag_expired_resources(templates))

    config = Config.load(config_path)
    asyncio.run(config.setup_aws_accounts())
    ctx.eval_only = True
    output_proposed_changes(asyncio.run(apply_changes(config, templates, ctx)))


@cli.command()
@click.option(
    "--config",
    "-c",
    "config_path",
    type=click.Path(exists=True),
    help="The config.yaml file path to apply. Example: ./prod/config.yaml",
)
def detect(config_path: str):
    run_detect(config_path)


def run_detect(config_path: str):
    config = Config.load(config_path)
    asyncio.run(config.setup_aws_accounts())
    asyncio.run(detect_changes(config))


@cli.command()
@click.option(
    "--config",
    "-c",
    "config_path",
    type=click.Path(exists=True),
    help="The config.yaml file path to apply. Example: ./prod/config.yaml",
)
@click.option(
    "--repo_base_path",
    "-d",
    "repo_base_path",
    required=True,
    type=click.Path(exists=True),
    help="The repo base directory that should contain the templates. Example: ~/iambic/templates",
)
def clone_repos(config_path: str, repo_base_path: str):
    run_clone_repos(config_path, repo_base_path)


def run_clone_repos(config_path: str, repo_base_path: str):
    config = Config.load(config_path)
    asyncio.run(config.setup_aws_accounts())
    asyncio.run(clone_git_repos(config, repo_base_path))


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
    help="The repo directory containing the templates. Example: ~/noq-templates",
)
def apply(force: bool, config_path: str, templates: list[str], repo_dir: str):
    run_apply(force, config_path, templates, repo_dir)


def run_apply(force: bool, config_path: str, templates: list[str], repo_dir: str):
    if not templates:
        templates = asyncio.run(gather_templates(repo_dir or str(pathlib.Path.cwd())))

    config = Config.load(config_path)
    # asyncio.run(config.setup_aws_accounts())
    ctx.eval_only = not force

    template_changes = asyncio.run(apply_changes(config, templates, ctx))
    output_proposed_changes(template_changes)

    if ctx.eval_only and template_changes and click.confirm("Proceed?"):
        ctx.eval_only = False
        asyncio.run(apply_changes(config, templates, ctx))
    asyncio.run(detect_changes(config))


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
    run_git_apply(config_path, repo_dir, allow_dirty, from_sha, to_sha)


def run_git_apply(
    config_path: str, repo_dir: str, allow_dirty: bool, from_sha: str, to_sha: str
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
    help="The repo directory containing the templates. Example: ~/noq-templates",
)
@click.option(
    "--plan-output",
    "-o",
    "plan_output",
    type=click.Path(exists=True),
    help="The location to output the plan Example: ./proposed_changes.json",
)
def git_plan(config_path: str, templates: list[str], repo_dir: str, plan_output: str):
    run_git_plan(config_path, templates, repo_dir, plan_output)


def run_git_plan(
    config_path: str, templates: list[str], repo_dir: str, output_path: str
):
    template_changes = asyncio.run(
        plan_git_changes(config_path, repo_dir or str(pathlib.Path.cwd()))
    )
    output_proposed_changes(template_changes, output_path=output_path)


@cli.command(name="import")
@click.option(
    "--config",
    "-c",
    "config_paths",
    multiple=True,
    type=click.Path(exists=True),
    help="The config.yaml file paths. Example: ./prod/config.yaml",
)
@click.option(
    "--repo-dir",
    "-d",
    "repo_dir",
    required=False,
    type=click.Path(exists=True),
    help="The repo directory containing the templates. Example: ~/noq-templates",
)
def import_(config_paths: list[str], repo_dir: str):
    run_import(config_paths, repo_dir or str(pathlib.Path.cwd()))


def run_import(config_paths: list[str], repo_dir: str):
    configs = []
    for config_path in config_paths:
        config = Config.load(config_path)
        asyncio.run(config.setup_aws_accounts())
        configs.append(config)
    asyncio.run(generate_templates(configs, repo_dir or str(pathlib.Path.cwd())))


if __name__ == "__main__":
    cli()
