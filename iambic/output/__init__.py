import pathlib
from jinja2 import Environment, FileSystemLoader
from iambic.output.filters import (
    ansi_format,
    ansi_text_table,
    rich_format,
    rich_text,
    rich_text_table
)


def get_template_env():
    my_path = pathlib.Path(__file__).parent.absolute()
    env = Environment(loader=FileSystemLoader(my_path / "templates"))
    env.filters["ansi_format"] = ansi_format
    env.filters["ansi_text_table"] = ansi_text_table
    env.filters["rich_format"] = rich_format
    env.filters["rich_text"] = rich_text
    env.filters["rich_text_table"] = rich_text_table
    return env
