from iambic.core.models import TemplateChangeDetails
from iambic.core.utils import yaml


update_template_yaml = """  - resource_id: t1000
    resource_type: aws:iam:role
    template_path: resources/aws/roles/demo-1/t1000.yaml
    proposed_changes:
      - account: demo-1 - (123456789012)
        resource_id: t1000
        current_value:
          Path: /
          RoleName: t1000
          RoleId: AROA6E2ETJ4MF7DDR6RK6
          Arn: arn:aws:iam::123456789012:role/t1000
          CreateDate: '2021-10-18T21:04:09+00:00'
          AssumeRolePolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Allow
                Principal:
                  AWS: arn:aws:iam::1234567890123:role/NoqCentralRole
                Action:
                  - sts:AssumeRole
                  - sts:TagSession
              - Effect: Allow
                Principal:
                  AWS: arn:aws:iam::940552945933:role/NoqCentralRoleCorpNoqDev
                Action:
                  - sts:AssumeRole
                  - sts:TagSession
          Description: Allows EC2 instances to call AWS services on your behalf.
          MaxSessionDuration: 3600
          Tags:
            - Key: noq-tra-active-users
              Value: ''
            - Key: noq-tra-supported-groups
              Value: engineering@noq.dev
            - Key: noq-authorized
              Value: engineering_group@noq.dev
          RoleLastUsed:
            LastUsedDate: '2023-01-27T22:37:21+00:00'
            Region: us-west-2
          ManagedPolicies: []
          InlinePolicies: []
        new_value:
          RoleName: t1000
          Description: Allows EC2 instances to call AWS services on your behalf.
          MaxSessionDuration: 3600
          Path: /
          Tags:
            - Key: noq-authorized
              Value: engineering_group@noq.dev
            - Key: noq-tra-active-users
              Value: ''
            - Key: noq-tra-supported-groups
              Value: engineering@noq.dev
          ManagedPolicies: []
          InlinePolicies:
            - PolicyName: spoke-acct-policy
              Statement:
                - Effect: Allow
                  Principal:
                    AWS: arn:aws:iam::1234567890123:role/NoqCentralRole
                  Action:
                    - s3:ListBucket
                - Effect: Allow
                  Principal:
                    AWS: arn:aws:iam::1234567890123:role/NoqCentralRole
                  Action:
                    - s3:CreateBucket
            - PolicyName: spoke-acct-policy-333
              Statement:
                - Effect: Allow
                  Principal:
                    AWS: arn:aws:iam::1234567890123:role/NoqCentralRole
                  Action:
                    - s3:DeleteBucket
                - Effect: Allow
                  Principal:
                    AWS: arn:aws:iam::1234567890123:role/NoqCentralRole
                  Action:
                    - s3:ListBucket
          AssumeRolePolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Allow
                Principal:
                  AWS: arn:aws:iam::1234567890123:role/NoqCentralRole
                Action:
                  - sts:AssumeRole
                  - sts:TagSession
              - Effect: Allow
                Principal:
                  AWS: arn:aws:iam::940552945933:role/NoqCentralRoleCorpNoqDev
                Action:
                  - sts:AssumeRole
                  - sts:TagSession
        proposed_changes:
          - change_type: Create
            attribute: inline_policies
            resource_id: spoke-acct-policy
            new_value:
              Statement:
                - Effect: Allow
                  Principal:
                    AWS: arn:aws:iam::1234567890123:role/NoqCentralRole
                  Action:
                    - s3:ListBucket
                - Effect: Allow
                  Principal:
                    AWS: arn:aws:iam::1234567890123:role/NoqCentralRole
                  Action:
                    - s3:CreateBucket
          - change_type: Create
            attribute: inline_policies
            resource_id: spoke-acct-policy-333
            new_value:
              Statement:
                - Effect: Allow
                  Principal:
                    AWS: arn:aws:iam::1234567890123:role/NoqCentralRole
                  Action:
                    - s3:DeleteBucket
                - Effect: Allow
                  Principal:
                    AWS: arn:aws:iam::1234567890123:role/NoqCentralRole
                  Action:
                    - s3:ListBucket
        exceptions_seen: []
    exceptions_seen: []
"""


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

def get_update_template():
    return [TemplateChangeDetails.parse_obj(x) for x in yaml.load(update_template_yaml)]
