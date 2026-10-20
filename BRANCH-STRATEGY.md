# Branch Strategy — Provable Resilience Intelligence

## Git Flow (Simplified)

```
main ←── production-ready, protected, deploys via bundle to prod target
  └── develop ←── integration branch, deploys to dev target
        ├── feature/<TASK-CODE> ←── agent/human work branches
        ├── fix/<TASK-CODE>
        └── data/<TASK-CODE>
```

## Branch Rules

| Branch | Protection | Merge via | Deploy target |
|--------|-----------|-----------|---------------|
| `main` | Required PR + 1 approval + passing CI | Squash merge | `prod` |
| `develop` | Required PR + passing CI | Merge commit | `dev` |
| `feature/*` | None | PR → develop | — |
| `fix/*` | None | PR → develop | — |
| `data/*` | None | PR → develop | — |

## Naming Convention

Branch names follow the Lakebase task code:

```
feature/P1-SYNTH-GEO-SITE
feature/P2-GOLD-RESILIENCE-SCORE
fix/P0-GITHUB-REPO
data/P1-INJECT-PATTERNS
```

## Agent Workflow

1. Agent picks task from Lakebase → marks `in_progress`
2. Creates branch `feature/<TASK-CODE>` from `develop`
3. Commits changes with message: `[<TASK-CODE>] <description>`
4. Opens PR to `develop` — CI runs `bundle validate`
5. @qa reviews, @devops merges
6. Agent marks task `completed` in Lakebase

## CI/CD Pipeline

* **On PR to develop:** `bundle validate --target dev` + Python lint + unit tests
* **On merge to develop:** `bundle deploy --target dev`
* **On merge to main:** `bundle deploy --target prod`

## Commit Message Format

```
[TASK-CODE] Short description (max 72 chars)

Optional body with details.
Reference: Lakebase task_code for traceability.
```

## Tags

Release tags follow semver: `v0.1.0`, `v0.2.0`, etc.
Milestone tags match project phases: `phase-0`, `phase-1`, etc.
