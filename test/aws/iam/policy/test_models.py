from __future__ import annotations

from iambic.core.template_generation import merge_model
from iambic.plugins.v0_1_0.aws.iam.policy.models import PolicyDocument


def test_merge_policy_document_with_sid(aws_accounts):
    existing_statement_list = [
        {
            "effect": "Allow",
            "sid": "ExpireStatement",
            "expires_at": "2023-01-24",
        }
    ]
    existing_document = PolicyDocument(
        policy_name="foo", version="bar", statement=existing_statement_list
    )
    new_statement_list = [{"effect": "Allow", "sid": "ExpireStatement"}]
    new_document = PolicyDocument(
        policy_name="foo", version="bar", statement=new_statement_list
    )
    merged_document: PolicyDocument = merge_model(
        new_document, existing_document, aws_accounts
    )

    assert (
        merged_document.statement[0].expires_at
        == existing_document.statement[0].expires_at
    )


def test_merge_policy_document_without_sid(aws_accounts):
    existing_statement_list = [
        {
            "effect": "Allow",
            "expires_at": "2023-01-24",
        }
    ]
    existing_document = PolicyDocument(
        policy_name="foo", version="bar", statement=existing_statement_list
    )
    new_statement_list = [{"effect": "Allow"}]
    new_document = PolicyDocument(
        policy_name="foo", version="bar", statement=new_statement_list
    )
    merged_document: PolicyDocument = merge_model(
        new_document, existing_document, aws_accounts
    )
    assert (
        merged_document.statement[0].expires_at
        == existing_document.statement[0].expires_at
    )
