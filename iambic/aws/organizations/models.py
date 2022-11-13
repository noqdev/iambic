import datetime
from typing import Any, Literal, Optional, Union

from pydantic import Field

from iambic.aws.accounts.models import AWSAccountTemplate
from iambic.aws.iam.models import Description
from iambic.aws.models import AccessModel, AWSTemplate
from iambic.aws.utils import maybe_assume_role
from iambic.core.logger import log
from iambic.core.models import BaseModel
from iambic.core.utils import aio_wrapper


class AutomaticallyOnboardIambicOptions(AccessModel):
    enabled: bool = Field(
        False,
        description="Whether to automatically onboard iambic to newly detected accounts.",
    )
    read_only: bool = Field(
        False,
        description="Whether to automatically onboard iambic to newly detect accounts in read-only mode.",
    )
    roles_to_assume: list[str] = Field(
        ["OrganizationAccountAccessRole", "AWSControlTowerExecution"],
        description="The list of role names to try to assume when onboarding a new account.",
    )


class AwsOrgChildAccount(BaseModel):
    Id: str
    Type: Literal["ACCOUNT", "ORGANIZATIONAL_UNIT"]
    parent: Optional[str] = ""
    children: list["AwsOrgChildAccount"] = []
    arn: str = ""
    name: str = ""
    email: str = ""
    status: str = ""
    joined_method: str = ""
    joined_timestamp: datetime.datetime = datetime.datetime(1970, 1, 1)


class AWSOrgAccount(BaseModel):
    account_id: str
    arn: str
    email: str
    name: str
    status: str
    joined_method: str
    joined_timestamp: datetime.datetime


class AWSOrgStructure(BaseModel):
    Id: str
    arn: str
    name: str
    policy_types: list[dict[str, Any]]
    children: list["AWSOrgStructure"] = []


