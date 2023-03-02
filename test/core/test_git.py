from __future__ import annotations

import os
import shutil
import tempfile

import git
import pytest
from iambic.core import git as the_git_module
from iambic.core.git import (
    GitDiff,
    create_templates_for_modified_files,
    get_remote_default_branch,
)
from iambic.core.models import BaseModel, BaseTemplate

TEST_TEMPLATE_YAML = """template_type: NOQ::Test
name: test_template
properties:
  name: {name}"""

TEST_TEMPLATE_TYPE = "NOQ::Test"
TEST_TEMPLATE_DIR = "resources/test/"
TEST_TEMPLATE_PATH = "resources/test/test_template.yaml"


class TestTemplateProperties(BaseModel):
    name: str


class TestTemplate(BaseTemplate):
    template_type = TEST_TEMPLATE_TYPE
    properties: TestTemplateProperties


@pytest.fixture
def template_class():
    original_templates = the_git_module.TEMPLATES.templates
    the_git_module.TEMPLATES.set_templates(original_templates + [TestTemplate])
    yield the_git_module.TEMPLATES.template_map
    the_git_module.TEMPLATES.set_templates(original_templates)


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
def git_diff(template_class):

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
    templates: list[TestTemplate] = create_templates_for_modified_files(None, git_diff)
    assert templates[0].properties.name == "after"
