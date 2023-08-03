from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile
import traceback

import pytest

import iambic.plugins.v0_1_0.example
from iambic.config.dynamic_config import load_config
from iambic.core.parser import load_template, load_templates

MISSING_REQUIRED_FIELDS_TEMPLATE_YAML = """template_type: NOQ::Example::LocalDatabase
template_schema_url: template_url
expires_at: tomorrow
name:
  - foo
properties:
  foo: bar
"""

MALFORMED_YAML = """template_type: NOQ::Example::LocalDatabase
   expires_at: tomorrow
"""

TEST_TEMPLATE_YAML = """template_type: NOQ::Example::LocalDatabase
template_schema_url: template_url
name: test_template
expires_at: tomorrow
properties:
  name: {name}"""

TEST_TEMPLATE_DIR = "resources/example/"
TEST_TEMPLATE_PATH = "resources/example/test_template.yaml"
MISSING_REQUIRED_FIELDS_TEMPLATE_PATH = "resources/example/bad_template.yaml"
MALFORMED_YAML_PATH = "resources/example/malformed_yaml.yaml"
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


@pytest.fixture(scope="function")
def example_test_filesystem():
    temp_templates_directory = tempfile.mkdtemp(
        prefix="iambic_test_temp_templates_directory"
    )

    try:
        os.makedirs(f"{temp_templates_directory}/{TEST_TEMPLATE_DIR}")
        os.makedirs(f"{temp_templates_directory}/{TEST_CONFIG_DIR}")

        with open(f"{temp_templates_directory}/{TEST_TEMPLATE_PATH}", "w") as f:
            f.write(TEST_TEMPLATE_YAML.format(name="before"))

        with open(
            f"{temp_templates_directory}/{MISSING_REQUIRED_FIELDS_TEMPLATE_PATH}", "w"
        ) as f:
            f.write(MISSING_REQUIRED_FIELDS_TEMPLATE_YAML)

        with open(f"{temp_templates_directory}/{MALFORMED_YAML_PATH}", "w") as f:
            f.write(MALFORMED_YAML)

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

    config = asyncio.run(load_config(config_path))
    templates = [f"{repo_dir}/{TEST_TEMPLATE_PATH}"]
    templates = load_templates(
        templates, config.template_map, raise_validation_err=True
    )
    assert len(templates) > 0


def test_load_templates_without_multiprocessing(example_test_filesystem):
    config_path, repo_dir = example_test_filesystem
    with open(f"{repo_dir}/{TEST_TEMPLATE_PATH}", "r") as f:
        before_template_content = "\n".join(f.readlines())
    assert "tomorrow" in before_template_content

    config = asyncio.run(load_config(config_path))
    templates = [f"{repo_dir}/{TEST_TEMPLATE_PATH}"]
    templates = load_templates(
        templates,
        config.template_map,
        raise_validation_err=True,
        use_multiprocessing=False,
    )
    assert len(templates) > 0


def test_load_template(example_test_filesystem):
    config_path, repo_dir = example_test_filesystem
    with open(f"{repo_dir}/{TEST_TEMPLATE_PATH}", "r") as f:
        before_template_content = "\n".join(f.readlines())
    assert "tomorrow" in before_template_content

    asyncio.run(load_config(config_path))
    template = f"{repo_dir}/{TEST_TEMPLATE_PATH}"
    template = load_template(template, raise_validation_err=True)
    assert template


def test_missing_required_fields_templates(example_test_filesystem):
    config_path, repo_dir = example_test_filesystem
    with open(f"{repo_dir}/{TEST_TEMPLATE_PATH}", "r") as f:
        before_template_content = "\n".join(f.readlines())
    assert "tomorrow" in before_template_content

    config = asyncio.run(load_config(config_path))
    templates = [f"{repo_dir}/{MISSING_REQUIRED_FIELDS_TEMPLATE_PATH}"]
    template_instances = []
    with pytest.raises(ValueError) as exc_info:
        template_instances = load_templates(
            templates, config.template_map, raise_validation_err=True
        )
    assert len(template_instances) == 0
    if sys.version_info < (3, 10):
        exc = exc_info.value
        captured_traceback_lines = traceback.format_exception(
            type(exc), exc, exc.__traceback__
        )
    else:
        captured_traceback_lines = traceback.format_exception(
            exc_info.value
        )  # this is a pytest specific format
    captured_traceback = "\n".join(captured_traceback_lines)
    assert "template has validation error" in captured_traceback
    assert (
        "ValidationError" in captured_traceback
    )  # checking the underlying Pydantic info is captured


def test_malformed_yaml(example_test_filesystem):
    config_path, repo_dir = example_test_filesystem

    config = asyncio.run(load_config(config_path))
    templates = [f"{repo_dir}/{MALFORMED_YAML_PATH}"]
    template_instances = []
    with pytest.raises(ValueError) as exc_info:
        template_instances = load_templates(
            templates, config.template_map, raise_validation_err=True
        )
    assert len(template_instances) == 0
    if sys.version_info < (3, 10):
        exc = exc_info.value
        captured_traceback_lines = traceback.format_exception(
            type(exc), exc, exc.__traceback__
        )
    else:
        captured_traceback_lines = traceback.format_exception(
            exc_info.value
        )  # this is a pytest specific format
    captured_traceback = "\n".join(captured_traceback_lines)
    assert "template has validation error" in captured_traceback
    assert (
        "ScannerError" in captured_traceback
    )  # checking the underlying raumel info is captured
