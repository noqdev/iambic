import pytest
from iambic.core.models import ProposedChange
from iambic.output.markdown import ActionSummaries, get_template_data, render_resource_changes

from iambic.core.utils import yaml
from iambic.core.models import TemplateChangeDetails


template_yaml = """  - resource_id: kris_test
    resource_type: aws:iam:role
    template_path: ./resources/aws/roles/development-2/kris_test.yaml
    proposed_changes:
      - account: development-2 - (350876197038)
        resource_id: kris_test
        current_value:
          Path: /
          RoleName: kris_test
          RoleId: AROAVDMOZ4CXKLKGMPAFP
          Arn: arn:aws:iam::350876197038:role/kris_test
          CreateDate: '2022-04-22T00:54:28+00:00'
          AssumeRolePolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Allow
                Principal:
                  Service: ec2.amazonaws.com
                Action: sts:AssumeRole
              - Sid: noqdeleteon20220429curtis1650738227
                Effect: Allow
                Principal:
                  AWS: arn:aws:iam::759357822767:role/NoqSaasRoleLocalDev
                Action:
                  - sts:AssumeRole
                  - sts:TagSession
              - Sid: noqdeleteon20220429curtis1650738517
                Effect: Allow
                Principal:
                  AWS: arn:aws:iam::759357822767:role/NoqSaasRoleLocalDev
                Action:
                  - sts:AssumeRole
                  - sts:TagSession
              - Effect: Allow
                Principal:
                  AWS: arn:aws:iam::759357822767:role/NoqCentralRoleLocalDev
                Action:
                  - sts:AssumeRole
                  - sts:TagSession
              - Effect: Allow
                Principal:
                  AWS: arn:aws:iam::759357822767:role/NoqCentralRoleLocalDev
                Action:
                  - sts:AssumeRole
                  - sts:TagSession
              - Effect: Allow
                Principal:
                  AWS: arn:aws:iam::759357822767:role/NoqCentralRoleLocalDev
                Action:
                  - sts:AssumeRole
                  - sts:TagSession
          Description: kris's test role
          MaxSessionDuration: 3600
          Tags:
            - Key: noq-authorized
              Value: non-admin:TestTwo:us-east-1_CNoZribID_Google:NewTestGroup
            - Key: noq-pending-resource-removal
              Value: '2022-09-01T23:55:11.460450+00:00'
          RoleLastUsed:
            LastUsedDate: '2022-04-28T19:41:47+00:00'
            Region: us-west-1
          ManagedPolicies:
            - PolicyName: AWSDirectConnectReadOnlyAccess
              PolicyArn: arn:aws:iam::aws:policy/AWSDirectConnectReadOnlyAccess
            - PolicyName: AWSIoT1ClickReadOnlyAccess
              PolicyArn: arn:aws:iam::aws:policy/AWSIoT1ClickReadOnlyAccess
          InlinePolicies:
            - PolicyName: noq_user_1659544539_nslq
              Version: '2012-10-17'
              Statement:
                - Resource:
                    - arn:aws:s3:::noq-development-2-test-bucket
                    - arn:aws:s3:::noq-development-2-test-bucket/*
                  Action:
                    - s3:abortmultipartupload
                    - s3:deleteobject
                    - s3:deleteobjecttagging
                    - s3:deleteobjectversion
                    - s3:deleteobjectversiontagging
                    - s3:getobject
                    - s3:getobjectacl
                    - s3:getobjecttagging
                    - s3:getobjectversion
                    - s3:getobjectversionacl
                    - s3:getobjectversiontagging
                    - s3:listbucket
                    - s3:listbucketversions
                    - s3:listmultipartuploadparts*
                    - s3:putobject
                    - s3:putobjecttagging
                    - s3:putobjectversiontagging
                  Effect: Allow
                  Sid: noquser1659544529haql
            - PolicyName: noq_user_1659545128_seob
              Statement:
                - Action:
                    - s3:putobject
                    - s3:putobjecttagging
                    - s3:putobjectversiontagging
                  Effect: Allow
                  Resource:
                    - arn:aws:s3:::noq-development-2-test-bucket
                    - arn:aws:s3:::noq-development-2-test-bucket/*
                  Sid: noquser1659544529haql
              Version: '2012-10-17'
            - PolicyName: noq_user_1665770085_lgks
              Statement:
                - Action:
                    - s3:getbucket*
                    - s3:getobject
                    - s3:getobjectacl
                    - s3:getobjecttagging
                    - s3:getobjectversion
                    - s3:getobjectversionacl
                    - s3:getobjectversiontagging
                  Effect: Allow
                  Resource:
                    - arn:aws:s3:::consoleme-dev-test-bucket
                    - arn:aws:s3:::consoleme-dev-test-bucket/*
                  Sid: noquser1665770063uboo
              Version: '2012-10-17'
            - PolicyName: noq_user_1665770091_yins
              Statement:
                - Action:
                    - s3:getbucket*
                    - s3:getobject
                    - s3:getobjectacl
                    - s3:getobjecttagging
                    - s3:getobjectversion
                    - s3:getobjectversionacl
                    - s3:getobjectversiontagging
                  Effect: Allow
                  Resource:
                    - arn:aws:s3:::consoleme-dev-test-bucket
                    - arn:aws:s3:::consoleme-dev-test-bucket/*
                  Sid: noquser1665770063uboo
              Version: '2012-10-17'
            - PolicyName: noq_will_1654542886_ekni
              Version: '2012-10-17'
              Statement:
                - Resource:
                    - arn:aws:sns:us-west-2:759357822767:testtopic
                  Action:
                    - sns:confirmsubscription
                    - sns:getendpointattributes
                    - sns:gettopicattributes
                    - sns:subscribe
                  Effect: Allow
                  Sid: noqwill1654542862mhki
            - PolicyName: noq_will_1654546707_fcqy
              Version: '2012-10-17'
              Statement:
                - Resource:
                    - arn:aws:sqs:us-west-2:759357822767:testqueue
                  Action:
                    - sqs:getqueueattributes
                    - sqs:getqueueurl
                    - sqs:sendmessage
                  Effect: Allow
                  Sid: noqwill1654546703lxlj
            - PolicyName: noq_will_1655326077_yhpo
              Statement:
                - Action:
                    - s3:abortmultipartupload
                    - s3:getobject
                    - s3:getobjectacl
                    - s3:getobjecttagging
                    - s3:getobjectversion
                    - s3:getobjectversionacl
                    - s3:getobjectversiontagging
                    - s3:listbucket
                    - s3:listbucketversions
                    - s3:listmultipartuploadparts*
                    - s3:putobject
                    - s3:putobjecttagging
                    - s3:putobjectversiontagging
                  Effect: Allow
                  Resource:
                    - arn:aws:s3:::noq-development-2-test-bucket
                    - arn:aws:s3:::noq-development-2-test-bucket/*
                  Sid: noqwill1655326065lpux
              Version: '2012-10-17'
        proposed_changes:
          - change_type: Delete
            resource_id: kris_test
            resource_type: aws:iam:role
        exceptions_seen: []
    exceptions_seen: []
  - resource_id: ConsoleMeCentralRoleDev
    resource_type: aws:iam:role
    template_path: ./resources/aws/roles/development/consolemecentralroledev.yaml
    proposed_changes:
      - account: development - (759357822767)
        resource_id: ConsoleMeCentralRoleDev
        current_value:
          Path: /
          RoleName: ConsoleMeCentralRoleDev
          RoleId: AROA3BTKA24X4UN7VKPBQ
          Arn: arn:aws:iam::759357822767:role/ConsoleMeCentralRoleDev
          CreateDate: '2022-03-23T13:58:37+00:00'
          AssumeRolePolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Allow
                Principal:
                  Service: ecs-tasks.amazonaws.com
                Action: sts:AssumeRole
              - Effect: Allow
                Principal:
                  AWS: arn:aws:iam::940552945933:role/NoqCentralRoleCorpNoqDev
                Action:
                  - sts:AssumeRole
                  - sts:TagSession
              - Effect: Allow
                Principal:
                  AWS: arn:aws:iam::940552945933:role/NoqCentralRoleCorpNoqDev
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
            - Key: noq-tear-supported-groups
              Value: engineering@noq.dev
          RoleLastUsed:
            LastUsedDate: '2022-06-16T15:13:09+00:00'
            Region: us-east-1
          ManagedPolicies: []
          InlinePolicies:
            - PolicyName: consoleme_policy
              Version: '2012-10-17'
              Statement:
                - Effect: Allow
                  Action:
                    - access-analyzer:*
                    - cloudtrail:*
                    - cloudwatch:*
                    - config:SelectResourceConfig
                    - config:SelectAggregateResourceConfig
                    - dynamodb:batchgetitem
                    - dynamodb:batchwriteitem
                    - dynamodb:deleteitem
                    - dynamodb:describe*
                    - dynamodb:getitem
                    - dynamodb:getrecords
                    - dynamodb:getsharditerator
                    - dynamodb:putitem
                    - dynamodb:query
                    - dynamodb:scan
                    - dynamodb:updateitem
                    - dynamodb:CreateTable
                    - dynamodb:UpdateTimeToLive
                    - sns:createplatformapplication
                    - sns:createplatformendpoint
                    - sns:deleteendpoint
                    - sns:deleteplatformapplication
                    - sns:getendpointattributes
                    - sns:getplatformapplicationattributes
                    - sns:listendpointsbyplatformapplication
                    - sns:publish
                    - sns:setendpointattributes
                    - sns:setplatformapplicationattributes
                    - sts:assumerole
                  Resource:
                    - '*'
                - Effect: Allow
                  Action:
                    - autoscaling:Describe*
                    - cloudwatch:Get*
                    - cloudwatch:List*
                    - config:BatchGet*
                    - config:List*
                    - config:Select*
                    - ec2:DescribeSubnets
                    - ec2:describevpcendpoints
                    - ec2:DescribeVpcs
                    - iam:GetAccountAuthorizationDetails
                    - iam:ListAccountAliases
                    - iam:ListAttachedRolePolicies
                    - ec2:describeregions
                    - s3:GetBucketPolicy
                    - s3:GetBucketTagging
                    - s3:ListAllMyBuckets
                    - s3:ListBucket
                    - s3:PutBucketPolicy
                    - s3:PutBucketTagging
                    - sns:GetTopicAttributes
                    - sns:ListTagsForResource
                    - sns:ListTopics
                    - sns:SetTopicAttributes
                    - sns:TagResource
                    - sns:UnTagResource
                    - sqs:GetQueueAttributes
                    - sqs:GetQueueUrl
                    - sqs:ListQueues
                    - sqs:ListQueueTags
                    - sqs:SetQueueAttributes
                    - sqs:TagQueue
                    - sqs:UntagQueue
                  Resource: '*'
                - Effect: Allow
                  Action:
                    - s3:ListBucket
                    - s3:GetObject
                    - s3:PutObject
                    - s3:DeleteObject
                  Resource:
                    - arn:aws:s3:::consoleme-dev-test-bucket
                    - arn:aws:s3:::consoleme-dev-test-bucket/*
                - Effect: Allow
                  Action:
                    - s3:ListBucket
                    - s3:GetObject
                  Resource:
                    - arn:aws:s3:::consoleme-dev-configuration-bucket
                    - arn:aws:s3:::consoleme-dev-configuration-bucket/*
            - PolicyName: noq_delete_on_20220504_user_1651619558
              Version: '2012-10-17'
              Statement:
                - Effect: Allow
                  Action:
                    - s3:getobject
                    - s3:getobjectacl
                    - s3:getobjecttagging
                    - s3:getobjectversion
                    - s3:getobjectversionacl
                    - s3:getobjectversiontagging
                    - s3:listbucket
                    - s3:listbucketversions
                  Resource:
                    - arn:aws:s3:::noq-development-2-test-bucket
                    - arn:aws:s3:::noq-development-2-test-bucket/*
                  Sid: noquser1651619552mrrc
            - PolicyName: noq_delete_on_20220711_user_1657459709
              Version: '2012-10-17'
              Statement:
                - Action:
                    - s3:getobject
                    - s3:getobjectacl
                    - s3:getobjecttagging
                    - s3:getobjectversion
                    - s3:getobjectversionacl
                    - s3:getobjectversiontagging
                    - s3:listbucket
                    - s3:listbucketversions
                  Effect: Allow
                  Resource:
                    - arn:aws:s3:::adostoma
                    - arn:aws:s3:::adostoma/*
                  Sid: noquser1657459619gxvf
        proposed_changes:
          - change_type: Delete
            resource_id: ConsoleMeCentralRoleDev
            resource_type: aws:iam:role
        exceptions_seen: []
    exceptions_seen: []
  - resource_id: '{{account_name}}_multi_account_admin'
    resource_type: aws:iam:role
    template_path: ./resources/aws/roles/multi_account/account_name_multi_account_admin.yaml
    proposed_changes:
      - account: development - (759357822767)
        resource_id: development_multi_account_admin
        current_value:
          Path: /
          RoleName: development_multi_account_admin
          RoleId: AROA3BTKA24XR7IH5OW2K
          Arn: arn:aws:iam::759357822767:role/development_multi_account_admin
          CreateDate: '2022-08-11T18:16:22+00:00'
          AssumeRolePolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Allow
                Principal:
                  AWS: arn:aws:iam::759357822767:role/NoqSaasRoleLocalDev
                Action:
                  - sts:AssumeRole
                  - sts:TagSession
          Description: Noq Admin Role
          MaxSessionDuration: 3600
          PermissionsBoundary:
            PermissionsBoundaryType: Policy
            PermissionsBoundaryArn: arn:aws:iam::aws:policy/AmazonGlacierReadOnlyAccess
          Tags:
            - Key: account_name
              Value: development
            - Key: noq-managed
              Value: 'true'
            - Key: noq-authorized-cli-only
              Value: curtis@noq.dev
            - Key: owner
              Value: noq_admins@noq.dev
          RoleLastUsed: {}
          ManagedPolicies:
            - PolicyName: AWSDirectConnectReadOnlyAccess
              PolicyArn: arn:aws:iam::aws:policy/AWSDirectConnectReadOnlyAccess
          InlinePolicies:
            - PolicyName: admin_policy
              Version: '2012-10-17'
              Statement:
                - Action:
                    - '*'
                  Effect: Allow
                  Resource: '*'
        proposed_changes:
          - change_type: Delete
            resource_id: development_multi_account_admin
            resource_type: aws:iam:role
        exceptions_seen: []
      - account: staging - (259868150464)
        resource_id: staging_multi_account_admin
        current_value:
          Path: /
          RoleName: staging_multi_account_admin
          RoleId: AROATZAKZJLAICECXXMTP
          Arn: arn:aws:iam::259868150464:role/staging_multi_account_admin
          CreateDate: '2022-08-11T18:16:08+00:00'
          AssumeRolePolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Allow
                Principal:
                  AWS: arn:aws:iam::759357822767:role/NoqSaasRoleLocalDev
                Action:
                  - sts:AssumeRole
                  - sts:TagSession
          Description: Noq Admin Role
          MaxSessionDuration: 3600
          PermissionsBoundary:
            PermissionsBoundaryType: Policy
            PermissionsBoundaryArn: arn:aws:iam::aws:policy/AmazonGlacierReadOnlyAccess
          Tags:
            - Key: account_name
              Value: staging
            - Key: noq-managed
              Value: 'true'
            - Key: noq-authorized-cli-only
              Value: curtis@noq.dev
            - Key: owner
              Value: noq_admins@noq.dev
          RoleLastUsed: {}
          ManagedPolicies:
            - PolicyName: NoqTestPolicy
              PolicyArn: arn:aws:iam::259868150464:policy/NoqTestPolicy
            - PolicyName: AWSDirectConnectReadOnlyAccess
              PolicyArn: arn:aws:iam::aws:policy/AWSDirectConnectReadOnlyAccess
          InlinePolicies:
            - PolicyName: admin_policy
              Version: '2012-10-17'
              Statement:
                - Action:
                    - '*'
                  Effect: Allow
                  Resource: '*'
            - PolicyName: other_policy
              Version: '2012-10-17'
              Statement:
                - Action:
                    - s3:*
                  Effect: Deny
                  Resource: '*'
        proposed_changes:
          - change_type: Delete
            resource_id: staging_multi_account_admin
            resource_type: aws:iam:role
        exceptions_seen: []
    exceptions_seen: []
  - resource_id: '{{account_name}}_multi_account_role'
    resource_type: aws:iam:role
    template_path: ./resources/aws/roles/multi_account/account_name_multi_account_role.yaml
    proposed_changes:
      - account: development - (759357822767)
        resource_id: development_multi_account_role
        current_value:
          Path: /
          RoleName: development_multi_account_role
          RoleId: AROA3BTKA24X6WQ7P6HJJ
          Arn: arn:aws:iam::759357822767:role/development_multi_account_role
          CreateDate: '2022-10-01T19:48:17+00:00'
          AssumeRolePolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Allow
                Principal:
                  AWS: arn:aws:iam::759357822767:role/NoqSaasRoleLocalDev
                Action:
                  - sts:AssumeRole
                  - sts:TagSession
          Description: Networking team role
          MaxSessionDuration: 3600
          PermissionsBoundary:
            PermissionsBoundaryType: Policy
            PermissionsBoundaryArn: arn:aws:iam::aws:policy/AmazonGlacierReadOnlyAccess
          Tags:
            - Key: noq-managed
              Value: 'true'
            - Key: networking-scp-exempt
              Value: 'true'
            - Key: owner
              Value: networking@example.com
          RoleLastUsed: {}
          ManagedPolicies: []
          InlinePolicies: []
        proposed_changes:
          - change_type: Delete
            resource_id: development_multi_account_role
            resource_type: aws:iam:role
        exceptions_seen: []
      - account: staging - (259868150464)
        resource_id: staging_multi_account_role
        current_value:
          Path: /
          RoleName: staging_multi_account_role
          RoleId: AROATZAKZJLAN3DHYDCDU
          Arn: arn:aws:iam::259868150464:role/staging_multi_account_role
          CreateDate: '2022-10-01T19:49:01+00:00'
          AssumeRolePolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Allow
                Principal:
                  AWS: arn:aws:iam::759357822767:role/NoqSaasRoleLocalDev
                Action:
                  - sts:AssumeRole
                  - sts:TagSession
          Description: Networking team role
          MaxSessionDuration: 3600
          PermissionsBoundary:
            PermissionsBoundaryType: Policy
            PermissionsBoundaryArn: arn:aws:iam::aws:policy/AmazonGlacierReadOnlyAccess
          Tags:
            - Key: noq-managed
              Value: 'true'
            - Key: networking-scp-exempt
              Value: 'true'
            - Key: owner
              Value: networking@example.com
          RoleLastUsed: {}
          ManagedPolicies: []
          InlinePolicies: []
        proposed_changes:
          - change_type: Delete
            resource_id: staging_multi_account_role
            resource_type: aws:iam:role
        exceptions_seen: []
    exceptions_seen: []
  - resource_id: ConsoleMe
    resource_type: aws:iam:role
    template_path: ./resources/aws/roles/multi_account/consoleme.yaml
    proposed_changes:
      - account: test - (242350334841)
        resource_id: ConsoleMe
        current_value:
          Path: /
          RoleName: ConsoleMe
          RoleId: AROATQ3JUUN466ZO5SECI
          Arn: arn:aws:iam::242350334841:role/ConsoleMe
          CreateDate: '2021-09-29T18:40:39+00:00'
          AssumeRolePolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Allow
                Principal:
                  AWS: AROATZAKZJLAO6SLARMN5
                Action:
                  - sts:AssumeRole
                  - sts:TagSession
          Description: Allows EC2 instances to call AWS services on your behalf.
          MaxSessionDuration: 3600
          Tags:
            - Key: noq-aa
              Value: aa
            - Key: consoleme-authorized
              Value: ccastrapel@gmail.com
          RoleLastUsed: {}
          ManagedPolicies: []
          InlinePolicies:
            - PolicyName: cm_ccastrapel_1633107564_lsix
              Statement:
                - Action:
                    - s3:getobject
                    - s3:getobjectacl
                    - s3:getobjecttagging
                    - s3:getobjectversion
                    - s3:getobjectversionacl
                    - s3:getobjectversiontagging
                    - s3:listbucket
                    - s3:listbucketversions
                  Effect: Allow
                  Resource:
                    - arn:aws:s3:::cdktoolkit-stagingbucket-1n7p9avb83roq
                    - arn:aws:s3:::cdktoolkit-stagingbucket-1n7p9avb83roq/*
                  Sid: cmccastrapel1633107551ibwb
              Version: '2012-10-17'
            - PolicyName: consolemespoke
              Statement:
                - Action:
                    - autoscaling:Describe*
                    - cloudwatch:Get*
                    - cloudwatch:List*
                    - config:BatchGet*
                    - config:List*
                    - config:Select*
                    - ec2:describeregions
                    - ec2:DescribeSubnets
                    - ec2:describevpcendpoints
                    - ec2:DescribeVpcs
                    - iam:*
                    - s3:GetBucketPolicy
                    - s3:GetBucketTagging
                    - s3:ListAllMyBuckets
                    - s3:ListBucket
                    - s3:PutBucketPolicy
                    - s3:PutBucketTagging
                    - sns:GetTopicAttributes
                    - sns:ListTagsForResource
                    - sns:ListTopics
                    - sns:SetTopicAttributes
                    - sns:TagResource
                    - sns:UnTagResource
                    - sqs:GetQueueAttributes
                    - sqs:GetQueueUrl
                    - sqs:ListQueues
                    - sqs:ListQueueTags
                    - sqs:SetQueueAttributes
                    - sqs:TagQueue
                    - sqs:UntagQueue
                  Effect: Allow
                  Resource:
                    - '*'
                  Sid: iam
              Version: '2012-10-17'
        proposed_changes:
          - change_type: Delete
            resource_id: ConsoleMe
            resource_type: aws:iam:role
        exceptions_seen: []
      - account: staging - (259868150464)
        resource_id: ConsoleMe
        current_value:
          Path: /
          RoleName: ConsoleMe
          RoleId: AROATZAKZJLAD5ZTJJESR
          Arn: arn:aws:iam::259868150464:role/ConsoleMe
          CreateDate: '2021-09-29T19:34:56+00:00'
          AssumeRolePolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Allow
                Principal:
                  AWS: arn:aws:iam::940552945933:role/NoqCentralRoleCorpNoqDev
                Action:
                  - sts:AssumeRole
                  - sts:TagSession
              - Effect: Allow
                Principal:
                  AWS: arn:aws:iam::759357822767:role/NoqCentralRoleLocalDev
                Action:
                  - sts:AssumeRole
                  - sts:TagSession
              - Effect: Allow
                Principal:
                  AWS: arn:aws:iam::259868150464:role/NoqCentralRoleStaging
                Action:
                  - sts:AssumeRole
                  - sts:TagSession
          Description: Allows EC2 instances to call AWS services on your behalf.
          MaxSessionDuration: 3600
          PermissionsBoundary:
            PermissionsBoundaryType: Policy
            PermissionsBoundaryArn: arn:aws:iam::259868150464:policy/adino
          RoleLastUsed:
            LastUsedDate: '2023-03-05T21:02:39+00:00'
            Region: us-east-1
          ManagedPolicies: []
          InlinePolicies:
            - PolicyName: spokerole
              Statement:
                - Action:
                    - autoscaling:Describe*
                    - cloudwatch:Get*
                    - cloudwatch:List*
                    - config:BatchGet*
                    - config:List*
                    - config:Select*
                    - ec2:describeregions
                    - ec2:DescribeSubnets
                    - ec2:describevpcendpoints
                    - ec2:DescribeVpcs
                    - iam:*
                    - s3:GetBucketPolicy
                    - s3:GetBucketTagging
                    - s3:ListAllMyBuckets
                    - s3:ListBucket
                    - s3:PutBucketPolicy
                    - s3:PutBucketTagging
                    - sns:GetTopicAttributes
                    - sns:ListTagsForResource
                    - sns:ListTopics
                    - sns:SetTopicAttributes
                    - sns:TagResource
                    - sns:UnTagResource
                    - sqs:GetQueueAttributes
                    - sqs:GetQueueUrl
                    - sqs:ListQueues
                    - sqs:ListQueueTags
                    - sqs:SetQueueAttributes
                    - sqs:TagQueue
                    - sqs:UntagQueue
                    - organizations:ListAccounts
                  Effect: Allow
                  Resource:
                    - '*'
                  Sid: iam
              Version: '2012-10-17'
        proposed_changes:
          - change_type: Delete
            resource_id: ConsoleMe
            resource_type: aws:iam:role
        exceptions_seen: []
    exceptions_seen: []
  - resource_id: ConsoleMeCentralRole
    resource_type: aws:iam:role
    template_path: ./resources/aws/roles/multi_account/consolemecentralrole.yaml
    proposed_changes:
      - account: test - (242350334841)
        resource_id: ConsoleMeCentralRole
        current_value:
          Path: /
          RoleName: ConsoleMeCentralRole
          RoleId: AROATQ3JUUN45LCF2LCMC
          Arn: arn:aws:iam::242350334841:role/ConsoleMeCentralRole
          CreateDate: '2021-10-18T17:48:02+00:00'
          AssumeRolePolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Sid: ConsoleMeAssumesTarget
                Effect: Allow
                Principal:
                  AWS: AROATZAKZJLAFEBPSIDEJ
                Action: sts:AssumeRole
          Description: ''
          MaxSessionDuration: 3600
          RoleLastUsed: {}
          ManagedPolicies: []
          InlinePolicies:
            - PolicyName: terraform-20211018174804250000000002
              Statement:
                - Action:
                    - access-analyzer:*
                    - cloudtrail:*
                    - cloudwatch:*
                    - config:SelectResourceConfig
                    - config:SelectAggregateResourceConfig
                    - dynamodb:batchgetitem
                    - dynamodb:batchwriteitem
                    - dynamodb:deleteitem
                    - dynamodb:describe*
                    - dynamodb:getitem
                    - dynamodb:getrecords
                    - dynamodb:getsharditerator
                    - dynamodb:putitem
                    - dynamodb:query
                    - dynamodb:scan
                    - dynamodb:updateitem
                    - dynamodb:CreateTable
                    - dynamodb:UpdateTimeToLive
                    - sns:createplatformapplication
                    - sns:createplatformendpoint
                    - sns:deleteendpoint
                    - sns:deleteplatformapplication
                    - sns:getendpointattributes
                    - sns:getplatformapplicationattributes
                    - sns:listendpointsbyplatformapplication
                    - sns:publish
                    - sns:setendpointattributes
                    - sns:setplatformapplicationattributes
                    - sts:assumerole
                  Effect: Allow
                  Resource:
                    - '*'
                - Action:
                    - ses:sendemail
                    - ses:sendrawemail
                  Condition:
                    StringLike:
                      ses:FromAddress:
                        - email_address_here@example.com
                  Effect: Allow
                  Resource: arn:aws:ses:*:123456789:identity/your_identity.example.com
                - Action:
                    - autoscaling:Describe*
                    - cloudwatch:Get*
                    - cloudwatch:List*
                    - config:BatchGet*
                    - config:List*
                    - config:Select*
                    - ec2:DescribeSubnets
                    - ec2:describevpcendpoints
                    - ec2:DescribeVpcs
                    - iam:GetAccountAuthorizationDetails
                    - iam:ListAccountAliases
                    - iam:ListAttachedRolePolicies
                    - ec2:describeregions
                    - s3:GetBucketPolicy
                    - s3:GetBucketTagging
                    - s3:ListAllMyBuckets
                    - s3:ListBucket
                    - s3:PutBucketPolicy
                    - s3:PutBucketTagging
                    - sns:GetTopicAttributes
                    - sns:ListTagsForResource
                    - sns:ListTopics
                    - sns:SetTopicAttributes
                    - sns:TagResource
                    - sns:UnTagResource
                    - sqs:GetQueueAttributes
                    - sqs:GetQueueUrl
                    - sqs:ListQueues
                    - sqs:ListQueueTags
                    - sqs:SetQueueAttributes
                    - sqs:TagQueue
                    - sqs:UntagQueue
                  Effect: Allow
                  Resource: '*'
              Version: '2012-10-17'
            - PolicyName: terraform-20211018180128632100000001
              Statement:
                - Action:
                    - access-analyzer:*
                    - cloudtrail:*
                    - cloudwatch:*
                    - config:SelectResourceConfig
                    - config:SelectAggregateResourceConfig
                    - dynamodb:batchgetitem
                    - dynamodb:batchwriteitem
                    - dynamodb:deleteitem
                    - dynamodb:describe*
                    - dynamodb:getitem
                    - dynamodb:getrecords
                    - dynamodb:getsharditerator
                    - dynamodb:putitem
                    - dynamodb:query
                    - dynamodb:scan
                    - dynamodb:updateitem
                    - dynamodb:CreateTable
                    - dynamodb:UpdateTimeToLive
                    - sns:createplatformapplication
                    - sns:createplatformendpoint
                    - sns:deleteendpoint
                    - sns:deleteplatformapplication
                    - sns:getendpointattributes
                    - sns:getplatformapplicationattributes
                    - sns:listendpointsbyplatformapplication
                    - sns:publish
                    - sns:setendpointattributes
                    - sns:setplatformapplicationattributes
                    - sts:assumerole
                  Effect: Allow
                  Resource:
                    - '*'
                - Action:
                    - ses:sendemail
                    - ses:sendrawemail
                  Condition:
                    StringLike:
                      ses:FromAddress:
                        - email_address_here@example.com
                  Effect: Allow
                  Resource: arn:aws:ses:*:123456789:identity/your_identity.example.com
                - Action:
                    - autoscaling:Describe*
                    - cloudwatch:Get*
                    - cloudwatch:List*
                    - config:BatchGet*
                    - config:List*
                    - config:Select*
                    - ec2:DescribeSubnets
                    - ec2:describevpcendpoints
                    - ec2:DescribeVpcs
                    - iam:GetAccountAuthorizationDetails
                    - iam:ListAccountAliases
                    - iam:ListAttachedRolePolicies
                    - ec2:describeregions
                    - s3:GetBucketPolicy
                    - s3:GetBucketTagging
                    - s3:ListAllMyBuckets
                    - s3:ListBucket
                    - s3:PutBucketPolicy
                    - s3:PutBucketTagging
                    - sns:GetTopicAttributes
                    - sns:ListTagsForResource
                    - sns:ListTopics
                    - sns:SetTopicAttributes
                    - sns:TagResource
                    - sns:UnTagResource
                    - sqs:GetQueueAttributes
                    - sqs:GetQueueUrl
                    - sqs:ListQueues
                    - sqs:ListQueueTags
                    - sqs:SetQueueAttributes
                    - sqs:TagQueue
                    - sqs:UntagQueue
                  Effect: Allow
                  Resource: '*'
              Version: '2012-10-17'
        proposed_changes:
          - change_type: Delete
            resource_id: ConsoleMeCentralRole
            resource_type: aws:iam:role
        exceptions_seen: []
      - account: demo-2 - (694815895589)
        resource_id: ConsoleMeCentralRole
        current_value:
          Path: /
          RoleName: ConsoleMeCentralRole
          RoleId: AROA2DRSBGAS4VZRXLHLD
          Arn: arn:aws:iam::694815895589:role/ConsoleMeCentralRole
          CreateDate: '2021-10-18T17:46:33+00:00'
          AssumeRolePolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Sid: ConsoleMeAssumesTarget
                Effect: Allow
                Principal:
                  AWS: AROATZAKZJLAFEBPSIDEJ
                Action: sts:AssumeRole
          Description: ''
          MaxSessionDuration: 3600
          RoleLastUsed: {}
          ManagedPolicies: []
          InlinePolicies:
            - PolicyName: terraform-20211018174634639300000002
              Statement:
                - Action:
                    - access-analyzer:*
                    - cloudtrail:*
                    - cloudwatch:*
                    - config:SelectResourceConfig
                    - config:SelectAggregateResourceConfig
                    - dynamodb:batchgetitem
                    - dynamodb:batchwriteitem
                    - dynamodb:deleteitem
                    - dynamodb:describe*
                    - dynamodb:getitem
                    - dynamodb:getrecords
                    - dynamodb:getsharditerator
                    - dynamodb:putitem
                    - dynamodb:query
                    - dynamodb:scan
                    - dynamodb:updateitem
                    - dynamodb:CreateTable
                    - dynamodb:UpdateTimeToLive
                    - sns:createplatformapplication
                    - sns:createplatformendpoint
                    - sns:deleteendpoint
                    - sns:deleteplatformapplication
                    - sns:getendpointattributes
                    - sns:getplatformapplicationattributes
                    - sns:listendpointsbyplatformapplication
                    - sns:publish
                    - sns:setendpointattributes
                    - sns:setplatformapplicationattributes
                    - sts:assumerole
                  Effect: Allow
                  Resource:
                    - '*'
                - Action:
                    - ses:sendemail
                    - ses:sendrawemail
                  Condition:
                    StringLike:
                      ses:FromAddress:
                        - email_address_here@example.com
                  Effect: Allow
                  Resource: arn:aws:ses:*:123456789:identity/your_identity.example.com
                - Action:
                    - autoscaling:Describe*
                    - cloudwatch:Get*
                    - cloudwatch:List*
                    - config:BatchGet*
                    - config:List*
                    - config:Select*
                    - ec2:DescribeSubnets
                    - ec2:describevpcendpoints
                    - ec2:DescribeVpcs
                    - iam:GetAccountAuthorizationDetails
                    - iam:ListAccountAliases
                    - iam:ListAttachedRolePolicies
                    - ec2:describeregions
                    - s3:GetBucketPolicy
                    - s3:GetBucketTagging
                    - s3:ListAllMyBuckets
                    - s3:ListBucket
                    - s3:PutBucketPolicy
                    - s3:PutBucketTagging
                    - sns:GetTopicAttributes
                    - sns:ListTagsForResource
                    - sns:ListTopics
                    - sns:SetTopicAttributes
                    - sns:TagResource
                    - sns:UnTagResource
                    - sqs:GetQueueAttributes
                    - sqs:GetQueueUrl
                    - sqs:ListQueues
                    - sqs:ListQueueTags
                    - sqs:SetQueueAttributes
                    - sqs:TagQueue
                    - sqs:UntagQueue
                  Effect: Allow
                  Resource: '*'
              Version: '2012-10-17'
            - PolicyName: terraform-20211018175424807000000001
              Statement:
                - Action:
                    - access-analyzer:*
                    - cloudtrail:*
                    - cloudwatch:*
                    - config:SelectResourceConfig
                    - config:SelectAggregateResourceConfig
                    - dynamodb:batchgetitem
                    - dynamodb:batchwriteitem
                    - dynamodb:deleteitem
                    - dynamodb:describe*
                    - dynamodb:getitem
                    - dynamodb:getrecords
                    - dynamodb:getsharditerator
                    - dynamodb:putitem
                    - dynamodb:query
                    - dynamodb:scan
                    - dynamodb:updateitem
                    - dynamodb:CreateTable
                    - dynamodb:UpdateTimeToLive
                    - sns:createplatformapplication
                    - sns:createplatformendpoint
                    - sns:deleteendpoint
                    - sns:deleteplatformapplication
                    - sns:getendpointattributes
                    - sns:getplatformapplicationattributes
                    - sns:listendpointsbyplatformapplication
                    - sns:publish
                    - sns:setendpointattributes
                    - sns:setplatformapplicationattributes
                    - sts:assumerole
                  Effect: Allow
                  Resource:
                    - '*'
                - Action:
                    - ses:sendemail
                    - ses:sendrawemail
                  Condition:
                    StringLike:
                      ses:FromAddress:
                        - email_address_here@example.com
                  Effect: Allow
                  Resource: arn:aws:ses:*:123456789:identity/your_identity.example.com
                - Action:
                    - autoscaling:Describe*
                    - cloudwatch:Get*
                    - cloudwatch:List*
                    - config:BatchGet*
                    - config:List*
                    - config:Select*
                    - ec2:DescribeSubnets
                    - ec2:describevpcendpoints
                    - ec2:DescribeVpcs
                    - iam:GetAccountAuthorizationDetails
                    - iam:ListAccountAliases
                    - iam:ListAttachedRolePolicies
                    - ec2:describeregions
                    - s3:GetBucketPolicy
                    - s3:GetBucketTagging
                    - s3:ListAllMyBuckets
                    - s3:ListBucket
                    - s3:PutBucketPolicy
                    - s3:PutBucketTagging
                    - sns:GetTopicAttributes
                    - sns:ListTagsForResource
                    - sns:ListTopics
                    - sns:SetTopicAttributes
                    - sns:TagResource
                    - sns:UnTagResource
                    - sqs:GetQueueAttributes
                    - sqs:GetQueueUrl
                    - sqs:ListQueues
                    - sqs:ListQueueTags
                    - sqs:SetQueueAttributes
                    - sqs:TagQueue
                    - sqs:UntagQueue
                  Effect: Allow
                  Resource: '*'
              Version: '2012-10-17'
        proposed_changes:
          - change_type: Delete
            resource_id: ConsoleMeCentralRole
            resource_type: aws:iam:role
        exceptions_seen: []
      - account: demo-1 - (972417093400)
        resource_id: ConsoleMeCentralRole
        current_value:
          Path: /
          RoleName: ConsoleMeCentralRole
          RoleId: AROA6E2ETJ4MMPHPSRDK4
          Arn: arn:aws:iam::972417093400:role/ConsoleMeCentralRole
          CreateDate: '2021-10-18T18:56:39+00:00'
          AssumeRolePolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Sid: ConsoleMeAssumesTarget
                Effect: Allow
                Principal:
                  AWS:
                    - AROATZAKZJLAFEBPSIDEJ
                    - AIDATZAKZJLANVTDUDSFH
                Action: sts:AssumeRole
          Description: ''
          MaxSessionDuration: 3600
          RoleLastUsed: {}
          ManagedPolicies: []
          InlinePolicies:
            - PolicyName: iAMPolicy-947b4ca
              Statement:
                - Action:
                    - access-analyzer:*
                    - cloudtrail:*
                    - cloudwatch:*
                    - config:SelectResourceConfig
                    - config:SelectAggregateResourceConfig
                    - dynamodb:batchgetitem
                    - dynamodb:batchwriteitem
                    - dynamodb:deleteitem
                    - dynamodb:describe*
                    - dynamodb:getitem
                    - dynamodb:getrecords
                    - dynamodb:getsharditerator
                    - dynamodb:putitem
                    - dynamodb:query
                    - dynamodb:scan
                    - dynamodb:updateitem
                    - dynamodb:CreateTable
                    - dynamodb:UpdateTimeToLive
                    - sns:createplatformapplication
                    - sns:createplatformendpoint
                    - sns:deleteendpoint
                    - sns:deleteplatformapplication
                    - sns:getendpointattributes
                    - sns:getplatformapplicationattributes
                    - sns:listendpointsbyplatformapplication
                    - sns:publish
                    - sns:setendpointattributes
                    - sns:setplatformapplicationattributes
                    - sts:assumerole
                  Effect: Allow
                  Resource:
                    - '*'
                - Action:
                    - ses:sendemail
                    - ses:sendrawemail
                  Condition:
                    StringLike:
                      ses:FromAddress:
                        - email_address_here@example.com
                  Effect: Allow
                  Resource: arn:aws:ses:*:123456789:identity/your_identity.example.com
                - Action:
                    - autoscaling:Describe*
                    - cloudwatch:Get*
                    - cloudwatch:List*
                    - config:BatchGet*
                    - config:List*
                    - config:Select*
                    - ec2:DescribeSubnets
                    - ec2:describevpcendpoints
                    - ec2:DescribeVpcs
                    - iam:GetAccountAuthorizationDetails
                    - iam:ListAccountAliases
                    - iam:ListAttachedRolePolicies
                    - ec2:describeregions
                    - s3:GetBucketPolicy
                    - s3:GetBucketTagging
                    - s3:ListAllMyBuckets
                    - s3:ListBucket
                    - s3:PutBucketPolicy
                    - s3:PutBucketTagging
                    - sns:GetTopicAttributes
                    - sns:ListTagsForResource
                    - sns:ListTopics
                    - sns:SetTopicAttributes
                    - sns:TagResource
                    - sns:UnTagResource
                    - sqs:GetQueueAttributes
                    - sqs:GetQueueUrl
                    - sqs:ListQueues
                    - sqs:ListQueueTags
                    - sqs:SetQueueAttributes
                    - sqs:TagQueue
                    - sqs:UntagQueue
                  Effect: Allow
                  Resource: '*'
              Version: '2012-10-17'
        proposed_changes:
          - change_type: Delete
            resource_id: ConsoleMeCentralRole
            resource_type: aws:iam:role
        exceptions_seen: []
      - account: demo-3 - (518317429440)
        resource_id: ConsoleMeCentralRole
        current_value:
          Path: /
          RoleName: ConsoleMeCentralRole
          RoleId: AROAXRLRAKLAGRKYZZEHN
          Arn: arn:aws:iam::518317429440:role/ConsoleMeCentralRole
          CreateDate: '2021-10-18T17:47:06+00:00'
          AssumeRolePolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Sid: ConsoleMeAssumesTarget
                Effect: Allow
                Principal:
                  AWS: AROATZAKZJLAFEBPSIDEJ
                Action: sts:AssumeRole
          Description: ''
          MaxSessionDuration: 3600
          RoleLastUsed: {}
          ManagedPolicies: []
          InlinePolicies:
            - PolicyName: terraform-20211018174708353000000002
              Statement:
                - Action:
                    - access-analyzer:*
                    - cloudtrail:*
                    - cloudwatch:*
                    - config:SelectResourceConfig
                    - config:SelectAggregateResourceConfig
                    - dynamodb:batchgetitem
                    - dynamodb:batchwriteitem
                    - dynamodb:deleteitem
                    - dynamodb:describe*
                    - dynamodb:getitem
                    - dynamodb:getrecords
                    - dynamodb:getsharditerator
                    - dynamodb:putitem
                    - dynamodb:query
                    - dynamodb:scan
                    - dynamodb:updateitem
                    - dynamodb:CreateTable
                    - dynamodb:UpdateTimeToLive
                    - sns:createplatformapplication
                    - sns:createplatformendpoint
                    - sns:deleteendpoint
                    - sns:deleteplatformapplication
                    - sns:getendpointattributes
                    - sns:getplatformapplicationattributes
                    - sns:listendpointsbyplatformapplication
                    - sns:publish
                    - sns:setendpointattributes
                    - sns:setplatformapplicationattributes
                    - sts:assumerole
                  Effect: Allow
                  Resource:
                    - '*'
                - Action:
                    - ses:sendemail
                    - ses:sendrawemail
                  Condition:
                    StringLike:
                      ses:FromAddress:
                        - email_address_here@example.com
                  Effect: Allow
                  Resource: arn:aws:ses:*:123456789:identity/your_identity.example.com
                - Action:
                    - autoscaling:Describe*
                    - cloudwatch:Get*
                    - cloudwatch:List*
                    - config:BatchGet*
                    - config:List*
                    - config:Select*
                    - ec2:DescribeSubnets
                    - ec2:describevpcendpoints
                    - ec2:DescribeVpcs
                    - iam:GetAccountAuthorizationDetails
                    - iam:ListAccountAliases
                    - iam:ListAttachedRolePolicies
                    - ec2:describeregions
                    - s3:GetBucketPolicy
                    - s3:GetBucketTagging
                    - s3:ListAllMyBuckets
                    - s3:ListBucket
                    - s3:PutBucketPolicy
                    - s3:PutBucketTagging
                    - sns:GetTopicAttributes
                    - sns:ListTagsForResource
                    - sns:ListTopics
                    - sns:SetTopicAttributes
                    - sns:TagResource
                    - sns:UnTagResource
                    - sqs:GetQueueAttributes
                    - sqs:GetQueueUrl
                    - sqs:ListQueues
                    - sqs:ListQueueTags
                    - sqs:SetQueueAttributes
                    - sqs:TagQueue
                    - sqs:UntagQueue
                  Effect: Allow
                  Resource: '*'
              Version: '2012-10-17'
            - PolicyName: terraform-20211018175444253500000001
              Statement:
                - Action:
                    - access-analyzer:*
                    - cloudtrail:*
                    - cloudwatch:*
                    - config:SelectResourceConfig
                    - config:SelectAggregateResourceConfig
                    - dynamodb:batchgetitem
                    - dynamodb:batchwriteitem
                    - dynamodb:deleteitem
                    - dynamodb:describe*
                    - dynamodb:getitem
                    - dynamodb:getrecords
                    - dynamodb:getsharditerator
                    - dynamodb:putitem
                    - dynamodb:query
                    - dynamodb:scan
                    - dynamodb:updateitem
                    - dynamodb:CreateTable
                    - dynamodb:UpdateTimeToLive
                    - sns:createplatformapplication
                    - sns:createplatformendpoint
                    - sns:deleteendpoint
                    - sns:deleteplatformapplication
                    - sns:getendpointattributes
                    - sns:getplatformapplicationattributes
                    - sns:listendpointsbyplatformapplication
                    - sns:publish
                    - sns:setendpointattributes
                    - sns:setplatformapplicationattributes
                    - sts:assumerole
                  Effect: Allow
                  Resource:
                    - '*'
                - Action:
                    - ses:sendemail
                    - ses:sendrawemail
                  Condition:
                    StringLike:
                      ses:FromAddress:
                        - email_address_here@example.com
                  Effect: Allow
                  Resource: arn:aws:ses:*:123456789:identity/your_identity.example.com
                - Action:
                    - autoscaling:Describe*
                    - cloudwatch:Get*
                    - cloudwatch:List*
                    - config:BatchGet*
                    - config:List*
                    - config:Select*
                    - ec2:DescribeSubnets
                    - ec2:describevpcendpoints
                    - ec2:DescribeVpcs
                    - iam:GetAccountAuthorizationDetails
                    - iam:ListAccountAliases
                    - iam:ListAttachedRolePolicies
                    - ec2:describeregions
                    - s3:GetBucketPolicy
                    - s3:GetBucketTagging
                    - s3:ListAllMyBuckets
                    - s3:ListBucket
                    - s3:PutBucketPolicy
                    - s3:PutBucketTagging
                    - sns:GetTopicAttributes
                    - sns:ListTagsForResource
                    - sns:ListTopics
                    - sns:SetTopicAttributes
                    - sns:TagResource
                    - sns:UnTagResource
                    - sqs:GetQueueAttributes
                    - sqs:GetQueueUrl
                    - sqs:ListQueues
                    - sqs:ListQueueTags
                    - sqs:SetQueueAttributes
                    - sqs:TagQueue
                    - sqs:UntagQueue
                  Effect: Allow
                  Resource: '*'
              Version: '2012-10-17'
        proposed_changes:
          - change_type: Delete
            resource_id: ConsoleMeCentralRole
            resource_type: aws:iam:role
        exceptions_seen: []
    exceptions_seen: []
  - resource_id: ConsoleMeSpokeRole
    resource_type: aws:iam:role
    template_path: ./resources/aws/roles/multi_account/consolemespokerole.yaml
    proposed_changes:
      - account: test - (242350334841)
        resource_id: ConsoleMeSpokeRole
        current_value:
          Path: /
          RoleName: ConsoleMeSpokeRole
          RoleId: AROATQ3JUUN4R52PEIRRD
          Arn: arn:aws:iam::242350334841:role/ConsoleMeSpokeRole
          CreateDate: '2021-10-18T17:48:02+00:00'
          AssumeRolePolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Sid: ConsoleMeAssumesTarget
                Effect: Allow
                Principal:
                  AWS:
                    - arn:aws:iam::242350334841:role/ConsoleMeCentralRole
                    - AROATZAKZJLAO6SLARMN5
                Action: sts:AssumeRole
          Description: ''
          MaxSessionDuration: 3600
          RoleLastUsed: {}
          ManagedPolicies: []
          InlinePolicies:
            - PolicyName: terraform-20211018174804249700000001
              Statement:
                - Action:
                    - autoscaling:Describe*
                    - cloudwatch:Get*
                    - cloudwatch:List*
                    - config:BatchGet*
                    - config:List*
                    - config:Select*
                    - ec2:describeregions
                    - ec2:DescribeSubnets
                    - ec2:describevpcendpoints
                    - ec2:DescribeVpcs
                    - iam:*
                    - s3:GetBucketPolicy
                    - s3:GetBucketTagging
                    - s3:ListAllMyBuckets
                    - s3:ListBucket
                    - s3:PutBucketPolicy
                    - s3:PutBucketTagging
                    - sns:GetTopicAttributes
                    - sns:ListTagsForResource
                    - sns:ListTopics
                    - sns:SetTopicAttributes
                    - sns:TagResource
                    - sns:UnTagResource
                    - sqs:GetQueueAttributes
                    - sqs:GetQueueUrl
                    - sqs:ListQueues
                    - sqs:ListQueueTags
                    - sqs:SetQueueAttributes
                    - sqs:TagQueue
                    - sqs:UntagQueue
                    - organizations:ListAccounts
                  Effect: Allow
                  Resource:
                    - '*'
                  Sid: iam
              Version: '2012-10-17'
            - PolicyName: terraform-20211018180130834800000002
              Statement:
                - Action:
                    - autoscaling:Describe*
                    - cloudwatch:Get*
                    - cloudwatch:List*
                    - config:BatchGet*
                    - config:List*
                    - config:Select*
                    - ec2:describeregions
                    - ec2:DescribeSubnets
                    - ec2:describevpcendpoints
                    - ec2:DescribeVpcs
                    - iam:*
                    - s3:GetBucketPolicy
                    - s3:GetBucketTagging
                    - s3:ListAllMyBuckets
                    - s3:ListBucket
                    - s3:PutBucketPolicy
                    - s3:PutBucketTagging
                    - sns:GetTopicAttributes
                    - sns:ListTagsForResource
                    - sns:ListTopics
                    - sns:SetTopicAttributes
                    - sns:TagResource
                    - sns:UnTagResource
                    - sqs:GetQueueAttributes
                    - sqs:GetQueueUrl
                    - sqs:ListQueues
                    - sqs:ListQueueTags
                    - sqs:SetQueueAttributes
                    - sqs:TagQueue
                    - sqs:UntagQueue
                    - organizations:ListAccounts
                  Effect: Allow
                  Resource:
                    - '*'
                  Sid: iam
              Version: '2012-10-17'
        proposed_changes:
          - change_type: Delete
            resource_id: ConsoleMeSpokeRole
            resource_type: aws:iam:role
        exceptions_seen: []
      - account: demo-2 - (694815895589)
        resource_id: ConsoleMeSpokeRole
        current_value:
          Path: /
          RoleName: ConsoleMeSpokeRole
          RoleId: AROA2DRSBGAS3HZSCFK36
          Arn: arn:aws:iam::694815895589:role/ConsoleMeSpokeRole
          CreateDate: '2021-10-18T17:46:33+00:00'
          AssumeRolePolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Sid: ConsoleMeAssumesTarget
                Effect: Allow
                Principal:
                  AWS:
                    - arn:aws:iam::694815895589:role/ConsoleMeCentralRole
                    - AROATZAKZJLAO6SLARMN5
                    - arn:aws:iam::972417093400:role/ConsoleMeCentralRole
                Action: sts:AssumeRole
          Description: ''
          MaxSessionDuration: 3600
          RoleLastUsed: {}
          ManagedPolicies: []
          InlinePolicies:
            - PolicyName: terraform-20211018174634611600000001
              Statement:
                - Action:
                    - autoscaling:Describe*
                    - cloudwatch:Get*
                    - cloudwatch:List*
                    - config:BatchGet*
                    - config:List*
                    - config:Select*
                    - ec2:describeregions
                    - ec2:DescribeSubnets
                    - ec2:describevpcendpoints
                    - ec2:DescribeVpcs
                    - iam:*
                    - s3:GetBucketPolicy
                    - s3:GetBucketTagging
                    - s3:ListAllMyBuckets
                    - s3:ListBucket
                    - s3:PutBucketPolicy
                    - s3:PutBucketTagging
                    - sns:GetTopicAttributes
                    - sns:ListTagsForResource
                    - sns:ListTopics
                    - sns:SetTopicAttributes
                    - sns:TagResource
                    - sns:UnTagResource
                    - sqs:GetQueueAttributes
                    - sqs:GetQueueUrl
                    - sqs:ListQueues
                    - sqs:ListQueueTags
                    - sqs:SetQueueAttributes
                    - sqs:TagQueue
                    - sqs:UntagQueue
                    - organizations:ListAccounts
                  Effect: Allow
                  Resource:
                    - '*'
                  Sid: iam
              Version: '2012-10-17'
            - PolicyName: terraform-20211018175426872300000002
              Statement:
                - Action:
                    - autoscaling:Describe*
                    - cloudwatch:Get*
                    - cloudwatch:List*
                    - config:BatchGet*
                    - config:List*
                    - config:Select*
                    - ec2:describeregions
                    - ec2:DescribeSubnets
                    - ec2:describevpcendpoints
                    - ec2:DescribeVpcs
                    - iam:*
                    - s3:GetBucketPolicy
                    - s3:GetBucketTagging
                    - s3:ListAllMyBuckets
                    - s3:ListBucket
                    - s3:PutBucketPolicy
                    - s3:PutBucketTagging
                    - sns:GetTopicAttributes
                    - sns:ListTagsForResource
                    - sns:ListTopics
                    - sns:SetTopicAttributes
                    - sns:TagResource
                    - sns:UnTagResource
                    - sqs:GetQueueAttributes
                    - sqs:GetQueueUrl
                    - sqs:ListQueues
                    - sqs:ListQueueTags
                    - sqs:SetQueueAttributes
                    - sqs:TagQueue
                    - sqs:UntagQueue
                    - organizations:ListAccounts
                  Effect: Allow
                  Resource:
                    - '*'
                  Sid: iam
              Version: '2012-10-17'
        proposed_changes:
          - change_type: Delete
            resource_id: ConsoleMeSpokeRole
            resource_type: aws:iam:role
        exceptions_seen: []
      - account: demo-1 - (972417093400)
        resource_id: ConsoleMeSpokeRole
        current_value:
          Path: /
          RoleName: ConsoleMeSpokeRole
          RoleId: AROA6E2ETJ4MAAJ2KANED
          Arn: arn:aws:iam::972417093400:role/ConsoleMeSpokeRole
          CreateDate: '2021-10-18T18:56:50+00:00'
          AssumeRolePolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Sid: ConsoleMeAssumesTarget
                Effect: Allow
                Principal:
                  AWS:
                    - arn:aws:iam::972417093400:role/ConsoleMeCentralRole
                    - AROATZAKZJLAO6SLARMN5
                Action: sts:AssumeRole
          Description: ''
          MaxSessionDuration: 3600
          RoleLastUsed: {}
          ManagedPolicies: []
          InlinePolicies:
            - PolicyName: iAMPolicy2-040960f
              Statement:
                - Action:
                    - autoscaling:Describe*
                    - cloudwatch:Get*
                    - cloudwatch:List*
                    - config:BatchGet*
                    - config:List*
                    - config:Select*
                    - ec2:describeregions
                    - ec2:DescribeSubnets
                    - ec2:describevpcendpoints
                    - ec2:DescribeVpcs
                    - iam:*
                    - s3:GetBucketPolicy
                    - s3:GetBucketTagging
                    - s3:ListAllMyBuckets
                    - s3:ListBucket
                    - s3:PutBucketPolicy
                    - s3:PutBucketTagging
                    - sns:GetTopicAttributes
                    - sns:ListTagsForResource
                    - sns:ListTopics
                    - sns:SetTopicAttributes
                    - sns:TagResource
                    - sns:UnTagResource
                    - sqs:GetQueueAttributes
                    - sqs:GetQueueUrl
                    - sqs:ListQueues
                    - sqs:ListQueueTags
                    - sqs:SetQueueAttributes
                    - sqs:TagQueue
                    - sqs:UntagQueue
                    - organizations:ListAccounts
                  Effect: Allow
                  Resource:
                    - '*'
                  Sid: iam
              Version: '2012-10-17'
        proposed_changes:
          - change_type: Delete
            resource_id: ConsoleMeSpokeRole
            resource_type: aws:iam:role
        exceptions_seen: []
      - account: demo-3 - (518317429440)
        resource_id: ConsoleMeSpokeRole
        current_value:
          Path: /
          RoleName: ConsoleMeSpokeRole
          RoleId: AROAXRLRAKLAHL22IWBOW
          Arn: arn:aws:iam::518317429440:role/ConsoleMeSpokeRole
          CreateDate: '2021-10-18T17:47:07+00:00'
          AssumeRolePolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Sid: ConsoleMeAssumesTarget
                Effect: Allow
                Principal:
                  AWS: arn:aws:iam::518317429440:role/ConsoleMeCentralRole
                Action: sts:AssumeRole
              - Effect: Allow
                Principal:
                  AWS: AROA6E2ETJ4MHYRF62AS5
                Action:
                  - sts:AssumeRole
                  - sts:TagSession
              - Effect: Allow
                Principal:
                  AWS: AROA6E2ETJ4MHYRF62AS5
                Action:
                  - sts:AssumeRole
                  - sts:TagSession
              - Effect: Allow
                Principal:
                  AWS: AROA6E2ETJ4MHYRF62AS5
                Action:
                  - sts:AssumeRole
                  - sts:TagSession
              - Effect: Allow
                Principal:
                  AWS: AROA6E2ETJ4MHYRF62AS5
                Action:
                  - sts:AssumeRole
                  - sts:TagSession
          Description: ''
          MaxSessionDuration: 3600
          Tags:
            - Key: noq-authorized-demo
              Value: rohit@noq.dev
          RoleLastUsed:
            LastUsedDate: '2022-11-07T19:47:51+00:00'
            Region: us-east-1
          ManagedPolicies: []
          InlinePolicies:
            - PolicyName: terraform-20211018174708352800000001
              Statement:
                - Action:
                    - autoscaling:Describe*
                    - cloudwatch:Get*
                    - cloudwatch:List*
                    - config:BatchGet*
                    - config:List*
                    - config:Select*
                    - ec2:describeregions
                    - ec2:DescribeSubnets
                    - ec2:describevpcendpoints
                    - ec2:DescribeVpcs
                    - iam:*
                    - s3:GetBucketPolicy
                    - s3:GetBucketTagging
                    - s3:ListAllMyBuckets
                    - s3:ListBucket
                    - s3:PutBucketPolicy
                    - s3:PutBucketTagging
                    - sns:GetTopicAttributes
                    - sns:ListTagsForResource
                    - sns:ListTopics
                    - sns:SetTopicAttributes
                    - sns:TagResource
                    - sns:UnTagResource
                    - sqs:GetQueueAttributes
                    - sqs:GetQueueUrl
                    - sqs:ListQueues
                    - sqs:ListQueueTags
                    - sqs:SetQueueAttributes
                    - sqs:TagQueue
                    - sqs:UntagQueue
                    - organizations:ListAccounts
                  Effect: Allow
                  Resource:
                    - '*'
                  Sid: iam
              Version: '2012-10-17'
            - PolicyName: terraform-20211018175446299400000002
              Statement:
                - Action:
                    - autoscaling:Describe*
                    - cloudwatch:Get*
                    - cloudwatch:List*
                    - config:BatchGet*
                    - config:List*
                    - config:Select*
                    - ec2:describeregions
                    - ec2:DescribeSubnets
                    - ec2:describevpcendpoints
                    - ec2:DescribeVpcs
                    - iam:*
                    - s3:GetBucketPolicy
                    - s3:GetBucketTagging
                    - s3:ListAllMyBuckets
                    - s3:ListBucket
                    - s3:PutBucketPolicy
                    - s3:PutBucketTagging
                    - sns:GetTopicAttributes
                    - sns:ListTagsForResource
                    - sns:ListTopics
                    - sns:SetTopicAttributes
                    - sns:TagResource
                    - sns:UnTagResource
                    - sqs:GetQueueAttributes
                    - sqs:GetQueueUrl
                    - sqs:ListQueues
                    - sqs:ListQueueTags
                    - sqs:SetQueueAttributes
                    - sqs:TagQueue
                    - sqs:UntagQueue
                    - organizations:ListAccounts
                  Effect: Allow
                  Resource:
                    - '*'
                  Sid: iam
              Version: '2012-10-17'
        proposed_changes:
          - change_type: Delete
            resource_id: ConsoleMeSpokeRole
            resource_type: aws:iam:role
        exceptions_seen: []
    exceptions_seen: []
  - resource_id: iambic_test_4327
    resource_type: aws:iam:role
    template_path: ./resources/aws/roles/multi_account/iambic_test_4327.yaml
    proposed_changes:
      - account: Noq Audit - (420317713496)
        resource_id: iambic_test_4327
        current_value:
          Path: /iambic_test/
          RoleName: iambic_test_4327
          RoleId: AROAWDXHDKRMCMGYTXK3Z
          Arn: arn:aws:iam::420317713496:role/iambic_test/iambic_test_4327
          CreateDate: '2023-01-09T15:21:36+00:00'
          AssumeRolePolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Deny
                Principal:
                  Service: ec2.amazonaws.com
                Action: sts:AssumeRole
          Description: Updated description
          MaxSessionDuration: 3600
          RoleLastUsed: {}
          ManagedPolicies: []
          InlinePolicies: []
        proposed_changes:
          - change_type: Delete
            resource_id: iambic_test_4327
            resource_type: aws:iam:role
        exceptions_seen: []
      - account: global_tenant_data_prod - (306086318698)
        resource_id: iambic_test_4327
        current_value:
          Path: /iambic_test/
          RoleName: iambic_test_4327
          RoleId: AROAUORBKSJVLXNP6QSPO
          Arn: arn:aws:iam::306086318698:role/iambic_test/iambic_test_4327
          CreateDate: '2023-01-09T15:21:36+00:00'
          AssumeRolePolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Deny
                Principal:
                  Service: ec2.amazonaws.com
                Action: sts:AssumeRole
          Description: Updated description
          MaxSessionDuration: 3600
          RoleLastUsed: {}
          ManagedPolicies: []
          InlinePolicies: []
        proposed_changes:
          - change_type: Delete
            resource_id: iambic_test_4327
            resource_type: aws:iam:role
        exceptions_seen: []
      - account: zelkova - (894599878328)
        resource_id: iambic_test_4327
        current_value:
          Path: /iambic_test/
          RoleName: iambic_test_4327
          RoleId: AROA5ASSO224DRHWEMTEC
          Arn: arn:aws:iam::894599878328:role/iambic_test/iambic_test_4327
          CreateDate: '2023-01-09T15:21:36+00:00'
          AssumeRolePolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Deny
                Principal:
                  Service: ec2.amazonaws.com
                Action: sts:AssumeRole
          Description: Updated description
          MaxSessionDuration: 3600
          RoleLastUsed: {}
          ManagedPolicies: []
          InlinePolicies: []
        proposed_changes:
          - change_type: Delete
            resource_id: iambic_test_4327
            resource_type: aws:iam:role
        exceptions_seen: []
      - account: nonstandard_org_role - (869532243584)
        resource_id: iambic_test_4327
        current_value:
          Path: /iambic_test/
          RoleName: iambic_test_4327
          RoleId: AROA4U5BJC2ANLXIAZ3FM
          Arn: arn:aws:iam::869532243584:role/iambic_test/iambic_test_4327
          CreateDate: '2023-01-09T15:21:36+00:00'
          AssumeRolePolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Deny
                Principal:
                  Service: ec2.amazonaws.com
                Action: sts:AssumeRole
          Description: Updated description
          MaxSessionDuration: 3600
          RoleLastUsed: {}
          ManagedPolicies: []
          InlinePolicies: []
        proposed_changes:
          - change_type: Delete
            resource_id: iambic_test_4327
            resource_type: aws:iam:role
        exceptions_seen: []
      - account: test - (242350334841)
        resource_id: iambic_test_4327
        current_value:
          Path: /iambic_test/
          RoleName: iambic_test_4327
          RoleId: AROATQ3JUUN4UGPEVNARF
          Arn: arn:aws:iam::242350334841:role/iambic_test/iambic_test_4327
          CreateDate: '2023-01-09T15:21:36+00:00'
          AssumeRolePolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Deny
                Principal:
                  Service: ec2.amazonaws.com
                Action: sts:AssumeRole
          Description: Updated description
          MaxSessionDuration: 3600
          RoleLastUsed: {}
          ManagedPolicies: []
          InlinePolicies: []
        proposed_changes:
          - change_type: Delete
            resource_id: iambic_test_4327
            resource_type: aws:iam:role
        exceptions_seen: []
      - account: production - (940552945933)
        resource_id: iambic_test_4327
        current_value:
          Path: /iambic_test/
          RoleName: iambic_test_4327
          RoleId: AROA5V7KTAEG2VGPCN33G
          Arn: arn:aws:iam::940552945933:role/iambic_test/iambic_test_4327
          CreateDate: '2023-01-09T15:21:36+00:00'
          AssumeRolePolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Deny
                Principal:
                  Service: ec2.amazonaws.com
                Action: sts:AssumeRole
          Description: Updated description
          MaxSessionDuration: 3600
          RoleLastUsed: {}
          ManagedPolicies: []
          InlinePolicies: []
        proposed_changes:
          - change_type: Delete
            resource_id: iambic_test_4327
            resource_type: aws:iam:role
        exceptions_seen: []
      - account: demo-2 - (694815895589)
        resource_id: iambic_test_4327
        current_value:
          Path: /iambic_test/
          RoleName: iambic_test_4327
          RoleId: AROA2DRSBGAS4ESX6VECU
          Arn: arn:aws:iam::694815895589:role/iambic_test/iambic_test_4327
          CreateDate: '2023-01-09T15:21:36+00:00'
          AssumeRolePolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Deny
                Principal:
                  Service: ec2.amazonaws.com
                Action: sts:AssumeRole
          Description: Updated description
          MaxSessionDuration: 3600
          RoleLastUsed: {}
          ManagedPolicies: []
          InlinePolicies: []
        proposed_changes:
          - change_type: Delete
            resource_id: iambic_test_4327
            resource_type: aws:iam:role
        exceptions_seen: []
      - account: '@!#!@#)(%*#R)QWITFGO)FG+=0984 - (969947703986)'
        resource_id: iambic_test_4327
        current_value:
          Path: /iambic_test/
          RoleName: iambic_test_4327
          RoleId: AROA6DVLDNKZEUKWIDLOU
          Arn: arn:aws:iam::969947703986:role/iambic_test/iambic_test_4327
          CreateDate: '2023-01-09T15:21:36+00:00'
          AssumeRolePolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Deny
                Principal:
                  Service: ec2.amazonaws.com
                Action: sts:AssumeRole
          Description: Updated description
          MaxSessionDuration: 3600
          RoleLastUsed: {}
          ManagedPolicies: []
          InlinePolicies: []
        proposed_changes:
          - change_type: Delete
            resource_id: iambic_test_4327
            resource_type: aws:iam:role
        exceptions_seen: []
      - account: demo-1 - (972417093400)
        resource_id: iambic_test_4327
        current_value:
          Path: /iambic_test/
          RoleName: iambic_test_4327
          RoleId: AROA6E2ETJ4MLG6VXQJZY
          Arn: arn:aws:iam::972417093400:role/iambic_test/iambic_test_4327
          CreateDate: '2023-01-09T15:21:36+00:00'
          AssumeRolePolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Deny
                Principal:
                  Service: ec2.amazonaws.com
                Action: sts:AssumeRole
          Description: Updated description
          MaxSessionDuration: 3600
          RoleLastUsed: {}
          ManagedPolicies: []
          InlinePolicies: []
        proposed_changes:
          - change_type: Delete
            resource_id: iambic_test_4327
            resource_type: aws:iam:role
        exceptions_seen: []
      - account: Noq Log Archive - (430422300865)
        resource_id: iambic_test_4327
        current_value:
          Path: /iambic_test/
          RoleName: iambic_test_4327
          RoleId: AROAWINZLDDA3XUEP2J4N
          Arn: arn:aws:iam::430422300865:role/iambic_test/iambic_test_4327
          CreateDate: '2023-01-09T15:21:36+00:00'
          AssumeRolePolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Deny
                Principal:
                  Service: ec2.amazonaws.com
                Action: sts:AssumeRole
          Description: Updated description
          MaxSessionDuration: 3600
          RoleLastUsed: {}
          ManagedPolicies: []
          InlinePolicies: []
        proposed_changes:
          - change_type: Delete
            resource_id: iambic_test_4327
            resource_type: aws:iam:role
        exceptions_seen: []
    exceptions_seen: []
  - resource_id: iambic_test_505
    resource_type: aws:iam:role
    template_path: ./resources/aws/roles/multi_account/iambic_test_505.yaml
    proposed_changes:
      - account: Noq Audit - (420317713496)
        resource_id: iambic_test_505
        current_value:
          Path: /iambic_test/
          RoleName: iambic_test_505
          RoleId: AROAWDXHDKRMGXEJYVLJM
          Arn: arn:aws:iam::420317713496:role/iambic_test/iambic_test_505
          CreateDate: '2023-01-09T15:11:13+00:00'
          AssumeRolePolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Deny
                Principal:
                  Service: ec2.amazonaws.com
                Action: sts:AssumeRole
          Description: This was created by a functional test.
          MaxSessionDuration: 3600
          RoleLastUsed: {}
          ManagedPolicies: []
          InlinePolicies: []
        proposed_changes:
          - change_type: Delete
            resource_id: iambic_test_505
            resource_type: aws:iam:role
        exceptions_seen: []
      - account: global_tenant_data_prod - (306086318698)
        resource_id: iambic_test_505
        current_value:
          Path: /iambic_test/
          RoleName: iambic_test_505
          RoleId: AROAUORBKSJVHA7ETEYHY
          Arn: arn:aws:iam::306086318698:role/iambic_test/iambic_test_505
          CreateDate: '2023-01-09T15:11:13+00:00'
          AssumeRolePolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Deny
                Principal:
                  Service: ec2.amazonaws.com
                Action: sts:AssumeRole
          Description: This was created by a functional test.
          MaxSessionDuration: 3600
          RoleLastUsed: {}
          ManagedPolicies: []
          InlinePolicies: []
        proposed_changes:
          - change_type: Delete
            resource_id: iambic_test_505
            resource_type: aws:iam:role
        exceptions_seen: []
      - account: zelkova - (894599878328)
        resource_id: iambic_test_505
        current_value:
          Path: /iambic_test/
          RoleName: iambic_test_505
          RoleId: AROA5ASSO224N5UENNAJG
          Arn: arn:aws:iam::894599878328:role/iambic_test/iambic_test_505
          CreateDate: '2023-01-09T15:11:13+00:00'
          AssumeRolePolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Deny
                Principal:
                  Service: ec2.amazonaws.com
                Action: sts:AssumeRole
          Description: This was created by a functional test.
          MaxSessionDuration: 3600
          RoleLastUsed: {}
          ManagedPolicies: []
          InlinePolicies: []
        proposed_changes:
          - change_type: Delete
            resource_id: iambic_test_505
            resource_type: aws:iam:role
        exceptions_seen: []
      - account: nonstandard_org_role - (869532243584)
        resource_id: iambic_test_505
        current_value:
          Path: /iambic_test/
          RoleName: iambic_test_505
          RoleId: AROA4U5BJC2AP3LUUJKO3
          Arn: arn:aws:iam::869532243584:role/iambic_test/iambic_test_505
          CreateDate: '2023-01-09T15:11:13+00:00'
          AssumeRolePolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Deny
                Principal:
                  Service: ec2.amazonaws.com
                Action: sts:AssumeRole
          Description: This was created by a functional test.
          MaxSessionDuration: 3600
          RoleLastUsed: {}
          ManagedPolicies: []
          InlinePolicies: []
        proposed_changes:
          - change_type: Delete
            resource_id: iambic_test_505
            resource_type: aws:iam:role
        exceptions_seen: []
      - account: test - (242350334841)
        resource_id: iambic_test_505
        current_value:
          Path: /iambic_test/
          RoleName: iambic_test_505
          RoleId: AROATQ3JUUN4XPL2V7UW4
          Arn: arn:aws:iam::242350334841:role/iambic_test/iambic_test_505
          CreateDate: '2023-01-09T15:11:13+00:00'
          AssumeRolePolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Deny
                Principal:
                  Service: ec2.amazonaws.com
                Action: sts:AssumeRole
          Description: This was created by a functional test.
          MaxSessionDuration: 3600
          RoleLastUsed: {}
          ManagedPolicies: []
          InlinePolicies: []
        proposed_changes:
          - change_type: Delete
            resource_id: iambic_test_505
            resource_type: aws:iam:role
        exceptions_seen: []
      - account: production - (940552945933)
        resource_id: iambic_test_505
        current_value:
          Path: /iambic_test/
          RoleName: iambic_test_505
          RoleId: AROA5V7KTAEGS2DSLD4KU
          Arn: arn:aws:iam::940552945933:role/iambic_test/iambic_test_505
          CreateDate: '2023-01-09T15:11:13+00:00'
          AssumeRolePolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Deny
                Principal:
                  Service: ec2.amazonaws.com
                Action: sts:AssumeRole
          Description: This was created by a functional test.
          MaxSessionDuration: 3600
          RoleLastUsed: {}
          ManagedPolicies: []
          InlinePolicies: []
        proposed_changes:
          - change_type: Delete
            resource_id: iambic_test_505
            resource_type: aws:iam:role
        exceptions_seen: []
      - account: demo-2 - (694815895589)
        resource_id: iambic_test_505
        current_value:
          Path: /iambic_test/
          RoleName: iambic_test_505
          RoleId: AROA2DRSBGASQ543SUJEY
          Arn: arn:aws:iam::694815895589:role/iambic_test/iambic_test_505
          CreateDate: '2023-01-09T15:11:13+00:00'
          AssumeRolePolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Deny
                Principal:
                  Service: ec2.amazonaws.com
                Action: sts:AssumeRole
          Description: This was created by a functional test.
          MaxSessionDuration: 3600
          RoleLastUsed: {}
          ManagedPolicies: []
          InlinePolicies: []
        proposed_changes:
          - change_type: Delete
            resource_id: iambic_test_505
            resource_type: aws:iam:role
        exceptions_seen: []
      - account: '@!#!@#)(%*#R)QWITFGO)FG+=0984 - (969947703986)'
        resource_id: iambic_test_505
        current_value:
          Path: /iambic_test/
          RoleName: iambic_test_505
          RoleId: AROA6DVLDNKZCVM5ZTQJC
          Arn: arn:aws:iam::969947703986:role/iambic_test/iambic_test_505
          CreateDate: '2023-01-09T15:11:13+00:00'
          AssumeRolePolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Deny
                Principal:
                  Service: ec2.amazonaws.com
                Action: sts:AssumeRole
          Description: This was created by a functional test.
          MaxSessionDuration: 3600
          RoleLastUsed: {}
          ManagedPolicies: []
          InlinePolicies: []
        proposed_changes:
          - change_type: Delete
            resource_id: iambic_test_505
            resource_type: aws:iam:role
        exceptions_seen: []
      - account: demo-1 - (972417093400)
        resource_id: iambic_test_505
        current_value:
          Path: /iambic_test/
          RoleName: iambic_test_505
          RoleId: AROA6E2ETJ4MJ2WVUFBFE
          Arn: arn:aws:iam::972417093400:role/iambic_test/iambic_test_505
          CreateDate: '2023-01-09T15:11:13+00:00'
          AssumeRolePolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Deny
                Principal:
                  Service: ec2.amazonaws.com
                Action: sts:AssumeRole
          Description: This was created by a functional test.
          MaxSessionDuration: 3600
          RoleLastUsed: {}
          ManagedPolicies: []
          InlinePolicies: []
        proposed_changes:
          - change_type: Delete
            resource_id: iambic_test_505
            resource_type: aws:iam:role
        exceptions_seen: []
      - account: Noq Log Archive - (430422300865)
        resource_id: iambic_test_505
        current_value:
          Path: /iambic_test/
          RoleName: iambic_test_505
          RoleId: AROAWINZLDDAV2JO5CVJD
          Arn: arn:aws:iam::430422300865:role/iambic_test/iambic_test_505
          CreateDate: '2023-01-09T15:11:13+00:00'
          AssumeRolePolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Deny
                Principal:
                  Service: ec2.amazonaws.com
                Action: sts:AssumeRole
          Description: This was created by a functional test.
          MaxSessionDuration: 3600
          RoleLastUsed: {}
          ManagedPolicies: []
          InlinePolicies: []
        proposed_changes:
          - change_type: Delete
            resource_id: iambic_test_505
            resource_type: aws:iam:role
        exceptions_seen: []
    exceptions_seen: []
  - resource_id: AutoCreateTest
    resource_type: aws:iam:role
    template_path: ./resources/aws/roles/staging/autocreatetest.yaml
    proposed_changes:
      - account: staging - (259868150464)
        resource_id: AutoCreateTest
        current_value:
          Path: /
          RoleName: AutoCreateTest
          RoleId: AROATZAKZJLAEIJ65HNIB
          Arn: arn:aws:iam::259868150464:role/AutoCreateTest
          CreateDate: '2022-06-07T13:16:19+00:00'
          AssumeRolePolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Sid: '123'
                Effect: Allow
                Principal:
                  Service: ec2.amazonaws.com
                Action: sts:AssumeRole
          Description: Something
          MaxSessionDuration: 3600
          PermissionsBoundary:
            PermissionsBoundaryType: Policy
            PermissionsBoundaryArn: arn:aws:iam::259868150464:policy/bob
          Tags:
            - Key: tesa
              Value: tesf
            - Key: Service
              Value: N/A
            - Key: noq-tra-supported-groups
              Value: user@noq.dev
          RoleLastUsed: {}
          ManagedPolicies: []
          InlinePolicies:
            - PolicyName: noq_curtis_1656429523_kxhd
              Statement:
                - Action:
                    - s3:abortmultipartupload
                    - s3:listbucket
                    - s3:listbucketversions
                    - s3:listmultipartuploadparts*
                    - s3:putobject
                    - s3:putobjecttagging
                    - s3:putobjectversiontagging
                  Effect: Allow
                  Resource:
                    - arn:aws:s3:::noq-local-dev-cache
                    - arn:aws:s3:::noq-local-dev-cache/*
                  Sid: noqcurtis1656429515xsgn
              Version: '2012-10-17'
            - PolicyName: noq_curtis_1659530435_clut
              Statement:
                - Action:
                    - s3:getobject
                    - s3:getobjectacl
                    - s3:getobjecttagging
                    - s3:getobjectversion
                    - s3:getobjectversionacl
                    - s3:getobjectversiontagging
                    - s3:listbucket
                    - s3:listbucketversions
                  Effect: Allow
                  Resource:
                    - arn:aws:s3:::noq-demo2-test-bucket
                    - arn:aws:s3:::noq-demo2-test-bucket/*
                  Sid: noqcurtis1659530431sjrk
              Version: '2012-10-17'
            - PolicyName: noq_delete_on_20220615_user_1655227824
              Statement:
                - Action:
                    - sts:assumerole
                    - sts:tagsession
                  Effect: Allow
                  Resource:
                    - arn:aws:iam::259868150464:role/ConsoleMe1
                  Sid: noquser1655227802xrjl
                - Action:
                    - sqs:deletemessage
                    - sqs:getqueueattributes
                    - sqs:getqueueurl
                    - sqs:purgequeue
                    - sqs:receivemessage
                    - sqs:sendmessage
                    - sqs:setqueueattributes
                  Effect: Allow
                  Resource:
                    - arn:aws:sqs:us-east-1:259868150464:phecfla
                    - arn:aws:sqs:us-west-2:759357822767:testqueue
                  Sid: noquser1655227802ojae
                - Action:
                    - sns:confirmsubscription
                    - sns:getendpointattributes
                    - sns:gettopicattributes
                    - sns:publish
                    - sns:subscribe
                    - sns:unsubscribe
                  Effect: Allow
                  Resource:
                    - arn:aws:sns:us-west-2:759357822767:local-dev-registration-topic
                  Sid: noquser1655227802bnpj
                - Action:
                    - s3:abortmultipartupload
                    - s3:deleteobject
                    - s3:deleteobjecttagging
                    - s3:deleteobjectversion
                    - s3:deleteobjectversiontagging
                    - s3:getobject
                    - s3:getobjectacl
                    - s3:getobjecttagging
                    - s3:getobjectversion
                    - s3:getobjectversionacl
                    - s3:getobjectversiontagging
                    - s3:listbucket
                    - s3:listbucketversions
                    - s3:listmultipartuploadparts*
                    - s3:putobject
                    - s3:putobjecttagging
                    - s3:putobjectversiontagging
                  Effect: Allow
                  Resource:
                    - arn:aws:s3:::ceuswiow
                    - arn:aws:s3:::ceuswiow/*
                  Sid: noquser1655227802qqoa
              Version: '2012-10-17'
            - PolicyName: noq_delete_on_20220618_user_1655496042
              Statement:
                - Action:
                    - s3:abortmultipartupload
                    - s3:getobject
                    - s3:getobjectacl
                    - s3:getobjecttagging
                    - s3:getobjectversion
                    - s3:getobjectversionacl
                    - s3:getobjectversiontagging
                    - s3:listmultipartuploadparts*
                    - s3:putobject
                    - s3:putobjecttagging
                    - s3:putobjectversiontagging
                  Effect: Allow
                  Resource:
                    - arn:aws:s3:::consoleme-dev-test-bucket
                    - arn:aws:s3:::consoleme-dev-test-bucket/*
                  Sid: noquser1655496005ycbh
              Version: '2012-10-17'
            - PolicyName: noq_delete_on_20220628_user_1656338589
              Statement:
                - Action:
                    - sts:assumerole
                    - sts:tagsession
                  Effect: Allow
                  Resource:
                    - arn:aws:iam::259868150464:role/ConsoleMe2
                  Sid: noquser1656338510czhc
                - Action:
                    - sqs:deletemessage
                    - sqs:getqueueattributes
                    - sqs:getqueueurl
                    - sqs:receivemessage
                    - sqs:sendmessage
                  Effect: Allow
                  Resource:
                    - arn:aws:sqs:us-west-2:759357822767:local-dev-registration-queue
                  Sid: noquser1656338510vmcr
                - Action:
                    - s3:abortmultipartupload
                    - s3:getobject
                    - s3:getobjectacl
                    - s3:getobjecttagging
                    - s3:getobjectversion
                    - s3:getobjectversionacl
                    - s3:getobjectversiontagging
                    - s3:listbucket
                    - s3:listbucketversions
                    - s3:listmultipartuploadparts*
                    - s3:putobject
                    - s3:putobjecttagging
                    - s3:putobjectversiontagging
                  Effect: Allow
                  Resource:
                    - arn:aws:s3:::consoleme-dev-configuration-bucket
                    - arn:aws:s3:::consoleme-dev-configuration-bucket/*
                  Sid: noquser1656338510pfcf
              Version: '2012-10-17'
            - PolicyName: noq_delete_on_20220710_user_1657380290
              Statement:
                - Action:
                    - s3:getobject
                    - s3:getobjectacl
                    - s3:getobjecttagging
                    - s3:getobjectversion
                    - s3:getobjectversionacl
                    - s3:getobjectversiontagging
                    - s3:listbucket
                    - s3:listbucketversions
                  Effect: Allow
                  Resource:
                    - arn:aws:s3:::adostoma
                    - arn:aws:s3:::adostoma/*
                  Sid: noquser1657380266wdnx
              Version: '2012-10-17'
            - PolicyName: noq_delete_on_20220711_user_1657381536
              Statement:
                - Action:
                    - s3:getobject
                    - s3:getobjectacl
                    - s3:getobjecttagging
                    - s3:getobjectversion
                    - s3:getobjectversionacl
                    - s3:getobjectversiontagging
                    - s3:listbucket
                    - s3:listbucketversions
                  Effect: Allow
                  Resource:
                    - arn:aws:s3:::cdk-hnb659fds-assets-259868150464-us-east-1
                    - arn:aws:s3:::cdk-hnb659fds-assets-259868150464-us-east-1/*
                  Sid: noquser1657381512ehjm
              Version: '2012-10-17'
            - PolicyName: noq_delete_on_20220914_080000_user_1663097282
              Version: '2012-10-17'
              Statement:
                - Effect: Allow
                  Action:
                    - s3:getbucket*
                    - s3:getobject
                    - s3:getobjectacl
                    - s3:getobjecttagging
                    - s3:getobjectversion
                    - s3:getobjectversionacl
                    - s3:getobjectversiontagging
                    - s3:listbucket
                    - s3:listbucketversions
                  Resource:
                    - arn:aws:s3:::noq-demo2-test-bucket
                    - arn:aws:s3:::noq-demo2-test-bucket/*
                  Sid: noquser1663097254lkqq
            - PolicyName: noq_user_1654644829_rdyf
              Statement:
                - Action:
                    - sns:getendpointattributes
                    - sns:gettopicattributes
                    - sns:publish
                  Effect: Allow
                  Resource:
                    - arn:aws:sns:us-east-1:259868150464:thtaeeduon
                  Sid: noquser1654644822cbog
                - Action:
                    - sqs:deletemessage
                    - sqs:getqueueattributes
                    - sqs:getqueueurl
                    - sqs:receivemessage
                    - sqs:sendmessage
                  Effect: Allow
                  Resource:
                    - arn:aws:sqs:us-east-1:259868150464:phecfla
                  Sid: noquser1654644822liuj
                - Action:
                    - s3:getobject
                    - s3:getobjectacl
                    - s3:getobjecttagging
                    - s3:getobjectversion
                    - s3:getobjectversionacl
                    - s3:getobjectversiontagging
                    - s3:listbucket
                    - s3:listbucketversions
                  Effect: Allow
                  Resource:
                    - arn:aws:s3:::noq-local-dev-cache
                    - arn:aws:s3:::noq-local-dev-cache/*
                  Sid: noquser1654644822qddq
              Version: '2012-10-17'
            - PolicyName: noq_user_1657381790_cxyv
              Statement:
                - Action:
                    - sqs:deletemessage
                    - sqs:getqueueattributes
                    - sqs:getqueueurl
                    - sqs:receivemessage
                    - sqs:sendmessage
                  Effect: Allow
                  Resource:
                    - arn:aws:sqs:us-east-1:350876197038:noq-development-2-test-queue
                  Sid: noquser1657381787loao
              Version: '2012-10-17'
            - PolicyName: noq_user_1657382787_qzdj
              Statement:
                - Action:
                    - s3:getobject
                    - s3:getobjectacl
                    - s3:getobjecttagging
                    - s3:getobjectversion
                    - s3:getobjectversionacl
                    - s3:getobjectversiontagging
                    - s3:listbucket
                    - s3:listbucketversions
                  Effect: Allow
                  Resource:
                    - arn:aws:s3:::noqmeter-us-west-2
                    - arn:aws:s3:::noqmeter-us-west-2/*
                  Sid: noquser1657382782hfao
              Version: '2012-10-17'
            - PolicyName: noq_user_1659130007_vbsa
              Version: '2012-10-17'
              Statement:
                - Action:
                    - s3:abortmultipartupload
                    - s3:deleteobject
                    - s3:deleteobjecttagging
                    - s3:deleteobjectversion
                    - s3:deleteobjectversiontagging
                    - s3:getobject
                    - s3:getobjectacl
                    - s3:getobjecttagging
                    - s3:getobjectversion
                    - s3:getobjectversionacl
                    - s3:getobjectversiontagging
                    - s3:listbucket
                    - s3:listbucketversions
                    - s3:listmultipartuploadparts*
                    - s3:putobject
                    - s3:putobjecttagging
                    - s3:putobjectversiontagging
                  Effect: Allow
                  Resource:
                    - arn:aws:s3:::read-only-test-bucket-2423-5033-4841
                    - arn:aws:s3:::read-only-test-bucket-2423-5033-4841/*
                  Sid: noquser1659129997mxch
            - PolicyName: noq_user_1665875774_rwvx
              Statement:
                - Action:
                    - s3:getbucket*
                    - s3:getobject
                    - s3:getobjectacl
                    - s3:getobjecttagging
                    - s3:getobjectversion
                    - s3:getobjectversionacl
                    - s3:getobjectversiontagging
                    - s3:listbucket
                    - s3:listbucketversions
                  Effect: Allow
                  Resource:
                    - arn:aws:s3:::ceuswiow
                    - arn:aws:s3:::ceuswiow/*
                  Sid: noquser1665875768sdxt
              Version: '2012-10-17'
            - PolicyName: noq_user_1665875828_xjoz
              Statement:
                - Action:
                    - s3:getbucket*
                    - s3:getobject
                    - s3:getobjectacl
                    - s3:getobjecttagging
                    - s3:getobjectversion
                    - s3:getobjectversionacl
                    - s3:getobjectversiontagging
                    - s3:listbucket
                    - s3:listbucketversions
                  Effect: Allow
                  Resource:
                    - arn:aws:s3:::ceuswiow
                    - arn:aws:s3:::ceuswiow/*
                  Sid: noquser1665875768sdxt
              Version: '2012-10-17'
        proposed_changes:
          - change_type: Delete
            resource_id: AutoCreateTest
            resource_type: aws:iam:role
        exceptions_seen: []
    exceptions_seen: []
  - resource_id: CloudWatchToElasticSearchRole
    resource_type: aws:iam:role
    template_path: ./resources/aws/roles/staging/cloudwatchtoelasticsearchrole.yaml
    proposed_changes:
      - account: staging - (259868150464)
        resource_id: CloudWatchToElasticSearchRole
        current_value:
          Path: /
          RoleName: CloudWatchToElasticSearchRole
          RoleId: AROATZAKZJLAPMWOIHJZN
          Arn: arn:aws:iam::259868150464:role/CloudWatchToElasticSearchRole
          CreateDate: '2022-05-02T22:52:35+00:00'
          AssumeRolePolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Allow
                Principal:
                  Service: lambda.amazonaws.com
                Action: sts:AssumeRole
          Description: Role created by curtis@noq.dev through ConsoleMe
          MaxSessionDuration: 3600
          RoleLastUsed:
            LastUsedDate: '2022-05-02T23:05:21+00:00'
            Region: us-west-2
          ManagedPolicies:
            - PolicyName: AWSLambdaVPCAccessExecutionRole
              PolicyArn: arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole
            - PolicyName: AmazonOpenSearchServiceFullAccess
              PolicyArn: arn:aws:iam::aws:policy/AmazonOpenSearchServiceFullAccess
          InlinePolicies: []
        proposed_changes:
          - change_type: Delete
            resource_id: CloudWatchToElasticSearchRole
            resource_type: aws:iam:role
        exceptions_seen: []
    exceptions_seen: []
  - resource_id: ConsoleMe1
    resource_type: aws:iam:role
    template_path: ./resources/aws/roles/staging/consoleme1.yaml
    proposed_changes:
      - account: staging - (259868150464)
        resource_id: ConsoleMe1
        current_value:
          Path: /
          RoleName: ConsoleMe1
          RoleId: AROATZAKZJLAIK2WADW44
          Arn: arn:aws:iam::259868150464:role/ConsoleMe1
          CreateDate: '2021-09-29T15:57:13+00:00'
          AssumeRolePolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Allow
                Principal:
                  AWS: arn:aws:iam::940552945933:role/NoqCentralRoleCorpNoqDev
                Action: sts:AssumeRole
          Description: ''
          MaxSessionDuration: 3600
          Tags:
            - Key: noq-tra-supported-groups
              Value: engineering@noq.dev
            - Key: consoleme-authorized
              Value: bayareasec@gmail.com:ccastrapel@gmail.com
          RoleLastUsed:
            LastUsedDate: '2022-10-27T16:18:46+00:00'
            Region: us-east-2
          ManagedPolicies: []
          InlinePolicies:
            - PolicyName: admin
              Version: '2012-10-17'
              Statement:
                - Action: '*'
                  Effect: Deny
                  Resource: '*'
            - PolicyName: noq_delete_on_20220618_user_1655495329
              Statement:
                - Action:
                    - s3:abortmultipartupload
                    - s3:listbucket
                    - s3:listbucketversions
                    - s3:listmultipartuploadparts*
                    - s3:putobject
                    - s3:putobjecttagging
                    - s3:putobjectversiontagging
                  Effect: Allow
                  Resource:
                    - arn:aws:s3:::consoleme-dev-test-bucket
                    - arn:aws:s3:::consoleme-dev-test-bucket/*
                  Sid: noquser1655495264kkus
              Version: '2012-10-17'
            - PolicyName: noq_user_1654695156_krwp
              Statement:
                - Action:
                    - s3:getobject
                    - s3:getobjectacl
                    - s3:getobjecttagging
                    - s3:getobjectversion
                    - s3:getobjectversionacl
                    - s3:getobjectversiontagging
                    - s3:listbucket
                    - s3:listbucketversions
                  Effect: Allow
                  Resource:
                    - arn:aws:s3:::ceuswiow
                    - arn:aws:s3:::ceuswiow/*
                  Sid: noquser1654695151zcsl
              Version: '2012-10-17'
        proposed_changes:
          - change_type: Delete
            resource_id: ConsoleMe1
            resource_type: aws:iam:role
        exceptions_seen: []
    exceptions_seen: []
  - resource_id: ConsoleMe2
    resource_type: aws:iam:role
    template_path: ./resources/aws/roles/staging/consoleme2.yaml
    proposed_changes:
      - account: staging - (259868150464)
        resource_id: ConsoleMe2
        current_value:
          Path: /
          RoleName: ConsoleMe2
          RoleId: AROATZAKZJLAHD2GGNKAX
          Arn: arn:aws:iam::259868150464:role/ConsoleMe2
          CreateDate: '2021-09-29T16:37:34+00:00'
          AssumeRolePolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Allow
                Principal:
                  AWS: AROATZAKZJLAO6SLARMN5
                Action: sts:AssumeRole
              - Sid: noqdeleteon20220628user1656338589
                Effect: Allow
                Principal:
                  AWS: arn:aws:iam::259868150464:role/AutoCreateTest
                Action:
                  - sts:TagSession
                  - sts:AssumeRole
          Description: Role cloned via ConsoleMe by consoleme_admin@example.com from arn:aws:iam::259868150464:role/ConsoleMe1
          MaxSessionDuration: 3600
          Tags:
            - Key: test
              Value: test
            - Key: consoleme-authorized
              Value: ccastrapel@gmail.com:bayareasec@gmail.com
          RoleLastUsed: {}
          ManagedPolicies:
            - PolicyName: aoiaedraf
              PolicyArn: arn:aws:iam::259868150464:policy/aoiaedraf
          InlinePolicies:
            - PolicyName: cm_consoleme_admin_1632935706_heel
              Statement:
                - Action:
                    - autoscaling:Describe*
                    - cloudwatch:Get*
                    - cloudwatch:List*
                    - config:BatchGet*
                    - config:List*
                    - config:Select*
                    - ec2:describeregions
                    - ec2:DescribeSubnets
                    - ec2:describevpcendpoints
                    - ec2:DescribeVpcs
                    - iam:*
                    - s3:GetBucketPolicy
                    - s3:GetBucketTagging
                    - s3:ListAllMyBuckets
                    - s3:ListBucket
                    - s3:PutBucketPolicy
                    - s3:PutBucketTagging
                    - sns:GetTopicAttributes
                    - sns:ListTagsForResource
                    - sns:ListTopics
                    - sns:SetTopicAttributes
                    - sns:TagResource
                    - sns:UnTagResource
                    - sqs:GetQueueAttributes
                    - sqs:GetQueueUrl
                    - sqs:ListQueues
                    - sqs:ListQueueTags
                    - sqs:SetQueueAttributes
                    - sqs:TagQueue
                    - sqs:UntagQueue
                    - organizations:listaccounts
                  Effect: Allow
                  Resource:
                    - '*'
                  Sid: iam
              Version: '2012-10-17'
            - PolicyName: cm_consoleme_admin_1632937591_bitr
              Statement:
                - Action:
                    - sqs:ReceiveMessage
                    - sqs:SendMessage
                    - sqs:DeleteMessage
                    - sqs:GetQueueUrl
                    - sqs:GetQueueAttributes
                  Effect: Allow
                  Resource: arn:aws:sqs:us-east-1:259868150464:chiyeps
        proposed_changes:
          - change_type: Delete
            resource_id: ConsoleMe2
            resource_type: aws:iam:role
        exceptions_seen: []
    exceptions_seen: []
  - resource_id: daw
    resource_type: aws:iam:role
    template_path: ./resources/aws/roles/staging/daw.yaml
    proposed_changes:
      - account: staging - (259868150464)
        resource_id: daw
        current_value:
          Path: /
          RoleName: daw
          RoleId: AROATZAKZJLANB2VI3NXY
          Arn: arn:aws:iam::259868150464:role/daw
          CreateDate: '2021-10-05T17:12:31+00:00'
          AssumeRolePolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Allow
                Principal:
                  Service: ec2.amazonaws.com
                Action: sts:AssumeRole
              - Effect: Allow
                Principal:
                  AWS: AROATZAKZJLAO6SLARMN5
                Action: sts:AssumeRole
          Description: ''
          MaxSessionDuration: 3600
          Tags:
            - Key: consoleme-authorized
              Value: ccastrapel@gmail.com:bayareasec@gmail.com
          RoleLastUsed: {}
          ManagedPolicies: []
          InlinePolicies: []
        proposed_changes:
          - change_type: Delete
            resource_id: daw
            resource_type: aws:iam:role
        exceptions_seen: []
    exceptions_seen: []
  - resource_id: diseiwetuypora
    resource_type: aws:iam:role
    template_path: ./resources/aws/roles/staging/diseiwetuypora.yaml
    proposed_changes:
      - account: staging - (259868150464)
        resource_id: diseiwetuypora
        current_value:
          Path: /
          RoleName: diseiwetuypora
          RoleId: AROATZAKZJLAG2V7VFQS5
          Arn: arn:aws:iam::259868150464:role/diseiwetuypora
          CreateDate: '2021-10-05T17:12:37+00:00'
          AssumeRolePolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Allow
                Principal:
                  Service: ec2.amazonaws.com
                Action: sts:AssumeRole
              - Effect: Allow
                Principal:
                  AWS: AROATZAKZJLAO6SLARMN5
                Action: sts:AssumeRole
          Description: ''
          MaxSessionDuration: 3600
          Tags:
            - Key: consoleme-authorized
              Value: ccastrapel@gmail.com:bayareasec@gmail.com
          RoleLastUsed: {}
          ManagedPolicies: []
          InlinePolicies: []
        proposed_changes:
          - change_type: Delete
            resource_id: diseiwetuypora
            resource_type: aws:iam:role
        exceptions_seen: []
    exceptions_seen: []
  - resource_id: dob
    resource_type: aws:iam:role
    template_path: ./resources/aws/roles/staging/dob.yaml
    proposed_changes:
      - account: staging - (259868150464)
        resource_id: dob
        current_value:
          Path: /
          RoleName: dob
          RoleId: AROATZAKZJLAH2MAPSWLO
          Arn: arn:aws:iam::259868150464:role/dob
          CreateDate: '2021-10-01T17:30:47+00:00'
          AssumeRolePolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Allow
                Principal:
                  Service: ec2.amazonaws.com
                Action: sts:AssumeRole
              - Effect: Allow
                Principal:
                  AWS: AROATZAKZJLAO6SLARMN5
                Action: sts:AssumeRole
          Description: ''
          MaxSessionDuration: 3600
          Tags:
            - Key: consoleme-authorized
              Value: ccastrapel@gmail.com:bayareasec@gmail.com
          RoleLastUsed: {}
          ManagedPolicies: []
          InlinePolicies: []
        proposed_changes:
          - change_type: Delete
            resource_id: dob
            resource_type: aws:iam:role
        exceptions_seen: []
    exceptions_seen: []
  - resource_id: efoa
    resource_type: aws:iam:role
    template_path: ./resources/aws/roles/staging/efoa.yaml
    proposed_changes:
      - account: staging - (259868150464)
        resource_id: efoa
        current_value:
          Path: /
          RoleName: efoa
          RoleId: AROATZAKZJLAK3KOEYXL3
          Arn: arn:aws:iam::259868150464:role/efoa
          CreateDate: '2021-10-05T17:13:02+00:00'
          AssumeRolePolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Allow
                Principal:
                  Service: ec2.amazonaws.com
                Action: sts:AssumeRole
              - Effect: Allow
                Principal:
                  AWS: AROATZAKZJLAO6SLARMN5
                Action: sts:AssumeRole
          Description: ''
          MaxSessionDuration: 3600
          Tags:
            - Key: consoleme-authorized
              Value: ccastrapel@gmail.com:bayareasec@gmail.com
          RoleLastUsed: {}
          ManagedPolicies: []
          InlinePolicies: []
        proposed_changes:
          - change_type: Delete
            resource_id: efoa
            resource_type: aws:iam:role
        exceptions_seen: []
    exceptions_seen: []
  - resource_id: MattsExperimentingWithWeepProxyRoleTest
    resource_type: aws:iam:role
    template_path: ./resources/aws/roles/staging/mattsexperimentingwithweepproxyroletest.yaml
    proposed_changes:
      - account: staging - (259868150464)
        resource_id: MattsExperimentingWithWeepProxyRoleTest
        current_value:
          Path: /
          RoleName: MattsExperimentingWithWeepProxyRoleTest
          RoleId: AROATZAKZJLAL3YWM2AGN
          Arn: arn:aws:iam::259868150464:role/MattsExperimentingWithWeepProxyRoleTest
          CreateDate: '2022-07-19T20:42:47+00:00'
          AssumeRolePolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Allow
                Principal:
                  Service: ec2.amazonaws.com
                Action: sts:AssumeRole
              - Effect: Allow
                Principal:
                  AWS: arn:aws:iam::940552945933:role/NoqCentralRoleCorpNoqDev
                Action:
                  - sts:AssumeRole
                  - sts:TagSession
              - Effect: Allow
                Principal:
                  AWS: arn:aws:iam::940552945933:role/NoqCentralRoleCorpNoqDev
                Action:
                  - sts:AssumeRole
                  - sts:TagSession
              - Effect: Allow
                Principal:
                  AWS: arn:aws:iam::940552945933:role/NoqCentralRoleCorpNoqDev
                Action:
                  - sts:AssumeRole
                  - sts:TagSession
              - Effect: Allow
                Principal:
                  AWS: arn:aws:iam::940552945933:role/NoqCentralRoleCorpNoqDev
                Action:
                  - sts:AssumeRole
                  - sts:TagSession
              - Effect: Allow
                Principal:
                  AWS: arn:aws:iam::940552945933:role/NoqCentralRoleCorpNoqDev
                Action:
                  - sts:AssumeRole
                  - sts:TagSession
              - Effect: Allow
                Principal:
                  AWS: arn:aws:iam::940552945933:role/NoqCentralRoleCorpNoqDev
                Action:
                  - sts:AssumeRole
                  - sts:TagSession
          Description: The role name is also the description
          MaxSessionDuration: 3600
          Tags:
            - Key: noq-authorized
              Value: engineering@noq.dev
          RoleLastUsed:
            LastUsedDate: '2022-09-02T23:27:43+00:00'
            Region: us-west-2
          ManagedPolicies: []
          InlinePolicies:
            - PolicyName: noq_matt_1658263648_dooy
              Statement:
                - Action:
                    - s3:ListBucket
                    - s3:GetObject
                  Effect: Allow
                  Resource:
                    - arn:aws:s3:::consoleme-dev-test-bucket
                    - arn:aws:s3:::consoleme-dev-test-bucket/*
                  Sid: s3readonly
            - PolicyName: noq_user_1659560951_kocq
              Version: '2012-10-17'
              Statement:
                - Action:
                    - s3:abortmultipartupload
                    - s3:deleteobject
                    - s3:deleteobjecttagging
                    - s3:deleteobjectversion
                    - s3:deleteobjectversiontagging
                    - s3:getobject
                    - s3:getobjectacl
                    - s3:getobjecttagging
                    - s3:getobjectversion
                    - s3:getobjectversionacl
                    - s3:getobjectversiontagging
                    - s3:listbucket
                    - s3:listbucketversions
                    - s3:listmultipartuploadparts*
                    - s3:putobject
                    - s3:putobjecttagging
                    - s3:putobjectversiontagging
                  Effect: Allow
                  Resource:
                    - arn:aws:s3:::my-bucket-1234-noq-1234
                    - arn:aws:s3:::my-bucket-1234-noq-1234/*
                  Sid: noquser1659560872akty
        proposed_changes:
          - change_type: Delete
            resource_id: MattsExperimentingWithWeepProxyRoleTest
            resource_type: aws:iam:role
        exceptions_seen: []
    exceptions_seen: []
  - resource_id: shannon_access_role
    resource_type: aws:iam:role
    template_path: ./resources/aws/roles/unusual_demo/shannon_access_role.yaml
    proposed_changes:
      - account: unusual_demo - (197024362139)
        resource_id: shannon_access_role
        current_value:
          Path: /
          RoleName: shannon_access_role
          RoleId: AROAS3X4RF2NZ6YI4JEHW
          Arn: arn:aws:iam::197024362139:role/shannon_access_role
          CreateDate: '2022-03-08T14:48:33+00:00'
          AssumeRolePolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Allow
                Principal:
                  Service: ec2.amazonaws.com
                Action: sts:AssumeRole
              - Effect: Allow
                Principal:
                  AWS: arn:aws:iam::197024362139:role/NoqCentralRole
                Action:
                  - sts:AssumeRole
                  - sts:TagSession
              - Effect: Allow
                Principal:
                  AWS: arn:aws:iam::197024362139:role/NoqCentralRole
                Action:
                  - sts:AssumeRole
                  - sts:TagSession
              - Effect: Allow
                Principal:
                  AWS: arn:aws:iam::197024362139:role/NoqCentralRole
                Action:
                  - sts:AssumeRole
                  - sts:TagSession
          Description: Role created by curtis@noq.dev through ConsoleMe
          MaxSessionDuration: 3600
          Tags:
            - Key: noq_authorized
              Value: shannon@unusual.vc:curtis@noq.dev:noq_admins
          RoleLastUsed:
            LastUsedDate: '2022-03-11T21:45:50+00:00'
            Region: us-west-2
          ManagedPolicies: []
          InlinePolicies:
            - PolicyName: noq_shannon_1647034634_ahrj
              Version: '2012-10-17'
              Statement:
                - Action:
                    - s3:abortmultipartupload
                    - s3:deleteobject
                    - s3:deleteobjecttagging
                    - s3:deleteobjectversion
                    - s3:deleteobjectversiontagging
                    - s3:getobject
                    - s3:getobjectacl
                    - s3:getobjecttagging
                    - s3:getobjectversion
                    - s3:getobjectversionacl
                    - s3:getobjectversiontagging
                    - s3:listbucket
                    - s3:listbucketversions
                    - s3:listmultipartuploadparts*
                    - s3:putobject
                    - s3:putobjecttagging
                    - s3:putobjectversiontagging
                  Effect: Allow
                  Resource:
                    - arn:aws:s3:::*
                  Sid: cmshannon1647034594vcwr
                - Action:
                    - iam:passrole
                  Effect: Allow
                  Resource:
                    - arn:aws:iam::197024362139:role/rds-monitoring-role
                  Sid: cmshannon1647034594kxfu
                - Action:
                    - ec2:attachvolume
                    - ec2:createvolume
                    - ec2:describelicenses
                    - ec2:describevolumes
                    - ec2:detachvolume
                    - ec2:reportinstancestatus
                    - ec2:resetsnapshotattribute
                  Effect: Allow
                  Resource:
                    - '*'
                  Sid: cmshannon1647034594cwoq
            - PolicyName: noq_shannon_1647035133_nlpr
              Version: '2012-10-17'
              Statement:
                - Action:
                    - s3:abortmultipartupload
                    - s3:deleteobject
                    - s3:deleteobjecttagging
                    - s3:deleteobjectversion
                    - s3:deleteobjectversiontagging
                    - s3:getobject
                    - s3:getobjectacl
                    - s3:getobjecttagging
                    - s3:getobjectversion
                    - s3:getobjectversionacl
                    - s3:getobjectversiontagging
                    - s3:listbucket
                    - s3:listbucketversions
                    - s3:listmultipartuploadparts*
                    - s3:putobject
                    - s3:putobjecttagging
                    - s3:putobjectversiontagging
                  Effect: Allow
                  Resource:
                    - arn:aws:s3:::*
                  Sid: cmshannon1647035119fskh
        proposed_changes:
          - change_type: Delete
            resource_id: shannon_access_role
            resource_type: aws:iam:role
        exceptions_seen: []
    exceptions_seen: []
  - resource_id: unusual_team
    resource_type: aws:iam:role
    template_path: ./resources/aws/roles/unusual_demo/unusual_team.yaml
    proposed_changes:
      - account: unusual_demo - (197024362139)
        resource_id: unusual_team
        current_value:
          Path: /
          RoleName: unusual_team
          RoleId: AROAS3X4RF2NQQZON6VWU
          Arn: arn:aws:iam::197024362139:role/unusual_team
          CreateDate: '2022-03-08T15:29:20+00:00'
          AssumeRolePolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Allow
                Principal:
                  Service: ec2.amazonaws.com
                Action: sts:AssumeRole
              - Effect: Allow
                Principal:
                  AWS: arn:aws:iam::197024362139:role/NoqCentralRole
                Action:
                  - sts:AssumeRole
                  - sts:TagSession
              - Effect: Allow
                Principal:
                  AWS: arn:aws:iam::197024362139:role/NoqCentralRole
                Action:
                  - sts:AssumeRole
                  - sts:TagSession
              - Effect: Allow
                Principal:
                  AWS: arn:aws:iam::197024362139:role/NoqCentralRole
                Action:
                  - sts:AssumeRole
                  - sts:TagSession
          Description: Role created by curtis@noq.dev through ConsoleMe
          MaxSessionDuration: 3600
          Tags:
            - Key: noq_authorized
              Value: shannon@unusual.vc:curtis@noq.dev:noq_admins
          RoleLastUsed:
            LastUsedDate: '2022-03-11T21:30:04+00:00'
            Region: us-east-1
          ManagedPolicies: []
          InlinePolicies: []
        proposed_changes:
          - change_type: Delete
            resource_id: unusual_team
            resource_type: aws:iam:role
        exceptions_seen: []
    exceptions_seen: []
"""


