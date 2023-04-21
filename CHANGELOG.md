## 0.3.0 (April 21, 2023)

BREAKING CHANGES:
* AWS templates containing account_id or account_name will need to be updated from `{{ account_id }}` to `{{ var.account_id }}` and from `{{ account_name }}` to `{{ var.account_name }}`. Alternatively, you can remove the files and re-import them.

You can use your favorite editor for find and replace, or give the following bash two-liner a try.

```bash
find . -type f -name "*.yaml" -print0 | xargs -0 sed -i '' -e 's/{{account_id}}/{{var.account_id}}/g'
find . -type f -name "*.yaml" -print0 | xargs -0 sed -i '' -e 's/{{account_name}}/{{var.account_name}}/g'
```

ENHANCEMENTS:
* Removed AWS package imports from core 
* Standardized variable naming in templates

BUG FIXES:
* Resolved type error on merge template when new value is None.



## 0.2.0 (April 17, 2023)

Initial plan is to do a every 2-week release cycle.

ENHANCEMENTS:
* Improve memory footprint in templates reading
* Minimize I/O in templates reading
