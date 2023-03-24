from __future__ import annotations

import sys
import traceback
from typing import Optional

import pytest
from pydantic import ValidationError

from iambic.core.models import ProviderChild
from iambic.core.template_generation import merge_access_model_list
from iambic.plugins.v0_1_0.aws.identity_center.permission_set.models import (
    AWSIdentityCenterPermissionSetProperties,
    AwsIdentityCenterPermissionSetTemplate,
    PermissionSetAccess,
)
from iambic.plugins.v0_1_0.aws.models import Description


def test_description_validation_with_default_being_none():
    properties = AWSIdentityCenterPermissionSetProperties(name="foo")
    assert properties.description is None


def test_description_validation_with_empty_string():
    with pytest.raises(ValidationError) as exc_info:
        AWSIdentityCenterPermissionSetProperties(name="foo", description="")
    if sys.version_info < (3, 10):
        exc = exc_info.value
        captured_traceback_lines = traceback.format_exception(
            type(exc), exc, exc.__traceback__
        )
    else:
        captured_traceback_lines = traceback.format_exception(
            exc_info.value
        )  # this is a pytest specific format
    captured_traceback = "\n".join(captured_traceback_lines)

    assert "description must be between 1 and 700 characters" in captured_traceback


def test_description_validation_with_valid_string():
    properties = AWSIdentityCenterPermissionSetProperties(name="foo", description="A")
    assert properties.description == "A"


def test_description_validation_with_valid_list():
    properties = AWSIdentityCenterPermissionSetProperties(
        name="foo", description=[Description(description="A")]
    )
    assert properties.description[0].description == "A"


def test_description_validation_with_list_with_empty_string():
    with pytest.raises(ValidationError) as exc_info:
        AWSIdentityCenterPermissionSetProperties(
            name="foo", description=[Description(description="")]
        )
    if sys.version_info < (3, 10):
        exc = exc_info.value
        captured_traceback_lines = traceback.format_exception(
            type(exc), exc, exc.__traceback__
        )
    else:
        captured_traceback_lines = traceback.format_exception(
            exc_info.value
        )  # this is a pytest specific format
    captured_traceback = "\n".join(captured_traceback_lines)
    assert "description must be between 1 and 700 characters" in captured_traceback


def test_description_sorting():

    description = [
        {"included_accounts": ["account_1", "account_2"], "description": "foo"},
        {"included_accounts": ["account_3"], "description": "bar"},
    ]
    properties_1 = AWSIdentityCenterPermissionSetProperties(
        name="foo", description=description
    )
    description_1 = properties_1.description
    description_2 = list(reversed(properties_1.description))
    assert description_1 != description_2  # because we reverse the list
    properties_1.description = description_2
    assert (
        properties_1.description == description_2
    )  # double check the list is reversed because validation doesn't happen after creation
    properties_1.validate_model_afterward()
    assert properties_1.description == description_1


def test_access_rule_validation():

    access_rules = [
        {"included_accounts": ["account_1", "account_2"], "users": ["foo"]},
        {"included_accounts": ["account_3"], "users": ["bar"]},
    ]
    properties_1 = AWSIdentityCenterPermissionSetProperties(name="foo")
    template_1 = AwsIdentityCenterPermissionSetTemplate(
        file_path="foo",
        identifier="foo",
        properties=properties_1,
        access_rules=access_rules,
    )
    access_rules_1 = template_1.access_rules
    access_rules_2 = list(reversed(template_1.access_rules))
    assert access_rules_1 != access_rules_2  # because we reverse the list
    template_1.access_rules = access_rules_2
    assert (
        template_1.access_rules == access_rules_2
    )  # double check the list is reversed because validation doesn't happen after creation
    template_1.validate_model_afterward()
    assert template_1.access_rules == access_rules_1


class FakeAccount(ProviderChild):

    name: str
    account_owner: str

    @property
    def parent_id(self) -> Optional[str]:
        """
        For example, the parent_id of an AWS account is the AWS organization ID
        """
        return self.account_owner

    @property
    def preferred_identifier(self) -> str:
        return self.name

    @property
    def all_identifiers(self) -> set[str]:
        return set([self.name])


def test_merge_access_rule():
    # if we have an old list of PermissionSets and a an new list of reversed-order PermissionSets
    # after merging, the expectation is nothing has changed from the old list.

    access_rules_1 = [
        {"included_accounts": ["account_1", "account_2"], "users": ["foo"]},
        {"included_accounts": ["account_3"], "users": ["bar"]},
    ]
    old_list = [PermissionSetAccess(**rule) for rule in access_rules_1]
    new_list = list(reversed(old_list))
    assert old_list != new_list  # because we reverse the list
    accounts = [
        FakeAccount(name="account_1", account_owner="foo"),
        FakeAccount(name="account_2", account_owner="foo"),
        FakeAccount(name="account_3", account_owner="foo"),
    ]
    new_value = merge_access_model_list(new_list, old_list, accounts)
    for i, element in enumerate(new_value):
        assert element.json() == new_list[i].json()
