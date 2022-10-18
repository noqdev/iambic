# Config

## Properties

- **`accounts`** *(array)*
  - **Items**: Refer to *[#/definitions/AccountConfig](#definitions/AccountConfig)*.
- **`google`**: Refer to *[#/definitions/GoogleConfig](#definitions/GoogleConfig)*.
- **`extends`** *(array)*: Default: `[]`.
  - **Items**: Refer to *[#/definitions/ExtendsConfig](#definitions/ExtendsConfig)*.
- **`secrets`** *(object)*
- **`role_access_tag`** *(string)*: The key of the tag used to store users and groups that can assume into the role the tag is on. Default: `"noq-authorized"`.
- **`variables`** *(array)*: A list of variables to be used when creating templates. These apply to all accounts but can be overwritten by an account. Default: `[]`.
  - **Items**: Refer to *[#/definitions/Variable](#definitions/Variable)*.
- **`slack_app`** *(string)*
- **`sqs`** *(object)*: Default: `{}`.
- **`slack`** *(object)*: Default: `{}`.
## Definitions

- <a id="definitions/RegionName"></a>**`RegionName`**: An enumeration. Must be one of: `["us-east-1", "us-west-1", "us-west-2", "eu-west-1", "eu-west-2", "eu-central-1", "ap-southeast-1", "ap-southeast-2", "ap-northeast-1", "ap-northeast-2", "sa-east-1", "cn-north-1"]`.
- <a id="definitions/Variable"></a>**`Variable`** *(object)*
  - **`key`** *(string)*
  - **`value`** *(string)*
- <a id="definitions/AccountConfig"></a>**`AccountConfig`** *(object)*
  - **`account_id`** *(string)*: The AWS Account ID.
  - **`org_id`** *(string)*: A unique identifier designating the identity of the organization.
  - **`account_name`** *(string)*
  - **`default_region`**: Default region to use when making AWS requests. Default: `"us-east-1"`.
    - **All of**
      - : Refer to *[#/definitions/RegionName](#definitions/RegionName)*.
  - **`aws_profile`** *(string)*: The AWS profile used when making calls to the account.
  - **`assume_role_arn`** *(string)*: The role arn to assume into when making calls to the account.
  - **`external_id`** *(string)*: The external id to use for assuming into a role when making calls to the account.
  - **`role_access_tag`** *(string)*: The key of the tag used to store users and groups that can assume into the role the tag is on.
  - **`variables`** *(array)*: A list of variables to be used when creating templates. Default: `[]`.
    - **Items**: Refer to *[#/definitions/Variable](#definitions/Variable)*.
  - **`boto3_session_map`** *(object)*
  - **`read_only`** *(boolean)*: If set to True, iambic will only log drift instead of apply changes when drift is detected. Default: `false`.
- <a id="definitions/GoogleGroupsConfig"></a>**`GoogleGroupsConfig`** *(object)*
  - **`enabled`** *(boolean)*: Default: `false`.
- <a id="definitions/GoogleConfig"></a>**`GoogleConfig`** *(object)*
  - **`groups`**: Refer to *[#/definitions/GoogleGroupsConfig](#definitions/GoogleGroupsConfig)*.
- <a id="definitions/ExtendsConfigKey"></a>**`ExtendsConfigKey`**: An enumeration. Must be one of: `["AWS_SECRETS_MANAGER"]`.
- <a id="definitions/ExtendsConfig"></a>**`ExtendsConfig`** *(object)*
  - **`key`**: Refer to *[#/definitions/ExtendsConfigKey](#definitions/ExtendsConfigKey)*.
  - **`value`** *(string)*
