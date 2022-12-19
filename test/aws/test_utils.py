import pytest
import yaml

from iambic.aws.models import AWSAccount
from iambic.aws.utils import evaluate_on_account
from iambic.config.templates import TEMPLATE_TYPE_MAP
from iambic.core.context import ExecutionContext

TEMPLATE_UNDER_TEST = """
template_type: NOQ::AWS::IAM::Role
identifier: iambic_itest_not_managed_by_iambic
included_accounts:
  - dev
  - regex*
properties:
  assume_role_policy_document:
    statement:
      - action: sts:AssumeRole
        effect: Deny
        principal:
          service: ec2.amazonaws.com
    version: '2012-10-17'
  description: This is role that is intentionally not managed by iambic. An invariant is this role should have no access grants.
  role_name: iambic_itest_not_managed_by_iambic
"""

template_dict = yaml.safe_load(TEMPLATE_UNDER_TEST)
template_cls = TEMPLATE_TYPE_MAP[template_dict["template_type"]]
resource_under_test = template_cls(file_path="/dev/null", **template_dict)
eval_only_context = ExecutionContext()
eval_only_context.eval_only = True


@pytest.mark.parametrize(
    "resource, aws_account, context, expected_value",
    [
        (
            resource_under_test,
            AWSAccount(account_id="123456789012"),
            eval_only_context,
            False,
        ),
        (
            resource_under_test,
            AWSAccount(account_id="123456789012", account_name="dev"),
            eval_only_context,
            True,
        ),
        (
            resource_under_test,
            AWSAccount(account_id="123456789012", account_name="development"),
            eval_only_context,
            False,
        ),
        (
            resource_under_test,
            AWSAccount(account_id="123456789012", account_name="regex1"),
            eval_only_context,
            True,
        ),
    ],
)
def test_evaluate_on_account(resource, aws_account, context, expected_value):
    value = evaluate_on_account(resource, aws_account, context)
    assert value == expected_value
