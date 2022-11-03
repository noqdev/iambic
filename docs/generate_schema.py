import os

import jsonschema2md2

from iambic.aws.iam.models import MaxSessionDuration, Path
from iambic.aws.iam.policy.models import (
    AssumeRolePolicyDocument,
    ManagedPolicyRef,
    ManagedPolicyTemplate,
    PolicyDocument,
    PolicyStatement,
)
from iambic.aws.iam.role.models import PermissionBoundary, RoleAccess, RoleTemplate
from iambic.config.models import AWSAccount, Config, ExtendsConfig, Variable
from iambic.core.utils import camel_to_snake
from iambic.google.group.models import GroupMember, GroupTemplate


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
            f.write("".join(parser.parse_schema(model.schema())))

    return schema_md_str


def generate_docs():
    aws_template_models = [
        RoleTemplate,
        AssumeRolePolicyDocument,
        ManagedPolicyRef,
        PolicyDocument,
        Path,
        PermissionBoundary,
        MaxSessionDuration,
        RoleAccess,
        PolicyStatement,
        ManagedPolicyTemplate,
    ]
    google_template_models = [GroupTemplate, GroupMember]
    config_models = [
        AWSAccount,
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
    schema_md_str += "\n# Config Models\n"
    schema_md_str = create_model_schemas(
        parser, schema_dir, schema_md_str, config_models
    )

    with open(os.path.join("docs", "SCHEMA.md"), "w") as f:
        f.write(schema_md_str)


if __name__ == "__main__":
    generate_docs()
