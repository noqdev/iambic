from __future__ import annotations
import pathlib
from typing import Any

import pytest
import yaml

from iambic.config.dynamic_config import Config, ExtendsConfig, ExtendsConfigKey, init_plugins
from iambic.core.iambic_enum import Command
from iambic.core.models import ExecutionMessage


@pytest.mark.asyncio
async def test_set_config_secrets_with_local_file(
    test_config: Config, test_config_path_one_extends: Any
):
    test_config.extends = [
        ExtendsConfig(
            key=ExtendsConfigKey.LOCAL_FILE,
            value=str(test_config_path_one_extends),
        )
    ]
    await test_config.set_config_secrets()
    assert any(
        x.value == str(test_config_path_one_extends) for x in test_config.extends
    )


@pytest.mark.asyncio
async def test_set_config_secrets_with_secret_in_secrets_manager(
    test_config: Config, test_config_path_one_extends: Any, secrets_setup: Any
):
    secret_key = "arn:aws:secretsmanager:us-west-2:123456789012:secret:iambic-config-secrets-9fae9066-5599-473f-b364-63fa0240b6f7"
    test_config.extends = [
        ExtendsConfig(
            key=ExtendsConfigKey.AWS_SECRETS_MANAGER,
            value=secret_key,
        )
    ]
    await test_config.set_config_secrets()
    assert any(x.value == secret_key for x in test_config.extends)


@pytest.mark.asyncio
async def test_run_discover_upstream_config_changes(test_config, test_config_path_two_accounts_plus_org: Config):
    execution_message = ExecutionMessage(
        execution_id="test",
        command = Command.APPLY,
    )
    config_path = pathlib.Path(test_config_path_two_accounts_plus_org)
    await test_config.run_discover_upstream_config_changes(execution_message, config_path.parent)
    with open(test_config.file_path, "r") as f:
        config = yaml.load(f, Loader=yaml.FullLoader)
    assert list(config.keys())[0] == "template_type"
    assert list(config.keys())[1] == "version"
    assert list(config.keys())[2] == "aws"


@pytest.mark.asyncio
async def test_init_plugins(test_config, test_config_path_two_accounts_plus_org):
    await init_plugins(test_config_path_two_accounts_plus_org)
    plugins = [pathlib.Path(x.location).name for x in test_config.plugins]
    assert "aws" in plugins
    assert "google_workspace" in plugins
    assert "okta" in plugins
    assert "github" in plugins
    assert "azure_ad" in plugins


@pytest.mark.asyncio
async def test_run_import(test_config, test_config_path_two_accounts_plus_org):
    execution_message = ExecutionMessage(
        execution_id="test",
        command = Command.APPLY,
    )
    config_path = pathlib.Path(test_config_path_two_accounts_plus_org)
    await test_config.run_import(execution_message, config_path.parent)
