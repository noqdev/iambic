from __future__ import annotations

import os

import jsonschema2md2
import pytest

from docs.generate_schema import create_model_schemas
from iambic.config.dynamic_config import Config, ExtendsConfig
from iambic.core.models import Variable
from iambic.plugins.v0_1_0.aws.iam.group.models import AwsIamGroupTemplate
from iambic.plugins.v0_1_0.aws.iam.policy.models import AwsIamManagedPolicyTemplate
from iambic.plugins.v0_1_0.aws.iam.role.models import AwsIamRoleTemplate
from iambic.plugins.v0_1_0.aws.iam.user.models import AwsIamUserTemplate
from iambic.plugins.v0_1_0.aws.iambic_plugin import AWSConfig
from iambic.plugins.v0_1_0.aws.identity_center.permission_set.models import (
    AwsIdentityCenterPermissionSetTemplate,
)
from iambic.plugins.v0_1_0.aws.models import (
    AWSAccount,
    AWSOrganization,
    BaseAWSAccountAndOrgModel,
)
from iambic.plugins.v0_1_0.azure_ad.group.models import (
    AzureActiveDirectoryGroupTemplate,
)
from iambic.plugins.v0_1_0.azure_ad.iambic_plugin import AzureADConfig
from iambic.plugins.v0_1_0.azure_ad.user.models import AzureActiveDirectoryUserTemplate
from iambic.plugins.v0_1_0.github.iambic_plugin import GithubConfig
from iambic.plugins.v0_1_0.google_workspace.group.models import (
    GoogleWorkspaceGroupTemplate,
)
from iambic.plugins.v0_1_0.google_workspace.iambic_plugin import GoogleWorkspaceConfig
from iambic.plugins.v0_1_0.okta.app.models import OktaAppTemplate
from iambic.plugins.v0_1_0.okta.group.models import OktaGroupTemplate
from iambic.plugins.v0_1_0.okta.iambic_plugin import OktaConfig
from iambic.plugins.v0_1_0.okta.user.models import OktaUserTemplate


@pytest.mark.parametrize(
    "klass",
    [
        AwsIamRoleTemplate,
        AwsIamManagedPolicyTemplate,
        AwsIdentityCenterPermissionSetTemplate,
        AwsIamGroupTemplate,
        AwsIamUserTemplate,
        AzureActiveDirectoryGroupTemplate,
        AzureActiveDirectoryUserTemplate,
        GoogleWorkspaceGroupTemplate,
        OktaGroupTemplate,
        OktaUserTemplate,
        OktaAppTemplate,
        Config,
        BaseAWSAccountAndOrgModel,
        AWSConfig,
        AWSAccount,
        AWSOrganization,
        OktaConfig,
        AzureADConfig,
        GoogleWorkspaceConfig,
        ExtendsConfig,
        Variable,
        GithubConfig,
    ],
)
def test_create_model_schemas(klass):
    # TODO: look for all subclasses of BaseEntity
    test_schema_dir = os.path.join("test", "docs", "schemas")
    os.makedirs(test_schema_dir, exist_ok=True)
    parser = jsonschema2md2.Parser(
        examples_as_yaml=True,
        show_examples="all",
    )

    try:
        create_model_schemas(parser, test_schema_dir, "", [klass], raise_exception=True)
    except Exception:
        assert False
    else:
        assert True
