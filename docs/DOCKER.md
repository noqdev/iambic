# Docker


Iambic ships with a docker container and a docker-compose.yaml file that can be ran either locally, in AWS Lambda, GitHub Actions, and potentially other places.

The container is purpose built to support Python 3.10 in AWS Lambda because at the current time, AWS Lambda does not support Python 3.10 (See: <https://github.com/aws/aws-lambda-base-images/issues/31>). See the Dockerfile for more information.

The Dockerfile ships with [AWSLambdaric](https://docs.aws.amazon.com/lambda/latest/dg/images-test.html), which allows us to test Lambda functions locally. The actual Iambic Lambda Python code is in iambic/lambda/app.py.

This code can import your AWS and Google environment, apply the environment, and perform other actions.

## Next Steps

- We support cloning git repos. We need to add support for accessing these repos for importing, planning, and applying templates. Check out the `clone_git_repos` function for the base functionality.
- Get this container running as a GitHub action on 1) main branch push (apply the changes), 2) schedule (Every 5 minutes) to detect/correct drift
- Support automatically detecting accounts via AWS organizations, and populating roles on these accounts.
- Create a specific role for iambic (And don't re-use Noq SaaS SpokeRole)
- Update Iambic container to be accessible on dockerhub or public ECR.

## Running Locally

### Running without Docker

To test the Iambic code without Docker, simply use the VSCode run configurations that start with `Iambic: Lambda`.

### Running in Docker

To run the container locally, run the following commands:

```bash
# Refresh AWS Credentials with a specific profile
noq file arn:aws:iam::940552945933:role/NoqCentralRoleCorpNoqDev -p arn:aws:iam::940552945933:role/NoqCentralRoleCorpNoqDev -f
# Build the container
docker-compose build

# Start the container
docker-compose up
```

This will run the container and mount the current directory into the container. This allows you to make changes to the code and see the changes reflected in the container.

When it is operational, you can invoke Lambda locally with the following:

```bash
# Import
curl -XPOST "http://localhost:9000/2015-03-31/functions/function/invocations" -d '{"command": "import"}'
# Detect
curl -XPOST "http://localhost:9000/2015-03-31/functions/function/invocations" -d '{"command": "detect"}'
```

For a full list of commands, see the `LambdaCommand` enum in iambic/lambda/app.py.

## Running in GitHub Actions

There is a GitHub action for testing the import functionality in `noq-templates/.github/workflows`. This action runs when changes are pushed to the main branch, and attempts to simply import the cloud environment. Right now, this is a no-op operation.

This Github action is rather inefficient because it is building the docker images manually during every run. In reality, it should utilize an image in Public DockerHub or ECR.

## Running in AWS Lambda

TBD


## Deploying to ECR

```bash
# Retrieve development_admin credentials
export AWS_PROFILE=development/development_admin
# Login to public ECR
aws ecr-public get-login-password --region us-east-1 | docker login --username AWS --password-stdin public.ecr.aws/s2p9s3r8
# (From iambic root directory) build the container
docker build -t iambic .
# Tag and push
docker tag iambic:latest public.ecr.aws/s2p9s3r8/iambic:latest
docker push public.ecr.aws/s2p9s3r8/iambic:latest
