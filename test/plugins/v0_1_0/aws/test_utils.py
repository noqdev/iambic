from __future__ import annotations

import pytest

from iambic.plugins.v0_1_0.aws.utils import get_identity_arn


@pytest.mark.parametrize(
    "caller_identity, expected_arn",
    [
        (
            {
                # simple user credentials
                "UserId": "AIDASAMPLEUSERID",
                "Account": "123456789012",
                "Arn": "arn:aws:iam::123456789012:user/DevAdmin",
            },
            "arn:aws:iam::123456789012:user/DevAdmin",
        ),
        (
            {
                # non-aws identity center role temp credentials
                "Account": "123456789012",
                "Arn": "arn:aws:sts::123456789012:assumed-role/my-role-name/my-role-session-name",
                "UserId": "AKIAI44QH8DHBEXAMPLE:my-role-session-name",
            },
            "arn:aws:iam::123456789012:role/my-role-name",
        ),
        (
            {
                # aws identity center role temp credentials
                "UserId": "fake-user-id:eample_user_1@example.com",
                "Account": "123456789012",
                "Arn": "arn:aws:sts::123456789012:assumed-role/AWSReservedSSO_AdministratorAccess_random_id/example_user_1@example.com",
            },
            "arn:aws:sts::123456789012:assumed-role/AWSReservedSSO_AdministratorAccess_random_id/example_user_1@example.com",
        ),
    ],
)
def test_get_identity_arn(caller_identity, expected_arn):
    arn = get_identity_arn(caller_identity)
    assert arn == expected_arn
