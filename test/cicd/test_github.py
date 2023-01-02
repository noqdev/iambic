from __future__ import annotations

from unittest.mock import patch

import pytest

from iambic.cicd.github import (
    MERGEABLE_STATE_BLOCKED,
    MERGEABLE_STATE_CLEAN,
    handle_issue_comment,
)


@pytest.fixture
def mock_github_client():
    with patch("iambic.cicd.github.Github", autospec=True) as mock_github:
        yield mock_github


@pytest.fixture
def issue_comment_context():
    return {
        "repository": "example.com/iambic-templates",
        "event_name": "issue_comment",
        "event": {
            "issue": {
                "number": 1,
            }
        },
    }


@pytest.fixture
def mock_lambda_run_handler():
    with patch(
        "iambic.cicd.github.lambda_run_handler", autospec=True
    ) as _mock_lambda_run_handler:
        yield _mock_lambda_run_handler


def test_issue_comment_with_non_clean_mergeable_state(
    mock_github_client, issue_comment_context, mock_lambda_run_handler
):
    mock_pull_request = mock_github_client.get_repo.return_value.get_pull.return_value
    mock_pull_request.mergeable_state = MERGEABLE_STATE_BLOCKED
    handle_issue_comment(mock_github_client, issue_comment_context)
    assert mock_lambda_run_handler.called is False
    assert mock_pull_request.merge.called is False


def test_issue_comment_with_clean_mergeable_state(
    mock_github_client, issue_comment_context, mock_lambda_run_handler
):
    mock_pull_request = mock_github_client.get_repo.return_value.get_pull.return_value
    mock_pull_request.mergeable_state = MERGEABLE_STATE_CLEAN
    handle_issue_comment(mock_github_client, issue_comment_context)
    assert mock_lambda_run_handler.called
    assert mock_pull_request.merge.called
