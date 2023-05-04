from __future__ import annotations

import pytest

from iambic.plugins.v0_1_0.aws.event_bridge.models import SCPMessageDetails


class TestSCPMessageDetails:
    @pytest.mark.parametrize(
        "resource, org, value",
        [
            ("TagResource", "organizations.amazonaws.com", True),
            ("UntagResource", "organizations.amazonaws.com", True),
            ("TagResource", "otherservice.amazonaws.com", False),
            ("UntagResource", "otherservice.amazonaws.com", False),
            ("OtherOperation", "organizations.amazonaws.com", False),
        ],
    )
    def test_tag_event(self, resource, org, value):
        assert SCPMessageDetails.tag_event(resource, org) == value

    @pytest.mark.parametrize(
        "request_params, response_elements, value",
        [
            ({"policyId": "foo"}, None, "foo"),
            (None, {"policy": {"policySummary": {"id": "bar"}}}, "bar"),
            (None, None, None),
        ],
    )
    def test_get_policy_id(self, request_params, response_elements, value):
        assert (
            SCPMessageDetails.get_policy_id(request_params, response_elements) == value
        )
