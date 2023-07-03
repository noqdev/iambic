## IAMbic GitHub Action Templates

Welcome to the IAMbic GitHub Action templates folder! If you've found yourself wondering about the unusual structure of the actions in this folder, and why they don't appear to be running any specific commands, you're in the right place. Let's demystify these actions for you.

These GitHub actions perform a unique role within the IAMbic system. Rather than directly running IAMbic commands, they trigger a GitHub [Workflow run](https://docs.github.com/en/webhooks-and-events/webhooks/webhook-events-and-payloads#workflow_run) event. This event contains details about the triggered event, such as the name of the file that caused the trigger.

Here's how it works:

1. **Triggering the Event:** Once an action defined in this folder is activated based on its cron schedule, it triggers a GitHub Workflow run event.

2. **Webhook and Event Details:** The details of this event are sent to your [IAMbic Github App's](https://docs.iambic.org/getting_started/github) webhook URL. The information shared includes the name of the file and other specifics about the event.

3. **Lambda Function Activation:** The received event at the webhook URL triggers the [IAMbic's Lambda function](https://github.com/noqdev/iambic/blob/8af32ce81b317f918849e68527315c626bd9858d/iambic/plugins/v0_1_0/github/github_app.py#L331).

4. **Performing the Requested Action:** The Lambda function analyzes the received event, determines the workflow that was activated, and then performs the requested action accordingly.

Feel free to explore the actions in this folder, and if you have any contributions or suggestions, they are always welcome!
