from __future__ import annotations

import itertools
from typing import Optional, Union

import pytest
from pydantic import Extra

from iambic.core.models import AccessModelMixin, BaseModel
from iambic.core.template_generation import (
    base_group_str_attribute,
    group_dict_attribute,
    merge_model,
)


class SampleGroup(BaseModel, AccessModelMixin):
    group_id: int

    @property
    def resource_type(self):
        return "group:"

    @property
    def resource_id(self):
        return self.group_id

    @property
    def included_children(self):
        return ["*"]

    def set_included_children(self, value):
        pass

    @property
    def excluded_children(self):
        return []

    def set_excluded_children(self, value):
        pass

    @property
    def included_parents(self):
        return ["*"]

    def set_included_parents(self, value):
        pass

    @property
    def excluded_parents(self):
        return []

    def set_excluded_parents(self, value):
        pass


class SampleNote(BaseModel, AccessModelMixin):
    note: str

    @classmethod
    def new_instance_from_string(cls, s: str):
        return SampleNote(note=s)

    @property
    def resource_type(self):
        return "note:"

    @property
    def resource_id(self):
        return "static-id"

    @property
    def included_children(self):
        return ["*"]

    def set_included_children(self, value):
        pass

    @property
    def excluded_children(self):
        return []

    def set_excluded_children(self, value):
        pass

    @property
    def included_parents(self):
        return ["*"]

    def set_included_parents(self, value):
        pass

    @property
    def excluded_parents(self):
        return []

    def set_excluded_parents(self, value):
        pass


class SampleModel(BaseModel):
    note: Optional[Union[str, SampleNote, list[SampleNote]]]
    group: Optional[Union[int, SampleGroup, list[SampleGroup]]]

    class Config:
        arbitrary_types_allowed = True
        # keep the forbid for testing code
        extra = Extra.forbid

    @property
    def resource_type(self):
        return "sample-model:"

    @property
    def resource_id(self):
        return "static-id"


def test_merge_model_mix_types_1():
    # going from not a list to a list
    existing_model = SampleModel(
        note=SampleNote(note="foo"), group=SampleGroup(group_id=1)
    )
    new_model = SampleModel(
        note=[SampleNote(note="bar")], group=[SampleGroup(group_id=2)]
    )
    updated_model: SampleModel = merge_model(new_model, existing_model, [])
    assert updated_model.note[0].note == "bar"
    assert updated_model.group[0].group_id == 2


def test_merge_model_mix_types_2():
    # going from list[AccessModelMixin] to a primitive
    existing_model = SampleModel(
        note=[SampleNote(note="foo")], group=[SampleGroup(group_id=1)]
    )
    new_model = SampleModel(note="bar", group=2)
    updated_model: SampleModel = merge_model(new_model, existing_model, [])
    assert (  # Be careful: it's note[0] because existing list is type list on note
        updated_model.note[0].note == "bar"
    )

    # int is treated differently because there is no new_instance_from_string method
    assert updated_model.group == 2


def test_merge_model_mix_types_3():
    # going from list[AccessModelMixin] to AccessModelMixin
    existing_model = SampleModel(
        note=[SampleNote(note="foo")], group=[SampleGroup(group_id=1)]
    )
    new_model = SampleModel(note=SampleNote(note="bar"), group=SampleGroup(group_id=2))
    updated_model: SampleModel = merge_model(new_model, existing_model, [])
    assert updated_model.note.note == "bar"
    assert updated_model.group.group_id == 2


@pytest.mark.skip(reason="Not sure if this is a scenario IAMbic needs to handle.")
def test_merge_model_mix_types_4():
    # going from AccessModelMixin to a primitive
    existing_model = SampleModel(
        note=SampleNote(note="foo"), group=SampleGroup(group_id=1)
    )
    new_model = SampleModel(note="bar", group=2)
    updated_model: SampleModel = merge_model(new_model, existing_model, [])
    assert updated_model.note.note == "bar"

    # int is treated differently because there is no new_instance_from_string method
    assert updated_model.group == 2


