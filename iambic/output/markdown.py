import pathlib
from typing import Any, Dict, List
from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel as PydanticBaseModel

from iambic.core.logger import log
from iambic.core.models import (
    AccountChangeDetails,
    ProposedChange,
    ProposedChangeType,
    TemplateChangeDetails,
)


class ApplicableChange(PydanticBaseModel):
    change: ProposedChange
    template_change: TemplateChangeDetails
    template_name: str

    def __init__(self, change: ProposedChange, template_change: TemplateChangeDetails, **data: Any) -> None:
        self.template_name = pathlib.Path(template_change.template_path).name
        super().__init__(change=change, template_change=template_change, **data)


class AccountSummary(PydanticBaseModel):
    account: str
    count: int
    proposed_changes: List[ProposedChange]

    def __init__(self, account: str, count: int, changes: List[ProposedChange], **data: Any) -> None:
        self.account = account
        self.count = count
        self.proposed_changes = changes


class TemplateSummary(PydanticBaseModel):
    template_path: str
    template_name: str
    count: int
    accounts: List[AccountSummary]

    def __init__(self, template_path: str, template_name: str, changes: List[ProposedChange], **data: Any) -> None:
        self.accounts = [AccountSummary(
            account=change.account,
            count=len(changes),
            proposed_changes=[x for x in changes if x.account == change.account],
        ) for change in changes]


class ActionSummary(PydanticBaseModel):
    action: str
    count: int
    templates: List[TemplateSummary]

    @classmethod
    async def compile_proposed_changes(cls, resources_changes: List[TemplateChangeDetails], proposed_change_type: str) -> Any:
        """Compile a list of TemplateChangeDetails into a list of TemplateSummary objects.

        :param resources_changes: list of TemplateChangeDetails objects
        :returns: None
        """
        def _get_annotated_change(change: ProposedChange, template_change: TemplateChangeDetails) -> ApplicableChange:
            return ApplicableChange(
                change=change,
                template_change=template_change,
            )

        applicable_changes: List[ApplicableChange] = list()
        for template_change in resources_changes:
            for proposed_change in template_change.proposed_changes:
                if isinstance(proposed_change, AccountChangeDetails):
                    # If proposed change is a list of AccountChangeDetails, we need to iterate through those
                    for account_change in proposed_change.proposed_changes:
                        if account_change.change_type == proposed_change_type:
                            applicable_changes.append(_get_annotated_change(account_change, template_change))
                if proposed_change.change_type == proposed_change_type:
                    # If proposed change is a single change, we can just append it
                    applicable_changes.append(_get_annotated_change(proposed_change, template_change))

        log.debug(f"Found {len(applicable_changes)} applicable changes")

        self = cls(action=proposed_change_type, count=len(applicable_changes), templates=[])
        self.templates = [
            TemplateSummary(
                template_path=x.template_change.template_path,
                template_name=x.template_name,
                changes=[y for y in applicable_changes if y.template_change.template_path == x.template_change.template_path],
            ) for x in applicable_changes]

        return self

    @classmethod
    async def compile_exceptions_seen(cls, resources_changes: List[TemplateChangeDetails]) -> Any:
        pass


class ExceptionSummary(PydanticBaseModel):
    exception: str


class ActionSummaries(PydanticBaseModel):
    num_actions: int
    num_templates: int
    num_accounts: int
    action_summaries: List[ActionSummary]
    exceptions: List[ExceptionSummary]

    def __init__(self, changes: List[TemplateChangeDetails]):
        self.action_summaries = [ActionSummary.compile(changes, x) for x in list(ProposedChangeType)]
        self.num_actions = len(self.action_summaries)
        self.num_templates = sum([len(x.templates) for x in self.action_summaries])
        self.num_accounts = sum([len(z.accounts) for y in self.action_summaries for z in y.templates])


async def get_template_data(resources_changes: List[TemplateChangeDetails]) -> Dict[str, Any]:
    """Convert TemplateChangeDetails into a format that is oriented in this format.

    * Action (Add, Delete, Modify)
    * Template Name (Count of <action>)
    * Account Name (Count of <action>)
    * Changes for Account (Count of <action>)
    * Table of proposed changes

    For each, the corresponding jinja2 templates are:

    * Action: templates/actions.jinja2
    * Template Name: templates/template.jinja2
    * Account Name: templates/accounts.jinja2
    * Changes for Account: templates/resource_change.jinja2

    There is also a jinja template to display all exceptions:

    * Exceptions: templates/exception_details.jinja2

    :param resources_changes: list of TemplateChangeDetails objects
    :returns: Dict[str, Any]
    """
    action_summaries = ActionSummaries(resources_changes)
    # Get all proposed changes

    return action_summaries


def render_resource_changes(resource_changes):
    my_path = pathlib.Path(__file__).parent.absolute()
    env = Environment(loader=FileSystemLoader(my_path / 'templates'))
    template = env.get_template("resource_change.jinja2")
    return template.render(resource_changes=resource_changes)
