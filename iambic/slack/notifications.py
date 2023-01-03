from __future__ import annotations

from iambic.config.models import Config


async def send_iam_mutation_message(
    config,
    identity: str,
    actor: str,
    event_source: str,
    event_name: str,
    session_name: str,
    cloudtrail_event: dict,
):
    event = event_source.split(".")[0] + ":" + event_name
    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "An unauthorized Cloud Identity Modification was detected and automatically remediated.\n\n*<fakeLink.toEmployeeProfile.com|Click here to view CloudTrail Logs>*",
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Identity:*\t<fakeLink.toNoqRole.com|{identity}>",
            },
        },
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*Action:*\t{event}"}},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Actor:*\t<fakeLink.toNoqRole.com|{actor}>",
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Session Name:*\t{session_name}",
            },
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "emoji": True,
                        "text": "Approve and Submit Request",
                    },
                    "style": "primary",
                    "value": "approve",
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "emoji": True, "text": "Ignore"},
                    "style": "danger",
                    "value": "ignore",
                },
            ],
        },
    ]

    await send_slack_notification_to_channel(
        config,
        config.slack["alert_channel_id"],
        "An unauthorized Cloud Identity Modification was detected and automatically remediated.",
        blocks,
    )


async def send_slack_notification_to_channel(
    config: Config, channel_id, text, blocks
) -> bool:
    if not (slack_app := config.slack_app):
        return False

    slack_app.client.chat_postMessage(channel=channel_id, text=text, blocks=blocks)
    return True
