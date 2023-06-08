from __future__ import annotations

import shutil
import tempfile
from unittest import mock
from unittest.mock import AsyncMock, MagicMock, PropertyMock, call, patch

import github
import pytest

from iambic.plugins.v0_1_0.github.github import (
    BODY_MAX_LENGTH,
    MERGEABLE_STATE_BLOCKED,
    MERGEABLE_STATE_CLEAN,
    HandleIssueCommentReturnCode,
    _post_artifact_to_companion_repository,
    ensure_body_length_fits_github_spec,
    format_github_url,
    get_session_name,
    handle_issue_comment,
    handle_pull_request,
    maybe_merge,
)


@pytest.fixture
def mock_github_client():
    with patch("github.Github", autospec=True) as mock_github:
        yield mock_github


@pytest.fixture
def issue_comment_git_apply_context():
    return {
        "server_url": "https://github.com",
        "run_id": "12345",
        "run_attempt": "1",
        "token": "fake-token",
        "sha": "fake-sha",
        "ref": "fake-branch",
        "repository": "example.com/iambic-templates",
        "event_name": "issue_comment",
        "event": {
            "comment": {
                "body": "iambic git-apply",
                "user": {
                    "login": "fake-commenter",
                },
            },
            "issue": {
                "number": 1,
            },
            "repository": {
                "clone_url": "https://github.com/example-org/iambic-templates.git",
            },
        },
        "user": {
            "login": "faker-user",
        },
    }


@pytest.fixture
def issue_comment_git_plan_context():
    return {
        "server_url": "https://github.com",
        "run_id": "12345",
        "run_attempt": "1",
        "token": "fake-token",
        "sha": "fake-sha",
        "ref": "fake-branch",
        "repository": "example.com/iambic-templates",
        "event_name": "issue_comment",
        "event": {
            "comment": {
                "body": "iambic git-plan",
                "user": {
                    "login": "fake-commenter",
                },
            },
            "issue": {
                "number": 1,
            },
            "repository": {
                "clone_url": "https://github.com/example-org/iambic-templates.git",
            },
        },
    }


@pytest.fixture
def issue_comment_git_approve_context():
    return {
        "server_url": "https://github.com",
        "run_id": "12345",
        "run_attempt": "1",
        "token": "fake-token",
        "sha": "fake-sha",
        "ref": "fake-branch",
        "repository": "example.com/iambic-templates",
        "event_name": "issue_comment",
        "event": {
            "comment": {
                "body": "iambic approve",
                "user": {
                    "login": "fake-commenter",
                },
            },
            "issue": {
                "number": 1,
            },
            "repository": {
                "clone_url": "https://github.com/example-org/iambic-templates.git",
            },
        },
    }


@pytest.fixture
def mock_lambda_run_handler():
    with patch(
        "iambic.plugins.v0_1_0.github.github.lambda_run_handler", autospec=True
    ) as _mock_lambda_run_handler:
        with patch(
            "iambic.plugins.v0_1_0.github.github.SHARED_CONTAINER_GITHUB_DIRECTORY",
            "/tmp",
        ) as _:
            with tempfile.TemporaryDirectory() as tmpdirname:
                with patch("iambic.lambda.app.REPO_BASE_PATH", tmpdirname):
                    yield _mock_lambda_run_handler


@pytest.fixture
def mock_resolve_config_template_path():
    async_mock = AsyncMock()
    with patch(
        "iambic.plugins.v0_1_0.github.github.resolve_config_template_path",
        side_effect=async_mock,
    ) as _mock_resolve_config_template_path:
        yield _mock_resolve_config_template_path


@pytest.fixture
def mock_load_config():
    async_mock = AsyncMock()
    with patch(
        "iambic.plugins.v0_1_0.github.github.load_config", side_effect=async_mock
    ) as _load_config:
        async_mock.return_value.github.allowed_bot_approver = "fake-commenter"
        yield _load_config


@pytest.fixture
def mock_run_git_plan():
    with patch(
        "iambic.plugins.v0_1_0.github.github.run_git_plan", autospec=True
    ) as _mock_run_git_plan:
        with patch(
            "iambic.plugins.v0_1_0.github.github.SHARED_CONTAINER_GITHUB_DIRECTORY",
            "/tmp",
        ) as _:
            with tempfile.TemporaryDirectory() as tmpdirname:
                with patch("iambic.lambda.app.REPO_BASE_PATH", tmpdirname):
                    yield _mock_run_git_plan