class AWSOrganizationTemplate(AWSTemplate):
    template_type = "NOQ::AWS::Organization"
    description: Optional[Union[str, list[Description]]] = Field(
        "",
        description="Description of the Organization.",
    )
    org_id: str = Field(
        description="The Organization ID.",
        example="o-1234567890",
    )
    account_id: str = Field(
        description="The Account ID of the Organizations management account.",
        example="123456789012",
    )
    automatically_onboard_iambic: AutomaticallyOnboardIambicOptions = Field(
        AutomaticallyOnboardIambicOptions(enabled=False)
    )
    assume_role_arn: str = Field(
        description="The role to assume on the Org Management account.",
        example="arn:aws:iam::123456789012:role/IambicRole",
    )

    async def _describe_ou(self, org_client, ou_id: str, **kwargs) -> dict[str, str]:
        result = org_client.describe_organizational_unit(
            OrganizationalUnitId=ou_id,
        )
        return result.get("OrganizationalUnit")

    async def _list_children_for_ou(
        self,
        org_client,
        parent_id: str,
        child_type: Literal["ACCOUNT", "ORGANIZATIONAL_UNIT"],
        **kwargs,
    ) -> list[AwsOrgChildAccount]:
        children = org_client.list_children(ChildType=child_type, ParentId=parent_id)
        return [AwsOrgChildAccount(**child) for child in children["Children"]]

    async def _describe_account(
        self,
        org_client,
        account_id: str,
    ) -> dict[str, str]:
        result = org_client.describe_account(AccountId=account_id)
        return result.get("Account")

    async def _get_children_for_ou(
        self, org_client, root_id: str
    ) -> list[AwsOrgChildAccount]:
        children: list[AwsOrgChildAccount] = []
        children.extend(
            await self._list_children_for_ou(org_client, root_id, "ORGANIZATIONAL_UNIT")
        )
        children.extend(
            await self._list_children_for_ou(org_client, root_id, "ACCOUNT")
        )
        for child in children:
            child.parent = root_id
            if child.Type == "ORGANIZATIONAL_UNIT":
                child.update(await self._describe_ou(org_client, child.Id))
                child.children = await self._get_children_for_ou(org_client, child.Id)
            else:
                child.update(await self._describe_account(org_client, child.Id))
        return children

    async def get_accounts_from_org_struc(
        self, org_struc: dict, org_id: str = None, accounts: Optional[set] = None
    ) -> set[str]:
        if accounts is None:
            accounts = set()
            for org_dict in org_struc.values():
                if not org_id or org_id in org_dict["Arn"]:
                    await self.get_accounts_from_org_struc(org_dict, org_id, accounts)

        if org_struc.get("Type") == "ACCOUNT":
            accounts.add(org_struc["Id"])

        for child in org_struc.get("Children", []):
            await self.get_accounts_from_org_struc(child, org_id, accounts)

        return accounts

    async def retrieve_org_structure(self, org_client) -> dict:
        roots = org_client.list_roots()
        org_structure = {}
        for root_u in roots.get("Roots", []):
            root_u["identifier"] = root_u["Id"]
            root = AWSOrgStructure(**root_u)
            root_id = root.Id
            root.children = await self._get_children_for_ou(org_client, root.Id)
            org_structure[root_id] = root
        return org_structure

    async def onboard_accounts(self, config: Any) -> list[AWSAccountTemplate]:
        new_accounts_onboarded = []
        new_accounts_excluded = []
        existing_accounts = []
        if not (
            self.automatically_onboard_iambic.enabled
            and self.automatically_onboard_iambic.roles_to_assume
        ):
            # TODO: Log
            return new_accounts_onboarded

        org_client = await maybe_assume_role(self.assume_role_arn, "organizations")
        paginator = org_client.get_paginator("list_accounts")
        for page in paginator.paginate():
            for account in page.get("Accounts"):
                account["account_id"] = account["Id"]
                existing_accounts.append(AWSOrgAccount(**account))

        org_struc = await self.retrieve_org_structure(org_client)
        child_accounts = await self.get_accounts_from_org_struc(org_struc, self.org_id)

        try:
            for account in child_accounts:
                log_data["account_id"] = account
                if spoke_accounts.query({"account_id": account}):
                    log.debug({"message": "Account already in Noq", **log_data})
                    continue  # We already know about this account, and can skip it
                elif account in org_account.accounts_excluded_from_automatic_onboard:
                    log.debug(
                        {
                            "message": "Automatic onboarding disabled for this account",
                            **log_data,
                        }
                    )
                    continue

                for aws_organizations_role_name in org_account.role_names:
                    # Get STS client on Org Account
                    # attempt sts:AssumeRole
                    org_role_arn = (
                        f"arn:aws:iam::{account}:role/{aws_organizations_role_name}"
                    )
                    log_data["org_role_arn"] = "org_role_arn"
                    try:
                        # TODO: SpokeRoles, by default, do not have the ability to assume other roles
                        # To automatically onboard a new account, we have to grant the Spoke role this capability
                        # temporarily then wait for the permission to propagate. THIS NEEDS TO BE DOCUMENTED
                        # and we need a finally statement to ensure we attempt to remove it.
                        # TODO: Inject retry and/or sleep
                        # TODO: Save somewhere that we know we attempted this account before, so no need to try again.
                        org_sts_client = boto3_cached_conn(
                            "sts",
                            tenant,
                            None,
                            region=config.region,
                            assume_role=spoke_role_name,
                            account_number=org_account.account_id,
                            session_name="noq_onboard_new_accounts_from_orgs",
                        )

                        # Use the spoke role on the org management account to assume into the org role on the
                        # new (unknown) account
                        new_account_credentials = await aio_wrapper(
                            org_sts_client.assume_role,
                            RoleArn=org_role_arn,
                            RoleSessionName="noq_onboard_new_accounts_from_orgs",
                        )

                        new_account_cf_client = await aio_wrapper(
                            boto3.client,
                            "cloudformation",
                            aws_access_key_id=new_account_credentials["Credentials"][
                                "AccessKeyId"
                            ],
                            aws_secret_access_key=new_account_credentials[
                                "Credentials"
                            ]["SecretAccessKey"],
                            aws_session_token=new_account_credentials["Credentials"][
                                "SessionToken"
                            ],
                            region_name=config.region,
                        )

                        # Onboard the account.
                        spoke_stack_name = config.get(
                            "_global_.integrations.aws.spoke_role_name",
                            "NoqSpokeRole",
                        )
                        spoke_role_template_url = config.get(
                            "_global_.integrations.aws.registration_spoke_role_cf_template",
                            "https://s3.us-east-1.amazonaws.com/cloudumi-cf-templates/cloudumi_spoke_role.yaml",
                        )
                        spoke_roles = spoke_accounts.models
                        external_id = config.get_tenant_specific_key(
                            "tenant_details.external_id", tenant
                        )
                        if not external_id:
                            log.error({**log_data, "error": "External ID not found"})
                            continue
                        cluster_role = config.get("_global_.integrations.aws.node_role")
                        if not cluster_role:
                            log.error({**log_data, "error": "Cluster role not found"})
                            continue
                        if spoke_roles:
                            spoke_role_name = spoke_roles[0].name
                            spoke_stack_name = spoke_role_name
                        else:
                            spoke_role_name = config.get(
                                "_global_.integrations.aws.spoke_role_name",
                                "NoqSpokeRole",
                            )
                        hub_account = (
                            ModelAdapter(HubAccount)
                            .load_config("hub_account", tenant)
                            .model
                        )
                        customer_central_account_role = hub_account.role_arn

                        region = config.get(
                            "_global_.integrations.aws.region", "us-west-2"
                        )
                        account_id = config.get("_global_.integrations.aws.account_id")
                        cluster_id = config.get("_global_.deployment.cluster_id")
                        registration_topic_arn = config.get(
                            "_global_.integrations.aws.registration_topic_arn",
                            f"arn:aws:sns:{region}:{account_id}:{cluster_id}-registration-topic",
                        )
                        spoke_role_parameters = [
                            {
                                "ParameterKey": "ExternalIDParameter",
                                "ParameterValue": external_id,
                            },
                            {
                                "ParameterKey": "CentralRoleArnParameter",
                                "ParameterValue": customer_central_account_role,
                            },
                            {
                                "ParameterKey": "HostParameter",
                                "ParameterValue": tenant,
                            },
                            {
                                "ParameterKey": "SpokeRoleNameParameter",
                                "ParameterValue": spoke_role_name,
                            },
                            {
                                "ParameterKey": "RegistrationTopicArnParameter",
                                "ParameterValue": registration_topic_arn,
                            },
                        ]
                        response = new_account_cf_client.create_stack(
                            StackName=spoke_stack_name,
                            TemplateURL=spoke_role_template_url,
                            Parameters=spoke_role_parameters,
                            Capabilities=[
                                "CAPABILITY_NAMED_IAM",
                            ],
                        )
                        log.debug(
                            {
                                "message": "Account onboarded successfully.",
                                "stack_id": response["StackId"],
                                **log_data,
                            }
                        )
                        new_accounts_onboarded.append(account)
                        break
                    except Exception as e:
                        log.error({"error": str(e), **log_data}, exc_info=True)
                        sentry_sdk.capture_exception()

                if account not in new_accounts_onboarded:
                    # If the account wasn't onboarded it failed so exclude it.
                    new_accounts_excluded.append(account)
        except Exception as e:
            log.error(
                {
                    "error": f"Unable to retrieve roles from AWS Organizations: {e}",
                    **log_data,
                },
                exc_info=True,
            )
            sentry_sdk.capture_exception()

        if new_accounts_excluded:
            # Extend excluded accounts if already set otherwise set it
            if not org_account.accounts_excluded_from_automatic_onboard:
                org_account.accounts_excluded_from_automatic_onboard = (
                    new_accounts_excluded
                )
            else:
                org_account.accounts_excluded_from_automatic_onboard.extend(
                    new_accounts_excluded
                )

            # Update the org account with the new accounts excluded from auto onboard
            await ModelAdapter(
                OrgAccount, "onboard_new_accounts_from_orgs"
            ).load_config("org_accounts", tenant).from_model(
                org_account
            ).with_object_key(
                ["org_id"]
            ).store_item_in_list()

        return new_accounts_onboarded
