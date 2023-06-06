from __future__ import annotations

import random
import uuid

from functional_tests.conftest import IAMBIC_TEST_DETAILS

from iambic.core.iambic_enum import Command
from iambic.core.logger import log
from iambic.core.models import ExecutionMessage
from iambic.core.template_generation import get_existing_template_map
from iambic.core.utils import gather_templates
from iambic.plugins.v0_1_0.aws.models import AWSAccount
from iambic.plugins.v0_1_0.aws.organizations.scp.models import (
    AWS_SCP_POLICY_TEMPLATE,
    AwsScpPolicyTemplate,
    PolicyDocument,
    PolicyProperties,
)
from iambic.plugins.v0_1_0.aws.organizations.scp.template_generation import (
    collect_aws_scp_policies,
    generate_aws_scp_policy_templates,
    get_template_dir,
)

EXAMPLE_POLICY_DOCUMENT = '{"Version":"2012-10-17","Statement":{"Effect":"Allow","Action":"lex:*","Resource":"*"}}'


async def generate_policy_template(
    repo_dir: str,
    aws_account: AWSAccount,
):
    """Generate a policy template for the given account

    Returns:
        AwsScpPolicyTemplate: The generated policy template,
            not yet written to disk and not yet applied to the account.
    """

    policy_dir = get_template_dir(repo_dir)

    policy_name = f"iambic_test_{random.randint(0, 10000)}"
    policy_description = "This was created by a functional test."
    policy_content = EXAMPLE_POLICY_DOCUMENT

    policy_template = AwsScpPolicyTemplate(
        identifier=policy_name,
        account_id=aws_account.account_id,
        org_id=aws_account.organization.org_id,
        file_path=f"{policy_dir}/{policy_name}.yaml",
        properties=PolicyProperties.parse_obj(
            dict(
                policy_name=policy_name,
                description=policy_description,
                type="SERVICE_CONTROL_POLICY",
                aws_managed=False,
                policy_document=PolicyDocument.parse_raw_policy(policy_content),
            ),
        ),
    )  # type: ignore

    policy_template.properties.path = "/iambic_test/"

    return policy_template


async def generate_scp_policy_template_from_base(
    repo_dir: str,
    create_policy: bool = False,
) -> AwsScpPolicyTemplate:
    policy_dir = get_template_dir(repo_dir)

    if not create_policy:
        scp_policies = await gather_templates(repo_dir, AWS_SCP_POLICY_TEMPLATE)
        policy_template = AwsScpPolicyTemplate.load(random.choice(scp_policies))

        if not scp_policies:
            message = "Policies should have been generated previously (policies in this account are empty)"
            log.error(message)
            raise Exception(message)

        policy_template.properties.policy_name = (
            f"iambic_test_{random.randint(0, 10000)}"
        )
        policy_template.identifier = policy_template.properties.policy_name
        policy_template.properties.policy_id = None
        policy_template.file_path = f"{policy_dir}/{policy_template.identifier}.yaml"
        policy_template.properties.path = "/iambic_test/"
        policy_template.write()

        log.info(
            "Using scp policy as base",
            managed_policy=policy_template.identifier,
        )
    else:
        # TODO: check create policy
        org_account = next(
            filter(
                lambda acc: acc.organization_account,
                IAMBIC_TEST_DETAILS.config.aws.accounts,
            )
        )

        policy_template = await generate_policy_template(repo_dir, org_account)

        policy_template.write()

        changes = await policy_template.apply(IAMBIC_TEST_DETAILS.config.aws)

        if changes.exceptions_seen:
            log.error("Error creating policy", changes=changes)
            raise Exception("Error creating policy")

        policy_template = AwsScpPolicyTemplate.load(str(policy_template.file_path))

        log.info(
            "Creating new scp policy",
            managed_policy=policy_template.identifier,
        )

    return policy_template


async def scp_policy_full_import(detect_messages: list = None):
    exe_message = ExecutionMessage(
        execution_id=str(uuid.uuid4()),
        command=Command.IMPORT,
        provider_type="aws",
        provider_id=IAMBIC_TEST_DETAILS.config.aws.organizations[0].org_account_id,
    )  # type: ignore

    scp_template_map = await get_existing_template_map(
        repo_dir=IAMBIC_TEST_DETAILS.template_dir_path,
        template_type=AWS_SCP_POLICY_TEMPLATE,
        template_map=IAMBIC_TEST_DETAILS.config.aws.template_map,
        nested=True,
    )

    await collect_aws_scp_policies(
        exe_message,
        IAMBIC_TEST_DETAILS.config.aws,
        scp_template_map,
        detect_messages,
    )
    await generate_aws_scp_policy_templates(
        exe_message,
        IAMBIC_TEST_DETAILS.config.aws,
        IAMBIC_TEST_DETAILS.template_dir_path,
        scp_template_map,
        detect_messages,
    )
