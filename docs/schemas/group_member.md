# GroupMember

## Properties

- **`expires_at`** *(string)*: The date and time the resource will be/was set to deleted.
- **`deleted`**: Denotes whether the resource has been removed from AWS.Upon being set to true, the resource will be deleted the next time iambic is ran. Default: `false`.
  - **Any of**
    - *boolean*
    - *array*
      - **Items**: Refer to *[#/definitions/Deleted](#definitions/Deleted)*.
- **`email`** *(string)*
- **`expand`** *(boolean)*: Expand the group into the members of the group. This is useful for nested groups. Default: `false`.
- **`role`**: Default: `"MEMBER"`.
  - **All of**
    - : Refer to *[#/definitions/GroupMemberRole](#definitions/GroupMemberRole)*.
- **`type`**: Default: `"USER"`.
  - **All of**
    - : Refer to *[#/definitions/GroupMemberType](#definitions/GroupMemberType)*.
- **`status`**: Default: `"ACTIVE"`.
  - **All of**
    - : Refer to *[#/definitions/GroupMemberStatus](#definitions/GroupMemberStatus)*.
- **`subscription`**: Default: `"EACH_EMAIL"`.
  - **All of**
    - : Refer to *[#/definitions/GroupMemberSubscription](#definitions/GroupMemberSubscription)*.
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
- <a id="definitions/GroupMemberRole"></a>**`GroupMemberRole`**: An enumeration. Must be one of: `["OWNER", "MANAGER", "MEMBER"]`.
- <a id="definitions/GroupMemberType"></a>**`GroupMemberType`**: An enumeration. Must be one of: `["USER", "GROUP", "EXTERNAL"]`.
- <a id="definitions/GroupMemberStatus"></a>**`GroupMemberStatus`**: An enumeration. Must be one of: `["ACTIVE", "INACTIVE", "PENDING"]`.
- <a id="definitions/GroupMemberSubscription"></a>**`GroupMemberSubscription`**: An enumeration. Must be one of: `["EACH_EMAIL", "DIGEST", "ABRIDGED", "NO_EMAIL"]`.
