from __future__ import annotations

import os
import shutil
import tempfile

import git
import pytest

from iambic.core import git as the_git_module
from iambic.core.git import GitDiff, create_templates_for_modified_files
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
    the_git_module.TEMPLATE_TYPE_MAP[TEST_TEMPLATE_TYPE] = TestTemplate
    yield the_git_module.TEMPLATE_TYPE_MAP
    del the_git_module.TEMPLATE_TYPE_MAP[TEST_TEMPLATE_TYPE]


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