@pytest.fixture
def mock_run_git_apply():
    with patch(
        "iambic.plugins.v0_1_0.github.github.run_git_apply", autospec=True
    ) as _mock_run_git_plan:
        with patch(
            "iambic.plugins.v0_1_0.github.github.SHARED_CONTAINER_GITHUB_DIRECTORY",
            "/tmp",
        ) as _:
            with tempfile.TemporaryDirectory() as tmpdirname:
                with patch("iambic.lambda.app.REPO_BASE_PATH", tmpdirname):
                    yield _mock_run_git_plan


@pytest.fixture
def mock_repository():
    with patch("iambic.core.git.Repo", autospec=True) as _mock_repository:
        yield _mock_repository


def test_issue_comment_with_non_clean_mergeable_state(
    mock_github_client, issue_comment_git_apply_context, mock_lambda_run_handler
):
    mock_pull_request = mock_github_client.get_repo.return_value.get_pull.return_value
    mock_pull_request.mergeable_state = MERGEABLE_STATE_BLOCKED
    handle_issue_comment(mock_github_client, issue_comment_git_apply_context)
    assert mock_lambda_run_handler.called is False
    assert mock_pull_request.merge.called is False


def test_issue_comment_with_not_applicable_comment_body(
    mock_github_client, issue_comment_git_apply_context, mock_lambda_run_handler
):
    issue_comment_git_apply_context["event"]["comment"]["body"] = "foo"
    return_code = handle_issue_comment(
        mock_github_client, issue_comment_git_apply_context
    )
    assert return_code == HandleIssueCommentReturnCode.NO_MATCHING_BODY


def test_issue_comment_with_clean_mergeable_state(
    mock_github_client,
    issue_comment_git_apply_context,
    mock_run_git_apply,
    mock_repository,
):
    mock_run_git_apply.return_value = []
    mock_pull_request = mock_github_client.get_repo.return_value.get_pull.return_value
    mock_pull_request.mergeable_state = MERGEABLE_STATE_CLEAN
    mock_pull_request.head.sha = issue_comment_git_apply_context["sha"]
    mock_repository.clone_from.return_value.head.commit.hexsha = (
        issue_comment_git_apply_context["sha"]
    )
    handle_issue_comment(mock_github_client, issue_comment_git_apply_context)
    assert mock_run_git_apply.called
    assert mock_pull_request.merge.called


# invariant: PR is only merged if and only if git-apply is successful
def test_issue_comment_with_clean_mergeable_state_and_lambda_handler_crashed(
    mock_github_client,
    issue_comment_git_apply_context,
    mock_run_git_apply,
    mock_repository,
):
    mock_pull_request = mock_github_client.get_repo.return_value.get_pull.return_value
    mock_pull_request.mergeable_state = MERGEABLE_STATE_CLEAN
    mock_pull_request.head.sha = issue_comment_git_apply_context["sha"]
    mock_repository.clone_from.return_value.head.commit.hexsha = (
        issue_comment_git_apply_context["sha"]
    )
    mock_run_git_apply.side_effect = Exception("unexpected failure")
    with pytest.raises(Exception):
        handle_issue_comment(mock_github_client, issue_comment_git_apply_context)
    assert mock_run_git_apply.called
    assert mock_pull_request.create_issue_comment.called
    assert "Traceback" in mock_pull_request.create_issue_comment.call_args[0][0]
    assert not mock_pull_request.merge.called


# invariant: PR is only merged if and only if git-apply is successful
def test_plan_issue_comment_with_clean_mergeable_state_and_lambda_handler_crashed(
    mock_github_client,
    issue_comment_git_plan_context,
    mock_run_git_plan,
    mock_repository,
):
    mock_pull_request = mock_github_client.get_repo.return_value.get_pull.return_value
    mock_pull_request.mergeable_state = MERGEABLE_STATE_CLEAN
    mock_pull_request.head.sha = issue_comment_git_plan_context["sha"]
    mock_repository.clone_from.return_value.head.commit.hexsha = (
        issue_comment_git_plan_context["sha"]
    )
    mock_run_git_plan.side_effect = Exception("unexpected failure")
    with pytest.raises(Exception):
        handle_issue_comment(mock_github_client, issue_comment_git_plan_context)
    assert mock_run_git_plan.called
    assert mock_pull_request.create_issue_comment.called
    assert "Traceback" in mock_pull_request.create_issue_comment.call_args[0][0]
    assert not mock_pull_request.merge.called


