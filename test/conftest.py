from __future__ import annotations

import itertools

import pytest
import yaml

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


@pytest.fixture(scope="function")
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

@pytest.fixture(scope="function")
def test_config_path_two_accounts_plus_org(fs):
    config_file_path = "/iambic/configuration.yaml"
    fs.create_file(config_file_path)
    with open(config_file_path, "w") as f:
        yaml.dump(yaml.load("""
            template_type: NOQ::Core::Config
            version: '1'
            aws:
            accounts:
              - account_id: '123456789010'
                account_name: dev1
                iambic_managed: read_and_write
                org_id: o-mlt3rs19sf
                spoke_role_arn: arn:aws:iam::123456789010:role/IambicSpokeRole
                variables:
                  - key: environment
                    value: prod
              - account_id: '123456789011'
                account_name: dev2
                iambic_managed: read_and_write
                org_id: o-mlt3rs19sf
                spoke_role_arn: arn:aws:iam::123456789011:role/IambicSpokeRole
              - account_id: '123456789012'
                account_name: staging1
                iambic_managed: read_and_write
                org_id: o-mlt3rs19sf
                spoke_role_arn: arn:aws:iam::123456789012:role/IambicSpokeRole
              - account_id: '123456789013'
                account_name: staging2
                iambic_managed: read_and_write
                org_id: o-mlt3rs19sf
                spoke_role_arn: arn:aws:iam::123456789013:role/IambicSpokeRole
              - account_id: '123456789014'
                account_name: qa1
                iambic_managed: read_and_write
                org_id: o-mlt3rs19sf
                spoke_role_arn: arn:aws:iam::123456789014:role/IambicSpokeRole
              - account_id: '123456789015'
                account_name: qa2
                iambic_managed: read_and_write
                org_id: o-mlt3rs19sf
                spoke_role_arn: arn:aws:iam::123456789015:role/IambicSpokeRole
              - account_id: '123456789016'
                account_name: prod1
                iambic_managed: read_and_write
                org_id: o-mlt3rs19sf
                spoke_role_arn: arn:aws:iam::123456789016:role/IambicSpokeRole
              - account_id: '123456789017'
                account_name: prod2
                iambic_managed: read_and_write
                org_id: o-mlt3rs19sf
                spoke_role_arn: arn:aws:iam::123456789017:role/IambicSpokeRole
              - account_id: '123456789018'
                account_name: prod3
                iambic_managed: read_and_write
                org_id: o-mlt3rs19sf
                spoke_role_arn: arn:aws:iam::123456789018:role/IambicSpokeRole
              - account_id: '123456789019'
                account_name: test
                iambic_managed: read_and_write
                org_id: o-mlt3rs19sf
                spoke_role_arn: arn:aws:iam::123456789019:role/IambicSpokeRole
            organizations:
              - default_rule:
                iambic_managed: read_and_write
                hub_role_arn: arn:aws:iam::123456789012:role/IambicHubRole
                identity_center: {}
                org_account_id: '123456789010'
                org_id: o-mlt3rs19sf
            sqs_cloudtrail_changes_queues:
                - arn:aws:sqs:us-east-1:123456789010:IAMbicChangeDetectionQueue
            core:
            minimum_ulimit: 64000
""", Loader=yaml.Loader), f)
    return config_file_path


@pytest.fixture(scope="function")
def test_config_path_one_extends(fs):
    extends_config_file_path = "/iambic/extends_secretsmanager.yaml"
    fs.create_file(extends_config_file_path)
    with open(extends_config_file_path, "w") as f:
        yaml.dump({
            "extends": [
                {
                    "assume_role_arn": "arn:aws:iam::123456789012:role/IambicSpokeRole",
                    "key": "AWS_SECRETS_MANAGER",
                    "value": "arn:aws:secretsmanager:us-west-2:123456789012:secret:iambic-config-secrets-9fae9066-5599-473f-b364-63fa0240b6f7"
                }
            ]
        }, f)
    return extends_config_file_path


@pytest.fixture(scope="function")
def test_config(fs, test_config_path_two_accounts_plus_org):
    config_path = test_config_path_two_accounts_plus_org
    base_config = Config(version=CURRENT_IAMBIC_VERSION, file_path=config_path)
    all_plugins = load_plugins(base_config.plugins)
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
        plugins=base_config.plugins,
        plugin_instances=all_plugins,
        aws=AWSConfig(),
    )

    TEMPLATES.set_templates(
        list(
            itertools.chain.from_iterable(
                [plugin.templates for plugin in config.plugin_instances]
            )
        )
    )
    return config
