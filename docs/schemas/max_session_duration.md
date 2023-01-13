# MaxSessionDuration

## Properties

- **`included_accounts`** *(array)*: A list of account ids and/or account names this statement applies to. Account ids/names can be represented as a regex and string. Default: `["*"]`.
  - **Items** *(string)*
- **`excluded_accounts`** *(array)*: A list of account ids and/or account names this statement explicitly does not apply to. Account ids/names can be represented as a regex and string. Default: `[]`.
  - **Items** *(string)*
- **`included_orgs`** *(array)*: A list of AWS organization ids this statement applies to. Org ids can be represented as a regex and string. Default: `["*"]`.
  - **Items** *(string)*
- **`excluded_orgs`** *(array)*: A list of AWS organization ids this statement explicitly does not apply to. Org ids can be represented as a regex and string. Default: `[]`.
  - **Items** *(string)*
- **`max_session_duration`** *(integer)*
