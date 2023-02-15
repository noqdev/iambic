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

## Setup for development

# `python3.10 -m venv env`

# `. env/bin/activate`

# `pip install poetry` # (last tested with poetry version 1.2.2)

# `poetry install`

## How to run

`python -m iambic.main import -c demo/config.yaml`

## Documentation

Documentation is housed in docs/web and can be launched by following these steps:

Note: you may have to first install yarn: https://classic.yarnpkg.com/lang/en/docs/install/#debian-stable and possibly nodejs/npm: https://docs.npmjs.com/downloading-and-installing-node-js-and-npm

In `docs/web`:

* `yarn`
* `yarn start`

This will launch your browser on http://localhost:3000 where you can view all IAMbic documentation.

## Additional Documentation

* [Schemas](docs/SCHEMA.md)
* [Contributing](docs/CONTRIBUTING.md)
* [Docker](docs/DOCKER.md)
