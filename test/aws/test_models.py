from __future__ import annotations

from iambic.aws.models import AccessModel, AWSTemplate
from iambic.core.template_generation import merge_model


def test_aws_template_merge(aws_accounts):
    existing_template = AWSTemplate(
        template_type="foo", file_path="bar", identifier="baz", expires_at="2023-01-27"
    )
    existing_template_expires_at = existing_template.expires_at
    new_template = AWSTemplate(
        template_type="foo_new", file_path="bar_new", identifier="baz_new"
    )
    merged_template = merge_model(new_template, existing_template, aws_accounts)
    assert merged_template.template_type == new_template.template_type
    assert merged_template.file_path == existing_template.file_path
    assert merged_template.identifier == new_template.identifier
    assert merged_template.expires_at == existing_template_expires_at


def test_access_model_sorting():

    included_accounts_1 = ["development", "ses"]
    included_accounts_2 = list(reversed(included_accounts_1))
    access_model_1 = AccessModel(included_accounts=included_accounts_1)
    access_model_2 = AccessModel(included_accounts=included_accounts_2)
    assert included_accounts_1 != included_accounts_2
    assert access_model_1.included_accounts == access_model_2.included_accounts
