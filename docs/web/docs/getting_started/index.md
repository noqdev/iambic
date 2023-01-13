---
title: Getting Started
---

# Getting Started

This page will guide you through setting up the required technologies that will allow you to run IAMbic. 

## Setting up your local environment

This section of the tutorial has the greatest potential for complications, as it pertains to the setup of IAMbic. If you encounter any issues, do not hesitate to reach out for assistance in our [Slack Community](https://communityinviter.com/apps/noqcommunity/noq). Our team would be delighted to assist you.

### Before You Start

Before proceeding you will need to have the following configured, and know the basics of using them:

- Git (see [GitHub’s set up Git guide](https://help.github.com/en/github/getting-started-with-github/set-up-git))
- ability to create a GitHub Repository
- one or more of the following: (TODO: Guidance needed for each of these flows)
  - AWS Credentials
  - Okta Credentials
  - Google Credentials


### Docker

We recommend using Docker to run IAMbic, as this provides the most accurate environment for its intended operation and helps to prevent issues caused by variations between different systems. If you plan to make changes to IAMbic, we suggest installing IAMbic locally instead. Guidance can be found in our Local Development guide below.

#### Install Docker and Docker Compose

- Install Docker (see [Docker&#39;s Quick Start Guide)](https://docs.docker.com/desktop/get-started/)

- Confirm Docker is installed properly:
`docker run --rm busybox true`

### Local Development
TBD?

#### Install Python (for local development)

If you're following the local development guide, you'll also need Python 3.10+ before proceeding:

- Install Python 3.10+ (see the [Python download page](https://www.python.org/downloads/))

- Confirm Python is installed properly:
`python -c "print('It\'s working!')"`

### Create a local Git Repository

IAMbic can use any folder as a database-on-disk. We strongly suggest using a version control system, as this will allow IAMbic to keep a historical record of changes to your Cloud IAM over time. We have created GitHub action workflows to automate the IAMbic processes as much as possible. For the purposes of the tutorials in IAMbic, we will use a Git repository that only exists on your system. If you wish to configure Iambic in production, we recommend configuring a repository in GitHub, as IAMbic ships with GitHub actions that keep your local repo in-sync with your cloud environment. (#TODO: Link to a production setup flow and reference this doc: Guidance on how to create a repository can be found in [Github&#39;s guide for creating a repo](https://docs.github.com/en/get-started/quickstart/create-a-repo).)

Create a private GitHub repository called `iambic-templates`.

```bash
mkdir iambic-templates
cd iambic-templates
git init
```

## Onto the Next Steps

Now that you have IAMbic installed, (COMMENT: We do? When/where?) you're ready to move on to the next steps. At this point, your experience will vary depending on the goals you want to achieve:

- Continue with AWS
- Continue with Okta
- Continue with Google
  
(COMMENT: presumably these will be links)