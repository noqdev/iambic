from __future__ import annotations

import asyncio
import os
import shutil
import tempfile

# test_your_module.py
from typing import Any
from unittest.mock import MagicMock, PropertyMock, call, patch

import git
import pytest
import yaml
from git import GitCommandError, Repo

import iambic.plugins.v0_1_0.example
from iambic.config.dynamic_config import load_config
from iambic.core.git import (
    GitDiff,
    clone_git_repos,
    create_templates_for_deleted_files,
    create_templates_for_modified_files,
    get_origin_head,
    get_remote_default_branch,
)
from iambic.core.models import BaseTemplate, ConfigMixin
from iambic.plugins.v0_1_0.example.local_file.models import (
    ExampleLocalFileMultiAccountTemplate,
    ExampleLocalFileMultiAccountTemplateProperties,
    ExampleLocalFileTemplate,
)

TEST_TEMPLATE_YAML = """template_type: NOQ::Example::LocalFile
name: test_template
expires_at: tomorrow
properties:
  name: {name}"""

TEST_TEMPLATE_MULTI_ACCOUNT_YAML = """template_type: NOQ::Example::LocalFileMultiAccount
name: test_multi_account_template
expires_at: tomorrow
included_accounts:
- account1
- account2
excluded_accounts: []
properties:
  name: {name}
"""

TEST_TEMPLATE_MULTI_ACCOUNT_INC_STAR_YAML = """template_type: NOQ::Example::LocalFileMultiAccount
name: test_multi_account_template
expires_at: tomorrow
included_accounts:
- "*"
excluded_accounts: []
properties:
  name: {name}
"""

TEST_TEMPLATE_MULTI_ACCOUNT_EXC_STAR_YAML = """template_type: NOQ::Example::LocalFileMultiAccount
name: test_multi_account_template
expires_at: tomorrow
included_accounts: []
excluded_accounts:
- "*"
properties:
  name: {name}
"""

TEST_TEMPLATE_DIR = "resources/example/"
TEST_TEMPLATE_PATH = "resources/example/test_template.yaml"
TEST_MULTI_ACCOUNT_TEMPLATE_PATH = "resources/example/test_multi_account_template.yaml"
TEST_CONFIG_DIR = "config/"
TEST_CONFIG_PATH = "config/test_config.yaml"

TEST_CONFIG_YAML = """template_type: NOQ::Core::Config
version: '1'

plugins:
  - type: DIRECTORY_PATH
    location: {example_plugin_location}
    version: v0_1_0
example:
  random: 1
"""

EXAMPLE_PLUGIN_PATH = iambic.plugins.v0_1_0.example.__path__[0]


TEST_TRACKING_BRANCH = "XYZ"


@pytest.fixture
def repo_with_single_commit():
    temp_templates_directory = tempfile.mkdtemp(
        prefix="iambic_test_temp_templates_directory"
    )

    bare_directory = tempfile.mkdtemp(
        prefix="iambic_test_temp_templates_directory_bare"
    )

    try:
        bare_repo = git.Repo.init(
            f"{bare_directory}", bare=True, initial_branch=TEST_TRACKING_BRANCH
        )
        repo = bare_repo.clone(temp_templates_directory)
        repo_config_writer = repo.config_writer()
        repo_config_writer.set_value(
            "user", "name", "Iambic Github Functional Test for Github"
        )
        repo_config_writer.set_value(
            "user", "email", "github-cicd-functional-test@iambic.org"
        )
        repo_config_writer.release()

        with open(f"{temp_templates_directory}/README.md", "w") as f:
            f.write("")

        repo.git.add(A=True)
        repo.git.commit(m="Add README.md")
        repo.remotes.origin.push()

        yield repo
    finally:
        try:
            shutil.rmtree(temp_templates_directory)
            shutil.rmtree(bare_directory)
        except Exception as e:
            print(e)


def test_get_remote_default_branch(repo_with_single_commit: Repo):
    assert TEST_TRACKING_BRANCH not in [
        "main",
        "master",
    ]  # make sure we are testing interesting example
    remote_branch_name = get_remote_default_branch(repo_with_single_commit)
    assert remote_branch_name == TEST_TRACKING_BRANCH


