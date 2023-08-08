from __future__ import annotations

import time

import boto3

REGION_NAME = "us-east-1"
CODE_BUILD_PROJECT_NAME = "iambic_code_build"
IAMBIC_FUNCTION_NAME = "iambic_github_app_webhook"
IAMBIC_REPOSITORY_NAME = "iambic-ecr-public/iambic/iambic"
IAMBIC_CF_LAMBDA_STACK_NAME = "IAMbicGitHubAppLambda"


def start_code_build_with_pin_version(ver):
    code_build_client = boto3.client("codebuild", region_name=REGION_NAME)

    response = code_build_client.start_build(
        projectName=CODE_BUILD_PROJECT_NAME,
        environmentVariablesOverride=[
            {
                "name": "IMAGE_TAG",
                "value": ver,
                "type": "PLAINTEXT",
            },
        ],
    )

    build_id = response["build"]["id"]
    # FIXME explain why this is stalling for builds
    # log.info("Preparing container image. This process should take around 2 minutes")
    for _ in range(6):
        resp = code_build_client.batch_get_builds(ids=[build_id])
        build_status = resp["builds"][0]["buildStatus"]
        if build_status == "IN_PROGRESS":
            time.sleep(30)
            continue
        elif build_status == "SUCCEEDED":
            break
        else:
            raise ValueError(f"build status is {build_status}")


def wait_until_image_is_ready(ver):
    repository_name = IAMBIC_REPOSITORY_NAME
    ecr_client = boto3.client("ecr", region_name=REGION_NAME)
    for _ in range(6):
        try:
            resp = ecr_client.describe_images(
                repositoryName=repository_name, imageIds=[{"imageTag": ver}]
            )
            if len(resp["imageDetails"]) == 0:
                time.sleep(30)
                continue
            else:
                break
        except ecr_client.exceptions.ImageNotFoundException:
            time.sleep(30)
            continue


def update_lambda_code(ver):
    client = boto3.client("lambda", region_name=REGION_NAME)
    response = client.get_function(
        FunctionName=IAMBIC_FUNCTION_NAME,
    )
    image_uri = response["Code"]["ImageUri"]
    base_uri, current_ver = image_uri.split(":")
    assert base_uri
    assert current_ver
    new_image_uri = f"{base_uri}:{ver}"
    print(f"new image uri: {new_image_uri}")
    response = client.update_function_code(
        FunctionName=IAMBIC_FUNCTION_NAME,
        ImageUri=new_image_uri,
        Publish=True,
    )


def update_cf_lambda_ver(ver):
    client = boto3.client("cloudformation", region_name=REGION_NAME)
    response = client.describe_stacks(
        StackName=IAMBIC_CF_LAMBDA_STACK_NAME,
    )
    existing_parameters = response["Stacks"][0]["Parameters"]
    new_parameters = []
    image_uri = None
    for param in existing_parameters:
        if param["ParameterKey"] != "ImageUri":
            new_parameters.append(
                {"ParameterKey": param["ParameterKey"], "UsePreviousValue": True}
            )
        else:
            image_uri = param["ParameterValue"]
    assert image_uri
    base_uri, current_ver = image_uri.split(":")
    assert base_uri
    assert current_ver
    new_image_uri = f"{base_uri}:{ver}"
    print(f"new image uri: {new_image_uri}")
    new_parameters.append({"ParameterKey": "ImageUri", "ParameterValue": new_image_uri})
    response = client.update_stack(
        StackName=IAMBIC_CF_LAMBDA_STACK_NAME,
        UsePreviousTemplate=True,
        Parameters=new_parameters,
    )
    for _ in range(6):
        response = client.describe_stacks(
            StackName=IAMBIC_CF_LAMBDA_STACK_NAME,
        )
        stack_status = response["Stacks"][0]["StackStatus"]
        if stack_status != "UPDATE_IN_PROGRESS":
            print(f"stack status: {stack_status}")
            break
        else:
            print("waiting for stack to finish updating")
            time.sleep(60)


def upgrade_lambda(ver):
    start_code_build_with_pin_version(ver)
    wait_until_image_is_ready(ver)
    update_cf_lambda_ver(ver)


if __name__ == "__main__":
    upgrade_lambda("0.11.30")
