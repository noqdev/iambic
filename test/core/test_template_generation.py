from __future__ import annotations

from typing import Union

import pytest
from iambic.core.models import AccessModelMixin, BaseModel
from iambic.core.template_generation import group_dict_attribute, merge_model


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

    note: Union[str, SampleNote, list[SampleNote]]

    class Config:
        arbitrary_types_allowed = True

    @property
    def resource_type(self):
        return "sample-model:"

    @property
    def resource_id(self):
        return "static-id"


def test_merge_model_mix_types_1():
    # going from not a list to a list
    existing_model = SampleModel(note=SampleNote(note="foo"))
    new_model = SampleModel(note=[SampleNote(note="bar")])
    updated_model: SampleModel = merge_model(new_model, existing_model, [])
    assert updated_model.note[0].note == "bar"


def test_merge_model_mix_types_2():
    # going from list[AccessModelMixin] to a primitive
    existing_model = SampleModel(note=[SampleNote(note="foo")])
    new_model = SampleModel(note="bar")
    updated_model: SampleModel = merge_model(new_model, existing_model, [])
    assert (
        updated_model.note[0].note == "bar"
    )  # be careful why it's note[0] because existing list is type list on note


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
    dict_attributes = await group_dict_attribute(
        aws_accounts_map,
        number_of_accounts,
        account_resources,
        False,
        prefer_templatized=False,
    )
    assert dict_attributes[0] == target_account_id

    # validate the case if we prefer templatized resources
    dict_attributes = await group_dict_attribute(
        aws_accounts_map,
        number_of_accounts,
        account_resources,
        False,
        prefer_templatized=True,
    )
    assert dict_attributes[0] == "{{account_id}}"
