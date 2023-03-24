# IAMbic: Cloud IAM as Code

"IAMbic: the Terraform of Cloud IAM"

Easily manage and streamline cloud Identity and Access Management (IAM) with IAMbic, a multi-cloud IAM control plane. Discover more at [https://www.iambic.org](https://www.iambic.org).

## Key Features

- **GitOps-driven Cloud IAM (IAMOps)**: Leverage GitOps-driven Cloud IAM with human-readable formats and your favorite tools.
- **[Multi-Cloud](https://iambic.org/getting_started/)**: Unify cloud identity management for AWS, Okta, Google Workspace, and more.
- **[Dynamic AWS Permissions](https://iambic.org/getting_started/aws#31---create-dynamic-iam-role-policies-that-vary-per-account)**: Simplify multi-account AWS management with flexible templates, allowing multi-account roles to have different permissions and access rules on different accounts.
- **[Temporary Access, Permissions, and Identities](https://iambic.org/getting_started/aws#32---create-temporary-expiring-iam-permissions)**: Declaratively define and automate expiration dates for resources, permissions, and access rules.
- **Centralized Management**: IAMbic keeps Git updated with the latest, complete state of your cloud environment, maintaining a single source of truth for auditing and compliance across multiple cloud providers in Git.
- **Extendable**: Integrate with various clouds and applications through a powerful plugin architecture.
- **Auditable**: Track changes to IAM policies, permissions, and rules with Git history. For AWS, IAmbic annotate out-of-band commits with details from CloudTrail.

## Getting Started

Dive into IAMbic with our [quick-start guide](http://iambic.org/getting_started/) and explore powerful template examples for AWS Multi-Account Roles, Dynamic Permissions, Okta Applications and Group Assignments, and Google Group Assignments. We are rapidly expanding support for existing resources and cloud providers, so check back often!

### Template Examples

Here are some examples showcasing IAMbic's capabilities:

#### AWS Multi-Account Cloudwatch Role

Create a Cloudwatch role with static permissions across three accounts, dynamically generating role names based on the account the role is deployed to. This template would
result in the creation of three roles: "dev_cloudwatch",
"staging_cloudwatch", and "prod_cloudwatch" on the respective AWS accounts.

```yaml
template_type: NOQ::AWS::IAM::Role
identifier: '{{account_name}}_cloudwatch'
included_accounts:
    - dev
    - staging
    - prod
properties:
  description:
    - description: Cloudwatch role for {{account_name}}
  assume_role_policy_document:
    statement:
      - action:
          - sts:AssumeRole
          - sts:TagSession
        effect: Allow
        principal:
          aws: arn:aws:iam::123456789012:role/NoqCentralRole
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
  role_name: '{{account_name}}_cloudwatch'
  tags:
    - key: owner
      value: devops
```

### AWS Dynamic Permissions

Create a BackendDeveloperRole with varying permissions based on the AWS account:

```yaml
template_type: NOQ::AWS::IAM::Role
identifier: '{{account_name}}_backend_developer'
included_accounts:
  - '*'
excluded_accounts:
  - compliance
properties:
  description:
    - description: Backend developer role for {{account_name}}
  assume_role_policy_document:
    statement:
      - action:
          - sts:AssumeRole
          - sts:TagSession
        effect: Allow
        principal:
          aws: arn:aws:iam::123456789012:role/NoqCentralRole
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
  role_name: '{{account_name}}_backend_developer'
  tags:
    - key: owner
      value: devops
```

### Okta Application Assignments

Manage Okta application assignments, including expiration dates for specific users:

```yaml
template_type: NOQ::Okta::App
properties:
  name: Salesforce.com
  assignments:
    - user: username@example.com
    - user: username2@example.com
    - user: username3@example.com
      expires_at: 2023-09-01T00:00 UTC
  idp_name: development
  status: ACTIVE
```

### Okta Group Assignments

Easily manage Okta group assignments with expiration dates for members:

```yaml
template_type: NOQ::Okta::Group
properties:
  name: engineering_interns
  description: Engineering Interns
  idp_name: main
  members:
    - username: intern1@example.com
      expires_at: 2023-09-01 # Interns last day
    - username: intern2@example.com
      expires_at: 2023-09-01

```

### Okta User Attributes (TODO)

### Google Group Assignments

Manage Google Workspace group assignments, including temporary access for external users:

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

IAMbic is licensed under the AGPL-3.0 license. Commercial licenses and support are also available from Noq Software, Inc.

### Provider Plugins

Provider Plugins (Such as the AWS, Okta, and Google Workspace plugins) are licensed under Apache 2. You are free to write your own provider plugins for internal services without releasing its source code.

### License

IAMbic is licensed with AGPLv3.

IAMBic plugins are licensed under Apache License, Version 2.0.

For more information, please visit [iambic.org](https://iambic.org/license).
