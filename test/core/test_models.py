from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
from datetime import date, datetime, timezone

import git
import pytest
import pytz
from git.diff import Diff

import iambic.plugins.v0_1_0.example
from iambic.config.dynamic_config import load_config
from iambic.core.iambic_enum import IambicManaged
from iambic.core.models import BaseTemplate, ExpiryModel
from iambic.core.parser import load_templates
from iambic.core.template_generation import merge_model


def test_merge_model():
    existing_template = BaseTemplate(
        template_type="foo",
        template_schema_url="test_url",
        notes="test_notes",
        file_path="bar",
        iambic_managed=IambicManaged.IMPORT_ONLY,
    )
    new_template = BaseTemplate(
        template_type="foo_new",
        template_schema_url="test_url",
        file_path="bar_new",
        iambic_managed=IambicManaged.UNDEFINED,
    )
    merged_template = merge_model(new_template, existing_template, [])
    assert merged_template.template_type == new_template.template_type
    assert merged_template.iambic_managed == IambicManaged.IMPORT_ONLY
    assert merged_template.file_path == existing_template.file_path
    assert merged_template.notes == existing_template.notes


def test_merge_model_with_none():
    existing_template = BaseTemplate(
        template_type="foo",
        template_schema_url="template_url",
        file_path="bar",
        iambic_managed=IambicManaged.IMPORT_ONLY,
    )
    new_template = None
    merged_template = merge_model(new_template, existing_template, [])
    assert merged_template is None


def test_expiry_model_to_json_with_datetime():
    expiry_date = datetime(2023, 3, 7, 12, 30, 0, tzinfo=timezone.utc)
    model = ExpiryModel(expires_at=expiry_date, deleted=True)
    expected_json = '{"expires_at": "2023-03-07T12:30 UTC", "deleted": true}'
    assert (
        model.json(exclude_unset=True, exclude_defaults=True, exclude_none=True)
        == expected_json
    )


def test_expiry_model_to_json_with_date():
    expiry_date = date(2023, 3, 7)
    model = ExpiryModel(expires_at=expiry_date, deleted=False)
    expected_json = '{"expires_at": "2023-03-07T00:00 UTC"}'
    assert (
        model.json(exclude_unset=True, exclude_defaults=True, exclude_none=True)
        == expected_json
    )


def test_expiry_model_to_json_with_str():
    expiry_date = "2023-03-07T12:30:00Z"
    model = ExpiryModel(expires_at=expiry_date, deleted=False)
    expected_json = '{"expires_at": "2023-03-07T12:30 UTC"}'
    assert (
        model.json(exclude_unset=True, exclude_defaults=True, exclude_none=True)
        == expected_json
    )


def test_expiry_model_to_json_with_null():
    model = ExpiryModel(expires_at=None, deleted=False)
    expected_json = "{}"
    assert (
        model.json(exclude_unset=True, exclude_defaults=True, exclude_none=True)
        == expected_json
    )


def test_expiry_model_from_json_with_datetime():
    json_str = '{"expires_at": "2023-03-07T12:30 UTC", "deleted": true}'
    expected_expiry_date = datetime(2023, 3, 7, 12, 30, 0, tzinfo=pytz.utc)
    expected_model = ExpiryModel(expires_at=expected_expiry_date, deleted=True)
    actual_model = ExpiryModel.parse_raw(json_str)
    assert actual_model == expected_model


def test_expiry_model_from_json_with_date():
    json_str = '{"expires_at": "2023-03-07T00:00 UTC"}'
    expected_expiry_date = date(2023, 3, 7)
    expected_model = ExpiryModel(expires_at=expected_expiry_date, deleted=False)
    actual_model = ExpiryModel.parse_raw(json_str)
    assert actual_model == expected_model


def test_expiry_model_from_json_with_str():
    json_str = '{"expires_at": "2023-03-07T12:30 UTC"}'
    expected_expiry_date = "2023-03-07T12:30:00Z"
    expected_model = ExpiryModel(expires_at=expected_expiry_date, deleted=False)
    actual_model = ExpiryModel.parse_raw(json_str)
    assert actual_model == expected_model


def test_expiry_model_from_json_with_null():
    json_str = '{"expires_at": null, "deleted": false}'
    expected_model = ExpiryModel(expires_at=None, deleted=False)
    actual_model = ExpiryModel.parse_raw(json_str)
    assert actual_model == expected_model


TEST_TEMPLATE_YAML = """# comment line 1
template_type: NOQ::Example::LocalFile
template_schema_url: test_url
notes: |-
  This is a test note
  with a newline
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
        repo.remotes.origin.push().raise_if_error()

        asyncio.run(load_config(f"{temp_templates_directory}/{TEST_CONFIG_PATH}"))
        yield f"{temp_templates_directory}/{TEST_CONFIG_PATH}", temp_templates_directory
    finally:
        try:
            shutil.rmtree(temp_templates_directory)
            shutil.rmtree(bare_directory)
        except Exception as e:
            print(e)


@pytest.mark.asyncio
async def test_template_delete(templates_repo: tuple[str, str]):
    config_path, repo_dir = templates_repo
    config = await load_config(config_path)

    repo = git.Repo(repo_dir)
    diff_index = repo.index.diff("HEAD")
    # assert there is no local changes
    assert len(diff_index) == 0

    template = load_templates(
        [f"{repo_dir}/{TEST_TEMPLATE_PATH}"], config.template_map
    )[0]
    template_path = str(template.file_path)
    template.delete()
    # verify the template has pending git removal status

    diff_index = repo.index.diff("HEAD")
    assert len(diff_index) == 1
    diff_removed: Diff = list(diff_index)[0]
    assert diff_removed.a_mode == 0
    # not using pathlib because git diff objects can have paths
    # that don't actually exist in filesystem. those path
    # are relative to the git tree
    assert f"{repo_dir}/{diff_removed.a_path}" == template_path


@pytest.mark.asyncio
async def test_get_body(templates_repo: tuple[str, str]):
    config_path, repo_dir = templates_repo
    config = await load_config(config_path)

    repo = git.Repo(repo_dir)
    diff_index = repo.index.diff("HEAD")
    # assert there is no local changes
    assert len(diff_index) == 0

    template = load_templates(
        [f"{repo_dir}/{TEST_TEMPLATE_PATH}"], config.template_map
    )[0]
    template_body = template.get_body()
    template_lines = template_body.split("\n")

    # we have the order being explicit here
    # this is to ensure first line is the type
    # this is to ensure second lien is the schema url
    assert template_lines[0] == "# comment line 1"
    assert template_lines[1] == "template_type: NOQ::Example::LocalFile"
    assert template_lines[2] == "template_schema_url: test_url"
