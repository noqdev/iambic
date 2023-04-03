import uuid
from typing import Union
from unittest import mock

import pytest
from aiohttp import ClientResponse
from aiohttp.helpers import TimerNoop
from yarl import URL

from iambic.plugins.v0_1_0.azure_ad.models import AzureADOrganization


class MockAzureADOrganization(AzureADOrganization):
    request_data = {"users": {}, "groups": {}}

    async def _make_request(  # noqa: C901
        self, request_type: str, endpoint: str, **kwargs
    ) -> Union[dict, list, None]:
        ref_keys = {"members"}
        response = ClientResponse(
            request_type,
            URL(f"https://graph.microsoft.com/v1.0/{endpoint}"),
            request_info=mock.Mock(),
            writer=mock.Mock(),
            continue100=None,
            timer=TimerNoop(),
            traces=[],
            loop=mock.Mock(),
            session=mock.Mock(),
        )
        split_endpoint = endpoint.split("/")
        if split_endpoint[0] not in list(self.request_data.keys()):
            response.status = 404
            response.message = "Not Found"
            response.reason = "Not Found"
            response.raise_for_status()

        if request_type not in {"post", "list", "delete"}:
            remote_obj = self.request_data[split_endpoint[0]].get(split_endpoint[1])
            if not remote_obj:
                response.status = 404
                response.message = "Not Found"
                response.reason = "Not Found"
                response.raise_for_status()

            # Strip ref keys from response
            remote_obj = dict(**remote_obj)
            for ref_key in ref_keys:
                remote_obj.pop(ref_key, None)

            if request_type == "get":
                return remote_obj
            elif request_type == "patch":
                remote_obj.update(kwargs["json"])
                self.request_data[split_endpoint[0]][split_endpoint[1]] = remote_obj
                return remote_obj
        elif request_type == "post":
            if len(split_endpoint) > 2:
                try:
                    if split_endpoint[2] == "members":
                        member_id = kwargs["json"]["@odata.id"].split("/")[-1]
                        cur_members = [
                            member["id"]
                            for member in self.request_data[split_endpoint[0]][
                                split_endpoint[1]
                            ]["members"]
                        ]
                        if member_id in cur_members:
                            raise Exception

                        if member_info := self.request_data["users"].get(member_id):
                            data_type = "user"
                        elif member_info := self.request_data["groups"].get(member_id):
                            data_type = "group"
                        else:
                            response.status = 400
                            response.message = "Member not found"
                            response.reason = "Member not found"
                            response.raise_for_status()

                        self.request_data[split_endpoint[0]][split_endpoint[1]][
                            "members"
                        ].append(
                            {
                                "id": member_id,
                                "@odata.type": f"#microsoft.graph.{data_type}",
                                **member_info,
                            }
                        )
                except Exception as err:
                    response.status = 400
                    response.message = repr(err)
                    response.reason = repr(err)
                    response.raise_for_status()
            else:
                kwargs["json"]["id"] = str(uuid.uuid4())
                if split_endpoint[0] == "groups":
                    kwargs["json"]["members"] = []

                self.request_data[split_endpoint[0]][kwargs["json"]["id"]] = kwargs[
                    "json"
                ]
                return {k: v for k, v in kwargs["json"].items() if k not in ref_keys}

        elif request_type == "list":
            all_objs = list(
                dict(**v) for v in self.request_data[split_endpoint[0]].values()
            )
            for elem, obj in enumerate(all_objs):
                for ref_key in ref_keys:
                    obj.pop(ref_key, None)
                    all_objs[elem] = obj

            if params := kwargs.get("params"):
                if split_filter := params.get("$filter", "").split(" "):
                    field_attr = split_filter[0]
                    field_val = " ".join(split_filter[2:])
                    field_val = field_val.replace("'", "")
                    return [obj for obj in all_objs if obj[field_attr] == field_val]
                else:
                    response.status = 400
                    response.message = "Invalid params"
                    response.reason = "Invalid params"
                    response.raise_for_status()
            elif len(split_endpoint) == 1:
                return all_objs
            elif len(split_endpoint) == 3:
                return (
                    self.request_data[split_endpoint[0]]
                    .get(split_endpoint[1], {})
                    .get(split_endpoint[2], [])
                )

        elif request_type == "delete":
            try:
                if len(split_endpoint) > 2:
                    if split_endpoint[2] == "members":
                        member_id = split_endpoint[3]
                        cur_members = [
                            member["id"]
                            for member in self.request_data[split_endpoint[0]][
                                split_endpoint[1]
                            ]["members"]
                        ]
                        if member_id not in cur_members:
                            raise Exception
                        self.request_data[split_endpoint[0]][split_endpoint[1]][
                            "members"
                        ] = [
                            member
                            for member in self.request_data[split_endpoint[0]][
                                split_endpoint[1]
                            ]["members"]
                            if member["id"] != member_id
                        ]
                else:
                    assert self.request_data[split_endpoint[0]].get(split_endpoint[1])
                    del self.request_data[split_endpoint[0]][split_endpoint[1]]
            except Exception as err:
                response.status = 400
                response.message = repr(err)
                response.reason = repr(err)
                response.raise_for_status()


# Fixture for AzureADOrganization
@pytest.fixture
def azure_ad_organization() -> AzureADOrganization:
    org = MockAzureADOrganization(
        idp_name="unittest",
        client_id="client_id",
        client_secret="client_secret",
        tenant_id="tenant_id",
    )
    return org
