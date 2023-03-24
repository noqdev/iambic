from __future__ import annotations

from iambic.core.template_generation import merge_model
from iambic.plugins.v0_1_0.aws.models import AccessModel, AWSTemplate


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


# Make sure even if includedd children is modified after model
# creation the sort weight is still stable
def test_access_model_sorting_weight():
    included_accounts_1 = ["development", "ses"]
    access_model_1 = AccessModel()
    access_model_2 = AccessModel()
    access_model_1.included_accounts.extend(included_accounts_1)
    access_model_2.included_accounts.extend(reversed(included_accounts_1))
    assert access_model_1.included_accounts != access_model_2.included_accounts
    assert (
        access_model_1.access_model_sort_weight()
        == access_model_2.access_model_sort_weight()
    )
