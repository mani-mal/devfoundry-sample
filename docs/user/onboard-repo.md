# Onboarding a New Git Repository

End-user guide: connect a new git repo to DevFoundry and get it qualified.

## Prerequisites

- DevFoundry account (ask your admin) — login at `http://<appliance>:3001/login`
- A git repository (GitHub, GitLab, or self-hosted) with a working build
- Access to the DevFoundry CLI or web console

## 1. Log in

```bash
# Web console
open http://localhost:3001/login

# Or CLI
devfoundry auth login
```

## 2. Register the repo

```bash
devfoundry project create \
  --name my-project \
  --repo-url https://github.com/acme/my-project \
  --default-branch main
```

This registers the repo and creates a project id. Note the project id — it's needed for tasks.

## 3. Verify the repo is reachable

```bash
devfoundry project status my-project
```

Expected: repo cloned, default branch detected, base commit recorded.

## 4. Create your first task

```bash
devfoundry task create "Fix the login redirect bug" \
  --project-id <projectId> \
  --user-id <userId>
```

Watch it progress through the lifecycle:

```
Submitted → Qualified → Validating → AwaitingReview
```

Check status:

```bash
devfoundry task status <taskId>
```

## 5. Review the outcome

When the task reaches `AwaitingReview`, a review packet is generated. Review it in the web console (Task Detail page) and disposition it — the human disposition moves the task to `Completed`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `EAI_AGAIN` errors | Set `--noproxy '*'` on curl, or unset `http_proxy` |
| Repo not reachable | Check credentials and network from the appliance |
| Task stuck in Submitted | Check worker is running (`kubectl -n runai-dev-foundry get pods`) |
| Task stuck in Qualified | Harness may be busy — non-fatal, wait |