@pytest.fixture(scope="function")
def git_diff_parameterized(request):
    def fin():
        shutil.rmtree(f"{temp_templates_directory}/{TEST_TEMPLATE_DIR}")
        shutil.rmtree(f"{temp_templates_directory}/{TEST_CONFIG_DIR}")

    request.addfinalizer(fin)

    temp_templates_directory = tempfile.mkdtemp(
        prefix="iambic_test_temp_templates_directory"
    )

    bare_directory = tempfile.mkdtemp(
        prefix="iambic_test_temp_templates_directory_bare"
    )

    bare_repo = git.Repo.init(f"{bare_directory}", bare=True)
    repo = bare_repo.clone(temp_templates_directory)
    repo_config_writer = repo.config_writer()
    repo_config_writer.set_value(
        "user", "name", "Iambic Github Functional Test for Github"
    )
    repo_config_writer.set_value(
        "user", "email", "github-cicd-functional-test@iambic.org"
    )
    repo_config_writer.release()

    os.makedirs(f"{temp_templates_directory}/{TEST_TEMPLATE_DIR}")
    os.makedirs(f"{temp_templates_directory}/{TEST_CONFIG_DIR}")

    def wrapped(template_under_test: str):
        with open(f"{temp_templates_directory}/{TEST_CONFIG_PATH}", "w") as f:
            f.write(
                TEST_CONFIG_YAML.format(example_plugin_location=EXAMPLE_PLUGIN_PATH)
            )
        asyncio.run(load_config(f"{temp_templates_directory}/{TEST_CONFIG_PATH}"))

        with open(f"{temp_templates_directory}/{TEST_TEMPLATE_PATH}", "w") as f:
            f.write(template_under_test.format(name="before"))

        repo.git.add(A=True)
        repo.git.commit(m="before")

        with open(f"{temp_templates_directory}/{TEST_TEMPLATE_PATH}", "w") as f:
            f.write(template_under_test.format(name="after"))

        repo.git.add(A=True)
        repo.git.commit(m="after")

        diff_index = repo.index.diff(repo.commit("HEAD~1"))
        diffs = []
        for file_obj in diff_index.iter_change_type("M"):
            diffs.append(
                GitDiff(
                    path=str(
                        os.path.join(temp_templates_directory, TEST_TEMPLATE_PATH)
                    ),
                    content=file_obj.a_blob.data_stream.read().decode("utf-8"),
                )
            )

        return diffs

    return wrapped


@pytest.fixture(scope="function")
def template_mixin_fake():
    class FakeMixin(ConfigMixin):
        @property
        def templates(self):
            return [
                ExampleLocalFileTemplate,
                ExampleLocalFileMultiAccountTemplateProperties,
                ExampleLocalFileMultiAccountTemplate,
            ]

    return FakeMixin()


def test_create_templates_for_modified_files_without_multi_account_support(
    git_diff_parameterized: list[Any],
    template_mixin_fake,
):
    config = template_mixin_fake

    templates: list[BaseTemplate] = create_templates_for_modified_files(
        config, git_diff_parameterized(TEST_TEMPLATE_YAML)
    )
    assert templates[0].properties.name == "after"


def test_create_templates_for_modified_files_with_multi_account_support(
    test_config_path_two_accounts_plus_org,
    git_diff_parameterized: list[Any],
    template_mixin_fake,
):
    config = template_mixin_fake

    templates: list[BaseTemplate] = create_templates_for_modified_files(
        config,
        git_diff_parameterized(TEST_TEMPLATE_MULTI_ACCOUNT_YAML),
    )
    assert templates[0].properties.name == "after"


def test_create_templates_for_modified_files_with_multi_account_incl_star_support(
    test_config_path_two_accounts_plus_org,
    git_diff_parameterized: list[Any],
    template_mixin_fake,
):
    config = template_mixin_fake

    templates: list[BaseTemplate] = create_templates_for_modified_files(
        config,
        git_diff_parameterized(TEST_TEMPLATE_MULTI_ACCOUNT_EXC_STAR_YAML),
    )
    assert templates[0].properties.name == "after"


@pytest.mark.asyncio
async def test_get_origin_head():
    # Mock the Repo instance and its related attributes
    mock_repo = MagicMock(spec=Repo)
    mock_remote = MagicMock()
    mock_repo.remotes.origin = mock_remote

    # Test case 1: Origin/HEAD exists
    mock_a = MagicMock()
    mock_a.configure_mock(name="origin/HEAD")
    mock_b = MagicMock()
    mock_b.configure_mock(name="origin/main")
    mock_c = MagicMock()
    mock_c.configure_mock(name="origin/dev")
    mock_refs = [
        mock_a,
        mock_b,
        mock_c,
    ]
    mock_remote.refs = mock_refs

    result = get_origin_head(mock_repo)
    assert result == "HEAD"

    # Test case 2: Origin/HEAD does not exist
    mock_refs = [
        MagicMock(name="origin/main"),
        MagicMock(name="origin/dev"),
    ]
    mock_remote.refs = mock_refs

    with pytest.raises(
        ValueError,
        match="Unable to determine the default branch for the repo 'origin' remote",
    ):
        get_origin_head(mock_repo)