def test_format_github_url():
    pr_url = "https://github.com/example-org/iambic-templates.git"
    fake_token = "foobar"
    expected_url = "https://oauth2:foobar@github.com/example-org/iambic-templates.git"
    url = format_github_url(pr_url, fake_token)
    assert url == expected_url


@pytest.fixture
def pull_request_context():
    return {
        "server_url": "https://github.com",
        "run_id": "12345",
        "run_attempt": "1",
        "token": "fake-token",
        "sha": "fake-sha",
        "repository": "example.com/iambic-templates",
        "event_name": "pull_request",
        "event": {
            "pull_request": {
                "number": 1,
            },
            "repository": {
                "clone_url": "https://github.com/example-org/iambic-templates.git",
            },
        },
        "iambic": {
            "GH_OVERRIDE_TOKEN": "fake_override_token",
        },
    }


def test_pull_request_plan(
    mock_github_client, pull_request_context, mock_run_git_plan, mock_repository
):
    mock_pull_request = mock_github_client.get_repo.return_value.get_pull.return_value
    mock_pull_request.head.sha = pull_request_context["sha"]
    mock_repository.clone_from.return_value.head.commit.hexsha = pull_request_context[
        "sha"
    ]
    handle_pull_request(mock_github_client, pull_request_context)
    assert (
        mock_run_git_plan.called is False
    )  # because this flow only directly calls create_issue_comment on the pull request
    assert (
        not mock_pull_request.merge.called
    )  # because this flow only issue the comment


@pytest.mark.parametrize(
    "repo_name,pr_number,expected_result",
    [
        (
            "noqdev/iambic-templates-itest",
            "1",
            "org=noqdev,repo=iambic-templates-itest,pr=1",
        ),
        ("noqdev/a^b", "1", "org=noqdev,repo=ab,pr=1"),
    ],
)
def test_get_session_name(repo_name, pr_number, expected_result):
    session_name = get_session_name(repo_name, pr_number)
    assert session_name == expected_result


def test_issue_comment_with_git_plan(
    mock_github_client,
    issue_comment_git_plan_context,
    mock_run_git_plan,
    mock_repository,
):
    mock_pull_request = mock_github_client.get_repo.return_value.get_pull.return_value
    mock_pull_request.mergeable_state = MERGEABLE_STATE_CLEAN
    mock_pull_request.head.sha = issue_comment_git_plan_context["sha"]
    mock_repository.clone_from.return_value.head.commit.hexsha = (
        issue_comment_git_plan_context["sha"]
    )
    handle_issue_comment(mock_github_client, issue_comment_git_plan_context)
    assert mock_run_git_plan.called
    assert not mock_pull_request.merge.called


def test_issue_comment_with_allowed_approver(
    mock_github_client,
    issue_comment_git_approve_context,
    mock_repository,
    mock_resolve_config_template_path,
    mock_load_config,
):
    mock_pull_request = mock_github_client.get_repo.return_value.get_pull.return_value
    assert mock_repository
    assert mock_resolve_config_template_path
    assert mock_load_config
    handle_issue_comment(mock_github_client, issue_comment_git_approve_context)
    assert mock_pull_request.create_review.called is True


def test_issue_comment_with_not_allowed_approver(
    mock_github_client,
    issue_comment_git_approve_context,
    mock_repository,
    mock_resolve_config_template_path,
    mock_load_config,
):
    mock_pull_request = mock_github_client.get_repo.return_value.get_pull.return_value
    assert mock_repository
    assert mock_resolve_config_template_path
    assert mock_load_config
    mock_load_config.side_effect.return_value.github.allowed_bot_approver = None
    handle_issue_comment(mock_github_client, issue_comment_git_approve_context)
    assert mock_pull_request.create_review.called is False


