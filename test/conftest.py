from __future__ import annotations

import pytest

from iambic.aws.models import AWSAccount


@pytest.fixture
def aws_accounts():
    return [
        AWSAccount(account_id="123456789010", account_name="dev1"),
        AWSAccount(account_id="123456789011", account_name="dev2"),
        AWSAccount(account_id="123456789012", account_name="staging1"),
        AWSAccount(account_id="123456789013", account_name="staging2"),
        AWSAccount(account_id="123456789014", account_name="qa1"),
        AWSAccount(account_id="123456789015", account_name="qa2"),
        AWSAccount(account_id="123456789016", account_name="prod1"),
        AWSAccount(account_id="123456789017", account_name="prod2"),
        AWSAccount(account_id="123456789018", account_name="prod3"),
        AWSAccount(account_id="123456789019", account_name="test"),
    ]
