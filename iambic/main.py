import asyncio
import pathlib
import warnings

import click

from iambic.config.models import Config
from iambic.core.context import ctx
from iambic.core.utils import gather_templates
from iambic.request_handler.apply import apply_changes, flag_expired_resources
from iambic.request_handler.detect import detect_changes
from iambic.request_handler.generate import generate_templates

warnings.filterwarnings("ignore", category=FutureWarning, module="botocore.client")


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
    help="The template file path(s) to apply.",
)
def plan(templates: list[str]):
    asyncio.run(flag_expired_resources(templates))


@cli.command()
@click.option(
    "--config",
    "-c",
    "config_path",
    required=False,
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
    required=False,
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
    "--template-repo-dir",
    "-d",
    "template_dir",
    required=False,
    type=click.Path(exists=True),
    help="The repo directory containing the templates. Example: ~/noq-templates",
)
def apply(no_prompt: bool, config_path: str, templates: list[str], template_dir: str):
    if not templates:
        templates = asyncio.run(
            gather_templates(template_dir or str(pathlib.Path.cwd()))
        )

    config = Config.load(config_path)
    config.set_account_defaults()
    ctx.eval_only = not no_prompt
    changes_made = asyncio.run(apply_changes(config, templates))
    if ctx.eval_only and changes_made and click.confirm("Proceed?"):
        ctx.eval_only = False
        asyncio.run(apply_changes(config, templates))
    asyncio.run(detect_changes(config))


@cli.command(name="import")
@click.option(
    "--config",
    "-c",
    "config_paths",
    required=False,
    multiple=True,
    type=click.Path(exists=True),
    help="The config.yaml file paths. Example: ./prod/config.yaml",
)
@click.option(
    "--output-dir",
    "-o",
    "output_dir",
    required=False,
    type=click.Path(exists=True),
    help="The output directory to export templates to. Example: ~/noq-templates",
)
def import_(config_paths: list[str], output_dir: str):
    if not output_dir:
        output_dir = str(pathlib.Path.cwd())

    configs = list()
    for config_path in config_paths:
        config = Config.load(config_path)
        config.set_account_defaults()
        configs.append(config)

    asyncio.run(generate_templates(configs, output_dir))


if __name__ == "__main__":
    cli()
