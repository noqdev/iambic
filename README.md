# Iambic


> IAM-better-in-config
> The python package used to generate, parse, and execute IAMbic yaml templates.

Features:

|                                                                                                                               |                     |
| ----------------------------------------------------------------------------------------------------------------------------- | ------------------- |
| Multi-Account Aware (Automatically recognizes and populates new accounts with default resources and identities) | X                   |
| Stateless (and *fast!*)                                                                                                      | X                   |
| Continuous Drift Correction Out of the Box (*What you see is what you git)*                                          | X                   |
| Dynamically define identity permissions across accounts                                                                | X                   |
| Centralize and link all human and cloud identities in a single repository                                              | X                   |
| Simple YAML DSL                                                                  | X                   |
| Easy Rollback Changes (*git revert* actually *reverts)*                                                           | X                   |
| Transpile into Terraform                                                                                                      | Coming Soon! |

Noq Enterprise offers many more enhancements on top of Iambic. Visit [https://www.noq.dev](https://www.noq.dev) to learn more and sign up for early access.

|                                                                                                               |                     |
| ------------------------------------------------------------------------------------------------------------- | ------------------- |
| Self-Service ChatOps and Web UI (With type-aheads for **all** the things)                        | Coming Soon! |
| Generate Cookie-Cutter Team Roles based on usage data                                                  | Coming Soon! |
| Alert on Unauthorized Out-of-band Changes (Convert to change request with one click)                   | Coming Soon! |
| Automatically Approve Low-Risk Permissions Requests                                                    | Coming Soon! |
| Discover the IAM Permissions of a Local Application                                                    | Coming Soon! |
| Lint changes automatically with Access Analyzer                                                        | Coming Soon! |
| Automatically Generate Service Control Policies base on usage                                          | Coming Soon! |
| Prune Unused IAM Permissions, Access, Identities, and Credentials                                      | Coming Soon! |
| Generate Dynamic Reports based on human identities, cloud identities, access, and permissions | Coming Soon! |

## Run these commands to setup IAMbic for development <!-- are these lines meant to be commented out? Otherwise they're all H1 headlines -->

# `python3.10 -m venv env`

# `. env/bin/activate`

# `pip install poetry` # (last tested with poetry version 1.2.2)

# `poetry install`

## How to run IAMbic

`python -m iambic.main import -c demo/config.yaml`

## Documentation

Documentation is located in docs/web and can be launched by following these steps:

Note: you may have to first install yarn: https://classic.yarnpkg.com/lang/en/docs/install/#debian-stable and possibly nodejs/npm: https://docs.npmjs.com/downloading-and-installing-node-js-and-npm

In `docs/web`:

* `yarn`
* `yarn start`

This will open your browser to http://localhost:3000 where you can view the IAMbic documentation.

## Additional Documentation

* [Schemas](docs/SCHEMA.md)
* [Contributing](docs/CONTRIBUTING.md)
* [Docker](docs/DOCKER.md)
