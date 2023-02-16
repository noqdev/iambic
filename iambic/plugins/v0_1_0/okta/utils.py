from __future__ import annotations

import asyncio
import json

import okta.models as models
from okta.errors.okta_api_error import OktaAPIError

from iambic.core.exceptions import RateLimitException
from iambic.plugins.v0_1_0.okta.exceptions import UserProfileNotUpdatableYet


async def generate_user_profile(user: models.User):
    """
    Generates a key-value pair of user profile attributes that aren't None.
    This is useful to keep user templates small.
    """
    return {k: v for (k, v) in user.profile.__dict__.items() if v is not None}


async def handle_okta_fn(fn, *args, **kwargs):
    try:
        res = await fn(*args, **kwargs)
    except asyncio.exceptions.TimeoutError:
        raise asyncio.exceptions.TimeoutError

    err = res[-1]
    if err:
        if isinstance(err, Exception):
            raise err
        # Handle the case where Okta SDK returns appropriately scoped OktaAPIError
        if isinstance(err, OktaAPIError):
            if err.error_code == "E0000047":
                raise RateLimitException(err.error_summary)
            if err.error_code == "E0000112":
                raise UserProfileNotUpdatableYet(
                    "Unable to update profile, user is not fully provisioned"
                )
            return res

        # Handle the case where Okta SDK returns JSON
        try:
            err_j = json.loads(err)
            if err_j.get("errorCode") == "E0000047":
                raise RateLimitException(err)
        except TypeError:
            pass
    return res
