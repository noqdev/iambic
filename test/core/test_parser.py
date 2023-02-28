from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
import traceback

import pytest

import iambic.plugins.v0_1_0.example
from iambic.config.dynamic_config import load_config
from iambic.core.parser import load_templates

BAD_TEMPLATE_YAML = """template_type: NOQ::Example::LocalDatabase
expires_at: tomorrow
"""

TEST_TEMPLATE_YAML = """template_type: NOQ::Example::LocalDatabase
name: test_template
expires_at: tomorrow
properties:
  name: {name}"""

TEST_TEMPLATE_DIR = "resources/example/"
TEST_TEMPLATE_PATH = "resources/example/test_template.yaml"
BAD_TEMPLATE_PATH = "resources/example/bad_template.yaml"
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
def example_test_filesystem():
    temp_templates_directory = tempfile.mkdtemp(
        prefix="iambic_test_temp_templates_directory"
    )

    try:

        os.makedirs(f"{temp_templates_directory}/{TEST_TEMPLATE_DIR}")
        os.makedirs(f"{temp_templates_directory}/{TEST_CONFIG_DIR}")

        with open(f"{temp_templates_directory}/{TEST_TEMPLATE_PATH}", "w") as f:
            f.write(TEST_TEMPLATE_YAML.format(name="before"))

        with open(f"{temp_templates_directory}/{BAD_TEMPLATE_PATH}", "w") as f:
            f.write(BAD_TEMPLATE_YAML)

        with open(f"{temp_templates_directory}/{TEST_CONFIG_PATH}", "w") as f:
            f.write(
                TEST_CONFIG_YAML.format(example_plugin_location=EXAMPLE_PLUGIN_PATH)
            )

        yield f"{temp_templates_directory}/{TEST_CONFIG_PATH}", temp_templates_directory
    finally:
        try:
            shutil.rmtree(temp_templates_directory)
        except Exception as e:
            print(e)


def test_load_templates(example_test_filesystem):
    config_path, repo_dir = example_test_filesystem
    with open(f"{repo_dir}/{TEST_TEMPLATE_PATH}", "r") as f:
        before_template_content = "\n".join(f.readlines())
    assert "tomorrow" in before_template_content

    asyncio.run(load_config(config_path))
    templates = [f"{repo_dir}/{TEST_TEMPLATE_PATH}"]
    templates = load_templates(templates, raise_validation_err=True)
    assert len(templates) > 0


def test_load_bad_templates(example_test_filesystem):
    config_path, repo_dir = example_test_filesystem
    with open(f"{repo_dir}/{TEST_TEMPLATE_PATH}", "r") as f:
        before_template_content = "\n".join(f.readlines())
    assert "tomorrow" in before_template_content

    asyncio.run(load_config(config_path))
    templates = [f"{repo_dir}/{BAD_TEMPLATE_PATH}"]
    template_instances = []
    with pytest.raises(ValueError) as exc_info:
        template_instances = load_templates(templates, raise_validation_err=True)
    assert len(template_instances) == 0
    captured_traceback_lines = traceback.format_exception(
        exc_info.value
    )  # this is a pytest specific format
    captured_traceback = "\n".join(captured_traceback_lines)
    assert "template has validation error" in captured_traceback
    assert (
        "ValidationError" in captured_traceback
    )  # checking the underlying Pydantic info is captured
    print(captured_traceback)
