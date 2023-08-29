from __future__ import annotations

import os
import re

# inline jsonschem2md via vendor
import dev_tools.vendor.jsonschema2md as jsonschema2md2

from iambic.config.dynamic_config import Config, ExtendsConfig
from iambic.core.logger import log
from iambic.core.models import Variable
from iambic.core.utils import camel_to_snake
from iambic.plugins.v0_1_0.aws.iam.group.models import AwsIamGroupTemplate
from iambic.plugins.v0_1_0.aws.iam.policy.models import AwsIamManagedPolicyTemplate
from iambic.plugins.v0_1_0.aws.iam.role.models import AwsIamRoleTemplate
from iambic.plugins.v0_1_0.aws.iam.user.models import AwsIamUserTemplate
from iambic.plugins.v0_1_0.aws.iambic_plugin import AWSConfig
from iambic.plugins.v0_1_0.aws.identity_center.permission_set.models import (
    AwsIdentityCenterPermissionSetTemplate,
)
from iambic.plugins.v0_1_0.aws.models import AWSAccount, AWSOrganization
from iambic.plugins.v0_1_0.aws.organizations.scp.models import AwsScpPolicyTemplate
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

aws_template_models = [
    AwsIamRoleTemplate,
    AwsIamManagedPolicyTemplate,
    AwsIdentityCenterPermissionSetTemplate,
    AwsIamGroupTemplate,
    AwsIamUserTemplate,
    AwsScpPolicyTemplate,
]
azure_ad_template_models = [
    AzureActiveDirectoryGroupTemplate,
    AzureActiveDirectoryUserTemplate,
]
google_template_models = [GoogleWorkspaceGroupTemplate]
okta_template_models = [OktaGroupTemplate, OktaUserTemplate, OktaAppTemplate]
config_models = [
    Config,
    AWSConfig,
    AWSAccount,
    AWSOrganization,
    OktaConfig,
    AzureADConfig,
    GoogleWorkspaceConfig,
    ExtendsConfig,
    Variable,
    GithubConfig,
]

models = (
    aws_template_models
    + azure_ad_template_models
    + google_template_models
    + okta_template_models
    + config_models
)


def model_customization_for_config(json_schema_string):
    return json_schema_string.replace(
        os.getcwd(), "."
    )  # i want to replace all current directory string with just "."


SCHEMA_OVERRIDE_BY_CLASS_NAME = {
    "Config": model_customization_for_config,
}


def create_model_schemas(
    parser: jsonschema2md2.Parser,
    schema_dir: str,
    schema_md_str: str,
    model_schemas: list,
    raise_exception: bool = False,
) -> str:
    # jsonschemam2md2 doesn't generate proper Docusaurus compatible markdown for definitions. This is a hack to fix that.
    re_pattern_add_newline_before_header = (
        r"^(?P<stars>\*\*)(?P<text>.*)$"  # Add newline before headers to fix markdown
    )
    re_pattern_replace_br = r"<br>"  # Replace <br> with <br \>
    re_pattern_move_links = r"^(-\s*)(<a.*?>.*?</a>)(.*?\s)"  # Moves link references before the line, to be compatible with docusaurus markdown

    for model in model_schemas:
        class_name = str(model.__name__)
        file_name = camel_to_snake(class_name)
        model_schema_path = str(os.path.join(schema_dir, f"{file_name}.mdx"))
        json_schema_path = str(os.path.join(schema_dir, f"{file_name}.json"))
        schema_md_str += (
            f"* [{class_name}]({model_schema_path.replace(schema_dir, '.')})\n"
        )
        with open(json_schema_path, "w") as f:
            model.update_forward_refs(**{m.__name__: m for m in models})
            try:
                model_json_schema_as_string = model.schema_json(
                    by_alias=False,
                    indent=2,
                )
                if class_name in SCHEMA_OVERRIDE_BY_CLASS_NAME:
                    model_json_schema_as_string = SCHEMA_OVERRIDE_BY_CLASS_NAME[
                        class_name
                    ](model_json_schema_as_string)

                f.write(model_json_schema_as_string)
            except Exception as e:
                log.error(f"Error generating schema for {class_name}: {e}")
                if raise_exception:
                    raise
                continue

        with open(model_schema_path, "w") as f:
            model_schema_l = parser.parse_schema(model.schema(by_alias=False))
            model_schema_l.insert(
                1,
                "See [Template Schema Validation](/reference/template_validation_ide) "
                "to learn how to validate templates automatically in your IDE.\n\n"
                "## Description\n\n",
            )
            # Remove italics from description
            model_schema_l[2] = model_schema_l[2].strip("*").replace("*\n\n", "\n\n")
            model_schema_md = "".join(model_schema_l)
            text = re.sub(
                re_pattern_move_links,
                r"\n\2\n\n\1\3",
                model_schema_md,
                flags=re.MULTILINE,
            )
            text = re.sub(
                re_pattern_add_newline_before_header,
                r"\n\g<stars>\g<text>",
                text,
                flags=re.MULTILINE,
            )

            text = re.sub(re_pattern_replace_br, r"<br \>", text)

            if class_name in SCHEMA_OVERRIDE_BY_CLASS_NAME:
                text = SCHEMA_OVERRIDE_BY_CLASS_NAME[class_name](text)

            f.write(text)

    return schema_md_str


def generate_docs():
    schema_dir = os.path.join("docs", "web", "docs", "3-reference", "3-schemas")
    os.makedirs(schema_dir, exist_ok=True)
    parser = jsonschema2md2.Parser(
        examples_as_yaml=True,
        show_examples="all",
    )

    schema_md_str = """---
title: Template Schema
---

These schema models are automatically generated. Check out
[IAMbic IAMOps Philosophy](/reference/iamops_philosophy) and the
[example IAMbic templates repository](https://github.com/noqdev/iambic-templates-examples) to see real-life
examples of IAMbic templates and GitOps flows. See [Template Schema Validation](/reference/template_validation_ide)
to learn how to validate templates automatically in your IDE.
\n\n"""
    schema_md_str += "# AWS Template Models\n"
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
        parser, schema_dir, schema_md_str, config_models, raise_exception=False
    )

    with open(os.path.join(schema_dir, "index.mdx"), "w") as f:
        f.write(schema_md_str)


if __name__ == "__main__":
    generate_docs()