@pytest.mark.asyncio
async def test_clone_git_repos(test_config, os_path: None, mocked_repo: MagicMock):
    # Prepare the configuration object
    config = MagicMock()
    config.secrets.get.return_value = {
        "repositories": [
            {"name": "repo1", "uri": "https://github.com/user/repo1.git"},
            {"name": "repo2", "uri": "https://github.com/user/repo2.git"},
        ]
    }

    # Mock the Repo class and its methods
    with patch.object(iambic.core.git.Repo, "clone_from") as mock_clone_from:

        # Mock the git attribute of the Repo instance
        mock_git = MagicMock()
        mocked_repo.return_value.git = mock_git

        # Mock the GitCommandError exception
        with patch("iambic.core.git.GitCommandError", autospec=True) as mock_git_error:
            mock_git_error.stderr = "already exists and is not an empty directory"

            # Test the clone_git_repos function
            repo_dir = "test_repo_dir"
            repos = await clone_git_repos(config, repo_dir)

            assert "repo1" in list(repos.keys())
            assert "repo2" in list(repos.keys())

            assert mock_clone_from.call_count == 2


@pytest.mark.asyncio
async def test_clone_git_repos_with_git_error(
    test_config, os_path: None, mocked_repo: MagicMock
):
    # Prepare the configuration object
    config = MagicMock()
    config.secrets.get.return_value = {
        "repositories": [
            {"name": "repo1", "uri": "https://github.com/user/repo1.git"},
            {"name": "repo2", "uri": "https://github.com/user/repo2.git"},
        ]
    }

    # Raise GitCommandError when cloning the second repository
    def clone_from_side_effect(uri, path):
        if path == "test_repo_dir/repo2":
            git_error = GitCommandError("clone", "mocked error")
            git_error.stderr = "already exists and is not an empty directory"
            raise git_error
        return mocked_repo.return_value

    with patch.object(
        iambic.core.git.Repo, "clone_from", side_effect=clone_from_side_effect
    ) as mock_clone_from:
        # Mock the git attribute of the Repo instance
        mock_git = MagicMock()
        mocked_repo.return_value.git = mock_git

        # Test the clone_git_repos function
        repo_dir = "test_repo_dir"
        repos = await clone_git_repos(config, repo_dir)

        # Verify the expected calls were made
        mock_clone_from.assert_has_calls(
            [
                call("https://github.com/user/repo1.git", "test_repo_dir/repo1"),
                call("https://github.com/user/repo2.git", "test_repo_dir/repo2"),
            ],
            any_order=True,
        )
        mock_git.pull.assert_called_once()

        # Check if the returned repos are correct
        assert set(repos.keys()) == {"repo1", "repo2"}
        assert all(isinstance(repo, Repo) for repo in repos.values())


class MockTemplate:
    def __init__(self, file_path, template_type, deleted=False):
        self.file_path = file_path
        self.template_type = MagicMock(default=template_type)
        self.deleted = deleted

    __fields__ = {"template_type": MagicMock(default="type1")}

    def delete(self):
        pass


class MockTemplate2(MockTemplate):
    __fields__ = {"template_type": MagicMock(default="type2")}

    def __init__(self, file_path, template_type, deleted=True):
        super().__init__(file_path, template_type, deleted)


def test_create_templates_for_deleted_files():
    # Mock the GitDiff objects
    git_diff1 = MagicMock(content="template_type: type1\n", file_path="path1.yaml")
    git_diff2 = MagicMock(content="template_type: type2\n", file_path="path2.yaml")

    deleted_files = [git_diff1, git_diff2]
    with patch(
        "iambic.core.models.ConfigMixin.templates",
        new_callable=PropertyMock,
        return_value=[MockTemplate, MockTemplate2],
    ):
        mixin = ConfigMixin()

        # Mock the yaml.load function
        with patch(
            "iambic.core.git.yaml.load",
            side_effect=lambda x: yaml.load(x, Loader=yaml.SafeLoader),
        ):
            # Mock the log.info function
            with patch("iambic.core.git.log.info"):
                # Test the create_templates_for_deleted_files function
                result = create_templates_for_deleted_files(
                    deleted_files, mixin.template_map
                )

                # Check if the returned templates are correct
                assert len(result) == 1

                # check returned template is marked as in_memory_only
                assert result[0].is_memory_only

                # verify delete() won't crash because in-memory template delete is no-op
                result[0].delete()


def test_get_template_map_return_none():
    from iambic.core.git import _get_template_map
    from iambic.core.logger import log

    with patch.object(log, "error") as mocked_error:
        template_map = {"Mock::Template": MockTemplate("path1.yaml", "type1")}
        template_dict = {
            "template_type": "Mock::NotExist",
        }

        assert not _get_template_map(template_map, template_dict)  # type: ignore
        mocked_error.assert_called_once()


def test_get_template_map_return_template():
    from iambic.core.git import _get_template_map
    from iambic.core.logger import log

    with patch.object(log, "error") as mocked_error:
        template_map = {"Mock::Template": MockTemplate("path1.yaml", "type1")}
        template_dict = {
            "template_type": "Mock::Template",
        }

        assert _get_template_map(template_map, template_dict)  # type: ignore

        mocked_error.assert_not_called()
