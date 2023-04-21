from __future__ import annotations

import asyncio
import os.path
from itertools import chain
from typing import TYPE_CHECKING, Any, List, Optional

from pydantic import Field, validator

from iambic.core.context import ctx
from iambic.core.iambic_enum import Command, IambicManaged
from iambic.core.logger import log
from iambic.core.models import (
    AccountChangeDetails,
    BaseModel,
    BaseTemplate,
    ExpiryModel,
    TemplateChangeDetails,
)
from iambic.core.utils import NoqSemaphore
from iambic.plugins.v0_1_0.okta.app.utils import (
    get_app,
    maybe_delete_app,
    update_app_assignments,
    update_app_name,
)
from iambic.plugins.v0_1_0.okta.models import App, Assignment, Status

if TYPE_CHECKING:
    from iambic.plugins.v0_1_0.okta.iambic_plugin import OktaConfig, OktaOrganization

OKTA_GET_APP_SEMAPHORE = NoqSemaphore(get_app, 10)
OKTA_APP_TEMPLATE_TYPE = "NOQ::Okta::App"


class AppProperties(ExpiryModel, BaseModel):
    name: str = Field(..., description="Name of the app")
    status: Optional[Status] = Field(None, description="Status of the app")
    id: Optional[str] = Field(
        None, description="Unique App ID for the app. Usually it's {idp-name}-{name}"
    )
    file_path: str = Field(
        "",
        description="Path to the template file",
        exclude=True,
        hidden_from_schema=True,
    )
    description: Optional[str] = Field("", description="Description of the app")
    extra: Any = Field(None, description=("Extra attributes to store"))
    created: Optional[str] = Field("", description="Date the app was created")
    assignments: List[Assignment] = Field([], description="List of assignments")

    @property
    def resource_type(self) -> str:
        return "okta:app"

    @property
    def resource_id(self) -> str:
        return self.id

    @validator("assignments")
    def sort_groups(cls, v: list[Assignment]):
        sorted_v = sorted(v, key=lambda assignment: assignment.resource_id)
        return sorted_v


