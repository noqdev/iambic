from __future__ import annotations

import asyncio
import os
import shutil
import tempfile

import git
import pytest
from git import Repo

import iambic.plugins.v0_1_0.example
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
    assert (
        sha_before_git_apply != sha_after_git_apply
    )  # this is to make sure apply_git_changes with template marked as deleted will add a commit that rm the deleted template


@pytest.fixture
def repo_with_modified_and_renamed_template():

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
        repo.remotes.origin.push().raise_if_error()  # this is to set the state of origin/HEAD

        # save the remove line to future test case
        # repo.index.remove([f"{temp_templates_directory}/{TEST_TEMPLATE_PATH}"], working_tree=True, force=True)
        new_path = f"{temp_templates_directory}/{TEST_TEMPLATE_PATH}".replace(
            "test_template.yaml", "test_template_foo.yaml"
        )
        repo.index.move([f"{temp_templates_directory}/{TEST_TEMPLATE_PATH}", new_path])
        repo.git.commit(m="rename template")

        with open(new_path, "w") as f:
            f.write(TEST_TEMPLATE_YAML.format(name="after"))

        repo.git.add(A=True)
        repo.git.commit(m="after")

        yield repo
    finally:
        try:
            shutil.rmtree(temp_templates_directory)
            shutil.rmtree(bare_directory)
        except Exception as e:
            print(e)


def get_git_root(repo: Repo):
    return repo.git.rev_parse("--show-toplevel")


@pytest.mark.asyncio
async def test_apply_git_changes_with_modified_and_renamed_template(
    repo_with_modified_and_renamed_template: Repo,
):
    repo_dir = get_git_root(repo_with_modified_and_renamed_template)
    config_path = f"{repo_dir}/{TEST_CONFIG_PATH}"
    template_change_details = await apply_git_changes(config_path, repo_dir)
    assert template_change_details is not None
