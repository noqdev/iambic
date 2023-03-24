from __future__ import annotations

import os

import jsonschema2md2

from iambic.config.dynamic_config import Config, ExtendsConfig
from iambic.core.models import Variable
from iambic.core.utils import camel_to_snake
from iambic.plugins.v0_1_0.aws.iam.group.models import AwsIamGroupTemplate
from iambic.plugins.v0_1_0.aws.iam.policy.models import AwsIamManagedPolicyTemplate
from iambic.plugins.v0_1_0.aws.iam.role.models import AwsIamRoleTemplate
from iambic.plugins.v0_1_0.aws.iam.user.models import AwsIamUserTemplate
from iambic.plugins.v0_1_0.aws.identity_center.permission_set.models import (
    AwsIdentityCenterPermissionSetTemplate,
)
from iambic.plugins.v0_1_0.aws.models import AWSAccount, AWSOrganization
from iambic.plugins.v0_1_0.azure_ad.group.models import (
    AzureActiveDirectoryGroupTemplate,
)
from iambic.plugins.v0_1_0.azure_ad.user.models import AzureActiveDirectoryUserTemplate
from iambic.plugins.v0_1_0.google_workspace.group.models import (
    GoogleWorkspaceGroupTemplate,
)
from iambic.plugins.v0_1_0.okta.app.models import OktaAppTemplate
from iambic.plugins.v0_1_0.okta.group.models import OktaGroupTemplate
from iambic.plugins.v0_1_0.okta.user.models import OktaUserTemplate


def create_model_schemas(
    parser: jsonschema2md2.Parser,
    schema_dir: str,
    schema_md_str: str,
    model_schemas: list,
) -> str:
    for model in model_schemas:
        class_name = str(model.__name__)
        file_name = camel_to_snake(class_name)
        model_schema_path = str(os.path.join(schema_dir, f"{file_name}.md"))
        json_schema_path = str(os.path.join(schema_dir, f"{file_name}.json"))
        schema_md_str += f"* [{class_name}]({model_schema_path.replace('docs/', '')})\n"
        with open(json_schema_path, "w") as f:
            f.write(model.schema_json(by_alias=False, indent=2))
        with open(model_schema_path, "w") as f:
            f.write("".join(parser.parse_schema(model.schema(by_alias=False))))

    return schema_md_str


def generate_docs():
    aws_template_models = [
        AwsIamRoleTemplate,
        AwsIamManagedPolicyTemplate,
        AwsIdentityCenterPermissionSetTemplate,
        AwsIamGroupTemplate,
        AwsIamUserTemplate,
    ]
    azure_ad_template_models = [
        AzureActiveDirectoryGroupTemplate,
        AzureActiveDirectoryUserTemplate,
    ]
    google_template_models = [GoogleWorkspaceGroupTemplate]
    okta_template_models = [OktaGroupTemplate, OktaUserTemplate, OktaAppTemplate]
    config_models = [
        AWSAccount,
        AWSOrganization,
        Config,
        ExtendsConfig,
        Variable,
    ]

    schema_dir = os.path.join("docs", "schemas")
    os.makedirs(schema_dir, exist_ok=True)
    parser = jsonschema2md2.Parser(
        examples_as_yaml=False,
        show_examples="all",
    )
    schema_md_str = "# AWS Template Models\n"
    schema_md_str = create_model_schemas(
        parser, schema_dir, schema_md_str, aws_template_models
    )
    schema_md_str += "\n# Azure AD Template Models\n"
    schema_md_str = create_model_schemas(
        parser, schema_dir, schema_md_str, azure_ad_template_models
    )
    schema_md_str += "\n# Google Template Models\n"
    schema_md_str = create_model_schemas(
        parser, schema_dir, schema_md_str, google_template_models
    )
    schema_md_str += "\n# Okta Template Models\n"
    schema_md_str = create_model_schemas(
        parser, schema_dir, schema_md_str, okta_template_models
    )
    schema_md_str += "\n# Config Models\n"
    schema_md_str = create_model_schemas(
        parser, schema_dir, schema_md_str, config_models
    )

    with open(os.path.join("docs", "SCHEMA.md"), "w") as f:
        f.write(schema_md_str)


if __name__ == "__main__":
    generate_docs()