@pytest.mark.asyncio
async def test_group_dict_attribute(aws_accounts: list):
    number_of_accounts = 1
    target_account = aws_accounts[0]
    target_account_id = target_account.account_id
    account_resources = [
        {
            "account_id": target_account_id,
            "resources": [{"resource_val": f"{target_account_id}"}],
        }
    ]
    aws_accounts_map = {account.account_id: account for account in aws_accounts}

    # validate the case if we don't prefer templatized resources
    # dict_attributes = await group_dict_attribute(
    #     aws_accounts_map,
    #     number_of_accounts,
    #     account_resources,
    #     False,
    #     prefer_templatized=False,
    # )
    # assert dict_attributes[0] == target_account_id

    # validate the case if we prefer templatized resources
    dict_attributes = await group_dict_attribute(
        aws_accounts_map,
        number_of_accounts,
        account_resources,
        "account_id",
        "included_accounts",
        False,
        prefer_templatized=True,
    )
    assert dict_attributes[0] == "{{var.account_id}}"


@pytest.mark.asyncio
async def test_base_group_str_attribute(aws_accounts: list):
    aws_account_map = {account.account_id: account for account in aws_accounts}
    # setup a scenario where a literal is both repeated and templatized
    repeated_literal = f"prefix-{aws_accounts[0].account_id}"
    account_0_resources = [
        {"account_id": aws_accounts[0].account_id, "resource_val": repeated_literal}
    ]
    account_1_resources = [
        {"account_id": aws_accounts[1].account_id, "resource_val": repeated_literal}
    ]
    account_2_resources = [
        {
            "account_id": aws_accounts[2].account_id,
            "resource_val": f"prefix-{aws_accounts[2].account_id}",
        }
    ]
    account_resources = [
        {"account_id": aws_accounts[0].account_id, "resources": account_0_resources},
        {"account_id": aws_accounts[1].account_id, "resources": account_1_resources},
        {"account_id": aws_accounts[2].account_id, "resources": account_2_resources},
    ]
    # grouped_role_map is in the format of "<shared-variable-reference>" : [account_resource_dict_1, account_resource_dict_n]
    # account_resource_dict_n must have key "account_id", and "resource_val"
    grouped_role_map = await base_group_str_attribute(
        aws_account_map, account_resources, "account_id"
    )
    grouped_keys_set = set(grouped_role_map.keys())
    expected_keys_set = set(
        ["prefix-{{var.account_id}}", f"prefix-{aws_accounts[0].account_id}"]
    )  # because we strongly preference on templatized version
    assert grouped_keys_set == expected_keys_set
    # the pattern is account_n_resources[0] because we only put 1 resource in the initial list
    assert account_0_resources[0] in grouped_role_map["prefix-{{var.account_id}}"]
    assert account_2_resources[0] in grouped_role_map["prefix-{{var.account_id}}"]
    assert account_1_resources[0] in grouped_role_map[repeated_literal]


@pytest.mark.asyncio
async def test_base_group_str_attribute_incoming_permutations(aws_accounts: list):
    aws_account_map = {account.account_id: account for account in aws_accounts}
    # setup a scenario where a literal is both repeated and templatized
    repeated_literal = f"prefix-{aws_accounts[0].account_id}"
    account_0_resources = [
        {"account_id": aws_accounts[0].account_id, "resource_val": repeated_literal}
    ]
    account_1_resources = [
        {"account_id": aws_accounts[1].account_id, "resource_val": repeated_literal}
    ]
    account_2_resources = [
        {
            "account_id": aws_accounts[2].account_id,
            "resource_val": f"prefix-{aws_accounts[2].account_id}",
        }
    ]
    account_resources = [
        {"account_id": aws_accounts[0].account_id, "resources": account_0_resources},
        {"account_id": aws_accounts[1].account_id, "resources": account_1_resources},
        {"account_id": aws_accounts[2].account_id, "resources": account_2_resources},
    ]

    account_resources_permutations = list(itertools.permutations(account_resources))

    # validate on each permutation
    for account_resource_permutation in account_resources_permutations:
        # grouped_role_map is in the format of "<shared-variable-reference>" : [account_resource_dict_1, account_resource_dict_n]
        # account_resource_dict_n must have key "account_id", and "resource_val"
        grouped_role_map = await base_group_str_attribute(
            aws_account_map, account_resource_permutation, "account_id"
        )
        grouped_keys_set = set(grouped_role_map.keys())
        expected_keys_set = set(
            ["prefix-{{var.account_id}}", f"prefix-{aws_accounts[0].account_id}"]
        )  # because we strongly preference on templatized version
        assert grouped_keys_set == expected_keys_set
        # the pattern is account_n_resources[0] because we only put 1 resource in the initial list
        assert account_0_resources[0] in grouped_role_map["prefix-{{var.account_id}}"]
        assert account_2_resources[0] in grouped_role_map["prefix-{{var.account_id}}"]
        assert account_1_resources[0] in grouped_role_map[repeated_literal]
