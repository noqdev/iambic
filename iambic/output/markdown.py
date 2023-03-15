from __future__ import annotations

import pathlib
from typing import Any, Dict, List, Set

from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel as PydanticBaseModel
from pydantic import Field
from recursive_diff import recursive_diff

from iambic.core.logger import log
from iambic.core.models import (
    AccountChangeDetails,
    ProposedChange,
    ProposedChangeType,
    TemplateChangeDetails,
)


class ProposedChangeDiff(ProposedChange):
    diff: str = Field(default=None)

    def __init__(self, proposed_change: ProposedChange) -> None:
        super().__init__(**proposed_change.dict())
        self.diff = "\n".join(list(recursive_diff(self.current_value, self.new_value)))


class ApplicableChange(PydanticBaseModel):
    account: str = Field(default=None)
    change: ProposedChange = Field(default=None)
    template_change: TemplateChangeDetails = Field(default=None)
    template_name: str = Field(default=None)
    resource_id: str = Field(default=None)
    resource_type: str = Field(default=None)

    def __hash__(self):
        return hash((self.resource_id, self.resource_type))

    def __init__(
        self,
        change: ProposedChange,
        template_change: TemplateChangeDetails,
        **data: Any,
    ) -> None:
        super().__init__(
            change=ProposedChangeDiff(change), template_change=template_change, **data
        )
        self.template_name = pathlib.Path(template_change.template_path).name


class AccountSummary(PydanticBaseModel):
    account: str = Field(default="NONE")
    count: int = Field(default=0)
    num_changes: int = Field(default=0)
    changes: List[ProposedChange] = Field(default=[])

    @classmethod
    def compile(
        cls, account: str, count: int, changes: List[ProposedChange], **data: Any
    ) -> None:
        instance = cls()
        instance.account = account
        instance.count = count
        instance.num_changes = len(changes)
        instance.changes = changes
        return instance


class TemplateSummary(PydanticBaseModel):
    template_path: str = Field(default="")
    template_name: str = Field(default="")
    count: int = Field(default=0)
    num_accounts: int = Field(default=0)
    accounts: List[AccountSummary] = Field(default=[])

    def __hash__(self):
        return hash(self.template_path)

    @classmethod
    def compile(
        cls,
        template_path: str,
        template_name: str,
        count: int,
        changes: List[ProposedChange],
        **data: Any,
    ) -> None:
        instance = cls()
        instance.template_path = template_path
        instance.template_name = template_name
        instance.count = count
        instance.num_accounts = len(set([x.account for x in changes]))
        instance.accounts = [
            AccountSummary.compile(
                account=change.account,
                count=len(changes),
                changes=[x for x in changes if x.account == change.account],
            )
            for change in changes
        ]
        return instance


def get_applicable_changes(
    template_changes: List[TemplateChangeDetails],
    proposed_change_type: str,
    attribute: str = "proposed_changes",
) -> Any:
    """Compile applicable changes as a list of ApplicableChange objects.

    :param template_changes: list of TemplateChangeDetails objects
    :param proposed_change_type: one of ProposedChangeType values
    :param attribute: str. is either "proposed_changes" or "exceptions_seen"
    :return: set of ApplicableChange
    """

    def _get_annotated_change(
        change: ProposedChange,
        template_change: TemplateChangeDetails,
        account: str = "NONE",
    ) -> ApplicableChange:
        return ApplicableChange(
            account=account,
            change=change,
            template_change=template_change,
            resource_id=change.resource_id,
            resource_type=change.resource_type,
        )

    applicable_changes: Set[ApplicableChange] = set()
    for template_change in template_changes:
        for proposed_change in getattr(template_change, attribute, []):
            if isinstance(proposed_change, AccountChangeDetails):
                # If proposed change is a list of AccountChangeDetails, we need to iterate through those
                for account_change in proposed_change.proposed_changes:
                    if account_change.change_type.value == proposed_change_type:
                        applicable_changes.add(
                            _get_annotated_change(
                                account_change, template_change, proposed_change.account
                            )
                        )
            else:
                if proposed_change.change_type.value == proposed_change_type:
                    # If proposed change is a single change, we can just append it
                    applicable_changes.add(
                        _get_annotated_change(proposed_change, template_change)
                    )

    return set(applicable_changes)  # collapse across accounts and no accounts


