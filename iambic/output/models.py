from __future__ import annotations

import json
import pathlib
from typing import Any, Dict, List, Optional, Set

from dictdiffer import diff
from pydantic import BaseModel as PydanticBaseModel
from pydantic import Field

from iambic.core.logger import log
from iambic.core.models import (
    AccountChangeDetails,
    ProposedChange,
    ProposedChangeType,
    TemplateChangeDetails,
)
from iambic.core.utils import camel_to_snake


class ProposedChangeDiff(ProposedChange):
    diff: Optional[str]
    diff_resolved: Optional[str]

    field_map = {
        "inline_policies": "InlinePolicies",
        "managed_policies": "ManagedPolicies",
        "policy_document": "PolicyDocument",
        "tags": "Tags",
        "assume_role_policy_document": "AssumeRolePolicyDocument",
        "permission_boundary": "PermissionBoundary",
        "customer_managed_policies": "CustomerManagedPolicies",
        "group_name": "GroupName",
        "group_email": "GroupEmail",
        "assignments": "Assignment",
        "domain": "Domain",
        "group": "Group",
        "groups": "Group",
        "users": "User",
        "user": "User",
    }

    def __init__(self, proposed_change: ProposedChange) -> None:
        super().__init__(**proposed_change.dict())
        try:
            object_attribute = camel_to_snake(self.attribute)
        except TypeError:
            object_attribute = None
        if self.current_value is None:
            self.current_value = {}
        if self.new_value is None:
            self.new_value = {}
        if isinstance(self.current_value, dict):
            self.diff = list(
                diff(self.current_value.get(object_attribute, {}), self.new_value)
            )
        else:
            self.diff = list(diff(self.current_value, self.new_value))

    @property
    def diff_plus_minus(self) -> List[str]:
        diff_plus_minus = ""
        for x in self.diff:
            label = self.attribute
            if x[0] == "change":
                if isinstance(x[2], list) or isinstance(x[2], tuple):
                    change_from = x[2][0]
                    change_to = x[2][1]
                else:
                    change_from = x[2]
                    change_to = x[2]
                if change_to:
                    diff_plus_minus += f"{label}:\n-(From)\n{json.dumps(change_from, indent=2)}\n+(To)\n{json.dumps(change_to, indent=2)}"
                else:
                    diff_plus_minus += (
                        f"{label}:\n-(Remove)\n{json.dumps(change_from, indent=2)}"
                    )
                diff_plus_minus.rstrip("\n")
            elif x[0] == "add":
                diff_plus_minus += (
                    f"{label}:\n+(Add)\n{json.dumps([y[1] for y in x[2]], indent=2)}"
                )
                diff_plus_minus.rstrip("\n")
            elif x[0] == "remove":
                diff_plus_minus += (
                    f"{label}:\n-(Remove)\n{json.dumps([y[1] for y in x[2]], indent=2)}"
                )
                diff_plus_minus.rstrip("\n")
        return diff_plus_minus


class ApplicableChange(PydanticBaseModel):
    account: Optional[str]
    change: Optional[ProposedChange]
    template_change: Optional[TemplateChangeDetails]
    template_name: Optional[str]
    resource_id: Optional[str]
    resource_type: Optional[str]

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
    account: Optional[str] = Field(default="NONE")
    count: Optional[int]
    num_changes: Optional[int]
    changes: Optional[List[ProposedChange]]

    def __hash__(self):
        return hash((self.account, self.num_changes))

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
    template_path: Optional[str]
    template_name: Optional[str]
    count: Optional[int]
    num_accounts: Optional[int]
    accounts: Optional[List[AccountSummary]]

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
        accounts = set(x.account for x in changes)
        instance.accounts = [
            AccountSummary.compile(
                account=account,
                count=len(changes),
                changes=[x for x in changes if x.account == account],
            )
            for account in accounts
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
    action: Optional[str]
    count: Optional[int]
    num_templates: Optional[int]
    templates: Optional[List[TemplateSummary]]

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
    action: Optional[str]
    count: Optional[int]
    num_templates: Optional[int]
    templates: Optional[List[TemplateSummary]]

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
    num_actions: Optional[int]
    num_templates: Optional[int]
    num_accounts: Optional[int]
    num_exceptions: Optional[int]
    action_summaries: Optional[List[ActionSummary]]
    exceptions: Optional[List[ExceptionSummary]]

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