# verify if there are changes during git_apply. those changes are push
# back into the PR
def test_issue_comment_with_clean_mergeable_state_with_additional_commits(
    mock_github_client,
    issue_comment_git_apply_context,
    mock_run_git_apply,
    mock_repository,
):
    mock_pull_request = mock_github_client.get_repo.return_value.get_pull.return_value
    mock_pull_request.mergeable_state = MERGEABLE_STATE_CLEAN
    mock_pull_request.head.sha = issue_comment_git_apply_context["sha"]
    mock_pull_request.head.ref = issue_comment_git_apply_context["ref"]
    pre_sha = "pre_sha"
    post_sha = "post_sha"

    # we are mocking how the sha has changed in the local checkout repo
    type(mock_repository.clone_from.return_value.head.commit).hexsha = PropertyMock(
        side_effect=[
            pre_sha,
            post_sha,
        ]
    )

    handle_issue_comment(mock_github_client, issue_comment_git_apply_context)
    assert mock_run_git_apply.called

    # verify we did push back the changes to remote
    pull_request_branch_name = mock_pull_request.head.ref
    refspec = f"HEAD:{pull_request_branch_name}"
    mock_repository.clone_from.return_value.remotes.origin.push.assert_called_with(
        refspec=refspec
    )

    # verify we are merging with the latest local repo sha
    mock_pull_request.merge.assert_called_with(sha=post_sha)


def test_run_handler():
    from iambic.plugins.v0_1_0.github.github import run_handler

    mock_Github = MagicMock(name="Github")
    with mock.patch(
        "iambic.plugins.v0_1_0.github.github.github.Github", new=mock_Github
    ):
        # mg.generate_uut_mocks_with_asserts(run_handler)
        arg = {
            "token": "fake-token",
            "event_name": "pull_request",
            "iambic": {"GH_OVERRIDE_TOKEN": "GH_OVERRIDE_TOKEN"},
            "repository": "exampleorg/iambic-templates",
            "event": {"pull_request": {"number": 4}},
        }
        run_handler(arg)
        assert 2 == mock_Github.call_count
        mock_Github.assert_has_calls(
            calls=[
                call("fake-token"),
                call("GH_OVERRIDE_TOKEN"),
            ]
        )
        mock_Github.return_value.get_repo.assert_called_once_with(
            "exampleorg/iambic-templates"
        )
        mock_Github.return_value.get_repo.return_value.get_pull.assert_called_once_with(
            4
        )
        mock_Github.return_value.get_repo.return_value.get_pull.return_value.create_issue_comment.assert_called_once_with(
            "iambic git-plan"
        )
        mock_Github.reset_mock()

        arg = {
            "token": "fake-token",
            "event_name": "issue_comment",
            "iambic": {"GH_OVERRIDE_TOKEN": "GH_OVERRIDE_TOKEN"},
            "repository": "exampleorg/iambic-templates",
            "event": {
                "comment": {
                    "body": "iambic git-apply",
                },
                "issue": {"number": 4},
                "repository": {
                    "clone_url": "https://github.com/exampleorg/iambic-templates.git"
                },
            },
        }
        run_handler(arg)
        assert 1 == mock_Github.call_count
        mock_Github.assert_called_once_with("fake-token")
        mock_Github.return_value.get_repo.assert_called_once_with(
            "exampleorg/iambic-templates"
        )
        mock_Github.return_value.get_repo.return_value.get_pull.assert_called_once_with(
            4
        )
        mock_Github.return_value.get_repo.return_value.get_pull.return_value.mergeable_state.__ne__.assert_called_once_with(
            "clean"
        )
        mock_Github.return_value.get_repo.return_value.get_pull.return_value.mergeable_state.__str__.assert_called_once_with()
        mock_Github.return_value.get_repo.return_value.get_pull.return_value.create_issue_comment.assert_called_once()
        assert (
            "This probably means that the necessary approvals have not been granted for the request."
            in mock_Github.return_value.get_repo.return_value.get_pull.return_value.create_issue_comment.call_args.args[
                0
            ]
        )
        mock_Github.reset_mock()

        arg = {
            "token": "fake-token",
            "event_name": "iambic_command",
            "iambic": {
                "GH_OVERRIDE_TOKEN": "GH_OVERRIDE_TOKEN",
                "IAMBIC_CLOUD_IMPORT_CMD": "import",
            },
            "repository": "exampleorg/iambic-templates",
            "event": {
                "comment": {
                    "body": "iambic git-apply",
                },
                "issue": {"number": 4},
                "repository": {
                    "clone_url": "https://github.com/exampleorg/iambic-templates.git"
                },
            },
        }
        # TODO: Need to mock the paths
        with pytest.raises(Exception):
            run_handler(arg)


@pytest.fixture
def mock_proposed_changes_filesystem():
    temp_templates_directory = tempfile.mkdtemp(
        prefix="iambic_test_temp_templates_directory"
    )

    try:
        contents = """hello world"""
        contents_path = f"{temp_templates_directory}/proposed_chagnes.yaml"

        with open(contents_path, "w") as f:
            f.write(contents)

        yield contents_path, contents
    finally:
        try:
            shutil.rmtree(temp_templates_directory)
        except Exception as e:
            print(e)


