from __future__ import annotations

import asyncio
import importlib
import os
import shutil
import tempfile

import pytest

import iambic.plugins.v0_1_0.github.github
from iambic.config.dynamic_config import load_config

TEST_CONFIG_DIR = "config/"
TEST_CONFIG_PATH = "config/test_config.yaml"

TEST_CONFIG_YAML = """template_type: NOQ::Core::Config
version: '1'

github:
  commit_message_user_name: "Test User"
  commit_message_user_email: "test_email@example.org"
  commit_message_for_detect: "TEST_DETECT_COMMIT_MESSAGE"
  commit_message_for_import: "TEST_IMPORT_COMMIT_MESSAGE"
  commit_message_for_expire: "TEST_EXPIRE_COMMIT_MESSAGE"
  commit_message_for_git_apply: "TEST_GIT_APPLY_COMMIT_MESSAGE"
"""


@pytest.fixture
def example_test_filesystem():
    temp_templates_directory = tempfile.mkdtemp(
        prefix="iambic_test_temp_templates_directory"
    )

    try:
        os.makedirs(f"{temp_templates_directory}/{TEST_CONFIG_DIR}")

        with open(f"{temp_templates_directory}/{TEST_CONFIG_PATH}", "w") as f:
            f.write(TEST_CONFIG_YAML)

        yield f"{temp_templates_directory}/{TEST_CONFIG_PATH}", temp_templates_directory
    finally:
        try:
            shutil.rmtree(temp_templates_directory)
        except Exception as e:
            print(e)


@pytest.mark.parametrize(
    "attribute, expected_value",
    [
        ("COMMIT_MESSAGE_USER_NAME", "Test User"),
        ("COMMIT_MESSAGE_USER_EMAIL", "test_email@example.org"),
        ("COMMIT_MESSAGE_FOR_DETECT", "TEST_DETECT_COMMIT_MESSAGE"),
        ("COMMIT_MESSAGE_FOR_IMPORT", "TEST_IMPORT_COMMIT_MESSAGE"),
        ("COMMIT_MESSAGE_FOR_EXPIRE", "TEST_EXPIRE_COMMIT_MESSAGE"),
        ("COMMIT_MESSAGE_FOR_GIT_APPLY_ABSOLUTE_TIME", "TEST_GIT_APPLY_COMMIT_MESSAGE"),
    ],
)
def test_load_config(example_test_filesystem, attribute, expected_value):
    config_path, repo_dir = example_test_filesystem
    module = iambic.plugins.v0_1_0.github.github
    # importlib.reload forces a reload, so we double check the value in module versus that in config
    importlib.reload(module)
    original_value = getattr(module, attribute)
    asyncio.run(load_config(config_path))

    new_value = getattr(module, attribute)
    assert original_value != new_value
    assert new_value == expected_value
