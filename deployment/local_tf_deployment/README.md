We recommend you use the `iambic setup` to deploy GitHub App Integration
We supply these terraform instructions in the event your org requires
these components be installed via terraform.

(Help wanted) These is not the best terraform deployment experience. Feel free
to open a pull request to make it better.

You have to replace DEPLOY_REGION_NAME and DEPLOY_PROFILE_NAME to match what your
organization needs.

1. deploy github app execution roles
1. deploy ecr
1. deploy iambic_code_build
1. aws --region DEPLOY_REGION_NAME --profile DEPLOY_PROFILE_NAME codebuild start-build --project-name iambic-code-build
1. wait til build is finished
1. wail til iambic-ecr-public/iambic/iambic shows a latest label image
1. get the output lambda function url and update your github app