# verify if there are changes during git_apply. those changes are push
# back into the PR
def test_post_artifact_to_companion_repository(
    mock_github_client,
    mock_proposed_changes_filesystem,
):
    contents_path, contents = mock_proposed_changes_filesystem
    markdown_summary = "test_summary"

    mock_template_repo = mock_github_client.get_repo.return_value

    # we are mocking how the sha has changed in the local checkout repo
    type(mock_template_repo).full_name = PropertyMock(
        side_effect=[
            "ExampleOrg/iambic-templates",
        ]
    )

    pull_number = "1337"
    op_name = "plan"
    html_url = _post_artifact_to_companion_repository(
        mock_github_client,
        mock_github_client.get_repo("ExampleOrg/iambic-templates"),
        pull_number,
        op_name,
        contents_path,
        markdown_summary,
    )

    mock_calls = mock_template_repo.create_file.mock_calls
    assert mock_calls

    # verify first call to upload proposed_changes.yaml
    proposed_changes_yaml_call = mock_calls[0]
    # index 1 is where the arguments are, next index 0 is the blob_path
    blob_path = proposed_changes_yaml_call[1][0]
    assert f"pr-{pull_number}" in blob_path
    assert f"{op_name}" in blob_path
    assert "proposed_changes.yaml" in blob_path

    # index 1 is where the arguments are, next index 1 is the commit_message
    commit_message = proposed_changes_yaml_call[1][1]
    assert commit_message == f"{op_name}"

    # index 1 is where the arguments are, next index 2 is the blob_contents
    blob_contents = proposed_changes_yaml_call[1][2]
    assert blob_contents == contents

    # verify second call to upload summary.md
    summary_md_call = mock_calls[1]
    # index 1 is where the arguments are, next index 0 is the blob_path
    blob_path = summary_md_call[1][0]
    assert f"pr-{pull_number}" in blob_path
    assert f"{op_name}" in blob_path
    assert "summary.md" in blob_path

    # index 1 is where the arguments are, next index 1 is the commit_message
    commit_message = summary_md_call[1][1]
    assert commit_message == f"{op_name}"

    # index 1 is where the arguments are, next index 2 is the blob_contents
    blob_contents = summary_md_call[1][2]
    assert blob_contents == markdown_summary

    assert html_url


def test_ensure_body_length_fits_github_spec():
    blob_html_url = "https://fake-location/"
    body = "h" * (BODY_MAX_LENGTH + 1)
    new_body = ensure_body_length_fits_github_spec(body, blob_html_url=blob_html_url)
    assert blob_html_url in new_body


def test_maybe_merge_crashes(
    mock_github_client,
):
    def merge_error(*args, **kwargs):
        raise github.GithubException(409, "409 unable to merge", {})

    mock_pull_request = mock_github_client.get_repo.return_value.get_pull.return_value
    mock_pull_request.mergeable_state = MERGEABLE_STATE_CLEAN
    mock_pull_request.merge.side_effect = merge_error
    templates_repo = mock_github_client.get_repo("ExampleOrg/iambic-templates")
    pull_number = 1337
    merge_sha = "non_existent_sha"
    expected_attempts = 3
    with pytest.raises(RuntimeError, match="Fail to merge PR"):
        maybe_merge(
            templates_repo,
            pull_number,
            merge_sha,
            max_attempts=expected_attempts,
            sleep_interval=0.1,
        )
    assert mock_pull_request.merge.called
    assert len(mock_pull_request.merge.mock_calls) == expected_attempts


def test_maybe_merge_does_not_crash(
    mock_github_client,
):
    def merge_error(*args, **kwargs):
        return MagicMock()

    mock_pull_request = mock_github_client.get_repo.return_value.get_pull.return_value
    mock_pull_request.mergeable_state = MERGEABLE_STATE_CLEAN
    mock_pull_request.merge.side_effect = merge_error
    templates_repo = mock_github_client.get_repo("ExampleOrg/iambic-templates")
    pull_number = 1337
    merge_sha = "non_existent_sha"
    expected_attempts = 3
    maybe_merge(
        templates_repo,
        pull_number,
        merge_sha,
        max_attempts=expected_attempts,
        sleep_interval=0.1,
    )
    assert mock_pull_request.merge.called
    assert len(mock_pull_request.merge.mock_calls) == 1