class OktaAppTemplate(BaseTemplate, ExpiryModel):
    template_type = OKTA_APP_TEMPLATE_TYPE
    properties: AppProperties = Field(..., description="Properties for the Okta App")
    owner: Optional[str] = Field(None, description="Owner of the app")
    idp_name: str = Field(
        ...,
        description="Name of the identity provider that's associated with the group",
    )

    async def apply(self, config: OktaConfig) -> TemplateChangeDetails:
        tasks = []
        template_changes = TemplateChangeDetails(
            resource_id=self.properties.id,
            resource_type=self.template_type,
            template_path=self.file_path,
        )
        log_params = dict(
            resource_type=self.resource_type,
            resource_name=self.properties.name,
        )

        if self.iambic_managed == IambicManaged.IMPORT_ONLY:
            log_str = "Resource is marked as import only."
            log.info(log_str, **log_params)
            template_changes.proposed_changes = []
            return template_changes

        for okta_organization in config.organizations:
            if self.idp_name != okta_organization.idp_name:
                continue
            if ctx.execute:
                log_str = "Applying changes to resource."
            else:
                log_str = "Detecting changes for resource."
            log.info(log_str, idp_name=okta_organization.idp_name, **log_params)
            tasks.append(self._apply_to_account(okta_organization))

        account_changes = await asyncio.gather(*tasks)
        template_changes.proposed_changes = [
            account_change
            for account_change in account_changes
            if any(account_change.proposed_changes)
        ]

        proposed_changes = [x for x in account_changes if x.proposed_changes]

        if proposed_changes and ctx.execute:
            log.info(
                "Successfully applied all or some resource changes to all Okta organizations. Any unapplied resources will have an accompanying error message.",
                **log_params,
            )
        elif proposed_changes:
            log.info(
                "Successfully detected all or some required resource changes on all Okta organizations. Any unapplied resources will have an accompanying error message.",
                **log_params,
            )
        else:
            log.debug("No changes detected for resource on any account.", **log_params)

        return template_changes

    @property
    def resource_id(self) -> str:
        return self.properties.id

    @property
    def resource_type(self) -> str:
        return "okta:app"

    def set_default_file_path(self, repo_dir: str):
        file_name = f"{self.properties.name}.yaml"
        self.file_path = os.path.expanduser(
            os.path.join(repo_dir, f"resources/okta/app/{self.idp_name}/{file_name}")
        )

    def apply_resource_dict(
        self,
        okta_organization: OktaOrganization,
    ):
        return {
            "name": self.properties.name,
            "owner": self.owner,
            "status": self.properties.status,
            "idp_name": self.idp_name,
            "description": self.properties.description,
            "extra": self.properties.extra,
            "created": self.properties.created,
            "assignments": self.properties.assignments,
        }

    async def _apply_to_account(
        self,
        okta_organization: OktaOrganization,
    ) -> AccountChangeDetails:
        proposed_app = self.apply_resource_dict(okta_organization)
        change_details = AccountChangeDetails(
            account=self.idp_name,
            resource_id=self.properties.id,
            resource_type=self.properties.resource_type,
            new_value=proposed_app,
            proposed_changes=[],
        )

        log_params = dict(
            resource_type=self.properties.resource_type,
            resource_id=self.properties.name,
            organization=str(self.idp_name),
        )

        current_app_task = await OKTA_GET_APP_SEMAPHORE.process(
            [{"okta_organization": okta_organization, "app_id": self.properties.id}]
        )

        current_app: Optional[App] = current_app_task[0]
        if current_app:
            change_details.current_value = current_app

            if ctx.command == Command.CONFIG_DISCOVERY:
                # Don't overwrite a resource during config discovery
                change_details.new_value = {}
                return change_details

        app_exists = bool(current_app)
        tasks = []

        if not app_exists and not self.deleted:
            log.error(
                "Iambic does not support creating new apps. "
                "Please create the app in Okta and then import it.",
                **log_params,
            )
            return change_details

        if self.deleted:
            log.info(
                "App is marked for deletion. Please delete manually in Okta",
                **log_params,
            )
            return change_details

        tasks.extend(
            [
                update_app_name(
                    current_app,
                    self.properties.name,
                    okta_organization,
                    log_params,
                ),
                update_app_assignments(
                    current_app,
                    [
                        assignment
                        for assignment in self.properties.assignments
                        if not assignment.deleted
                    ],
                    okta_organization,
                    log_params,
                ),
                maybe_delete_app(
                    self.deleted,
                    current_app,
                    okta_organization,
                    log_params,
                ),
            ]
        )

        changes_made = await asyncio.gather(*tasks)
        if any(changes_made):
            change_details.extend_changes(list(chain.from_iterable(changes_made)))

        if ctx.execute:
            log.debug(
                "Successfully finished execution for resource",
                changes_made=bool(change_details.proposed_changes),
                **log_params,
            )
            # TODO: Check if deleted, remove git commit the change to ratify it
            if self.deleted:
                self.delete()
            self.write()
        else:
            log.debug(
                "Successfully finished scanning for drift for resource",
                requires_changes=bool(change_details.proposed_changes),
                **log_params,
            )

        return change_details


async def get_app_template(okta_app) -> OktaAppTemplate:
    """Get a template for an app"""
    file_name = f"{okta_app.name}.yaml"
    app = OktaAppTemplate(
        file_path=f"resources/okta/apps/{okta_app.idp_name}/{file_name}",
        template_type="NOQ::Okta::App",
        idp_name=okta_app.idp_name,
        properties=AppProperties(
            name=okta_app.name,
            status=okta_app.status,
            id=okta_app.id,
            file_path="{}.yaml".format(okta_app.name),
            assignments=okta_app.assignments,
        ),
    )
    return app
