[![noqdev - iambic](https://img.shields.io/static/v1?label=noqdev&message=iambic&color=blue&logo=github)](https://github.com/noqdev/iambic "Go to GitHub repo")
[![Supported Versions](https://img.shields.io/pypi/pyversions/iambic-core.svg)](https://pypi.org/project/iambic-core)
[![codecov.io](https://codecov.io/github/noqdev/iambic/coverage.svg?branch=main)](https://codecov.io/github/noqdev/iambic?branch=main)
[![stars - iambic](https://img.shields.io/github/stars/noqdev/iambic?style=social)](https://github.com/noqdev/iambic)
[![forks - iambic](https://img.shields.io/github/forks/noqdev/iambic?style=social)](https://github.com/noqdev/iambic)

[![slack](https://img.shields.io/badge/Slack-4A154B?style=for-the-badge&logo=slack&logoColor=white)](https://communityinviter.com/apps/noqcommunity/noq)

# IAMbic: Cloud IAM as Code

"IAMbic: Version Control for IAM"

IAMbic is designed for DevSecOps, Security, and Compliance teams. It provides enhanced visibility, auditing, and (optionally) control over IAM at scale. It integrates with IAM sources like AWS, Okta, Azure AD, and Google Workspace, consolidating them into a single version control system (Git) in a common, human-readable YAML files that are called "IAMbic templates".

Whether you're managing resources through Terraform, CDK, CloudFormation, manual console operations, or a combination of these, IAMbic keeps your Git repository updated with the real-time state of your cloud IAM. Any IAM change, irrespective of its origin, triggers a git commit. This ensures you have a consolidated Git repository of all your IAM, presented in a common format, complete with a comprehensive audit trail in Git History. This trail details every change, its timestamp, and the responsible entity.

If you'd prefer a hands-off approach, IAMbic can function purely as an auditing and visibility tool to have increased visibility over IAM changes, as mentioned above. But you can also use IAMbic to manage and prevent drift on the IAM resources that you specify. IAMbic templates are bi-directional, which means IAMbic can also write IAM changes back to the cloud through your CI/CD pipeline. A pull request with the desired change would be created in GitHub, approved, and then reflected back in the cloud and Git. Additionally, IAMbic lets you declare temporary access or permissions - It will take care of expiring and removing policies after a defined expiration period. Examples of this are [in IAMbic's Quick Start Guide](https://docs.iambic.org/getting_started/aws#32---create-temporary-expiring-iam-permissions).

If you'd like to learn more about the Github Pull-Request flow for making IAM changes, Check out an example on our [GitOps/IAMOps Philosophy page](https://docs.iambic.org/reference/iamops_philosophy#guide-to-the-iambic-apply-process). We also have a [sample iambic-templates repository](https://github.com/noqdev/iambic-templates-examples), which is fully managed by IAMbic.

Discover more at [https://docs.iambic.org](https://docs.iambic.org), and check out [BeABetterDev's IAMbic Overview and Deep Dive video](https://www.youtube.com/watch?v=ryEseI_-12o) on YouTube. We're also on [Slack](https://communityinviter.com/apps/noqcommunity/noq) if you'd like help getting started or have any questions.

## Key Features

<!-- Keep this in sync with the list of features in the IAMbic Docs Overview Page -->

- **[Version Control for IAM](https://docs.iambic.org/reference/iamops_philosophy)**: IAMbic helps you audit and (optionally) manage IAM from different sources by bringing them together into one Git repository in an easy-to-read format.
- **[Comprehensive audit trail](https://github.com/noqdev/iambic-templates-examples/commits/main)**: IAMbic creates Git commits for all IAM changes, regardless of how they take place. This gives you a comprehensive audit trail in Git history.
- **[Temporary Access and Permissions](https://docs.iambic.org/getting_started/aws#32---create-temporary-expiring-iam-permissions)**: Declaratively define and automate expiration dates for resources, permissions, and access rules.
- **[Drift Prevention](https://docs.iambic.org/how_to_guides/prevent-drift)**: Protect the IAM resources you want to be exclusively managed via IAMbic. IAMbic will automatically revert any out-of-band changes to those resources.
- **[Dynamic AWS Permissions](https://docs.iambic.org/getting_started/aws#31---create-dynamic-iam-role-policies-that-vary-per-account)**: Simplify multi-account AWS management with flexible templates, allowing multi-account roles to have different permissions and access rules on different accounts.
- **Centralized Management**: IAMbic keeps Git updated with the latest, complete state of your cloud environment, maintaining a single source of truth for auditing and compliance across multiple cloud providers in Git.
- **Extendable**: Integrate with various clouds and applications through a powerful plugin architecture.
- **Auditable**: Track changes to IAM policies, permissions, and rules with Git history. For AWS, IAmbic annotates out-of-band commits with details from CloudTrail.

Check out [IAMbic IAMOps Philosophy](https://docs.iambic.org/reference/iamops_philosophy) and an [example IAMbic templates repository](https://github.com/noqdev/iambic-templates-examples) to see a real-life example of IAMbic.

## 📣 Let's chat

Do you want to connect with our contributors?

Just click the button below and follow the instructions.

[![slack](https://img.shields.io/badge/Slack-4A154B?style=for-the-badge&logo=slack&logoColor=white)](https://communityinviter.com/apps/noqcommunity/noq)

## Getting Started

Dive into IAMbic with our [quick-start guide](http://docs.iambic.org/getting_started/) and explore powerful
[template examples](https://github.com/noqdev/iambic-templates-examples/) for AWS Multi-Account Roles,
Identity Center (SSO) Permission Sets, Service Control Policies, Dynamic Permissions,
Okta Applications and Group Assignments, Azure Active Directory Users and Groups, and Google Workspace Group Assignments.

We are rapidly expanding support for existing resources and cloud providers, so check back often!

## Installing IAMbic and Supported Versions

IAMbic is available on PyPI:

```console
python -m pip install iambic-core
```

IAMbic officially supports Python 3.9+.

### Template Examples

Here are some examples showcasing IAMbic's capabilities:

#### AWS Multi-Account Cloudwatch Role

Create a Cloudwatch role with static permissions across three accounts, dynamically generating role names based on the account the role is deployed to. This template would result in the creation of three roles: "dev_cloudwatch",
"staging_cloudwatch", and "prod_cloudwatch" on the respective AWS accounts.

See the [Getting Started guide for AWS](https://docs.iambic.org/getting_started/aws), the AWS IAM Role section of our [Example Templates repository](https://github.com/noqdev/iambic-templates-examples/blob/main/resources/aws/iam/role/all_accounts/account_name_iambic_test_role.yaml), and our [blog post on multi-account roles](https://www.noq.dev/blog/aws-permission-bouncers-letting-loose-in-dev-keeping-it-tight-in-prod) for more information.

```yaml
template_type: NOQ::AWS::IAM::Role
identifier: '{{var.account_name}}_cloudwatch'
included_accounts:
    - dev
    - staging
    - prod
properties:
  description:
    - description: Cloudwatch role for {{var.account_name}}
  assume_role_policy_document:
    statement:
      - action:
          - sts:AssumeRole
          - sts:TagSession
        effect: Allow
        principal:
          aws: arn:aws:iam::123456789012:role/ExampleRole
    version: '2012-10-17'
  inline_policies:
    policy_name: cloudwatch_logs
    statement:
      - effect: allow
        action:
            - logs:DescribeLogGroups
            - logs:DescribeLogStreams
            - logs:GetLogEvents
            - logs:GetLogRecord
            - logs:GetQueryResults
            - logs:TestMetricFilter
            - logs:FilterLogEvents
            - logs:StartQuery
            - logs:StopQuery
        resource: "*"
  managed_policies:
    - policy_arn: arn:aws:iam::aws:policy/AdministratorAccess
  role_name: '{{var.account_name}}_cloudwatch'
  tags:
    - key: owner
      value: devops
```

### AWS Dynamic Permissions

Create a BackendDeveloperRole with varying permissions based on the AWS account. See the [Getting Started guide for AWS](https://docs.iambic.org/getting_started/aws) for more information.

```yaml
template_type: NOQ::AWS::IAM::Role
identifier: '{{var.account_name}}_backend_developer'
included_accounts:
  - '*'
excluded_accounts:
  - compliance
properties:
  description:
    - description: Backend developer role for {{var.account_name}}
  assume_role_policy_document:
    statement:
      - action:
          - sts:AssumeRole
          - sts:TagSession
        effect: Allow
        principal:
          aws: arn:aws:iam::123456789012:role/ExampleRole
    version: '2012-10-17'
  inline_policies:
    - policy_name: s3_policy
      statement:
        - # Policy applies to role on all accounts except `customer_data`.
          excluded_accounts:
            - customer_data
          effect: allow
          action:
              - s3:GetObject
              - s3:ListObject
          resource:
              - "*"
          condition:
            StringNotEquals:
                s3:ResourceTag/sensitive: 'true'
        - # Allow write access to non-sensitive resources on the dev account
          included_accounts:
            - dev
          effect: allow
          action:
              - s3:PutObject
          resource:
              - "*"
          condition:
                StringNotEquals:
                    s3:ResourceTag/sensitive: 'true'
  role_name: '{{var.account_name}}_backend_developer'
  tags:
    - key: owner
      value: devops
```

### AWS Identity Center (SSO) Permission Sets

Create an AWS Identity Center (SSO) permission set with varying permissions based on the AWS account. See the [Getting Started guide for AWS](https://docs.iambic.org/getting_started/aws), the AWS IC/SSO Permission Set section of our [Example Templates repository](https://github.com/noqdev/iambic-templates-examples/blob/main/resources/aws/identity_center/permission_set/design.yaml), and our blog post on [Tailoring AWS Identity Center (SSO) Permissions Per Account with IAMbic](https://www.noq.dev/blog/tailor-aws-identity-center-sso-permissions-per-account-with-iambic) for more information.

```yaml
template_type: NOQ::AWS::IdentityCenter::PermissionSet
access_rules:
  - expires_at: 2028-05-19T14:17 UTC
    groups:
      - engineering
identifier: design
properties:
  name: design
  customer_managed_policy_references:
    - name: base_deny
  inline_policy:
    statement:
      - action:
          - ec2:list*
        effect: Deny
        resource:
          - '*'
      - action:
          - ec2:list*
        effect: Deny
        expires_at: 2033-05-19T14:17 UTC
        resource:
          - '*'
  managed_policies:
    - arn: arn:aws:iam::aws:policy/AWSHealthFullAccess
  permissions_boundary:
    customer_managed_policy_reference:
      name: base_permission_boundary
  session_duration: PT4H
  tags:
    - key: owner
      value: design@example.com
```

### Okta Application Assignments

Manage Okta application assignments, including expiration dates for specific users. See the [Getting Started guide for Okta](https://docs.iambic.org/getting_started/okta) for more information.

```yaml
template_type: NOQ::Okta::App
idp_name: development
properties:
  name: Salesforce.com
  assignments:
    - user: username@example.com
    - user: username2@example.com
    - user: username3@example.com
      expires_at: 2023-09-01T00:00 UTC
  status: ACTIVE
```

### AWS Service Control Policies

Managing access to AWS services can be a tricky business. That's where Service Control Policies (SCPs) come in. SCPs allow you to define what services and actions are accessible within your AWS accounts. With IAMbic, you can import your existing SCPs, create new ones that restrict access to specific AWS services, and prevent any drift from occurring to ensure that you're protecting sensitive information the way you intend.

For instance, let's say you want to limit access to certain AWS regions. You can create an SCP that denies access to all regions except those you specify. This can be particularly useful if you're looking to maintain tighter control over your data residency and compliance.

Here's an example of how you can set this up:

```yaml
template_type: NOQ::AWS::Organizations::SCP
account_id: '123456789012'
iambic_managed: enforced
identifier: RestrictRegions
org_id: o-123456
properties:
  policy_document:
    statement:
      - condition:
          StringNotEquals:
            aws:RequestedRegion:
              - us-east-1
              - us-west-2
        effect: Deny
        not_action:
          - a4b:*
          - budgets:*
          - ce:*
          - chime:*
          - cloudfront:*
          - cur:*
          - globalaccelerator:*
          - health:*
          - iam:*
          - importexport:*
          - mobileanalytics:*
          - organizations:*
          - route53:*
          - route53domains:*
          - shield:*
          - support:*
          - trustedadvisor:*
          - waf:*
          - wellarchitected:*
        resource:
          - '*'
  policy_name: RestrictRegions
  targets:
    roots:
      - r-123
```

In this example, the SCP named `RestrictRegions` denies access to all AWS regions except `us-east-1` and `us-west-2`. It also excludes certain global services from the restriction.

For more information on how to get started with AWS and SCPs, check out our [Getting Started guide for AWS](https://docs.iambic.org/getting_started/aws) and the [AWS SCP Section of our Example Templates repository](https://github.com/noqdev/iambic-templates-examples/blob/main/resources/aws/organizations/scp/iambic_test_org_account/restrict_regions.yaml). You can also learn more about tailoring AWS Identity Center (SSO) permissions per account with IAMbic in our [blog post](https://noq-0.webflow.io/blog/scps-protecting-your-aws-environment-and-your-job).

### Okta Group Assignments

Easily manage Okta group assignments with expiration dates for members. See the [Getting Started guide for Okta](https://docs.iambic.org/getting_started/okta) for more information.

```yaml
template_type: NOQ::Okta::Group
idp_name: main
properties:
  name: engineering_interns
  description: Engineering Interns
  members:
    - username: intern1@example.com
      expires_at: 2023-09-01 # Interns last day
    - username: intern2@example.com
      expires_at: 2023-09-01

```

### Google Group Assignments

Manage Google Workspace group assignments, including temporary access for external users. See the [Getting Started guide for Google
Workspace](https://docs.iambic.org/getting_started/google) for more information.

```yaml
template_type: NOQ::GoogleWorkspace::Group
properties:
  name: DockerHub
  description: Dockerhub Access
  domain: example.com
  email: dockerhub@example.com
  members:
    - email: owner@example.com
      role: OWNER
    - email: external_user@gmail.com
    - email: some_engineer@example.com
      expires_at: 2023-03-05
```

## Azure Active Directory Users

Manage Azure Active Directory users and their attributes. See the [Getting Started guide for Azure AD](https://docs.iambic.org/getting_started/azure_ad) for more information.

```yaml
expires_at: 2025-01-01
template_type: NOQ::AzureAD::User
idp_name: development
properties:
  display_name: Example User
  given_name: Example
  username: user@example.com
```

### Azure Active Directory Groups and Group Assignments

Manage Azure Active Directory groups and group assignments, including temporary access for external users. See the [Getting Started guide for Azure AD](https://docs.iambic.org/getting_started/azure_ad) for more information.

```yaml
template_type: NOQ::AzureAD::Group
idp_name: development
properties:
  name: iambic_test_group
  description: A test group to use with IAMbic
  members:
    - name: user@example.com
      data_type: user
      expires_at: tomorrow
```

## Preview standalone IAMbic templates repository

Preview a standalone [IAMbic templates repository](https://github.com/noqdev/iambic-templates-examples) on how IAMbic tracks multi-cloud IAM assets in GitHub. The repository is made public for you to study. No need to make your repository public.

## IAMbic - Beta Software

IAMbic is currently in beta, and is not yet recommended for use in production environments. We are actively working to improve the stability and performance of the software, and welcome feedback from the community.

If you choose to use IAMbic in its current state, please be aware that you may encounter bugs, performance issues, or other unexpected behavior. We strongly recommend testing IAMbic thoroughly in a non-production environment before using it in production.

Please report any issues or feedback to our GitHub issue tracker. Thank you for your support and contributions to the project!

## Contributing

Contributions to IAMbic are welcome and encouraged! If you find a bug or want to suggest an enhancement, please open an issue. Pull requests are also welcome.

## Contact Us

If you have any questions or feedback, please reach out to us on [Slack](https://communityinviter.com/apps/noqcommunity/noq). We'd love to hear from you!

## License

### IAMbic (This repo)

IAMbic is licensed under the Apache-2.0 license. Commercial licenses and support are also available from Noq Software, Inc.

### Provider Plugins

Provider Plugins (Such as the AWS, Okta, Azure Active Directory, and Google Workspace plugins) are licensed under Apache 2. You are free to write your own provider plugins for internal services without releasing its source code.

For more information, please visit [https://docs.iambic.org/license](https://docs.iambic.org/license).
