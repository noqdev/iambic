from __future__ import annotations

from iambic.core.iambic_enum import IambicManaged
from iambic.core.models import BaseTemplate, merge_model


def test_merge_model():
    existing_template = BaseTemplate(
        template_type="foo", file_path="bar", iambic_managed=IambicManaged.IMPORT_ONLY
    )
    new_template = BaseTemplate(
        template_type="foo_new",
        file_path="bar_new",
        iambic_managed=IambicManaged.UNDEFINED,
    )
    merged_template = merge_model(existing_template, new_template)
    assert merged_template.template_type == new_template.template_type
    assert merged_template.iambic_managed == IambicManaged.IMPORT_ONLY
    assert merged_template.file_path == existing_template.file_path


def test_merge_model_with_none():
    existing_template = BaseTemplate(
        template_type="foo", file_path="bar", iambic_managed=IambicManaged.IMPORT_ONLY
    )
    new_template = None
    merged_template = merge_model(existing_template, new_template)
    assert merged_template is None
