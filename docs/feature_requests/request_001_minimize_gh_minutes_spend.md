Minimize GitHub action minutes spend.

Design constraints
1. Binary is delivered as a container image

Motivation
1. The github action minutes is computed by trigger of action to end of action.
2. Pulling image across public network incurs much idling time, and increase GH minutes spent
3. Github action minutes spent is different from a typical user's public cloud spend.

Solutions

1. The action trigger needs to end as soon as possible, so we need the state machine execution and transition happening in the user's preferred compute surface. (This is likely ECS, lambda, or whatever, GKE, Azure, etc)
2. Instead of manually wire per event action, it's more future-proof to integrate via Github Webhook events. The transition of state will happen external of
