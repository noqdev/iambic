# RoleAccess

## Properties

- **`included_accounts`** *(array)*: A list of account ids and/or account names this statement applies to. Account ids/names can be represented as a regex and string. Default: `["*"]`.
  - **Items** *(string)*
- **`excluded_accounts`** *(array)*: A list of account ids and/or account names this statement explicitly does not apply to. Account ids/names can be represented as a regex and string. Default: `[]`.
  - **Items** *(string)*
- **`included_orgs`** *(array)*: A list of AWS organization ids this statement applies to. Org ids can be represented as a regex and string. Default: `["*"]`.
  - **Items** *(string)*
- **`excluded_orgs`** *(array)*: A list of AWS organization ids this statement explicitly does not apply to. Org ids can be represented as a regex and string. Default: `[]`.
  - **Items** *(string)*
- **`expires_at`**: The date and time the resource will be/was set to deleted.
  - **Any of**
    - *string*
    - *string*
    - *string*
- **`deleted`** *(boolean)*: Denotes whether the resource has been removed from AWS.Upon being set to true, the resource will be deleted the next time iambic is ran. Default: `false`.
- **`users`** *(array)*: List of users who can assume into the role. Default: `[]`.
  - **Items** *(string)*
- **`groups`** *(array)*: List of groups. Users in one or more of the groups can assume into the role. Default: `[]`.
  - **Items** *(string)*
