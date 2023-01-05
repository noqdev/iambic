from __future__ import annotations

import asyncio
import random

from iambic.aws.iam.policy.models import (
    AWS_MANAGED_POLICY_TEMPLATE_TYPE,
    ManagedPolicyTemplate,
)
from iambic.aws.iam.policy.template_generation import get_managed_policy_dir
from iambic.aws.iam.policy.utils import get_managed_policy
from iambic.aws.models import AWSAccount
from iambic.core.logger import log
from iambic.core.utils import gather_templates


async def generate_managed_policy_template_from_base(
    repo_dir: str,
) -> ManagedPolicyTemplate:
    managed_policies = await gather_templates(
        repo_dir, AWS_MANAGED_POLICY_TEMPLATE_TYPE
    )
    managed_policy_dir = get_managed_policy_dir(repo_dir)
    managed_policy_template = ManagedPolicyTemplate.load(
        random.choice(managed_policies)
    )
    log.info(
        "Using managed policy as base",
        managed_policy=managed_policy_template.identifier,
    )

    managed_policy_template.identifier = f"iambic_test_{random.randint(0, 10000)}"
    managed_policy_template.file_path = (
        f"{managed_policy_dir}/{managed_policy_template.identifier}.yaml"
    )
    managed_policy_template.properties.path = "/iambic_test/"
    managed_policy_template.properties.policy_name = managed_policy_template.identifier
    managed_policy_template.properties.description = (
        "This was created by a functional test."
    )

    return managed_policy_template


async def get_managed_policy_across_accounts(
    aws_accounts: list[AWSAccount], managed_policy_path: str, managed_policy_name: str
) -> dict:
    async def get_managed_policy_for_account(aws_account: AWSAccount):
        iam_client = await aws_account.get_boto3_client("iam")
        arn = f"arn:aws:iam::{aws_account.account_id}:policy{managed_policy_path}{managed_policy_name}"
        return {aws_account.account_id: await get_managed_policy(iam_client, arn)}

    account_on_managed_policies = await asyncio.gather(
        *[get_managed_policy_for_account(aws_account) for aws_account in aws_accounts]
    )
    return {
        account_id: mp
        for resp in account_on_managed_policies
        for account_id, mp in resp.items()
    }
