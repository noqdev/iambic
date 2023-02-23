from __future__ import annotations

import os
import shutil
import tempfile

import pytest

import iambic.plugins.v0_1_0.example
from iambic.main import run_apply

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


def test_run_apply(example_test_filesystem):
    config_path, repo_dir = example_test_filesystem
    with open(f"{repo_dir}/{TEST_TEMPLATE_PATH}", "r") as f:
        before_template_content = "\n".join(f.readlines())
    assert "tomorrow" in before_template_content
    run_apply(False, config_path, None, repo_dir)
    with open(f"{repo_dir}/{TEST_TEMPLATE_PATH}", "r") as f:
        after_template_content = "\n".join(f.readlines())
    assert "tomorrow" not in after_template_content
