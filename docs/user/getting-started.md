# Onboarding as a Developer

First-time setup: get an account, log in, and make your first task.

## 1. Get an account

Ask your DevFoundry admin for an account (email + password).

## 2. Log in

Web console: `http://<appliance>:3001/login`

Or via CLI:

```bash
devfoundry auth login
```

## 3. Onboard your first repo

```bash
devfoundry project create --name my-project \
  --repo-url https://github.com/acme/my-project
```

See [Onboarding a New Git Repository](onboard-repo.md).

## 4. Develop a skill (optional)

Write a `SKILL.md`, install it into the catalog, get it approved.

See [Developing Skills](skills.md).

## 5. Run tasks and review

```bash
devfoundry task create "Fix the bug" --project-id <projectId>
devfoundry task status <taskId>
```

When the task reaches `AwaitingReview`, review the packet in the web console and disposition it.

## Lifecycle

```
Submitted → Qualified → Validating → AwaitingReview → (human) → Completed
```
