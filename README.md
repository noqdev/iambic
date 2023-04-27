[![Supported Versions](https://img.shields.io/pypi/pyversions/iambic-core.svg)](https://pypi.org/project/iambic-core)
[![codecov.io](https://codecov.io/github/noqdev/iambic/coverage.svg?branch=main)](https://codecov.io/github/noqdev/iambic?branch=main)

# IAMbic: Cloud IAM as Code

"IAMbic: the Terraform of Cloud IAM"

Easily manage and streamline cloud Identity and Access Management (IAM) with IAMbic, a multi-cloud IAM control plane. Discover more at [https://docs.iambic.org](https://docs.iambic.org).

## Key Features

<!-- Keep this in sync with the list of features in the IAMbic Docs Overview Page -->

- **[Universal Cloud Identity](https://docs.iambic.org/getting_started/)**: Unify cloud identity management for AWS, Okta, Azure Active Directory, Google Workspace with more to come.
- **[Temporary Access](https://docs.iambic.org/getting_started/aws#32---create-temporary-expiring-iam-permissions)**: Declaratively define and automate expiration dates for resources, permissions, and access rules.
- **[Dynamic AWS Permissions](https://docs.iambic.org/getting_started/aws#31---create-dynamic-iam-role-policies-that-vary-per-account)**: Simplify multi-account AWS management with flexible templates, allowing multi-account roles to have different permissions and access rules on different accounts.
- **[Drift Prevention](https://docs.iambic.org/how_to_guides/prevent-drift)**: Protect the IAM resources you want to be exclusively managed via IAMbic. What is in Git becomes the absolute source of truth.
- **[GitOps-driven Cloud IAM (IAMOps)](https://docs.iambic.org/reference/iamops_philosophy)**: Leverage GitOps-driven Cloud IAM with human-readable formats and your favorite tools.
- **Centralized Management**: IAMbic keeps Git updated with the latest, complete state of your cloud environment, maintaining a single source of truth for auditing and compliance across multiple cloud providers in Git.
- **Extendable**: Integrate with various clouds and applications through a powerful plugin architecture.
- **Auditable**: Track changes to IAM policies, permissions, and rules with Git history. For AWS, IAmbic annotates out-of-band commits with details from CloudTrail.

## 📣 Let's chat
Do you want to connect with our contributors?

Just click the button below and follow the instructions.

[![slack](https://img.shields.io/badge/Slack-4A154B?style=for-the-badge&logo=slack&logoColor=white)](https://communityinviter.com/apps/noqcommunity/noq)

## Getting Started

Dive into IAMbic with our [quick-start guide](http://docs.iambic.org/getting_started/) and explore powerful template examples for AWS Multi-Account Roles, Dynamic Permissions, Okta Applications and Group Assignments, Azure Active Directory Users and Groups, and Google Workspace Group Assignments. We are rapidly expanding support for existing resources and cloud providers, so check back often!

## Installing IAMbic and Supported Versions

IAMbic is available on PyPI:

```console
python -m pip install iambic-core
```

IAMbic officially supports Python 3.9+.

### Template Examples

Here are some examples showcasing IAMbic's capabilities:

#### AWS Multi-Account Cloudwatch Role

Create a Cloudwatch role with static permissions across three accounts, dynamically generating role names based on the account the role is deployed to. This template would
result in the creation of three roles: "dev_cloudwatch",
"staging_cloudwatch", and "prod_cloudwatch" on the respective AWS accounts. See the [Getting Started guide for AWS](https://docs.iambic.org/getting_started/aws) for more information.

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
