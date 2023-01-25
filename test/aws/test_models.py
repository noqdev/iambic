from __future__ import annotations

from iambic.aws.models import AWSTemplate
from iambic.core.models import merge_model


def test_aws_template_merge():
    existing_template = AWSTemplate(
        template_type="foo", file_path="bar", identifier="baz", expires_at="2023-01-27"
    )
    existing_template_expires_at = existing_template.expires_at
    new_template = AWSTemplate(
        template_type="foo_new", file_path="bar_new", identifier="baz_new"
    )
    merged_template = merge_model(existing_template, new_template)
    assert merged_template.template_type == new_template.template_type
    assert merged_template.file_path == new_template.file_path
    assert merged_template.identifier == new_template.identifier
    assert merged_template.expires_at == existing_template_expires_at
