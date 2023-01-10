# GroupMember

## Properties

- **`ExpiresAt`**: The date and time the resource will be/was set to deleted.
  - **Any of**
    - *string*
    - *string*
    - *string*
- **`Deleted`** *(boolean)*: Denotes whether the resource has been removed from AWS.Upon being set to true, the resource will be deleted the next time iambic is ran. Default: `false`.
- **`Email`** *(string)*
- **`Expand`** *(boolean)*: Expand the group into the members of the group. This is useful for nested groups. Default: `false`.
- **`Role`**: Default: `"MEMBER"`.
  - **All of**
    - : Refer to *[#/definitions/GroupMemberRole](#definitions/GroupMemberRole)*.
- **`Type`**: Default: `"USER"`.
  - **All of**
    - : Refer to *[#/definitions/GroupMemberType](#definitions/GroupMemberType)*.
- **`Status`**: Default: `"ACTIVE"`.
  - **All of**
    - : Refer to *[#/definitions/GroupMemberStatus](#definitions/GroupMemberStatus)*.
- **`Subscription`**: Default: `"EACH_EMAIL"`.
  - **All of**
    - : Refer to *[#/definitions/GroupMemberSubscription](#definitions/GroupMemberSubscription)*.
## Definitions

- <a id="definitions/GroupMemberRole"></a>**`GroupMemberRole`**: An enumeration. Must be one of: `["OWNER", "MANAGER", "MEMBER"]`.
- <a id="definitions/GroupMemberType"></a>**`GroupMemberType`**: An enumeration. Must be one of: `["USER", "GROUP", "EXTERNAL"]`.
- <a id="definitions/GroupMemberStatus"></a>**`GroupMemberStatus`**: An enumeration. Must be one of: `["ACTIVE", "INACTIVE", "PENDING", "UNDEFINED"]`.
- <a id="definitions/GroupMemberSubscription"></a>**`GroupMemberSubscription`**: An enumeration. Must be one of: `["EACH_EMAIL", "DIGEST", "ABRIDGED", "NO_EMAIL"]`.