class ActionSummary(PydanticBaseModel):
    action: str = Field(default="")
    count: int = Field(default=0)
    num_templates = Field(default=0)
    templates: List[TemplateSummary] = Field(default=[])

    @classmethod
    def compile_proposed_changes(
        cls, template_changes: List[TemplateChangeDetails], proposed_change_type: str
    ) -> Any:
        """Compile a list of TemplateChangeDetails into a list of TemplateSummary objects.

        :param resources_changes: list of TemplateChangeDetails objects
        :returns: None
        """
        applicable_changes = get_applicable_changes(
            template_changes, proposed_change_type, attribute="proposed_changes"
        )
        log.debug(f"Found {len(applicable_changes)} applicable changes")

        instance = cls(
            action=proposed_change_type, count=len(applicable_changes), templates=[]
        )
        templates = set(
            [
                TemplateSummary.compile(
                    template_path=x.template_change.template_path,
                    template_name=x.template_name,
                    count=1,
                    changes=[
                        y
                        for y in applicable_changes
                        if y.template_change.template_path
                        == x.template_change.template_path
                    ],
                )
                for x in applicable_changes
            ]
        )
        instance.templates = templates
        instance.num_templates = len(templates)

        return instance


class ExceptionSummary(PydanticBaseModel):
    action: str = Field(default="")
    count: int = Field(default=0)
    num_templates = Field(default=0)
    templates: List[TemplateSummary] = Field(default=[])

    @classmethod
    def compile_exceptions_seen(
        cls, template_changes: List[TemplateChangeDetails], proposed_change_type: str
    ) -> Any:
        exceptions = get_applicable_changes(
            template_changes, proposed_change_type, attribute="exceptions_seen"
        )
        log.debug(f"Found {len(exceptions)} exceptions")

        instance = cls(
            action=proposed_change_type,
            count=len(exceptions),
            num_templates=0,
            templates=[],
        )
        templates = set(
            [
                TemplateSummary.compile(
                    template_path=x.template_change.template_path,
                    template_name=x.template_name,
                    count=1,
                    changes=[
                        y
                        for y in exceptions
                        if y.template_change.template_path
                        == x.template_change.template_path
                    ],
                )
                for x in exceptions
            ]
        )
        instance.templates = templates
        instance.num_templates = len(templates)

        return instance


class ActionSummaries(PydanticBaseModel):
    num_actions: int = Field(default=0)
    num_templates: int = Field(default=0)
    num_accounts: int = Field(default=0)
    num_exceptions: int = Field(default=0)
    action_summaries: List[ActionSummary] = Field(default=[])
    exceptions: List[ExceptionSummary] = Field(default=[])

    @classmethod
    def compile(cls, changes: List[TemplateChangeDetails]):
        instance = cls()
        instance.action_summaries = [
            ActionSummary.compile_proposed_changes(changes, x)
            for x in list([e.value for e in ProposedChangeType])
        ]
        instance.num_actions = sum(
            [1 for x in instance.action_summaries if x.count > 0]
        )
        instance.num_templates = sum(
            [len(x.templates) for x in instance.action_summaries]
        )
        accounts = set(
            [
                g.account
                for y in instance.action_summaries
                for z in y.templates
                for g in z.accounts
            ]
        )
        instance.num_accounts = len(accounts)
        instance.exceptions = [
            ExceptionSummary.compile_exceptions_seen(changes, x)
            for x in list([e.value for e in ProposedChangeType])
        ]
        instance.num_exceptions = sum([1 for x in instance.exceptions if x.count > 0])
        return instance


def get_template_data(resources_changes: List[TemplateChangeDetails]) -> Dict[str, Any]:
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
    return ActionSummaries.compile(resources_changes)


def gh_render_resource_changes(resource_changes: List[TemplateChangeDetails]):
    template_data = get_template_data(resource_changes)
    my_path = pathlib.Path(__file__).parent.absolute()
    env = Environment(loader=FileSystemLoader(my_path / "templates"))
    template = env.get_template("github_summary.jinja2")
    return template.render(iambic=template_data)
