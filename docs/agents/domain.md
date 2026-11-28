# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

## Before exploring, read these

- **`docs/superpowers/CONTEXT.md`**: the glossary.
- **`docs/superpowers/adr/`**: read ADRs that touch the area you're about to work in.

Both live in the private notes repository (`docs/superpowers/`, see `CLAUDE.md` "Read first"), never at the public repo root: the glossary and decisions can name things the owner keeps private. A session without the owner's folder proceeds without them.

Architecture decisions made before ADRs existed are in `docs/superpowers/specs/00-conventions.md` (private, see `CLAUDE.md` "Read first"). Where `CLAUDE.md` and it differ, `CLAUDE.md` wins.

If any of these files don't exist, **proceed silently**. Don't flag their absence; don't suggest creating them upfront. The `/domain-modeling` skill (reached via `/grill-with-docs` and `/improve-codebase-architecture`) creates them lazily when terms or decisions actually get resolved.

## File structure

Single-context, in the private notes repository:

```
docs/superpowers/
├── CONTEXT.md
└── adr/
    ├── 0001-<slug>.md
    └── 0002-<slug>.md
```

## Use the glossary's vocabulary

When your output names a domain concept (in an issue title, a refactor proposal, a hypothesis, a test name), use the term as defined in `docs/superpowers/CONTEXT.md`. Don't drift to synonyms the glossary explicitly avoids.

If the concept you need isn't in the glossary yet, that's a signal: either you're inventing language the project doesn't use (reconsider) or there's a real gap (note it for `/domain-modeling`).

## Flag ADR conflicts

If your output contradicts an existing ADR, surface it explicitly rather than silently overriding:

> _Contradicts ADR-0007 (event-sourced orders), but worth reopening because…_
