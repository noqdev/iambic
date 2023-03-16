from typing import List
from colors import color
from rich.console import Console    
from rich.style import Style
from rich.text import Text
from rich.table import Table
from tabulate import tabulate


console = Console()
def rich_format(value: str, style_str: str) -> str:
    style = Style.parse(style_str)
    return console.render_str(value, style)


def rich_text(text: str, style_str: str) -> str:
    style = Style.parse(style_str)
    return Text(text, style=style)


def rich_text_table(table_headers: List[str], table_data: List[List[str]]) -> str:
    table = Table(show_header=True, header_style="bold magenta")
    for header in table_headers:
        table.add_column(header, justify="left", style="dim", no_wrap=True)
    for row in table_data:
        table.add_row(*row)
    console.render_lines(table)


def ansi_format(value, style_str):
    return color(value, style_str)


def ansi_text_table(table_headers: List[str], table_data: List[List[str]]) -> str:
    # color formatting
    return tabulate(table_data, headers=table_headers, tablefmt="simple")    
