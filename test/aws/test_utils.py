from __future__ import annotations

import pytest
import yaml

from iambic.core.context import ExecutionContext
from iambic.core.utils import evaluate_on_provider
from iambic.plugins.v0_1_0.aws.iam.role.models import AwsIamRoleTemplate
from iambic.plugins.v0_1_0.aws.models import AWSAccount

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
template_cls = AwsIamRoleTemplate
resource_under_test = template_cls(file_path="/dev/null", **template_dict)
eval_only_context = ExecutionContext()
eval_only_context.eval_only = True


@pytest.mark.parametrize(
    "resource, aws_account, context, expected_value",
    [
        (
            resource_under_test,
            AWSAccount(account_id="123456789012", account_name="something"),
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
    value = evaluate_on_provider(resource, aws_account, context)
    assert value == expected_value
