#!/bin/bash
# Re-onboard the routeforge demo-api after a pod restart.
#
# The demo-api (deploy routeforge, ns runai-dev-foundry) keeps its state in an
# ephemeral sqlite db at /tmp/routeforge.db inside the container layer — every
# pod restart wipes it. This script restores everything the DevFoundry worker
# path needs:
#
#   1. onboarded_models row for glm-5.3-flash (endpoint = alias-proxy)
#   2. devfoundry application
#   3. devfoundry policy (stream_mode + max_cost)
#   4. fresh API token, minted and patched into deploy/opencode
#      OPENCODE_CONFIG_CONTENT (OpenCode ignores per-message model overrides,
#      so the token must live in the pod's configured default)
#
# Env vars (defaults in parens):
#   RF_NS (runai-dev-foundry)        OpenCode ns for kubectl exec
#   OPENCODE_DEPLOY (opencode)
#   OPENCODE_NS ($RF_NS)
#   RF_BASE_URL (http://127.0.0.1:8000)  port-forward target for the demo-api
#   RF_ADMIN_USER (admin@routeforge.local)
#   RF_ADMIN_PASSWORD (changeme)
#   VLLM_KEY (required)  glm-flash vLLM API key (alias-proxy relays it)
#   SP_ONPREM_API_KEY (rf_live_reonboarded)  secret key to store in routeforge
#   RF_COOKIE (/tmp/opencode/rf-cookie2.txt)
#   DF_NS (runai-dev-foundry)        devfoundry API ns for port-forward
#   DF_API_URL (http://127.0.0.1:3000)
#   DF_COOKIE (/tmp/opencode/df-cookie.txt)

set -euo pipefail

RF_NS="${RF_NS:-runai-dev-foundry}"
OPENCODE_DEPLOY="${OPENCODE_DEPLOY:-opencode}"
OPENCODE_NS="${OPENCODE_NS:-$RF_NS}"
RF_BASE_URL="${RF_BASE_URL:-http://127.0.0.1:8000}"
RF_ADMIN_USER="${RF_ADMIN_USER:-admin@routeforge.local}"
RF_ADMIN_PASSWORD="${RF_ADMIN_PASSWORD:-changeme}"
VLLM_KEY="${VLLM_KEY:?VLLM_KEY is required (glm-flash vLLM API key)}"
SP_ONPREM_API_KEY="${SP_ONPREM_API_KEY:-rf_live_reonboarded}"
RF_COOKIE="${RF_COOKIE:-/tmp/opencode/rf-cookie2.txt}"
DF_NS="${DF_NS:-runai-dev-foundry}"
DF_API_URL="${DF_API_URL:-http://127.0.0.1:3000}"
DF_COOKIE="${DF_COOKIE:-/tmp/opencode/df-cookie.txt}"

APP_ID=devfoundry
SLUG=glm-5.3-flash
ENDPOINT="http://alias-proxy.runai-routeforge.svc.cluster.local:8000/a/${SLUG}/v1"

say() { echo "[re-onboard] $*"; }

# ---------------------------------------------------------------------------
# 0. Kill stale port-forwards, restart both (Run:ai kills them constantly).
say "restarting port-forwards"
pkill -f "port-forward" 2>/dev/null || true
sleep 2
kubectl -n "$RF_NS" port-forward svc/routeforge 8000:8000 >/tmp/opencode/pf-rf.log 2>&1 &
kubectl -n "$DF_NS" port-forward svc/devfoundry-api 3000:3000 >/tmp/opencode/pf-df.log 2>&1 &
sleep 4
for i in $(seq 1 10); do
  curl -s --noproxy '*' -m 2 -o /dev/null "$RF_BASE_URL/health" && break
  sleep 2
done

