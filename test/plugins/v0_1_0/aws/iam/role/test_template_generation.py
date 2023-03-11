from __future__ import annotations

from iambic.plugins.v0_1_0.aws.iam.role.models import RoleProperties, RoleTemplate
from iambic.plugins.v0_1_0.aws.iam.role.template_generation import (
    calculate_import_preference,
)


def test_calculate_import_preference():
    template = RoleTemplate(
        file_path="foo", identifier="foo", properties=RoleProperties(role_name="foo")
    )
    templatized_preferrence = calculate_import_preference(template)
    assert templatized_preferrence is False  # because we are not using variables

    template = RoleTemplate(
        file_path="foo",
        identifier="{{account_name}} admin",
        properties=RoleProperties(role_name="{{account_name}} admin"),
    )
    templatized_preferrence = calculate_import_preference(template)
    assert templatized_preferrence is True  # because we are using variables

    template = RoleTemplate(
        file_path="foo",
        identifier="{{account_name}} admin",
        properties=RoleProperties(role_name="{{account_name}} admin"),
    )
    # break template
    template.properties.description = lambda x: x  # lambda is not json-able
    templatized_preferrence = calculate_import_preference(template)
    assert templatized_preferrence is False  # because template preference crashed.
