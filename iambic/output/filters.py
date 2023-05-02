from __future__ import annotations

from io import StringIO
from typing import List

from rich.console import Console
from rich.style import Style
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from iambic.output.models import ActionSummary, ExceptionSummary

console = Console()


def rich_format(value: str, style_str: str) -> str:
    style = Style.parse(style_str)
    return console.render_str(str(value), style=style)


def rich_text(text: str, style_str: str) -> str:
    style = Style.parse(style_str)
    return Text(str(text), style=style)


def rich_text_table(table_headers: List[str], table_data: List[List[str]]) -> str:
    table = Table(show_header=True, header_style="bold magenta")
    for header in table_headers:
        table.add_column(header, justify="left", style="dim", no_wrap=True)
    for row in table_data:
        table.add_row(*row)
    console.render_lines(table)


def rich_tree_summary(action_summary: ActionSummary):
    action_summary_tree = Tree(action_summary.action, expanded=True)
    for template in action_summary.templates:
        template_tree = action_summary_tree.add(template.template_path, expanded=True)
        for account in template.accounts:
            account_tree = template_tree.add(account.account, expanded=True)
            for change in account.changes:
                change_tree = account_tree.add(
                    f"{change.change.resource_type} // {change.change.resource_id}",
                    expanded=True,
                )
                if change.change.diff:
                    change_tree.add(change.change.diff_plus_minus)
    console = Console(file=StringIO(), force_terminal=True)
    console.print(action_summary_tree)
    output = console.file.getvalue()
    return output


def rich_tree_exception(exceptions: ExceptionSummary):
    exception_tree = Tree(exceptions.action, expanded=True)
    for template in exceptions.templates:
        template_tree = exception_tree.add(template.template_path, expanded=True)
        for account in template.accounts:
            account_tree = template_tree.add(account.account, expanded=True)
            for change in account.changes:
                change_tree = account_tree.add(
                    str(change.change.change_type), expanded=True
                )
                change_tree.add(change.change.resource_id)
                change_tree.add(change.change.resource_type)
                change_tree.add(str(change.change.change_type.value))
                if change.change.diff:
                    change_tree.add("* " + "\n* ".join(change.change.diff_plus_minus))
    console = Console(file=StringIO(), force_terminal=True)
    console.print(exception_tree)
    output = console.file.getvalue()
    return output