# ---------------------------------------------------------------------------
# 1. Admin cookie for later onboarding (model + app).
say "logging in"
kubectl -n "$RF_NS" port-forward svc/routeforge 8000:8000 >/tmp/opencode/pf-rf.log 2>&1 &
PFPID=$!
sleep 4
for i in $(seq 1 10); do curl -s --noproxy '*' -m 2 -o /dev/null "$RF_BASE_URL/health" && break; sleep 2; done
curl -s --noproxy '*' -m 10 -c "$RF_COOKIE" -X POST "$RF_BASE_URL/admin/login" \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"$RF_ADMIN_USER\",\"password\":\"$RF_ADMIN_PASSWORD\"}" >/dev/null
kill $PFPID 2>/dev/null || true

# 2. Store the vLLM key in the secret routeforge reads (SP_ONPREM_API_KEY).
say "patching devfoundry-secrets/SP_ONPREM_API_KEY"
kubectl -n "$RF_NS" patch secret devfoundry-secrets --type merge -p \
  "{\"stringData\":{\"SP_ONPREM_API_KEY\":\"$VLLM_KEY\"}}" >/dev/null
kubectl -n "$RF_NS" set env deploy/routeforge SP_ONPREM_API_KEY="$VLLM_KEY" >/dev/null
kubectl -n "$RF_NS" rollout status deploy/routeforge --timeout=180s >/dev/null
sleep 2
# The restart kills the old pod's network sandbox — restart the port-forward.
pkill -f "port-forward" 2>/dev/null || true
sleep 2
kubectl -n "$RF_NS" port-forward svc/routeforge 8000:8000 >/tmp/opencode/pf-rf.log 2>&1 &
PFPID=$!
sleep 4
for i in $(seq 1 10); do
  curl -s --noproxy '*' -m 2 -o /dev/null "$RF_BASE_URL/health" && break
  sleep 2
done
# The env restart created a fresh container — /tmp db is wiped. Re-onboard the
# model via the admin API (the registry refreshes on admin writes).
say "re-onboarding $SLUG after restart"
curl -s --noproxy '*' -m 10 -c "$RF_COOKIE" -X POST "$RF_BASE_URL/admin/login" \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"$RF_ADMIN_USER\",\"password\":\"$RF_ADMIN_PASSWORD\"}" >/dev/null
curl -s --noproxy '*' -m 30 -b "$RF_COOKIE" -X POST "$RF_BASE_URL/admin/infra/models" \
  -H 'Content-Type: application/json' \
  -d "{\"slug\":\"$SLUG\",\"display_name\":\"GLM 5.3 Flash\",\"tier\":\"mid\",\"endpoint\":\"$ENDPOINT\",\"api_key_env\":\"SP_ONPREM_API_KEY\",\"price_input\":0.0,\"price_output\":0.0,\"quality\":0.5,\"context_window\":262144,\"enabled\":true,\"accepts_raw_sensitive\":true}" \
  > /tmp/opencode/onboard.json || true
# 409 (already onboarded and enabled) = no write happened — force a registry
# refresh by PUT-ing the model (an admin write always refreshes the cache).
if grep -q "already exists" /tmp/opencode/onboard.json 2>/dev/null; then
  say "model already onboarded — PUT to refresh the registry"
  curl -s --noproxy '*' -m 30 -b "$RF_COOKIE" -X PUT "$RF_BASE_URL/admin/infra/models/$SLUG" \
    -H 'Content-Type: application/json' \
    -d "{\"slug\":\"$SLUG\",\"display_name\":\"GLM 5.3 Flash\",\"tier\":\"mid\",\"endpoint\":\"$ENDPOINT\",\"api_key_env\":\"SP_ONPREM_API_KEY\",\"price_input\":0.0,\"price_output\":0.0,\"quality\":0.5,\"context_window\":262144,\"enabled\":true,\"accepts_raw_sensitive\":true}" \
    > /tmp/opencode/onboard-put.json || true
  head -c 200 /tmp/opencode/onboard-put.json; echo
fi
kill $PFPID 2>/dev/null || true

