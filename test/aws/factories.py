from random import choice

from pydantic_factories import Ignore, ModelFactory, Use

from iambic.aws.iam.role.models import RoleTemplate
from iambic.aws.iam.policy import models as policy_models


class AssumeRolePolicyDocumentFactory(ModelFactory):
    __model__ = policy_models.AssumeRolePolicyDocument


class PolicyDocumentFactory(ModelFactory):
    __model__ = policy_models.PolicyDocument


class RoleFactory(ModelFactory):
    __model__ = RoleTemplate

    deleted = Ignore()
    included_orgs = Ignore()
    excluded_orgs = Ignore()

