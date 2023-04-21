from __future__ import annotations

import pathlib

from jinja2 import Environment, FileSystemLoader

from iambic.output.filters import (
    rich_format,
    rich_text,
    rich_text_table,
    rich_tree_exception,
    rich_tree_summary,
)


def get_template_env():
    my_path = pathlib.Path(__file__).parent.absolute()
    env = Environment(loader=FileSystemLoader(my_path / "templates"))
    env.filters["rich_format"] = rich_format
    env.filters["rich_text"] = rich_text
    env.filters["rich_text_table"] = rich_text_table
    env.filters["rich_tree_summary"] = rich_tree_summary
    env.filters["rich_tree_exception"] = rich_tree_exception
    return env
