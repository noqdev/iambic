
## Why Github App

* Make comment on pull-request as it's own identity.

## Constraint of Github App

* Github App has to be [hosted](https://docs.github.com/en/developers/apps/getting-started-with-apps/about-apps)

## Open source Github App and hosting responsibilities

For the open source version, Github App needs to be deployed by the user.

1. Github Organization administrator has to create an app that is installable by its own organization. (This will be a private Github App owned by the organization). In this process, they will generate a private key for their app (which they can store in secret manager). They will also get a new Github App id.

2. Github Organization administrator will install the newly created app to their own iambic templates repository.

## Authentication

1. Github App Private Key (owned by the user that just created the Github App)

2. Use Github App Private Key as signing key to sign a JWT claim that is referred as Github App Token

3. Use Github App Token to get an Installation Token (specific to the repository that is connected to the Github App)

4. Use the installation token to interact with the repository's pull request and repository.


## Hosted App Implementation

* API Gateway to provided internet route-able url
* Connect API Gateway to Lambda backed by container image

## Quarks

* Lambda only works with private ECR in the same region and same account
* To reliable invoke lambda function to the right version of container image, i have to configure to use the SHA256 instead of label