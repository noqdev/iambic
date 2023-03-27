# AzureActiveDirectoryGroupTemplate

*A base model class that provides additional helper methods and
configurations for other models used in IAMbic.*

## Properties

- **`metadata_commented_dict`** *(object)*: yaml inline comments. Default: `{}`.
- **`metadata_iambic_fields`** *(array)*: metadata for iambic. Default: `[]`.
  - **Items**
- **`template_type`** *(string)*: Default: `"NOQ::AzureAD::Group"`.
- **`owner`** *(string)*: Owner of the group.
- **`iambic_managed`**: Controls the directionality of Iambic changes. Default: `"undefined"`.
  - **All of**
    - : Refer to *[#/definitions/IambicManaged](#definitions/IambicManaged)*.
- **`idp_name`** *(string)*: Name of the identity provider that's associated with the resource.
- **`expires_at`**: The date and time the resource will be/was set to deleted.
  - **Any of**
    - *string*
    - *string*
    - *string*
- **`deleted`** *(boolean)*: Denotes whether the resource has been removed from AWS.Upon being set to true, the resource will be deleted the next time iambic is ran. Default: `false`.
- **`properties`**: Properties for the Azure AD Group.
  - **All of**
    - : Refer to *[#/definitions/GroupTemplateProperties](#definitions/GroupTemplateProperties)*.
## Definitions

- <a id="definitions/IambicManaged"></a>**`IambicManaged`**: An enumeration. Must be one of: `["undefined", "read_and_write", "import_only", "disabled"]`.
- <a id="definitions/MemberDataType"></a>**`MemberDataType`**: An enumeration. Must be one of: `["user", "group"]`.
- <a id="definitions/Member"></a>**`Member`** *(object)*: A base model class that provides additional helper methods and
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
  - **`id`** *(string)*
  - **`name`** *(string)*
  - **`data_type`**: Refer to *[#/definitions/MemberDataType](#definitions/MemberDataType)*.
- <a id="definitions/GroupTemplateProperties"></a>**`GroupTemplateProperties`** *(object)*: A base model class that provides additional helper methods and
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
  - **`name`** *(string)*: Name of the group.
  - **`mail_nickname`** *(string)*: Mail nickname of the group.
  - **`group_id`** *(string)*: Unique Group ID for the group. Usually it's {idp-name}-{name}.
  - **`description`** *(string)*: Description of the group. Default: `""`.
  - **`group_types`** *(array)*: Specifies the group type and its membership. Default: `[]`.
    - **Items** *(string)*
  - **`mail`** *(string)*: Email address of the group.
  - **`mail_enabled`** *(boolean)*: Default: `false`.
  - **`security_enabled`** *(boolean)*: Default: `true`.
  - **`extra`**: Extra attributes to store.
  - **`is_assignable_to_role`** *(boolean)*: Indicates whether this group can be assigned to an Azure Active Directory role or not.
  - **`membership_rule`** *(string)*: The rule that determines members for this group if the group is a dynamic group.
  - **`members`** *(array)*: A list of users in the group. Default: `[]`.
    - **Items**: Refer to *[#/definitions/Member](#definitions/Member)*.
