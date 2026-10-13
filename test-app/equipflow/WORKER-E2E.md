# Worker routed-model E2E (worker v1.4.7, 2026-10-13)

Autonomous completion through the RouteForge path, live-verified.

## Chain
opencode (devfoundry ns) -> routeforge demo-api :8000 -> onboarded glm-5.3-flash
endpoint = alias-proxy /a/glm-flash/v1 (runai-routeforge ns) -> glm-flash vLLM
(runai-glm-coding ns, NodePort 30856).

## Fixes that made it work
1. Worker v1.4.6: ROUTEFORGE_TIER_MODEL_MAP resolves tier names (mid) -> model
   slug (glm-5.3-flash) before sendInput.
2. Opencode pod: OPENCODE_CONFIG_CONTENT sets top-level
   model/small_model = routeforge/glm-5.3-flash and drops the fake cheap/mid/
   frontier model keys (OpenCode ignores per-message modelID overrides; the
   agent used its configured default).
3. Demo-api app policy: PUT /admin/applications/devfoundry/policy (PATCH drops
   stream_mode) sets stream_mode=verified_then_stream + max_cost_usd_per_request=2.0
   (deployment default 0.05 rejects the 8k-token agent prompt).
4. Onboarded endpoint repointed: api.runai-routeforge:8080 (nested demo-api that
   budget-filters) -> alias-proxy /a/glm-flash/v1 (proxy straight to vLLM).
5. SP_ONPREM_API_KEY secret = glm-flash vLLM key (the alias-proxy relays auth
   to vLLM which validates its own key).
6. Worker v1.4.7: review packet collects git-less evidence from the
   checkpoint's OpenCode session (task.workspaceId is the DevFoundry workspace,
   not a session id).
7. NOTE: demo-api sqlite db lives at /tmp/routeforge.db in the container layer
   — every routeforge pod restart wipes it (model + app + token). Re-onboard
   script below.

## Evidence
Task 69ab1d14 (FACT-CHECK11.txt "routed model works"): lifecycle Pending ->
Qualified -> Running (agent created the file via glm-5.3-flash) -> review
packet with non-empty patchDigest (7588cd69) -> approve -> Completed, outcome
"Approved at review". Worker used repair 2 (git-less validation timing, not a
model failure).

## Re-onboard after a routeforge restart
psql-free sqlite one-shot (see git history of this file) inserts
onboarded_models row, then POST /admin/applications + PUT .../policy +
POST .../tokens with the admin cookie (admin@routeforge.local/changeme), then
patch the token into deploy/opencode OPENCODE_CONFIG_CONTENT.
