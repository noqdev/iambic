# AWSAccount

## Properties

- **`default_region`**: Default region to use when making AWS requests. Default: `"us-east-1"`.
  - **All of**
    - : Refer to *[#/definitions/RegionName](#definitions/RegionName)*.
- **`aws_profile`** *(string)*: The AWS profile used when making calls to the account.
- **`assume_role_arn`** *(string)*: The role arn to assume into when making calls to the account.
- **`external_id`** *(string)*: The external id to use for assuming into a role when making calls to the account.
- **`boto3_session_map`** *(object)*
- **`account_id`** *(string)*: The AWS Account ID.
- **`org_id`** *(string)*: A unique identifier designating the identity of the organization.
- **`account_name`** *(string)*
- **`partition`**: The AWS partition the account is in. Options are aws, aws-us-gov, and aws-cn. Default: `"aws"`.
  - **All of**
    - : Refer to *[#/definitions/Partition](#definitions/Partition)*.
- **`role_access_tag`** *(string)*: The key of the tag used to store users and groups that can assume into the role the tag is on.
- **`iambic_managed`**: Controls the directionality of iambic changes. Default: `"undefined"`.
  - **All of**
    - : Refer to *[#/definitions/IambicManaged](#definitions/IambicManaged)*.
- **`variables`** *(array)*: A list of variables to be used when creating templates. Default: `[]`.
  - **Items**: Refer to *[#/definitions/Variable](#definitions/Variable)*.
- **`org_session_info`** *(object)*
- **`identity_center_details`**: Refer to *[#/definitions/IdentityCenterDetails](#definitions/IdentityCenterDetails)*.
## Definitions

- <a id="definitions/RegionName"></a>**`RegionName`**: An enumeration. Must be one of: `["us-east-1", "us-west-1", "us-west-2", "eu-west-1", "eu-west-2", "eu-central-1", "ap-southeast-1", "ap-southeast-2", "ap-northeast-1", "ap-northeast-2", "sa-east-1", "cn-north-1"]`.
- <a id="definitions/Partition"></a>**`Partition`**: An enumeration. Must be one of: `["aws", "aws-us-gov", "aws-cn"]`.
- <a id="definitions/IambicManaged"></a>**`IambicManaged`**: An enumeration. Must be one of: `["undefined", "read_and_write", "import_only"]`.
- <a id="definitions/Variable"></a>**`Variable`** *(object)*
  - **`key`** *(string)*
  - **`value`** *(string)*
- <a id="definitions/IdentityCenterDetails"></a>**`IdentityCenterDetails`** *(object)*
  - **`region`** *(string)*
  - **`instance_arn`** *(string)*
  - **`identity_store_id`** *(string)*
  - **`permission_set_map`** *(object)*
  - **`user_map`** *(object)*
  - **`group_map`** *(object)*
  - **`org_account_map`** *(object)*
