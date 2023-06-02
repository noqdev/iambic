from __future__ import annotations

from iambic.core.template import ConfigMixin
from iambic.plugins.v0_1_0.okta.app.models import OktaAppTemplate
from iambic.plugins.v0_1_0.okta.group.models import OktaGroupTemplate
from iambic.plugins.v0_1_0.okta.user.models import OktaUserTemplate


class OktaConfigMixin(ConfigMixin):
    templates = [
        OktaAppTemplate,
        OktaGroupTemplate,
        OktaUserTemplate,
    ]
