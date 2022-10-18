# ManagedPolicyRef

## Properties

- **`expires_at`** *(string)*: The date and time the resource will be/was set to deleted.
- **`deleted`**: Denotes whether the resource has been removed from AWS.Upon being set to true, the resource will be deleted the next time iambic is ran. Default: `false`.
  - **Any of**
    - *boolean*
    - *array*
      - **Items**: Refer to *[#/definitions/Deleted](#definitions/Deleted)*.
- **`included_accounts`** *(array)*: A list of account ids and/or account names this statement applies to. Account ids/names can be represented as a regex and string. Default: `["*"]`.
  - **Items**
- **`excluded_accounts`** *(array)*: A list of account ids and/or account names this statement explicitly does not apply to. Account ids/names can be represented as a regex and string. Default: `[]`.
  - **Items**
- **`included_orgs`** *(array)*: A list of AWS organization ids this statement applies to. Org ids can be represented as a regex and string. Default: `["*"]`.
  - **Items**
- **`excluded_orgs`** *(array)*: A list of AWS organization ids this statement explicitly does not apply to. Org ids can be represented as a regex and string. Default: `[]`.
  - **Items**
- **`policy_arn`** *(string)*
## Definitions

- <a id="definitions/Deleted"></a>**`Deleted`** *(object)*
  - **`included_accounts`** *(array)*: A list of account ids and/or account names this statement applies to. Account ids/names can be represented as a regex and string. Default: `["*"]`.
    - **Items**
  - **`excluded_accounts`** *(array)*: A list of account ids and/or account names this statement explicitly does not apply to. Account ids/names can be represented as a regex and string. Default: `[]`.
    - **Items**
  - **`included_orgs`** *(array)*: A list of AWS organization ids this statement applies to. Org ids can be represented as a regex and string. Default: `["*"]`.
    - **Items**
  - **`excluded_orgs`** *(array)*: A list of AWS organization ids this statement explicitly does not apply to. Org ids can be represented as a regex and string. Default: `[]`.
    - **Items**
  - **`deleted`** *(boolean)*: Denotes whether the resource has been removed from AWS.Upon being set to true, the resource will be deleted the next time iambic is ran.