def get_templates():
    return TemplateChangeDetails.parse_obj(yaml.load(template_yaml))


# def test_render_resource_changes():
#     resource_changes = [
#         {'resource_type': 'EC2 Instance', 'resource_id': 'i-1234567890abcdefg', 'action': 'Stop', 'proposed_change': 'None', 'accounts': ['Account A', 'Account B'], 'template_id': 'template_1'},
#         {'resource_type': 'RDS Instance', 'resource_id': 'db-abcdefghijklmno', 'action': 'Delete', 'proposed_change': 'None', 'accounts': ['Account A'], 'template_id': 'template_1'},
#         {'resource_type': 'Lambda Function', 'resource_id': 'arn:aws:lambda:us-west-2:123456789012:function:my-function', 'action': 'Update', 'proposed_change': 'Increase Memory', 'accounts': ['Account B'], 'template_id': 'template_2'},
#         {'resource_type': 'S3 Bucket', 'resource_id': 'my-bucket', 'action': 'Delete', 'proposed_change': 'None', 'accounts': ['Account A', 'Account B'], 'template_id': 'template_2'},
#     ]

#     expected_output = '''
# <table>
#     <thead>
#         <tr>
#             <th>Template ID</th>
#             <th>Account</th>
#             <th>Resource Type</th>
#             <th>Resource ID</th>
#             <th>Action</th>
#             <th>Proposed Change</th>
#         </tr>
#     </thead>
#     <tbody>
#         <tr class="accordion-toggle">
#             <td rowspan="1">template_1</td>
#             <td>Account A</td>
#             <td>RDS Instance</td>
#             <td>db-abcdefghijklmno</td>
#             <td>Delete</td>
#             <td>None</td>
#         </tr>
#             <tr class="accordion-toggle">
#             <td rowspan="1">template_1</td>
#             <td>Account A, Account B</td>
#             <td>EC2 Instance</td>
#             <td>i-1234567890abcdefg</td>
#             <td>Stop</td>
#             <td>None</td>
#         </tr>
#             <tr class="accordion-toggle">
#             <td rowspan="1">template_2</td>
#             <td>Account A, Account B</td>
#             <td>S3 Bucket</td>
#             <td>my-bucket</td>
#             <td>Delete</td>
#             <td>None</td>
#         </tr>
#             <tr class="accordion-toggle">
#             <td rowspan="1">template_2</td>
#             <td>Account B</td>
#             <td>Lambda Function</td>
#             <td>arn:aws:lambda:us-west-2:123456789012:function:my-function</td>
#             <td>Update</td>
#             <td>Increase Memory</td>
#         </tr>
#             </tbody>
# </table>
# '''

#     # Render the actual output
#     actual_output = render_resource_changes(resource_changes)

#     with open("test.md", "w") as f:
#         f.write(actual_output)

#     # Compare the expected and actual output
#     assert actual_output.strip().replace(' ', '') == expected_output.strip().replace(' ', '')


@pytest.mark.parametrize("template_change_details, expected_output", [
    (get_templates(), ActionSummaries),
])
def test_get_template_data(template_change_details, expected_output):
    template_data = get_template_data(template_change_details)
    assert template_data == expected_output
