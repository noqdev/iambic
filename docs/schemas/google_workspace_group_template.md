# GoogleWorkspaceGroupTemplate

*A base model class that provides additional helper methods and
configurations for other models used in IAMbic.*

## Properties

- **`metadata_commented_dict`** *(object)*: yaml inline comments. Default: `{}`.
- **`metadata_iambic_fields`** *(array)*: metadata for iambic. Default: `[]`.
  - **Items**
- **`expires_at`**: The date and time the resource will be/was set to deleted.
  - **Any of**
    - *string*
    - *string*
    - *string*
- **`deleted`** *(boolean)*: Denotes whether the resource has been removed from AWS.Upon being set to true, the resource will be deleted the next time iambic is ran. Default: `false`.
- **`template_type`** *(string)*: Default: `"NOQ::GoogleWorkspace::Group"`.
- **`owner`** *(string)*: Owner of the group.
- **`iambic_managed`**: Controls the directionality of Iambic changes. Default: `"undefined"`.
  - **All of**
    - : Refer to *[#/definitions/IambicManaged](#definitions/IambicManaged)*.
- **`properties`**: Refer to *[#/definitions/GroupTemplateProperties](#definitions/GroupTemplateProperties)*.
## Definitions

- <a id="definitions/IambicManaged"></a>**`IambicManaged`**: An enumeration. Must be one of: `["undefined", "read_and_write", "import_only", "disabled"]`.
- <a id="definitions/GroupMemberRole"></a>**`GroupMemberRole`**: An enumeration. Must be one of: `["OWNER", "MANAGER", "MEMBER"]`.
- <a id="definitions/GroupMemberType"></a>**`GroupMemberType`**: An enumeration. Must be one of: `["USER", "GROUP", "EXTERNAL"]`.
- <a id="definitions/GroupMemberStatus"></a>**`GroupMemberStatus`**: An enumeration. Must be one of: `["ACTIVE", "INACTIVE", "PENDING", "UNDEFINED"]`.
- <a id="definitions/GroupMemberSubscription"></a>**`GroupMemberSubscription`**: An enumeration. Must be one of: `["EACH_EMAIL", "DIGEST", "ABRIDGED", "NO_EMAIL"]`.
- <a id="definitions/GroupMember"></a>**`GroupMember`** *(object)*: A base model class that provides additional helper methods and
configurations for other models used in IAMbic.
  - **`metadata_commented_dict`** *(object)*: yaml inline comments. Default: `{}`.
  - **`metadata_iambic_fields`** *(array)*: metadata for iambic. Default: `[]`.
    - **Items**
  - **`expires_at`**: The date and time the resource will be/was set to deleted.
    - **Any of**
      - *string*
      - *string*
      - *string*
  - **`deleted`** *(boolean)*: Denotes whether the resource has been removed from AWS.Upon being set to true, the resource will be deleted the next time iambic is ran. Default: `false`.
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
- <a id="definitions/WhoCanInvite"></a>**`WhoCanInvite`**: An enumeration. Must be one of: `["ALL_MANAGERS_CAN_INVITE", "ALL_MEMBERS_CAN_INVITE"]`.
- <a id="definitions/WhoCanJoin"></a>**`WhoCanJoin`**: An enumeration. Must be one of: `["ALL_IN_DOMAIN_CAN_JOIN", "ANYONE_CAN_JOIN", "CAN_REQUEST_TO_JOIN"]`.
- <a id="definitions/WhoCanPostMessage"></a>**`WhoCanPostMessage`**: An enumeration. Must be one of: `["ALL_IN_DOMAIN_CAN_POST", "ALL_MANAGERS_CAN_POST", "ALL_MEMBERS_CAN_POST", "ANYONE_CAN_POST", "NONE_CAN_POST"]`.
- <a id="definitions/WhoCanViewGroup"></a>**`WhoCanViewGroup`**: An enumeration. Must be one of: `["ALL_IN_DOMAIN_CAN_VIEW", "ALL_MANAGERS_CAN_VIEW", "ALL_MEMBERS_CAN_VIEW", "ANYONE_CAN_VIEW"]`.
- <a id="definitions/WhoCanViewMembership"></a>**`WhoCanViewMembership`**: An enumeration. Must be one of: `["ALL_IN_DOMAIN_CAN_VIEW", "ALL_MANAGERS_CAN_VIEW", "ALL_MEMBERS_CAN_VIEW", "ANYONE_CAN_VIEW"]`.
- <a id="definitions/GroupTemplateProperties"></a>**`GroupTemplateProperties`** *(object)*: A base model class that provides additional helper methods and
configurations for other models used in IAMbic.
  - **`metadata_commented_dict`** *(object)*: yaml inline comments. Default: `{}`.
  - **`metadata_iambic_fields`** *(array)*: metadata for iambic. Default: `[]`.
    - **Items**
  - **`name`** *(string)*
  - **`domain`** *(string)*
  - **`email`** *(string)*
  - **`description`** *(string)*
  - **`welcome_message`** *(string)*
  - **`members`** *(array)*
    - **Items**: Refer to *[#/definitions/GroupMember](#definitions/GroupMember)*.
  - **`who_can_invite`**: Default: `"ALL_MANAGERS_CAN_INVITE"`.
    - **All of**
      - : Refer to *[#/definitions/WhoCanInvite](#definitions/WhoCanInvite)*.
  - **`who_can_join`**: Default: `"CAN_REQUEST_TO_JOIN"`.
    - **All of**
      - : Refer to *[#/definitions/WhoCanJoin](#definitions/WhoCanJoin)*.
  - **`who_can_post_message`**: Default: `"NONE_CAN_POST"`.
    - **All of**
      - : Refer to *[#/definitions/WhoCanPostMessage](#definitions/WhoCanPostMessage)*.
  - **`who_can_view_group`**: Default: `"ALL_MANAGERS_CAN_VIEW"`.
    - **All of**
      - : Refer to *[#/definitions/WhoCanViewGroup](#definitions/WhoCanViewGroup)*.
  - **`who_can_view_membership`**: Default: `"ALL_MANAGERS_CAN_VIEW"`.
    - **All of**
      - : Refer to *[#/definitions/WhoCanViewMembership](#definitions/WhoCanViewMembership)*.
  - **`iambic_managed`**: Default: `"undefined"`.
    - **All of**
      - : Refer to *[#/definitions/IambicManaged](#definitions/IambicManaged)*.
  - **`extra`**: Extra attributes to store.
