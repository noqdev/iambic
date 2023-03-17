from typing import List
from colors import color
from rich.console import Console    
from rich.style import Style
from rich.text import Text
from rich.table import Table
from rich.tree import Tree
from tabulate import tabulate
from iambic.output.models import ActionSummary, ExceptionSummary


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


def rich_tree_summary(action_summary: ActionSummary):
    action_summary_tree = Tree(action_summary.action_name, expanded=False)
    for template in action_summary.templates:
        template_tree = action_summary_tree.add(template.template_path, expanded=False)
        for account in template.accounts:
            account_tree = template_tree.add(account.account_name, expanded=False)
            for change in account.changes:
                change_tree = account_tree.add(change.change_type, expanded=False)
                change_tree.add(change.resource_id)
                change_tree.add(change.resource_type)
                change_tree.add(change.change.change_type.value)
                if change.diff:
                    change_tree.add(change.diff)
    return action_summary_tree


def rich_tree_exception(exceptions: ExceptionSummary):
    exception_tree = Tree(exceptions.action_name, expanded=False)
    for template in exceptions.templates:
        template_tree = exception_tree.add(template.template_path, expanded=False)
        for account in template.accounts:
            account_tree = template_tree.add(account.account_name, expanded=False)
            for change in account.changes:
                change_tree = account_tree.add(change.change_type, expanded=False)
                change_tree.add(change.resource_id)
                change_tree.add(change.resource_type)
                change_tree.add(change.change.change_type.value)
                if change.diff:
                    change_tree.add(change.diff)
    return exception_tree


def ansi_format(value, style_str):
    return color(value, style_str)


def ansi_text_table(table_headers: List[str], table_data: List[List[str]]) -> str:
    # color formatting
    return tabulate(table_data, headers=table_headers, tablefmt="simple")    
