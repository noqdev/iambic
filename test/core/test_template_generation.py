from __future__ import annotations

from typing import Union

from iambic.core.models import AccessModelMixin, BaseModel
from iambic.core.template_generation import merge_model


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
    assert updated_model.note.note == "bar"
