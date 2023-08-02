# CEP 003 - GitHub App Deployment Revamp

## Summary
* Remove Docker invocation in terraform deployment
* Use API Gateway instead of lambda public function url
* Use GitHub App Manifest flow to create the self hosted IAMbic GitHub integration

## Rationale

### Remove Docker invocation in terraform deployment

Terraform Cloud and SpaceLift both do run docker on the tenant process. customers are expected
to have their own reachable Docker daemon to build containers. For customers who use dockers, they
typically have an existing mechanism to checkout the source tree of Dockerfile to do build and push
to registry.

By using ECR Pull Through [Cache](https://docs.aws.amazon.com/AmazonECR/latest/userguide/pull-through-cache.html), we can avoid a round trip to pull IAMbic container image from public ECR gallery and then upload it back to AWS ECR.

By using AWS CodeBuild, we can trigger the initial upstream fetch for the ECR Pull Through. These series of steps are required to work around AWS Lambda does not allow external container image.

### Use API Gateway instead of lambda public function url

This is an optional deployment compared to the Lambda function url. When using lambda function url used as a webhook for GitHub, there is no auth because GitHub webhook does not auth. Products like SecurityHub may warn regarding lambda function url not using auth. Beware that the GitHub webhook implementation uses a webhook secret to verify the signature of the incoming payload. API Gateway can be used to deliver the webhook event to lambda. However, it also costs extra to use API Gateway compared to the lambda functional url.

### Use GitHub App Manifest flow to create the self hosted IAMbic GitHub integration

GitHub has a reference [implementation](https://docs.github.com/en/apps/sharing-github-apps/registering-a-github-app-from-a-manifest) to allow easy sharing of GitHub Apps. By implementing this flow, IAMbic can automate the task of storing the newly created GitHub app and webhook secret to AWS Secrets Manager. Furthermore, IAMbic wizard can automate the steps to deploy the lambda integration in user chosen AWS account.

## Customer Experience
How does the customer interact with this enhancement?

## Alternative
Is there alternative considered?

## Implementation
What's needed on the implementation?

## Compatibility concern
Is there any compatibility concern?