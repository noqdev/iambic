# IAMbic: Entitlements as Code

IAMbic revolutionizes cloud entitlements management by providing a centralized and organized way to track and edit your cloud access and permissions. With IAMbic, teams can easily manage changes to identities, access rules, and permissions, and grant temporary or emergency access for end-users, all while reducing the latency, overhead, and risk associated with permissions management. IAMbic integrates with GitHub actions to keep your repository updated with the live state of your cloud entitlements, regardless of whether they are managed through IAMbic,
infrastructure-as-code, or ClickOps.

IAMbic provides a plugin-based architecture, and can be customized to support internal authentication and authorization providers. The current implementation ships with plugins for AWS IAM, AWS Identity Center (Formerly known as AWS SSO), Okta, and Google. We are planning to release additional plugins, and we welcome contributions from the community.

The goal of IAMbic is to provide an open source and standardized request workflow, allowing self-serve access requests within the developer workflow. Approvals for shared access are integrated into the Git workflow, providing a streamlined and efficient process for managing cloud entitlements. IAMbic should only take an hour to get up and running, and will import entitlements from your existing environment.

## Features

- Human-readable entitlements across AWS, Okta, Google. More to come soon.
- Always up-to-date entitlements, with historical tracking of changes through Git
- Selective management of entitlements without interfering with other flows you may be using (Such as Terraform or CloudFormation)
- Multi-Account AWS Roles with dynamic permissions and access rules depending on the account
- Temporary Access Rules (For AWS Identity Center, Okta Apps/Groups, Google Apps/Groups)
- Temporary Fine-Grained AWS Permissions (For AWS IAM Roles/Users/Groups/Policies and Identity Center Permission Sets)

## Getting Started

Please follow our quick-start guide here to get IAMbic up and running: http://iambic.org/getting_started/.

## Development Setup

### IAMbic Development

IAMbic is written in Python. We provide VSCode run configurations to make it easy to get started. Here is a quick guide:

```bash
# Clone IAMbic
git clone git@github.com:noqdev/iambic.git

# Set up Python depenedencies
cd iambic
python3.10 -m venv env
. env/bin/activate
pip install poetry
poetry install
```

### Documentation Development

Documentation requires [Yarn](https://classic.yarnpkg.com/lang/en/docs/install/#debian-stable) and [nodejs/npm](https://docs.npmjs.com/downloading-and-installing-node-js-and-npm).

Documentation is located in docs/web and can be launched by following these steps:

```bash
# From the `iambic` repository directory
cd docs/web
yarn
yarn start
```

This will open your browser to http://localhost:3000 where you can view the IAMbic documentation and see live edits to the Markdown files.

## License

### IAMbic (This repo)

IAMbic is licensed under the AGPL-3.0 license. Commercial licenses and support are also available from Noq Software, Inc.

### Provider Plugins

Provider Plugins (Such as the AWS, Okta, and Google-Suite plugins) are licensed under Apache 2. You are free to write your own provider plugins for internal services without releasing its source code.

### Licensing Policy

Our purpose in choosing the AGPL v3.0 as our open source license is to ensure that any improvements made to IAMbic are shared with the community. This is because the traditional GPL license is no longer effective for a large amount of cloud-based software. To encourage contributions for proprietary providers, our provider plugins are made available under the Apache License v2.0. You are also free to write plugins for internal providers without needing to open source the plugin code.

If the use of our plugins under the Apache License v2.0 or IAMbic core under the AGPLv3 does not meet the legal requirements of your organization (as some may not accept the GPL in any form), commercial licenses are available through Noq Software. Please reach out to us for more information.

### Noq Trademark Guidelines

IAMbic, Noq, and the Noq logo are registered trademarks of Noq Software, Inc.. For trademark use approval or any questions you have about using these trademarks, please email trademark@noq.dev.