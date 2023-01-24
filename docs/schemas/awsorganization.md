# AWSOrganization

## Properties

- **`default_region`**: Default region to use when making AWS requests. Default: `"us-east-1"`.
  - **All of**
    - : Refer to *[#/definitions/RegionName](#definitions/RegionName)*.
- **`aws_profile`** *(string)*: The AWS profile used when making calls to the account.
- **`assume_role_arn`** *(string)*: The role arn to assume into when making calls to the account.
- **`external_id`** *(string)*: The external id to use for assuming into a role when making calls to the account.
- **`org_id`** *(string)*: A unique identifier designating the identity of the organization.
- **`org_name`** *(string)*
- **`identity_center_account`**: The AWS Account ID and region of the AWS Identity Center instance to use for this organization.
  - **All of**
    - : Refer to *[#/definitions/AWSIdentityCenterAccount](#definitions/AWSIdentityCenterAccount)*.
- **`default_rule`**: The rule used to determine how an organization account should be handled if the account was not found in account_rules.
  - **All of**
    - : Refer to *[#/definitions/BaseAWSOrgRule](#definitions/BaseAWSOrgRule)*.
- **`account_rules`** *(array)*: A list of rules used to determine how organization accounts are handled. Default: `[]`.
  - **Items**: Refer to *[#/definitions/AWSOrgAccountRule](#definitions/AWSOrgAccountRule)*.
## Definitions

- <a id="definitions/RegionName"></a>**`RegionName`**: An enumeration. Must be one of: `["us-east-1", "us-west-1", "us-west-2", "eu-west-1", "eu-west-2", "eu-central-1", "ap-southeast-1", "ap-southeast-2", "ap-northeast-1", "ap-northeast-2", "sa-east-1", "cn-north-1"]`.
- <a id="definitions/AWSIdentityCenterAccount"></a>**`AWSIdentityCenterAccount`** *(object)*
  - **`account_id`** *(string)*: The AWS Account ID.
  - **`region`** *(string)*
- <a id="definitions/IambicManaged"></a>**`IambicManaged`**: An enumeration. Must be one of: `["undefined", "read_and_write", "import_only"]`.
- <a id="definitions/BaseAWSOrgRule"></a>**`BaseAWSOrgRule`** *(object)*
  - **`enabled`** *(boolean)*: If set to False, iambic will ignore the included accounts. Default: `true`.
  - **`iambic_managed`**: Controls the directionality of iambic changes. Default: `"undefined"`.
    - **All of**
      - : Refer to *[#/definitions/IambicManaged](#definitions/IambicManaged)*.
  - **`assume_role_name`**: The role name(s) to use when assuming into an included account. If not provided, this iambic will use the default AWS organization role(s). Default: `["OrganizationAccountAccessRole", "AWSControlTowerExecution"]`.
    - **Any of**
      - *string*
      - *array*
        - **Items** *(string)*
- <a id="definitions/AWSOrgAccountRule"></a>**`AWSOrgAccountRule`** *(object)*
  - **`enabled`** *(boolean)*: If set to False, iambic will ignore the included accounts. Default: `true`.
  - **`iambic_managed`**: Controls the directionality of iambic changes. Default: `"undefined"`.
    - **All of**
      - : Refer to *[#/definitions/IambicManaged](#definitions/IambicManaged)*.
  - **`assume_role_name`**: The role name(s) to use when assuming into an included account. If not provided, this iambic will use the default AWS organization role(s). Default: `["OrganizationAccountAccessRole", "AWSControlTowerExecution"]`.
    - **Any of**
      - *string*
      - *array*
        - **Items** *(string)*
  - **`included_accounts`** *(array)*: A list of account ids and/or account names this rule applies to. Account ids/names can be represented as a regex and string. Default: `["*"]`.
    - **Items** *(string)*
  - **`excluded_accounts`** *(array)*: A list of account ids and/or account names this rule explicitly does not apply to. Account ids/names can be represented as a regex and string. Default: `[]`.
    - **Items** *(string)*
