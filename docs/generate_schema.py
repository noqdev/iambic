from __future__ import annotations

import os

import jsonschema2md2

from iambic.config.models import Config, ExtendsConfig
from iambic.core.models import Variable
from iambic.core.utils import camel_to_snake
from iambic.google.group.models import GroupTemplate
from iambic.okta.group.models import OktaGroupTemplate
from iambic.plugins.aws.iam.group import GroupTemplate as AWSGroupTemplate
from iambic.plugins.aws.iam.policy.models import ManagedPolicyTemplate
from iambic.plugins.aws.iam.role.models import RoleTemplate
from iambic.plugins.aws.identity_center.permission_set.models import (
    AWSIdentityCenterPermissionSetTemplate,
)
from iambic.plugins.aws.models import AWSAccount, AWSOrganization


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
        schema_md_str += f"* [{class_name}]({model_schema_path.replace('docs/', '')})\n"

        with open(model_schema_path, "w") as f:
            f.write("".join(parser.parse_schema(model.schema(by_alias=False))))

    return schema_md_str


def generate_docs():
    aws_template_models = [
        RoleTemplate,
        ManagedPolicyTemplate,
        AWSIdentityCenterPermissionSetTemplate,
        AWSGroupTemplate,
    ]
    google_template_models = [GroupTemplate]
    okta_template_models = [OktaGroupTemplate]
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
