from __future__ import annotations

from pydantic_factories import Ignore, ModelFactory

from iambic.plugins.aws.iam.policy import models as policy_models
from iambic.plugins.aws.iam.role.models import RoleTemplate


class AssumeRolePolicyDocumentFactory(ModelFactory):
    __model__ = policy_models.AssumeRolePolicyDocument


class PolicyDocumentFactory(ModelFactory):
    __model__ = policy_models.PolicyDocument


class RoleFactory(ModelFactory):
    __model__ = RoleTemplate

    deleted = Ignore()
    included_orgs = Ignore()
    excluded_orgs = Ignore()
