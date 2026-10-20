# Contributing — Provable Resilience Intelligence

## Branch Strategy (GitFlow-lite)

### Protected Branches

| Branch | Protection | Merge From |
|--------|-----------|------------|
| `main` | Requires PR + 1 approval, no force-push | `develop` (release) or `hotfix/*` |
| `develop` | Requires PR, no force-push | `feature/*` |

### Working Branches

| Pattern | Purpose | Base | Merges Into |
|---------|---------|------|-------------|
| `feature/<task-code>-<slug>` | New capability | `develop` | `develop` |
| `hotfix/<task-code>-<slug>` | Urgent production fix | `main` | `main` + `develop` |
| `data/<task-code>-<slug>` | Synthetic data or schema changes | `develop` | `develop` |

### Naming Convention

Branch names MUST include the Lakebase task code:
```
feature/P1-SYNTH-GEO-SITE-geographic-sites
hotfix/P2-GOLD-RESILIENCE-SCORE-null-fix
data/P1-SYNTH-CONDUIT-conduit-generator
```

## Commit Messages

Use Conventional Commits:
```
feat(P1-SYNTH-GEO-SITE): add geographic_site synthetic generator
fix(P2-GOLD-RESILIENCE-SCORE): handle null SRLG scores
chore(P0-BUNDLE-INIT): initialize DAB config
docs(README): update deployment instructions
```

## PR Checklist

- [ ] Task code referenced in branch name and PR title
- [ ] `databricks bundle validate --target dev` passes
- [ ] No `Lumen` or `Lumen Technologies` in any produced asset (use `Lakelink Fiber`)
- [ ] All tables/columns have COMMENT ON descriptions
- [ ] Tests pass (`pytest tests/`)
- [ ] Lakebase task status updated

## DAB Deployment

```bash
# Always validate first
cd bundle && databricks bundle validate --target dev

# Deploy to dev for testing
databricks bundle deploy --target dev

# Only @devops deploys to prod after PR merge to main
databricks bundle deploy --target prod
```

## Tagging Mandate

All assets MUST be tagged: `telco_project: provable_resilience_intelligence`
