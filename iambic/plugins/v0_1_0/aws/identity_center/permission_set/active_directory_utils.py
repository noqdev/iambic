from __future__ import annotations

import socket

import aiohttp
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

from iambic.core import noq_json


async def alternate_list_users(session, directory_id, region):
    domain = choose_up_sso_domain(region)
    url = f"https://{domain}/identitystore/"

    payload = {"IdentityStoreId": directory_id, "MaxResults": 100}
    data = noq_json.dumps(payload)

    sigv4 = SigV4Auth(session.get_credentials(), "identitystore", region)

    headers = {
        "Content-Type": "application/x-amz-json-1.1",
        "X-Amz-Target": "AWSIdentityStoreService.SearchUsers",
    }
    request = AWSRequest(method="POST", url=url, data=data, headers=headers)
    request.context["payload_signing_enabled"] = True
    sigv4.add_auth(request)

    prepped = request.prepare()
    text = None
    total_users = []

    async with aiohttp.ClientSession(headers=headers) as aiohttp_session:
        async with aiohttp_session.post(
            prepped.url, headers=prepped.headers, data=data
        ) as r:
            text = await r.text()

        # necessary because the response header is not regular json
        id_resp = noq_json.loads(text)
        total_users.extend(id_resp["Users"])

        while "NextToken" in id_resp:
            payload["NextToken"] = id_resp["NextToken"]
            data = noq_json.dumps(payload)
            request = AWSRequest(method="POST", url=url, data=data, headers=headers)
            request.context["payload_signing_enabled"] = True
            sigv4.add_auth(request)

            prepped = request.prepare()
            async with aiohttp_session.post(
                prepped.url, headers=prepped.headers, data=data
            ) as r:
                text = await r.text
                id_resp = noq_json.loads(text)

            total_users.extend(id_resp["Users"])

    # for compatibility for list_users
    for user in total_users:
        if (
            user.get("user_attributes", {})
            .get("display_name", {})
            .get("string_value", None)
        ):
            user["display_name"] = user["user_attributes"]["display_name"][
                "string_value"
            ]
        else:
            user["display_name"] = "ERROR UNABLE TO DECODE, CONTACT DEVELOPERS"

    return {"Users": total_users}


# Unfortunately, the up.sso domain is not consistent. some region use up.sso
# while others use up-sso. That's the fate of undocumented API
def choose_up_sso_domain(region):
    domain = f"up.sso.{region}.amazonaws.com"
    try:
        ip_list = list({addr[-1][0] for addr in socket.getaddrinfo(domain, 0, 0, 0, 0)})
    except socket.gaierror:
        domain = f"up-sso.{region}.amazonaws.com"
        try:
            ip_list = list(
                {addr[-1][0] for addr in socket.getaddrinfo(domain, 0, 0, 0, 0)}
            )
            assert ip_list
        except socket.gaierror:
            raise
    return domain


async def alternate_list_groups(session, directory_id, region):
    domain = choose_up_sso_domain(region)
    url = f"https://{domain}/identitystore/"
    payload = {"IdentityStoreId": directory_id, "MaxResults": 100}
    data = noq_json.dumps(payload)

    sigv4 = SigV4Auth(session.get_credentials(), "identitystore", region)

    headers = {
        "Content-Type": "application/x-amz-json-1.1",
        "X-Amz-Target": "AWSIdentityStoreService.SearchGroups",
    }
    request = AWSRequest(method="POST", url=url, data=data, headers=headers)
    request.context["payload_signing_enabled"] = True
    sigv4.add_auth(request)

    prepped = request.prepare()
    # response = requests.post(prepped.url, headers=prepped.headers, data=data)
    text = None
    total_groups = []

    async with aiohttp.ClientSession(headers=headers) as aiohttp_session:
        async with aiohttp_session.post(
            prepped.url, headers=prepped.headers, data=data
        ) as r:
            text = await r.text()

        id_resp = noq_json.loads(text)
        total_groups.extend(id_resp["Groups"])

        while "NextToken" in id_resp:
            payload["NextToken"] = id_resp["NextToken"]
            data = noq_json.dumps(payload)
            request = AWSRequest(method="POST", url=url, data=data, headers=headers)
            request.context["payload_signing_enabled"] = True
            sigv4.add_auth(request)

            prepped = request.prepare()
            async with aiohttp_session.post(
                prepped.url, headers=prepped.headers, data=data
            ) as r:
                text = await r.text
                id_resp = noq_json.loads(text)
                total_groups.extend(id_resp["Groups"])

    # for compatibility for list_groups
    for group in total_groups:
        if group.get("DisplayName", None):
            group["display_name"] = group["DisplayName"]
        else:
            group["display_name"] = "ERROR UNABLE TO DECODE, CONTACT DEVELOPERS"

    return {"Groups": total_groups}
