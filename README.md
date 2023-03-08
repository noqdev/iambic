# IAMbic: Entitlements as Code

"It's like Terraform, but for Entitlements"

IAMbic is a multi-cloud identity and access management (IAM) control plane that centralizes and organizes the tracking and management of cloud access and permissions. With IAMbic, teams can easily manage changes to identities, access rules, and permissions, and grant temporary or emergency access for end-users, while reducing the latency, overhead, and risk associated with permissions management. Learn more at [https://www.iambic.org](https://www.iambic.org).

## Key Features

- **[Multi-Cloud](https://iambic.org/getting_started/)**: No more juggling between multiple cloud UIs. Manage your cloud identities across AWS, Okta, Google Workspace, and other cloud platforms in the future in one simple human-readable format.
- **[Dynamic AWS Permissions](https://iambic.org/getting_started/aws#31---create-dynamic-iam-role-policies-that-vary-per-account)**: Stop wasting time bootstrapping IAM "in a unique way" for each of your accounts. IAMbic provides a fully round-tripped, multi-account template structure designed to make multi-account AWS easier. IAMbic's template structure supports different permission levels, access rules, and expirations based on the AWS account the identity will be deployed to. IAMbic also groups similar identities across accounts in a single template, making multi-account AWS management easier.
- **[Temporary Access, Permissions, and Identities](https://iambic.org/getting_started/aws#32---create-temporary-expiring-iam-permissions)**: IAMbic enables teams to declaratively define when a resource, cloud permission, or access rule will expire. Relative expiration dates are supported, and are automatically converted into absolute dates once the change is merged in. IAMbic provides GitHub Actions that automatically remove expired identities, access, and permissions.
- **Always Updated Source of Truth**: Entitlements at scale has gotten out of hand. Compliance, Security, and Ops *need* a central repository to reason about and manage human and cloud identities. IAMbic's open format and tools enable you to create an entitlements infrastructure that works seamlessly with your existing infrastructure-as-code solutions, such as Terraform.
- **Extendable**: IAMbic offers a robust plugin architecture, enabling development of internal plugins and plugins for different cloud providers.
- **Auditable**: IAMbic provides a complete record of when entitlement changes happened within your environment, whether they happened through IAMbic, IaC, or ClickOps.
- **Developer-friendly Workflow**: The source of truth in IAMbic is based in Git. Developers, Cloud Operations, Security, and Compliance teams are free to use existing tools at their disposal.
- **Custom Template Parameters**: Stuck looking at CloudTrail logs having to context switch to discover which account arn:aws:iam::874326598251:role/administrator belongs to? No more! Specify variables such as `{{account_name}}` anywhere within
a template and IAMbic will automatically perform the substitution. For example, `role_name: {{account_name}}_administrator` would result in a role name of `prod_administrator` if deployed to the `prod` account.

## Getting Started

Please follow our [quick-start guide](http://iambic.org/getting_started/) to get up and running with IAMbic.

### Template Examples

This section provides a sneak peak at the power of IAMbic.

#### AWS Multi-Account Administrator Role

```yaml
template_type: NOQ::AWS::IAM::Role
identifier: '{{account_name}}_administrator'
properties:
  description:
    - description: Admin Role
  assume_role_policy_document:
    statement:
      - action:
          - sts:AssumeRole
          - sts:TagSession
        effect: Allow
        principal:
          aws: arn:aws:iam::940552945933:role/NoqCentralRoleCorpNoqDev
    version: '2012-10-17'
  managed_policies:
    - policy_arn: arn:aws:iam::aws:policy/AdministratorAccess
  role_name: '{{account_name}}_administrator'
  tags:
    - key: owner
      value: cloud_sec
```

### AWS Dynamic Permissions

```yaml
template_type: NOQ::AWS::IAM::Role
identifier: "{{account_name}}_iambic_test_role"
included_accounts:
  - "*" # Include this role on all AWS Accounts
expires_at: in 3 days
properties:
  description: IAMbic test role on {{account_name}}
  assume_role_policy_document:
    statement:
      - action: sts:AssumeRole
        effect: Deny
        principal:
          service: ec2.amazonaws.com
  inline_policies:
    - policy_name: spoke-acct-policy
      statement:
        - expires_at: 2021-01-01 # Expire the permission on a specific date
          excluded_accounts: # Include this policy on the role across all accounts, except ACCOUNT_A
            - ACCOUNT_A
          action:
            - s3:ListBucket
          effect: Deny
          resource: "*"
        - expires_at: tomorrow # Expire the permission at a relative time. IAMbic converts this to an absolute date once it is applied and merged
          included_accounts: # Only include the policy statement on ACCOUNT_A
            - ACCOUNT_A
          action:
            - s3:GetObject
          effect: Deny
          resource: "*"
        - expires_at: in 4 hours
          included_accounts: # Include the policy statement on all accounts except ACCOUNT_A and ACCOUNT_B
            - "*"
          excluded_accounts:
            - ACCOUNT_A
            - ACCOUNT_B
          action:
            - s3:ListAllMyBuckets
          effect: Deny
          resource: "*"
  managed_policies:
    - policy_arn: arn:aws:iam::aws:policy/job-function/ViewOnlyAccess
  path: /iambic_test/
  permissions_boundary:
    policy_arn: arn:aws:iam::aws:policy/AWSDirectConnectReadOnlyAccess
  role_name: "{{account_name}}_iambic_test_role"
```

### Okta Application Assignments

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

### Okta User Attributes

### Google Group Assignments

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

### Licensing Policy

Our purpose in choosing AGPL v3.0 as our open source license is to ensure that any improvements made to IAMbic are shared with the community. This is because the traditional GPL license is no longer effective for a large amount of cloud-based software. To encourage contributions for proprietary providers, our provider plugins are made available under the Apache License v2.0. You are also free to write plugins for internal providers without needing to open source the plugin code.

If the use of our plugins under the Apache License v2.0 or IAMbic core under the AGPLv3 does not meet the legal requirements of your organization (as some may not accept the GPL in any form), commercial licenses are available through Noq Software. Please reach out to us for more information.

### Noq Trademark Guidelines

IAMbic, Noq, and the Noq logo are registered trademarks of Noq Software, Inc.. For trademark use approval or any questions you have about using these trademarks, please email trademark@noq.dev.
