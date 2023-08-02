# IAMbic CodeBuild Module

## Purpose of this Module

This module is designed to facilitate the deployment of IAMbic's Lambda function using a container without requiring system dependencies on the user's system (such as Docker or Podman). The container for the Lambda function must reside in the account's Elastic Container Registry (ECR) for this process to work. While ECR's pull-through-cache supports pulling from public repositories (like the official IAMbic Docker Image), an initial pull from ECR on your account must be performed before a Lambda function can reference the ECR repository.

If a user doesn't want to install Docker or Podman, a remote Docker pull needs to be executed. AWS CodeBuild, a service capable of running a build script, provides Docker out of the box. This Terraform module configures a project to trigger a Docker login (your private ECR with pull-through cache), after which you can use the AWS interface to trigger the first build.

## How to Trigger a Build

To trigger a build, run the following command:

```bash
aws codebuild start-build --project-name iambic-code-build --profile YOUR_PREFERRED_PROFILE_NAME --region YOUR_PREFERRED_REGION
```

Typically, the image pull process completes in about 2 minutes during the build.

Please note, this procedure only ensures the pull-through cache can pull the public image into the ECR. No changes are made to your host in this process.
