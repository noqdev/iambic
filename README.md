# Iambic


> IAM-better-in-config
> The python package used to generate, parse, and execute IAMbic yaml templates.

Features:

|                                                                                                                               |                     |
| ----------------------------------------------------------------------------------------------------------------------------- | ------------------- |
| Multi-Account Aware`<br>`(Automatically recognizes and populates`<br>`new accounts with default resources and identities) | X                   |
| Stateless (and*fast!*)                                                                                                      | X                   |
| Continuous Drift Correction Out of the Box`<br>`(*What you see is what you git)*                                          | X                   |
| Dynamically define identity permissions`<br>`across accounts                                                                | X                   |
| Centralize and link all human and cloud identities in a`<br>`single repository                                              | X                   |
| Simple YAML DSL`<br>`(Even a developer can understand it!)                                                                  | X                   |
| Easy Rollback Changes`<br>`(*git revert* actually *reverts)*                                                           | X                   |
| Transpile into Terraform                                                                                                      | Coming`<br>`Soon! |

Noq Enterprise offers many more enhancements on top of Iambic. Visit [https://www.noq.dev](https://www.noq.dev) to learn more and sign up for early access.

|                                                                                                               |                     |
| ------------------------------------------------------------------------------------------------------------- | ------------------- |
| Self-Service ChatOps and Web UI`<br>`(With type-aheads for **all** the things)                        | Coming`<br>`Soon! |
| Generate Cookie-Cutter Team Roles based on`<br>`usage data                                                  | Coming`<br>`Soon! |
| Alert on Unauthorized Out-of-band Changes`<br>`(Convert to change request with one click)                   | Coming`<br>`Soon! |
| Automatically Approve Low-Risk Permissions`<br>`Requests                                                    | Coming`<br>`Soon! |
| Discover the IAM Permissions of a`<br>`Local Application                                                    | Coming`<br>`Soon! |
| Lint changes automatically with Access`<br>`Analyzer                                                        | Coming`<br>`Soon! |
| Automatically Generate Service Control Policies`<br>`base on usage                                          | Coming`<br>`Soon! |
| Prune Unused IAM Permissions, Access, Identities,`<br>`and Credentials                                      | Coming`<br>`Soon! |
| Generate Dynamic Reports based on`<br>`human identities, cloud identities, access, `<br>`and permissions | Coming`<br>`Soon! |


## License

### IAMbic (This repo)

IAMbic is licensed under the AGPL-3.0 license. Commercial licenses are also available from Noq Software, Inc.

### Provider Plugins

Provider Plugins (Such as the AWS, Okta, and Google-Suite plugins) are licensed under Apache 2. You are free to write your own provider plugins for internal services without releasing its source code.

### Licensing Policy

Our goal in selecting the AGPL v3.0 as our open source license is to require that enhancements to IAMbic be released to the community. Traditional GPL often does not achieve this anymore as a huge amount of software runs in the cloud. We also make our provider plugins available under the Apache License v2.0 to encourage proprietary plugin contribution.

If use of our drivers under the Apache License v2.0 or the database under the AGPL v3 does not satisfy your organization’s vast legal department (some will not approve GPL in any form), commercial licenses are available with Noq Software. Feel free to contact us for more details.

### Noq Trademark Guidelines

IAMbic, Noq, and the Noq logo are registered trademarks of Noq Software, Inc.. For trademark use approval or any questions you have about using these trademarks, please email trademark@noq.dev.

## Setup for development

# `python3.10 -m venv env`

# `. env/bin/activate`

# `pip install poetry` # (last tested with poetry version 1.2.2)

# `poetry install`

## How to run

`python -m iambic.main import -c demo/config.yaml`

## Additional Documentation

* [Schemas](docs/SCHEMA.md)
* [Contributing](docs/CONTRIBUTING.md)
* [Docker](docs/DOCKER.md)
