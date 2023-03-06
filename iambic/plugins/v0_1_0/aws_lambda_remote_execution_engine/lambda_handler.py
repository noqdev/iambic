from __future__ import annotations

import datetime
import json
import os.path


def lambda_handler(event, context):
    # TODO implement

    path = "/mnt/efs/hello_world.txt"
    lines = []
    if os.path.exists(path):
        with open(path, "r") as f:
            lines = f.readlines()

    print(lines)

    lines.append("{0}\n".format(datetime.datetime.now()))

    with open(path, "w") as f:
        f.writelines(lines)

    return {"statusCode": 200, "body": json.dumps("Hello from Lambda!")}
