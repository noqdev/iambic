from __future__ import annotations

import asyncio
import os
import shutil
import tempfile

import git
import iambic.plugins.v0_1_0.example
import pytest
from git import Repo
from iambic.config.dynamic_config import load_config
from iambic.core.parser import load_templates
from iambic.request_handler.git_apply import apply_git_changes

TEST_TEMPLATE_YAML = """template_type: NOQ::Example::LocalFile
name: test_template
expires_at: tomorrow
properties:
  name: {name}"""

TEST_TEMPLATE_TYPE = "NOQ::Test"
TEST_TEMPLATE_DIR = "resources/test/"
TEST_TEMPLATE_PATH = "resources/test/test_template.yaml"
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


@pytest.fixture
def templates_repo():

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

        with open(f"{temp_templates_directory}/{TEST_TEMPLATE_PATH}", "w") as f:
            f.write(TEST_TEMPLATE_YAML.format(name="before"))

        with open(f"{temp_templates_directory}/{TEST_CONFIG_PATH}", "w") as f:
            f.write(
                TEST_CONFIG_YAML.format(example_plugin_location=EXAMPLE_PLUGIN_PATH)
            )

        repo.git.add(A=True)
        repo.git.commit(m="before")
        repo.remotes.origin.push()

        with open(f"{temp_templates_directory}/{TEST_TEMPLATE_PATH}", "w") as f:
            f.write(TEST_TEMPLATE_YAML.format(name="after"))

        repo.git.add(A=True)
        repo.git.commit(m="after")

        asyncio.run(load_config(f"{temp_templates_directory}/{TEST_CONFIG_PATH}"))
        yield f"{temp_templates_directory}/{TEST_CONFIG_PATH}", temp_templates_directory
    finally:
        try:
            shutil.rmtree(temp_templates_directory)
            shutil.rmtree(bare_directory)
        except Exception as e:
            print(e)


@pytest.mark.asyncio
async def test_apply_git_changes(templates_repo):
    config_path, repo_dir = templates_repo
    with open(f"{repo_dir}/{TEST_TEMPLATE_PATH}", "r") as f:
        before_template_content = "\n".join(f.readlines())
    assert "tomorrow" in before_template_content
    await apply_git_changes(config_path, repo_dir)
    with open(f"{repo_dir}/{TEST_TEMPLATE_PATH}", "r") as f:
        after_template_content = "\n".join(f.readlines())
    assert "tomorrow" not in after_template_content


@pytest.mark.asyncio
async def test_apply_git_changes_with_deleted_template(templates_repo):
    config_path, repo_dir = templates_repo
    repo = Repo(repo_dir)
    sha_before_git_apply = repo.head.commit.hexsha
    template = load_templates([f"{repo_dir}/{TEST_TEMPLATE_PATH}"])[0]
    assert template.deleted is False
    template.deleted = True
    template.write()
    await apply_git_changes(config_path, repo_dir)
    sha_after_git_apply = repo.head.commit.hexsha
    assert sha_before_git_apply != sha_after_git_apply
