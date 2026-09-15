# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

This repo is **single-context** (despite the `core/` + `frontend/` split, it is one Python+Vue hybrid application with one domain vocabulary). One `CONTEXT.md` at the root, one `docs/adr/`.

## Before exploring, read these

- **`CONTEXT.md`** at the repo root
- **`docs/adr/`**: read ADRs that touch the area you're about to work in
- **`AGENTS.md`** at the repo root is the authoritative architecture reference; `docs/` holds per-version human-facing records. Treat those records as history, not as the current contract.

If `CONTEXT.md` or `docs/adr/` don't exist yet, **proceed silently**. Don't flag their absence; don't suggest creating them upfront. The `/domain-modeling` skill (reached via `/grill-with-docs` and `/improve-codebase-architecture`) creates them lazily when terms or decisions actually get resolved.

## File structure

```
/
├── CONTEXT.md            ← shared language / glossary (agent's dictionary)
├── docs/adr/             ← short ADRs: what was chosen, why, what was rejected
├── docs/<version>/       ← human-facing per-version records (not agent contracts)
└── core/ + frontend/     ← the code
```

## Use the glossary's vocabulary

When your output names a domain concept (in an issue title, a refactor proposal, a hypothesis, a test name), use the term as defined in `CONTEXT.md`. Don't drift to synonyms the glossary explicitly avoids.

If the concept you need isn't in the glossary yet, that's a signal: either you're inventing language the project doesn't use (reconsider) or there's a real gap (note it for `/domain-modeling`).

## Flag ADR conflicts

If your output contradicts an existing ADR, surface it explicitly rather than silently overriding:

> _Contradicts ADR-0007, but worth reopening because…_
