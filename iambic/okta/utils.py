from __future__ import annotations

import okta.models as models


async def generate_user_profile(user: models.User):
    """
    Generates a key-value pair of user profile attributes that aren't None.
    This is useful to keep user templates small.
    """
    return {k: v for (k, v) in user.profile.__dict__.items() if v is not None}
