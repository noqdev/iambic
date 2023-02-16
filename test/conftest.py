from __future__ import annotations

import itertools

import pytest

from iambic.config.dynamic_config import (
    CURRENT_IAMBIC_VERSION,
    Config,
    create_pydantic_model,
    load_plugins,
)
from iambic.config.templates import TEMPLATES
from iambic.core.logger import log
from iambic.plugins.v0_1_0.aws.iambic_plugin import AWSConfig
from iambic.plugins.v0_1_0.aws.models import AWSAccount


@pytest.fixture
def aws_accounts():
    return [
        AWSAccount(account_id="123456789010", account_name="dev1"),
        AWSAccount(account_id="123456789011", account_name="dev2"),
        AWSAccount(account_id="123456789012", account_name="staging1"),
        AWSAccount(account_id="123456789013", account_name="staging2"),
        AWSAccount(account_id="123456789014", account_name="qa1"),
        AWSAccount(account_id="123456789015", account_name="qa2"),
        AWSAccount(account_id="123456789016", account_name="prod1"),
        AWSAccount(account_id="123456789017", account_name="prod2"),
        AWSAccount(account_id="123456789018", account_name="prod3"),
        AWSAccount(account_id="123456789019", account_name="test"),
    ]


@pytest.fixture(scope="session")
def test_config():
    config_path = "cool_file_man.yaml"
    base_config = Config(version=CURRENT_IAMBIC_VERSION, file_path=config_path)
    all_plugins = load_plugins(base_config.plugin_paths)
    config_fields = {}
    log.warning("All plugins", plugins=[plugin.config_name for plugin in all_plugins])
    for plugin in all_plugins:
        config_fields[plugin.config_name] = (plugin.provider_config, None)

    dynamic_config = create_pydantic_model(
        "DynamicConfig", __base__=Config, **config_fields
    )
    config = dynamic_config(
        version=CURRENT_IAMBIC_VERSION,
        file_path=config_path,
        plugins=all_plugins,
        aws=AWSConfig(),
    )

    TEMPLATES.set_templates(
        list(
            itertools.chain.from_iterable(
                [plugin.templates for plugin in config.plugins]
            )
        )
    )
    return config
