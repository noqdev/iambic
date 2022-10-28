import asyncio
import json
import pathlib
import warnings

import click

from iambic.config.models import Config
from iambic.core.context import ctx
from iambic.core.logger import log
from iambic.core.models import TemplateChangeDetails
from iambic.core.utils import gather_templates
from iambic.request_handler.apply import apply_changes, flag_expired_resources
from iambic.request_handler.detect import detect_changes
from iambic.request_handler.generate import generate_templates
from iambic.request_handler.git_apply import apply_git_changes

warnings.filterwarnings("ignore", category=FutureWarning, module="botocore.client")


def output_proposed_changes(template_changes: list[TemplateChangeDetails]):
    if template_changes:
        file_name = "proposed_changes.json"
        log.info(f"A detailed summary of descriptions was saved to {file_name}")

        with open(file_name, "w") as f:
            f.write(
                json.dumps(
                    [template_change.dict() for template_change in template_changes],
                    indent=2,
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
    if not templates:
        templates = asyncio.run(gather_templates(repo_dir or str(pathlib.Path.cwd())))

    asyncio.run(flag_expired_resources(templates))

    config = Config.load(config_path)
    config.set_account_defaults()
    ctx.eval_only = True
    output_proposed_changes(asyncio.run(apply_changes(config, templates)))


@cli.command()
@click.option(
    "--config",
    "-c",
    "config_path",
    type=click.Path(exists=True),
    help="The config.yaml file path to apply. Example: ./prod/config.yaml",
)
def detect(config_path: str):
    config = Config.load(config_path)
    config.set_account_defaults()
    asyncio.run(detect_changes(config))


@cli.command()
@click.option(
    "--no-prompt",
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
def apply(no_prompt: bool, config_path: str, templates: list[str], repo_dir: str):
    if not templates:
        templates = asyncio.run(gather_templates(repo_dir or str(pathlib.Path.cwd())))

    config = Config.load(config_path)
    config.set_account_defaults()
    ctx.eval_only = not no_prompt
    template_changes = asyncio.run(apply_changes(config, templates))
    output_proposed_changes(template_changes)

    if ctx.eval_only and template_changes and click.confirm("Proceed?"):
        ctx.eval_only = False
        asyncio.run(apply_changes(config, templates))
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
def git_apply(config_path: str, repo_dir: str):
    template_changes = asyncio.run(
        apply_git_changes(config_path, repo_dir or str(pathlib.Path.cwd()))
    )
    output_proposed_changes(template_changes)


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
    configs = list()
    for config_path in config_paths:
        config = Config.load(config_path)
        config.set_account_defaults()
        configs.append(config)

    asyncio.run(generate_templates(configs, repo_dir or str(pathlib.Path.cwd())))


if __name__ == "__main__":
    cli()
