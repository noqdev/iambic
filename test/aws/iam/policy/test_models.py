from __future__ import annotations

from iambic.aws.iam.policy.models import PolicyDocument
from iambic.core.models import merge_model


def test_merge_policy_document_with_sid():
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
    merged_document: PolicyDocument = merge_model(existing_document, new_document)
    assert (
        merged_document.statement[0].expires_at
        == existing_document.statement[0].expires_at
    )


def test_merge_policy_document_without_sid():
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
    merged_document: PolicyDocument = merge_model(existing_document, new_document)
    assert (
        merged_document.statement[0].expires_at
        == existing_document.statement[0].expires_at
    )
