from pydantic import BaseModel as PydanticBaseModel


class AWSSSOInstance(PydanticBaseModel):
    arn: str
    region: str
    access_portal_url: str
    identity_store_id: str


class AWSSSOPermissionSetBasic(PydanticBaseModel):
    arn: str
    name: str
