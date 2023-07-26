== What is this module for? ==

Lambda can be deployed using a container; however, this container must be available in ECR in the account.
Although ECR pull-through-cache supports pull through from public repository. A initial pull from the ECR
must occur before a lambda function can reference this ECR repository. If the user does not want to install
docker or podman, a remote docker pull needs to happen. CodeBuild is an AWS Service that can run a build script.
Because docker can be available out of hte box from AWS CodeBuild. This terraform module configure a project
to simply trigger a docker login (your private ECR with pull through cache), and then you can use the AWS
interface to trigger the first build.

== How to trigger a build? ==

```bash
aws codebuild start-build --project-name iambic-code-build --profile YOUR_PREFERRED_PROFILE_NAME --region YOUR_PREFERRED_REGION
```

Typically it takes about 2 min for the image pull to complete in build.

This procedure simply make sure the pull through cache can pull the public image into ECR. No changes have been made to your host.