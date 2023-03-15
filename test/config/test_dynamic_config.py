from moto import mock_secretsmanager
import pytest

from iambic.config.dynamic_config import (
    ExtendsConfig,
    ExtendsConfigKey,
)


@pytest.mark.asyncio
async def test_set_config_secrets_with_local_file(fs, test_config, test_config_path_one_extends):
    test_config.extends = [
        ExtendsConfig(
            key=ExtendsConfigKey.LOCAL_FILE,
            value=test_config_path_one_extends,
        )
    ]
    await test_config.set_config_secrets()
    assert any(x.value == test_config_path_one_extends for x in test_config.extends)


@pytest.mark.asyncio
async def test_set_config_secrets_with_secret_in_secrets_manager(fs, test_config, test_config_path_one_extends, secrets_setup):
    test_config.extends = [
        ExtendsConfig(
            key=ExtendsConfigKey.AWS_SECRETS_MANAGER,
            value="arn:aws:secretsmanager:us-west-2:123456789012:secret:iambic-config-secrets-9fae9066-5599-473f-b364-63fa0240b6f7",
        )
    ]
    await test_config.set_config_secrets()
    assert any(x.value == test_config_path_one_extends for x in test_config.extends)