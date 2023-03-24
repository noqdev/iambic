from __future__ import annotations

from pydantic_factories import Ignore, ModelFactory

from iambic.plugins.v0_1_0.aws.iam.policy import models as policy_models
from iambic.plugins.v0_1_0.aws.iam.role.models import AwsIamRoleTemplate


class AssumeRolePolicyDocumentFactory(ModelFactory):
    __model__ = policy_models.AssumeRolePolicyDocument


class PolicyDocumentFactory(ModelFactory):
    __model__ = policy_models.PolicyDocument


class RoleFactory(ModelFactory):
    __model__ = AwsIamRoleTemplate

    deleted = Ignore()
    included_orgs = Ignore()
    excluded_orgs = Ignore()