# ---------------------------------------------------------------------------
# 3. Admin login + create application.
say "logging in and creating application $APP_ID"
pkill -f "port-forward" 2>/dev/null || true
sleep 2
kubectl -n "$RF_NS" port-forward svc/routeforge 8000:8000 >/tmp/opencode/pf-rf.log 2>&1 &
PFPID=$!
sleep 4
for i in $(seq 1 10); do curl -s --noproxy '*' -m 2 -o /dev/null "$RF_BASE_URL/health" && break; sleep 2; done
curl -s --noproxy '*' -m 10 -c "$RF_COOKIE" -X POST "$RF_BASE_URL/admin/login" \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"$RF_ADMIN_USER\",\"password\":\"$RF_ADMIN_PASSWORD\"}" >/dev/null

curl -s --noproxy '*' -m 10 -b "$RF_COOKIE" -X POST "$RF_BASE_URL/admin/applications" \
  -H 'Content-Type: application/json' \
  -d "{\"id\":\"$APP_ID\",\"name\":\"DevFoundry Console\",\"owner_email\":\"admin@devfoundry.local\",\"default_residency\":\"any\"}" \
  > /tmp/opencode/app-create.json
TOKEN=$(python3 -c "
import json
d = json.load(open('/tmp/opencode/app-create.json'))
print(d.get('initial_token') or d.get('token') or '')
")
if [ -z "$TOKEN" ]; then say "no initial token in app-create.json — minting one"; fi

# 4. Policy.
curl -s --noproxy '*' -m 10 -b "$RF_COOKIE" -X PUT "$RF_BASE_URL/admin/applications/$APP_ID/policy" \
  -H 'Content-Type: application/json' \
  -d '{"stream_mode":"verified_then_stream","max_cost_usd_per_request":2.0}' >/dev/null

# 5. Mint a token if the initial one is missing.
if [ -z "$TOKEN" ]; then
  TOKEN=$(curl -s --noproxy '*' -m 10 -b "$RF_COOKIE" -X POST "$RF_BASE_URL/admin/applications/$APP_ID/tokens" \
    -H 'Content-Type: application/json' -d '{}' | python3 -c "
import json, sys
d = json.load(sys.stdin)
print(d.get('token') or d.get('initial_token') or '')
")
fi
[ -n "$TOKEN" ] || { say "ERROR: no token obtained"; exit 1; }
kill $PFPID 2>/dev/null || true

# ---------------------------------------------------------------------------
# 6. Patch the token into the opencode pod's configured default (OpenCode
#    ignores per-message model overrides, so it must be the pod default).
say "patching OPENCODE_CONFIG_CONTENT with the fresh token"
kubectl -n "$OPENCODE_NS" set env deploy/"$OPENCODE_DEPLOY" \
  OPENCODE_CONFIG_CONTENT="{\"model\":\"routeforge/glm-5.3-flash\",\"small_model\":\"routeforge/glm-5.3-flash\",\"provider\":{\"routeforge\":{\"npm\":\"@ai-sdk/openai-compatible\",\"options\":{\"baseURL\":\"http://routeforge:8000/v1\",\"apiKey\":\"$TOKEN\"},\"models\":{\"glm-5.3-flash\":{\"name\":\"GLM 5.3 Flash\"}}}}}" >/dev/null
kubectl -n "$OPENCODE_NS" rollout status deploy/"$OPENCODE_DEPLOY" --timeout=180s >/dev/null

# ---------------------------------------------------------------------------
# 7. Smoke probe: a minimal streaming completion through the full chain.
say "smoke probe (streaming completion through the full chain)"
kubectl -n "$RF_NS" port-forward svc/routeforge 8000:8000 >/tmp/opencode/pf-rf.log 2>&1 &
PFPID=$!
sleep 4
CODE=$(curl -s --noproxy '*' -m 30 -o /tmp/opencode/reonboard-probe.txt -w '%{http_code}' \
  -X POST "$RF_BASE_URL/v1/chat/completions" \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"model":"glm-5.3-flash","messages":[{"role":"user","content":"Say OK"}],"max_tokens":8,"stream":true}')
if [ "$CODE" = "200" ]; then
  say "OK: smoke probe 200, chain is live"
else
  say "WARN: smoke probe returned $CODE (chain may need attention)"
  head -c 300 /tmp/opencode/reonboard-probe.txt || true
fi
kill $PFPID 2>/dev/null || true
pkill -f "port-forward" 2>/dev/null || true
say "done"
