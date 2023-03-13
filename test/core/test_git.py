from __future__ import annotations

import asyncio
import os
import shutil
import tempfile

import git
import iambic.plugins.v0_1_0.example
import pytest
from iambic.config.dynamic_config import load_config
from iambic.core.git import (
    GitDiff,
    create_templates_for_modified_files,
    get_remote_default_branch,
)
from iambic.core.models import BaseTemplate

TEST_TEMPLATE_YAML = """template_type: NOQ::Example::LocalFile
name: test_template
expires_at: tomorrow
properties:
  name: {name}"""

TEST_TEMPLATE_DIR = "resources/example/"
TEST_TEMPLATE_PATH = "resources/example/test_template.yaml"
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


def test_get_remote_default_branch(repo_with_single_commit):
    assert TEST_TRACKING_BRANCH not in [
        "main",
        "master",
    ]  # make sure we are testing interesting example
    remote_branch_name = get_remote_default_branch(repo_with_single_commit)
    assert remote_branch_name == TEST_TRACKING_BRANCH


@pytest.fixture
def git_diff():

    temp_templates_directory = tempfile.mkdtemp(
        prefix="iambic_test_temp_templates_directory"
    )

    bare_directory = tempfile.mkdtemp(
        prefix="iambic_test_temp_templates_directory_bare"
    )

    try:
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

        with open(f"{temp_templates_directory}/{TEST_CONFIG_PATH}", "w") as f:
            f.write(
                TEST_CONFIG_YAML.format(example_plugin_location=EXAMPLE_PLUGIN_PATH)
            )
        asyncio.run(load_config(f"{temp_templates_directory}/{TEST_CONFIG_PATH}"))

        with open(f"{temp_templates_directory}/{TEST_TEMPLATE_PATH}", "w") as f:
            f.write(TEST_TEMPLATE_YAML.format(name="before"))

        repo.git.add(A=True)
        repo.git.commit(m="before")

        with open(f"{temp_templates_directory}/{TEST_TEMPLATE_PATH}", "w") as f:
            f.write(TEST_TEMPLATE_YAML.format(name="after"))

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

        yield diffs
    finally:
        try:
            shutil.rmtree(temp_templates_directory)
            shutil.rmtree(bare_directory)
        except Exception as e:
            print(e)


def test_create_templates_for_modified_files_without_multi_account_support(git_diff):
    templates: list[BaseTemplate] = create_templates_for_modified_files(None, git_diff)
    assert templates[0].properties.name == "after"
