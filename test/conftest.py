from __future__ import annotations

import itertools
import json
import os
import pathlib

import boto3
import pytest
import yaml
from moto import mock_secretsmanager

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
from iambic.plugins.v0_1_0.aws.utils import boto3_retry


@pytest.fixture(scope="session")
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
def prevent_aws_real_mutants(request):
    def fin():
        if current_aws_access_key_id:
            os.environ["AWS_ACCESS_KEY_ID"] = current_aws_access_key_id
        if current_aws_secret_access_key:
            os.environ["AWS_SECRET_ACCESS_KEY"] = current_aws_secret_access_key
        if current_aws_default_region:
            os.environ["AWS_DEFAULT_REGION"] = current_aws_default_region
        if current_aws_session_token:
            os.environ["AWS_SESSION_TOKEN"] = current_aws_session_token
        if current_aws_security_token:
            os.environ["AWS_SECURITY_TOKEN"] = current_aws_security_token
        if current_aws_profile:
            os.environ["AWS_PROFILE"] = current_aws_profile   

    request.addfinalizer(fin)
    current_aws_access_key_id = os.environ.get("AWS_ACCESS_KEY_ID")
    current_aws_secret_access_key = os.environ.get("AWS_SECRET_ACCESS_KEY")
    current_aws_default_region = os.environ.get("AWS_DEFAULT_REGION")
    current_aws_session_token = os.environ.get("AWS_SESSION_TOKEN")
    current_aws_security_token = os.environ.get("AWS_SECURITY_TOKEN")
    current_aws_profile = os.environ.get("AWS_PROFILE")

    os.environ["AWS_ACCESS_KEY_ID"] = "test"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "test"
    os.environ["AWS_DEFAULT_REGION"] = "us-west-2"
    os.environ["AWS_SESSION_TOKEN"] = "test"
    os.environ["AWS_SECURITY_TOKEN"] = "test"
    os.environ.pop("AWS_PROFILE", None)


@pytest.fixture(scope="function")
def test_config_path_two_accounts_plus_org(tmp_path):
    config_file_path = tmp_path / "iambic/configuration.yaml"
    os.makedirs(tmp_path / "iambic", exist_ok=True)
    with open(config_file_path, "w") as f:
        yaml.dump(
            yaml.load(
                """
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
""",
                Loader=yaml.Loader,
            ),
            f,
        )
    return config_file_path


@pytest.fixture(scope="function")
def test_config_path_one_extends(tmp_path):
    extends_config_file_path = tmp_path / "iambic/extends_secretsmanager.yaml"
    os.makedirs(tmp_path / "iambic", exist_ok=True)
    with open(extends_config_file_path, "w") as f:
        yaml.dump(
            {
                "extends": [
                    {
                        "assume_role_arn": "arn:aws:iam::123456789012:role/IambicSpokeRole",
                        "key": "AWS_SECRETS_MANAGER",
                        "value": "arn:aws:secretsmanager:us-west-2:123456789012:secret:iambic-config-secrets-9fae9066-5599-473f-b364-63fa0240b6f7",
                    }
                ]
            },
            f,
        )
    return extends_config_file_path


@pytest.fixture(scope="session", autouse=True)
def secrets_setup(prevent_aws_real_mutants):
    with mock_secretsmanager():
        secretmgr = boto3.client("secretsmanager", region_name="us-west-2")
        secretmgr.create_secret(
            Name="arn:aws:secretsmanager:us-west-2:123456789012:secret:iambic-config-secrets-9fae9066-5599-473f-b364-63fa0240b6f7",
            SecretString=json.dumps(
                {
                    "secrets": {
                        "git": {
                            "repositories": [
                                {
                                    "name": "test-iambic",
                                    "url": "file:///iambic/git",
                                }
                            ]
                        }
                    }
                }
            ),
        )
        yield secretmgr


@pytest.fixture(scope="function")
def test_config(test_config_path_two_accounts_plus_org):
    config_path = str(test_config_path_two_accounts_plus_org)
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
        aws=AWSConfig(
            region_name="us-west-2",
        ),
    )

    TEMPLATES.set_templates(
        list(
            itertools.chain.from_iterable(
                [plugin.templates for plugin in config.plugin_instances]
            )
        )
    )
    return config


@pytest.fixture(scope="function")
def mock_aws_account_rw_secretsmanager_session(test_config):
    test_config.aws = AWSAccount(
        account_id="123456789012",
        account_name="test",
        iambic_managed="read_and_write",
    )
