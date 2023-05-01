import os
import shutil
import tempfile
from unittest import mock

import pytest

from iambic.config.wizard import ConfigurationWizard


@pytest.fixture
def example_test_filesystem():
    temp_templates_directory = tempfile.mkdtemp(
        prefix="iambic_test_temp_templates_directory"
    )
    yield temp_templates_directory
    try:
        shutil.rmtree(temp_templates_directory)
    except Exception as e:
        print(e)


@pytest.fixture
def config_wizard(example_test_filesystem):
    with mock.patch.dict(os.environ, {}, clear=True):
        # we really want to skip __init__
        yield ConfigurationWizard.__new__(
            ConfigurationWizard, str(example_test_filesystem)
        )


def test_resolve_aws_profile_defaults_from_env_with_environment_variables(
    config_wizard,
):
    with mock.patch.dict(
        os.environ,
        {
            "AWS_ACCESS_KEY_ID": "fake-access-key",
            "AWS_PROFILE": "fake-profile",
            "AWS_DEFAULT_PROFILE": "fake-default-profile",
        },
        clear=True,
    ):
        assert "AWS_ACCESS_KEY_ID" in os.environ
        assert "AWS_PROFILE" in os.environ
        assert "AWS_DEFAULT_PROFILE" in os.environ
        profile = config_wizard.resolve_aws_profile_defaults_from_env()
        assert profile == "None"


def test_resolve_aws_profile_defaults_from_env_with_explicit_profile(config_wizard):
    with mock.patch.dict(
        os.environ,
        {"AWS_PROFILE": "fake-profile", "AWS_DEFAULT_PROFILE": "fake-default-profile"},
        clear=True,
    ):
        assert "AWS_PROFILE" in os.environ
        assert "AWS_DEFAULT_PROFILE" in os.environ
        profile = config_wizard.resolve_aws_profile_defaults_from_env()
        assert profile == "fake-profile"


def test_resolve_aws_profile_defaults_from_env_with_fallback_profile(config_wizard):
    with mock.patch.dict(
        os.environ, {"AWS_DEFAULT_PROFILE": "fake-default-profile"}, clear=True
    ):
        assert "AWS_DEFAULT_PROFILE" in os.environ
        profile = config_wizard.resolve_aws_profile_defaults_from_env()
        assert profile == "fake-default-profile"


def test_resolve_aws_profile_defaults_from_env_with_nothing(config_wizard):
    with mock.patch.dict(os.environ, {}, clear=True):
        profile = config_wizard.resolve_aws_profile_defaults_from_env()
        assert profile == "None"
