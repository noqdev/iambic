from __future__ import annotations

from enum import Enum
from typing import Any, List, Optional

from iambic.core.models import BaseModel, ExpiryModel
from iambic.core.utils import normalize_dict_keys
from pydantic import Field


class UserStatus(Enum):
    active = "active"
    provisioned = "provisioned"
    deprovisioned = "deprovisioned"


class UserSimple(BaseModel, ExpiryModel):
    username: str
    status: Optional[UserStatus] = UserStatus.active

    @property
    def resource_type(self) -> str:
        return "azure_ad:user"

    @property
    def resource_id(self) -> str:
        return self.username


class UserTemplateProperties(BaseModel, ExpiryModel):
    username: str
    user_id: Optional[str]
    domain: Optional[str]
    fullname: Optional[str]
    status: Optional[UserStatus]
    created: Optional[str]
    updated: Optional[str]
    groups: Optional[List[str]]
    extra: Any = Field(None, description=("Extra attributes to store"))
    profile: dict[str, Any]

    @property
    def resource_type(self) -> str:
        return "azure_ad:user"

    @property
    def resource_id(self) -> str:
        return self.username

    @classmethod
    def from_azure_response(cls, azure_response: dict) -> UserTemplateProperties:
        azure_response = normalize_dict_keys(azure_response)
        return cls(
            user_id=azure_response.get("id"),
            username=azure_response.get("user_principal_name"),
            profile={
                "display_name": azure_response.get("display_name"),
                "given_name": azure_response.get("given_name"),
                "surname": azure_response.get("surname"),
                "mail": azure_response.get("mail"),
            },
        )
