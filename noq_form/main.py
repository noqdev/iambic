import asyncio

import click

from noq_form.config.models import Config
from noq_form.core.context import ctx
from noq_form.google.models import generate_group_templates
from noq_form.request_handler.apply import apply_changes, flag_expired_resources
from noq_form.request_handler.detect import detect_changes
import warnings
warnings.filterwarnings('ignore', category=FutureWarning, module='botocore.client')

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
def apply(no_prompt: bool, config_path: str, templates: list[str]):
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
    "config_path",
    required=False,
    type=click.Path(exists=True),
    help="The config.yaml file path to apply. Example: ./prod/config.yaml",
)
@click.option(
    "--output-dir",
    "-o",
    "output_dir",
    required=True,
    type=click.Path(exists=True),
    help="The output directory to export templates to. Example: ~/noq-templates",
)
def import_(config_path: str, output_dir: str):
    config = Config.load(config_path)
    config.set_account_defaults()
    # TODO (wbeasley): Support importing AWS roles
    # TODO: Create a setting to enable support for google groups
    # TODO: Ensure google_groups are not excluded from sync
    asyncio.run(generate_group_templates(config, "noq.dev", output_dir))


if __name__ == "__main__":
    cli()
