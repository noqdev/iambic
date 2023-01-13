---
title: AWS
---

## Configure AWS

In this tutorial, you will configure IAMbic for an AWS account or multiple accounts in an AWS organization.

### Prerequisites

You will need administrative-level access to AWS in order to create and manage IAM identities. This level of access is required to create an IAM identity for the use of IAMbic and also to manage policies associated with it.

These credentials should be configured in the terminal you are using to configure Iambic.

You should also be aware of [how AWS credentials are sourced locally](https://docs.aws.amazon.com/sdkref/latest/guide/standardized-credentials.html#credentialProviderChain) by the Amazon SDKs. This will help debug different scenarios, such as credential prioritization and expiration.

<!-- ### 1.1 Obtain AWS Credentials

You will need AWS credentials to perform subsquent steps.

First, create a Hub Role for Iambic. The Hub Role is the role that Iambic uses directly

#### Hub Role Policy

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Action": [
        "sts:assumerole",
        "sts:tagsession"
      ],
      "Effect": "Allow",
      "Resource": [
        "arn:aws:iam::*:role/IambicSpokeRole"
      ]
    }
  ]
}
```

TODO: Define Hub and Spoke Role Permissions

You will need AWS credentials with an appropriate level of permissions before proceeding. IAMbic works on a Hub-and-Spoke model across multiple AWS accounts. It is assumed that you are running IAMbic with direct access with the equivalent of Hub role permissions. We recommend using an IAM role or an AWS SSO permission set as the credentials of these identities are temporary. The use of IAM user should be avoided, if possible. -->

<!-- 1.1.1 Option A: Create an AWS IAM Role

https://docs.aws.amazon.com/IAM/latest/UserGuide/id\_roles\_create.html

1.1.2 Option B: Create an AWS SSO Permission Set

https://docs.aws.amazon.com/singlesignon/latest/userguide/howtocreatepermissionset.html  -->

### 1. Configuring AWS
   
1.1 Write a configuration

You'll need to tell IAMbic how to connect to your AWS account or AWS organization. IAMbic can connect to your AWS accounts or AWS organizations via a number of different methods, Including using a predefined AWS profile, performing assume role operations, or a combination of these. This guide will walk you through the basic configuration. For anything more advanced, please consult the Configuration Reference. (TODO: Link needed)

1.1.1 AWS Organizations

Before starting, you will need your AWS Organizations ID, Organizations name, and administrative-level credentials for your Organization management account.

If you have credentials to your AWS Organizations management account, run `aws organizations describe-organization`. Your Organizations ID is the value of the `Id` parameter.

Use these attributes to create a to create a YAML configuration tailored for your environment, such as the following.

We recommend placing this in your Git repository under `config/config.yaml`

An example configuration is included below:

```
version: '1'
aws:
  organizations:
    - org_id: 'o-12345'
      aws_profile: 'profile_name' # Optional. If not provided, the default profile will be used
      # assume_role_arn is optional. The assume role ARN is processed after the `aws_profile` is used.
      assume_role_arn: 'arn:aws:iam::123456:role/IambicSpokeRole'
      # `org_name` is a required friendly-name for the AWS organization
      org_name: 'main'
      # `identity_center_account` is optional. If you're using AWS Identity Center,
      # specify the account ID and region of your configuration here.
      identity_center_account:
        account_id: '259868150464'
        region: 'us-east-1'
      # `accounts_rules` specifies which accounts Iambic should include or exclude.
      # The configuration below will includ all accounts in the organization.
      account_rules:
        - included_accounts:
            - '*'
          enabled: true
      default_rule:
        enabled: true
```

1.1.2 AWS Accounts

If preferred, you can also connect to accounts individually. In order to do this,


1.2 Test the configuration