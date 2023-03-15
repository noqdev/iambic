from __future__ import annotations

import pytest
from iambic.core.models import TemplateChangeDetails
from iambic.core.utils import yaml
from iambic.output.markdown import (
    ActionSummaries,
    get_template_data,
    gh_render_resource_changes,
)

template_yaml = """  - resource_id: prod_iambic_test_role
    resource_type: aws:iam:role
    template_path: resources/aws/iam/role/design-prod/iambic_test_role_prod.yaml
    proposed_changes:
      - account: design-prod - (006933239187)
        resource_id: prod_iambic_test_role
        new_value:
          RoleName: prod_iambic_test_role
          Description: IAMbic test role on design-prod
          MaxSessionDuration: 3600
          Path: /iambic_test/
          Tags: []
          ManagedPolicies:
            - PolicyArn: arn:aws:iam::aws:policy/job-function/ViewOnlyAccess
          InlinePolicies:
            - PolicyName: spoke-acct-policy
              Statement:
                - Effect: Deny
                  Action:
                    - s3:ListBucket
                  Resource: '*'
                - Effect: Deny
                  Action:
                    - s3:GetObject
                  Resource: '*'
                - Effect: Deny
                  Action:
                    - s3:ListAllMyBuckets
                  Resource: '*'
          AssumeRolePolicyDocument:
            Version: '2008-10-17'
            Statement:
              - Effect: Deny
                Principal:
                  Service: ec2.amazonaws.com
                Action: sts:AssumeRole
          PermissionsBoundary:
            PolicyArn: arn:aws:iam::aws:policy/AWSDirectConnectReadOnlyAccess
        proposed_changes:
          - change_type: Create
            resource_id: prod_iambic_test_role
            resource_type: aws:iam:role
        exceptions_seen: []
    exceptions_seen: []
  - resource_id: '{{account_name}}_iambic_test_role'
    resource_type: aws:iam:role
    template_path: resources/aws/iam/role/all_accounts/iambic_test_role.yaml
    proposed_changes:
      - account: product-dev - (572565049541)
        resource_id: product-dev_iambic_test_role
        new_value:
          RoleName: product-dev_iambic_test_role
          Description: IAMbic test role on product-dev
          MaxSessionDuration: 3600
          Path: /iambic_test/
          Tags: []
          ManagedPolicies:
            - PolicyArn: arn:aws:iam::aws:policy/job-function/ViewOnlyAccess
          InlinePolicies:
            - PolicyName: spoke-acct-policy
              Statement:
                - Effect: Deny
                  Action:
                    - s3:ListBucket
                  Resource: '*'
                - Effect: Deny
                  Action:
                    - s3:ListAllMyBuckets
                  Resource: '*'
          AssumeRolePolicyDocument:
            Version: '2008-10-17'
            Statement:
              - Effect: Deny
                Principal:
                  Service: ec2.amazonaws.com
                Action: sts:AssumeRole
          PermissionsBoundary:
            PolicyArn: arn:aws:iam::aws:policy/AWSDirectConnectReadOnlyAccess
        proposed_changes:
          - change_type: Create
            resource_id: product-dev_iambic_test_role
            resource_type: aws:iam:role
        exceptions_seen: []
      - account: Iambic Standalone Org - (566255053759)
        resource_id: IambicStandaloneOrg_iambic_test_role
        new_value:
          RoleName: IambicStandaloneOrg_iambic_test_role
          Description: IAMbic test role on IambicStandaloneOrg
          MaxSessionDuration: 3600
          Path: /iambic_test/
          Tags: []
          ManagedPolicies:
            - PolicyArn: arn:aws:iam::aws:policy/job-function/ViewOnlyAccess
          InlinePolicies:
            - PolicyName: spoke-acct-policy
              Statement:
                - Effect: Deny
                  Action:
                    - s3:ListBucket
                  Resource: '*'
                - Effect: Deny
                  Action:
                    - s3:ListAllMyBuckets
                  Resource: '*'
          AssumeRolePolicyDocument:
            Version: '2008-10-17'
            Statement:
              - Effect: Deny
                Principal:
                  Service: ec2.amazonaws.com
                Action: sts:AssumeRole
          PermissionsBoundary:
            PolicyArn: arn:aws:iam::aws:policy/AWSDirectConnectReadOnlyAccess
        proposed_changes:
          - change_type: Create
            resource_id: IambicStandaloneOrg_iambic_test_role
            resource_type: aws:iam:role
        exceptions_seen: []
      - account: design-dev - (570737236821)
        resource_id: design-dev_iambic_test_role
        new_value:
          RoleName: design-dev_iambic_test_role
          Description: IAMbic test role on design-dev
          MaxSessionDuration: 3600
          Path: /iambic_test/
          Tags: []
          ManagedPolicies:
            - PolicyArn: arn:aws:iam::aws:policy/job-function/ViewOnlyAccess
          InlinePolicies:
            - PolicyName: spoke-acct-policy
              Statement:
                - Effect: Deny
                  Action:
                    - s3:ListBucket
                  Resource: '*'
                - Effect: Deny
                  Action:
                    - s3:ListAllMyBuckets
                  Resource: '*'
          AssumeRolePolicyDocument:
            Version: '2008-10-17'
            Statement:
              - Effect: Deny
                Principal:
                  Service: ec2.amazonaws.com
                Action: sts:AssumeRole
          PermissionsBoundary:
            PolicyArn: arn:aws:iam::aws:policy/AWSDirectConnectReadOnlyAccess
        proposed_changes:
          - change_type: Create
            resource_id: design-dev_iambic_test_role
            resource_type: aws:iam:role
        exceptions_seen: []
      - account: design-tools - (728312732489)
        resource_id: design-tools_iambic_test_role
        new_value:
          RoleName: design-tools_iambic_test_role
          Description: IAMbic test role on design-tools
          MaxSessionDuration: 3600
          Path: /iambic_test/
          Tags: []
          ManagedPolicies:
            - PolicyArn: arn:aws:iam::aws:policy/job-function/ViewOnlyAccess
          InlinePolicies:
            - PolicyName: spoke-acct-policy
              Statement:
                - Effect: Deny
                  Action:
                    - s3:ListBucket
                  Resource: '*'
                - Effect: Deny
                  Action:
                    - s3:ListAllMyBuckets
                  Resource: '*'
          AssumeRolePolicyDocument:
            Version: '2008-10-17'
            Statement:
              - Effect: Deny
                Principal:
                  Service: ec2.amazonaws.com
                Action: sts:AssumeRole
          PermissionsBoundary:
            PolicyArn: arn:aws:iam::aws:policy/AWSDirectConnectReadOnlyAccess
        proposed_changes:
          - change_type: Create
            resource_id: design-tools_iambic_test_role
            resource_type: aws:iam:role
        exceptions_seen: []
      - account: design-staging - (158048798909)
        resource_id: design-staging_iambic_test_role
        new_value:
          RoleName: design-staging_iambic_test_role
          Description: IAMbic test role on design-staging
          MaxSessionDuration: 3600
          Path: /iambic_test/
          Tags: []
          ManagedPolicies:
            - PolicyArn: arn:aws:iam::aws:policy/job-function/ViewOnlyAccess
          InlinePolicies:
            - PolicyName: spoke-acct-policy
              Statement:
                - Effect: Deny
                  Action:
                    - s3:ListBucket
                  Resource: '*'
                - Effect: Deny
                  Action:
                    - s3:ListAllMyBuckets
                  Resource: '*'
          AssumeRolePolicyDocument:
            Version: '2008-10-17'
            Statement:
              - Effect: Deny
                Principal:
                  Service: ec2.amazonaws.com
                Action: sts:AssumeRole
          PermissionsBoundary:
            PolicyArn: arn:aws:iam::aws:policy/AWSDirectConnectReadOnlyAccess
        proposed_changes:
          - change_type: Create
            resource_id: design-staging_iambic_test_role
            resource_type: aws:iam:role
        exceptions_seen: []
      - account: design-prod - (006933239187)
        resource_id: design-prod_iambic_test_role
        new_value:
          RoleName: design-prod_iambic_test_role
          Description: IAMbic test role on design-prod
          MaxSessionDuration: 3600
          Path: /iambic_test/
          Tags: []
          ManagedPolicies:
            - PolicyArn: arn:aws:iam::aws:policy/job-function/ViewOnlyAccess
          InlinePolicies:
            - PolicyName: spoke-acct-policy
              Statement:
                - Effect: Deny
                  Action:
                    - s3:ListBucket
                  Resource: '*'
                - Effect: Deny
                  Action:
                    - s3:ListAllMyBuckets
                  Resource: '*'
          AssumeRolePolicyDocument:
            Version: '2008-10-17'
            Statement:
              - Effect: Deny
                Principal:
                  Service: ec2.amazonaws.com
                Action: sts:AssumeRole
          PermissionsBoundary:
            PolicyArn: arn:aws:iam::aws:policy/AWSDirectConnectReadOnlyAccess
        proposed_changes:
          - change_type: Create
            resource_id: design-prod_iambic_test_role
            resource_type: aws:iam:role
        exceptions_seen: []
      - account: design-vpc - (172623945520)
        resource_id: design-vpc_iambic_test_role
        new_value:
          RoleName: design-vpc_iambic_test_role
          Description: IAMbic test role on design-vpc
          MaxSessionDuration: 3600
          Path: /iambic_test/
          Tags: []
          ManagedPolicies:
            - PolicyArn: arn:aws:iam::aws:policy/job-function/ViewOnlyAccess
          InlinePolicies:
            - PolicyName: spoke-acct-policy
              Statement:
                - Effect: Deny
                  Action:
                    - s3:ListBucket
                  Resource: '*'
                - Effect: Deny
                  Action:
                    - s3:ListAllMyBuckets
                  Resource: '*'
          AssumeRolePolicyDocument:
            Version: '2008-10-17'
            Statement:
              - Effect: Deny
                Principal:
                  Service: ec2.amazonaws.com
                Action: sts:AssumeRole
          PermissionsBoundary:
            PolicyArn: arn:aws:iam::aws:policy/AWSDirectConnectReadOnlyAccess
        proposed_changes:
          - change_type: Create
            resource_id: design-vpc_iambic_test_role
            resource_type: aws:iam:role
        exceptions_seen: []
      - account: design-workspaces - (667373557420)
        resource_id: design-workspaces_iambic_test_role
        new_value:
          RoleName: design-workspaces_iambic_test_role
          Description: IAMbic test role on design-workspaces
          MaxSessionDuration: 3600
          Path: /iambic_test/
          Tags: []
          ManagedPolicies:
            - PolicyArn: arn:aws:iam::aws:policy/job-function/ViewOnlyAccess
          InlinePolicies:
            - PolicyName: spoke-acct-policy
              Statement:
                - Effect: Deny
                  Action:
                    - s3:ListBucket
                  Resource: '*'
                - Effect: Deny
                  Action:
                    - s3:ListAllMyBuckets
                  Resource: '*'
          AssumeRolePolicyDocument:
            Version: '2008-10-17'
            Statement:
              - Effect: Deny
                Principal:
                  Service: ec2.amazonaws.com
                Action: sts:AssumeRole
          PermissionsBoundary:
            PolicyArn: arn:aws:iam::aws:policy/AWSDirectConnectReadOnlyAccess
        proposed_changes:
          - change_type: Create
            resource_id: design-workspaces_iambic_test_role
            resource_type: aws:iam:role
        exceptions_seen: []
      - account: design-test - (992251240124)
        resource_id: design-test_iambic_test_role
        new_value:
          RoleName: design-test_iambic_test_role
          Description: IAMbic test role on design-test
          MaxSessionDuration: 3600
          Path: /iambic_test/
          Tags: []
          ManagedPolicies:
            - PolicyArn: arn:aws:iam::aws:policy/job-function/ViewOnlyAccess
          InlinePolicies:
            - PolicyName: spoke-acct-policy
              Statement:
                - Effect: Deny
                  Action:
                    - s3:ListBucket
                  Resource: '*'
                - Effect: Deny
                  Action:
                    - s3:GetObject
                  Resource: '*'
          AssumeRolePolicyDocument:
            Version: '2008-10-17'
            Statement:
              - Effect: Deny
                Principal:
                  Service: ec2.amazonaws.com
                Action: sts:AssumeRole
          PermissionsBoundary:
            PolicyArn: arn:aws:iam::aws:policy/AWSDirectConnectReadOnlyAccess
        proposed_changes:
          - change_type: Create
            resource_id: design-test_iambic_test_role
            resource_type: aws:iam:role
        exceptions_seen: []
      - account: product-prod - (883466000970)
        resource_id: product-prod_iambic_test_role
        new_value:
          RoleName: product-prod_iambic_test_role
          Description: IAMbic test role on product-prod
          MaxSessionDuration: 3600
          Path: /iambic_test/
          Tags: []
          ManagedPolicies:
            - PolicyArn: arn:aws:iam::aws:policy/job-function/ViewOnlyAccess
          InlinePolicies:
            - PolicyName: spoke-acct-policy
              Statement:
                - Effect: Deny
                  Action:
                    - s3:ListBucket
                  Resource: '*'
                - Effect: Deny
                  Action:
                    - s3:ListAllMyBuckets
                  Resource: '*'
          AssumeRolePolicyDocument:
            Version: '2008-10-17'
            Statement:
              - Effect: Deny
                Principal:
                  Service: ec2.amazonaws.com
                Action: sts:AssumeRole
          PermissionsBoundary:
            PolicyArn: arn:aws:iam::aws:policy/AWSDirectConnectReadOnlyAccess
        proposed_changes:
          - change_type: Create
            resource_id: product-prod_iambic_test_role
            resource_type: aws:iam:role
        exceptions_seen: []
    exceptions_seen: []
"""


def get_templates_mixed():
    return [TemplateChangeDetails.parse_obj(x) for x in yaml.load(template_yaml)]


@pytest.mark.parametrize(
    "template_change_details, expected_output",
    [
        (
            get_templates_mixed(),
            ActionSummaries(num_accounts=10, num_actions=1, num_templates=2),
        ),
    ],
)
def test_get_template_data(
    template_change_details: list[TemplateChangeDetails],
    expected_output: ActionSummaries,
):
    template_data = get_template_data(template_change_details)
    assert template_data.num_accounts == expected_output.num_accounts
    assert template_data.num_actions == expected_output.num_actions
    assert template_data.num_templates == expected_output.num_templates


@pytest.mark.parametrize(
    "template_change_details, expected_output",
    [
        (
            get_templates_mixed(),
            ActionSummaries(num_accounts=10, num_actions=1, num_templates=2),
        ),
    ],
)
def test_gh_render_resource_changes(
    template_change_details: list[TemplateChangeDetails],
    expected_output: ActionSummaries,
):
    rendered_markdown = gh_render_resource_changes(template_change_details)
    import time

    with open(f"test_render_resource_changes-{time.time()}.md", "w") as f:
        f.write(rendered_markdown)
    assert rendered_markdown != ""
