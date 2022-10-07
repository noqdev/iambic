import os
from datetime import datetime, timedelta

from noq_form.aws.iam.policy.models import AssumeRolePolicyDocument, ManagedPolicy
from noq_form.aws.iam.role.models import MultiAccountRoleTemplate, RoleAccess
from noq_form.core.models import Tag
from noq_form.core.utils import yaml

file_path = str(os.path.join(os.path.dirname(__file__), "admin_role.yaml"))

admin_role = MultiAccountRoleTemplate(
    role_name="Noqform_{{account_name}}_admin",
    enabled=True,
    description="Noq Admin Role",
    owner="noq_admins@noq.dev",
    file_path=file_path,
    managed_policies=[
        ManagedPolicy(policy_arn="arn:aws:iam::aws:policy/AdministratorAccess")
    ],
    role_access=[
        RoleAccess(groups=["engineering@noq.dev"], excluded_accounts=["prod*"]),
        RoleAccess(
            users=["curtis@noq.dev", "matt@noq.dev", "will@noq.dev"],
            included_accounts=["prod*"],
            expires_at=datetime.utcnow() - timedelta(weeks=1),
        ),
    ],
    tags=[Tag(key="owner", value="{{ owner }}")],
    assume_role_policy_document=AssumeRolePolicyDocument(
        **{
            "version": "2012-10-17",
            "statement": [
                {
                    "effect": "Allow",
                    "principal": {
                        "AWS": "arn:aws:iam::940552945933:role/NoqCentralRoleCorpNoqDev"
                    },
                    "action": ["sts:AssumeRole", "sts:TagSession"],
                },
                {
                    "effect": "Allow",
                    "principal": {
                        "AWS": "arn:aws:iam::759357822767:role/NoqCentralRoleLocalDev"
                    },
                    "action": ["sts:AssumeRole", "sts:TagSession"],
                },
                {
                    "Sid": "noqcurtis1651181313tunb",
                    "effect": "Allow",
                    "principal": {"AWS": "arn:aws:iam::940552945933:role/prod_admin"},
                    "action": ["sts:TagSession", "sts:AssumeRole"],
                },
                {
                    "effect": "Allow",
                    "principal": {
                        "AWS": "arn:aws:iam::259868150464:role/NoqCentralRoleStaging"
                    },
                    "action": ["sts:AssumeRole", "sts:TagSession"],
                },
            ],
        }
    ),
)

with open(file_path, "w") as f:
    f.write(yaml.dump(admin_role.dict(exclude_none=True, exclude_unset=True)))
