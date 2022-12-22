import asyncio
from typing import Optional, Union

from pydantic import Field

from iambic.aws.models import AccessModel, AWSTemplate, Tag, Description, AWSAccount
from iambic.aws.utils import evaluate_on_account
from iambic.config.models import Config
from iambic.core.context import ExecutionContext
from iambic.core.logger import log
from iambic.core.models import BaseModel, AccountChangeDetails, TemplateChangeDetails


AWS_SSO_PERMISSION_SET_TEMPLATE_TYPE = "NOQ::AWS::SSO::PermissionSet"


class AWSSSOInstance(BaseModel):
    arn: str
    region: str
    access_portal_url: str
    identity_store_id: str


class CustomerManagedPolicyReference(AccessModel):
    path: str
    name: str

    @property
    def resource_type(self) -> str:
        return "aws:iam:managed_policy"

    @property
    def resource_id(self) -> str:
        return f"{self.path}{self.name}"


class ManagedPolicyArn(AccessModel):
    arn: str

    @property
    def resource_type(self) -> str:
        return "aws:iam:managed_policy"

    @property
    def resource_id(self) -> str:
        return self.arn


class SessionDuration(AccessModel):
    session_duration: str


class InlinePolicy(AccessModel):
    inline_policy: str


class AWSSSOPermissionSetProperties(BaseModel):
    name: str
    description: Optional[Union[str, list[Description]]] = Field(
        "",
        description="Description of the role",
    )
    customer_managed_policy_references: list[CustomerManagedPolicyReference]
    session_duration: Union[str, list[SessionDuration]]
    inline_policy: Union[str, list[InlinePolicy]]
    managed_policies: list[Union[str, ManagedPolicyArn]]
    tags: Optional[list[Tag]]

    @property
    def resource_type(self) -> str:
        return "aws:sso:permission_set"

    @property
    def resource_id(self) -> str:
        return self.name


class AWSSSOPermissionSetTemplate(AWSTemplate, AccessModel):
    template_type: str = AWS_SSO_PERMISSION_SET_TEMPLATE_TYPE
    properties: AWSSSOPermissionSetProperties
    identifier: str

    async def _apply_to_account(
        self, aws_account: AWSAccount, context: ExecutionContext
    ) -> AccountChangeDetails:
        """Apply the permission set to the given AWS account

        :param aws_account:
        :param context:
        :return:
        """

        """
        Need to assign all org accounts to an attribute of AWSAccount.sso_details
        Then to gather accounts it should be provisioned to, 
            diff it against the template's included_accounts/excluded_accounts
        """
        sso_client = await aws_account.get_client("sso-admin")
        instance_arn = aws_account.sso_details.instance_arn
        permission_set_arn = aws_account.sso_details.permission_set_map.get(self.properties.name)
        # If changes made to policies or account scope has changed, you need to call this
        # provision_permission_set()

    async def apply(
        self, config: Config, context: ExecutionContext
    ) -> TemplateChangeDetails:
        tasks = []
        template_changes = TemplateChangeDetails(
            resource_id=self.resource_id,
            resource_type=self.resource_type,
            template_path=self.file_path,
        )
        log_params = dict(
            resource_type=self.resource_type, resource_id=self.resource_id
        )
        for account in config.aws_accounts:
            """
            TODO: This part has to be re-written
            
            The way it will need to be evaluated for SSO is:
                1. Check if the account has an SSO instance
                2. Check if the org is defined within included_orgs and not in excluded_orgs
            """
            if evaluate_on_account(self, account, context):
                if context.execute:
                    log_str = "Applying changes to resource."
                else:
                    log_str = "Detecting changes for resource."
                log.info(log_str, account=str(account), **log_params)
                tasks.append(self._apply_to_account(account, context))

        account_changes = await asyncio.gather(*tasks)
        template_changes.proposed_changes = [
            account_change
            for account_change in account_changes
            if any(account_change.proposed_changes)
        ]
        if account_changes and context.execute:
            log.info(
                "Successfully applied resource changes to all aws_accounts.",
                **log_params,
            )
        elif account_changes and not context.execute:
            log.info(
                "Successfully detected required resource changes on all aws_accounts.",
                **log_params,
            )
        else:
            log.debug("No changes detected for resource on any account.", **log_params)

        return template_changes

    @property
    def resource_type(self) -> str:
        return "aws:sso:permission_set"

    @property
    def resource_id(self) -> str:
        return self.identifier
