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
