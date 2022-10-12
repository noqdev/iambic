import asyncio

import click

from noq_form.core.context import ctx
from noq_form.request_handler.apply import apply_changes, flag_expired_resources
from noq_form.request_handler.generate import generate_templates


@click.group()
def cli():
    ...


@cli.command()
@click.option(
    "--config",
    "-c",
    "configs",
    required=False,
    multiple=True,
    type=click.Path(exists=True),
    help="The config.yaml file paths. Example: ./prod/config.yaml",
)
def generate(configs: list[str]):
    # We should auto-detect in the long-term
    asyncio.run(generate_templates(configs))


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
    "--no-prompt",
    is_flag=True,
    show_default=True,
    help="Apply changes without asking for permission?",
)
@click.option(
    "--config",
    "-c",
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
def apply(no_prompt: bool, config: str, templates: list[str]):
    ctx.eval_only = not no_prompt
    changes_made = asyncio.run(apply_changes(config, templates))
    if ctx.eval_only and changes_made and click.confirm("Proceed?"):
        ctx.eval_only = False
        asyncio.run(apply_changes(config, templates))


if __name__ == "__main__":
    cli()
