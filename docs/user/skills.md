# Developing Skills

Skills are reusable agent capabilities stored in a Git-backed catalog with approval status. End-user guide: write, install, and use skills.

## Skill lifecycle

```
draft → approved → deprecated
```

Only `approved` skills are used in qualified task execution paths.

## 1. Write a skill

A skill is a directory inside your repo (or a standalone repo) containing:

- `SKILL.md` — instructions for the agent
- optional supporting scripts/files

Minimal `SKILL.md`:

```markdown
---
name: run-lint
description: Run the repo lint suite and report failures
---

# Run lint

1. Run `npm run lint --if-present`
2. Report any errors found
3. Suggest fixes
```

## 2. Install a skill into the catalog

```bash
devfoundry skill install run-lint \
  --version 1.0.0 \
  --git-repo https://github.com/acme/my-project \
  --git-commit HEAD \
  --path skills/run-lint \
  --description "Run the repo lint suite" \
  --status draft
```

Install pulls the skill content and records a content digest.

## 3. List installed skills

```bash
devfoundry skill list
```

Output:

```
Skills:
  - run-lint@1.0.0 (draft) digest=abc123def456
```

## 4. Promote a skill to approved

Ask your admin to flip the approval status from `draft` to `approved` (or use the admin CLI). Only approved skills are attached to qualified tasks.

## 5. Use skills in tasks

Skills attach at task creation:

```bash
devfoundry task create "Fix the bug" --skills skill-git,run-lint
```

The OpenCode harness receives the skills and follows the `SKILL.md` instructions.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Skill not attached | Check status is `approved` |
| Digest mismatch on install | Repo content changed — reinstall with the new commit |
| Skill not visible | `devfoundry skill list` reads the Git-backed catalog |
