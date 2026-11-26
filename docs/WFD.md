# Tarsier — Development & Operations Workflow (WFD)

**Version:** 1.0 (v1 scope)
**Status:** Approved for use
**Date:** 2026-10-10
**Companion to:** PRD v1.0, TAD v1.0, FSD v1.0, DVS v1.0, FTL v1.0

---

## 0. How to use this document

### For Claude Code (the builder)
- This document governs **how code moves from idea to shipped**, not what to build (see PRD) or how (see TAD/FSD/DVS).
- Every change happens on a **branch**, through a **Pull Request (PR)**, referencing the relevant **FTL ID(s)**.
- A PR cannot merge unless its related FTL test(s) pass (Section 4).
- Every PR must pass the **security checklist** (Section 6) before merging.

### For the Manager / repo owner
- Use this document to run the repo day to day: branching, reviewing, releasing, and handling contributors and security reports.

---

## 1. Team & contribution model (current stage)

- **Current team:** one person (repo owner) writing code, with **2 colleagues** being invited to test and contribute.
- **Contributors beyond the core team:** expected later, once the project is public on GitHub and stable.
- **Code lives on GitHub**, under the company's GitHub account, licensed **Apache-2.0**.

**Growth path for trust:**
1. **Now:** owner writes code and self-reviews/merges their own PRs.
2. **Next:** the 2 colleagues contribute via PRs; owner reviews and merges.
3. **Later (earned, not automatic):** a colleague who has had a handful of PRs merged cleanly may be given **merge rights** to `main`.
4. **Future (public contributors):** same PR process; merge rights stay limited to proven, trusted people — never open to anyone by default.

---

## 2. Branching model

- **`main`** — always the current stable, working version. Nothing is committed to it directly.
- **Feature/fix branches** — all work happens here, named with a simple convention:

```
feature/TRS-019-statistics-engine
fix/TRS-042-change-capture-bug
chore/update-readme
docs/wfd-update
```

- Format: `type/TRS-###-short-description` (type = `feature`, `fix`, `chore`, or `docs`; the `TRS-###` is omitted only for work with no matching FTL ID, like a pure docs or chore change).
- Branch from the latest `main`; keep branches focused on one FTL item (or a small related group) at a time.

**Acceptance check:** no direct commits to `main`; every branch name follows the convention.

---

## 3. Pull Request (PR) process

1. **Open a PR** from the feature/fix branch into `main`.
2. **PR title/description must reference the FTL ID(s)** it addresses, e.g.:
   > `Implements TRS-019, TRS-020 — per-column stats + messy-category detection`
3. **Automatic checks (CI) run on every PR:**
   - Backend tests (`pytest`)
   - Frontend tests (`Vitest` / React Testing Library)
   - Any relevant FTL-linked test(s) for the PR's claimed IDs
4. **A PR cannot merge if:**
   - Its linked FTL test(s) are failing (Section 4), or
   - The security checklist (Section 6) is not completed, or
   - (Once another reviewer exists) it has not been approved by someone other than the author.
5. **Right now (solo stage):** the owner opens the PR, waits for CI to pass, completes the security checklist, then self-approves and merges.
6. **Once a second trusted person exists:** PRs require **at least one approval from someone other than the author** before merging — this becomes mandatory the moment a second person has merge rights.

**Acceptance check:** every merged PR shows passing CI, a completed security checklist, and (once applicable) a non-author approval.

---

## 4. Testing requirement (ties to the FTL)

- Every PR that implements or changes behavior covered by the **FTL (FTL.md)** must bring its linked row(s) from `Not Started`/`Built` to at least `Tested` as part of that PR.
- **CI blocks the merge** if a linked FTL test fails.
- The Manager updates the FTL's `Status` column to `Passed` after independently confirming the result (per FTL Section 0 — the builder doesn't self-mark `Passed`).
- **Stage 1 (internal exam) is complete** when all FTL rows reach `Passed` — this is the gate before the v1.0 release (Section 8).

**Acceptance check:** no PR merges with a linked FTL test in a `Failed` state; the FTL status table stays current as work merges.

---

## 5. Issue tracking

- **GitHub Issues** is used for all bugs, ideas, and discussion — no separate tracker.
- Bug reports should reference the relevant **FTL ID** if they relate to a specific tested feature; otherwise filed as a new, undesignated issue.
- Feature ideas beyond the current PRD scope are filed as issues tagged `future` / `v2`, not built into v1 without a PRD update.
- Security vulnerabilities are **never filed as a public Issue** — see Section 7.

**Acceptance check:** the repo's Issues tab is the single place bugs and ideas are tracked; no parallel tracker is used.

---

## 6. Security checklist (mandatory on every PR)

Before any PR merges, it must be checked against this list. **This is a starting checklist — more items will be added once the app is fully built and real risk areas are clearer (noted as a living document, Section 6.1).**

- [ ] Does this change add any **write access** to a user's connected data source? (Should be **no**, except the one approved, documented exception: the optional PostGIS change-tracking trigger install, PRD §6.2.)
- [ ] Does this change **log or expose a secret** (API key, database password) in plain text, in logs, or in an error message?
- [ ] Does this change add a **new outbound network call**? If yes, is it limited to an explicitly configured AI endpoint, SMTP server, or webhook URL (TAD §9), triggered by the user's test send or enabled rule, and free of telemetry/phone-home behavior?
- [ ] Does this change affect how **secrets are stored** (TAD §9 — OS secure storage / encrypted at rest)? If yes, has it been verified not to weaken that storage?
- [ ] Does this change touch the **change-tracking trigger install** flow (PRD §6.2)? If yes, is the one-time, optional, skippable, permission-based design still intact?
- [ ] Does this change introduce a new dependency? If yes, is it from a reputable source, and does it match the locked stack (TAD §3) rather than an unapproved substitute?

### 6.1 Living document note
As Tarsier nears completion, this checklist will be expanded to include app-specific risks discovered during building (e.g. around the automation builder's webhook action, or AI query handling). Updates to this checklist are themselves a PR, reviewed like any other change.

**Acceptance check:** every merged PR shows this checklist completed in its description; checklist updates are version-controlled like any other document change.

---

## 7. Reporting a security problem

- Security vulnerabilities are reported **privately** — using **GitHub's private vulnerability reporting** feature on the repo, or a dedicated private contact email (set up when the repo goes public).
- **Never** as a public GitHub Issue or public PR — this avoids exposing an unfixed flaw.
- The repo owner acknowledges the report, investigates, and fixes privately before any public disclosure.
- Once fixed, a summary may be published (e.g. in release notes) without exposing exploit details irresponsibly.

**Acceptance check:** the repo's `SECURITY.md` (referenced in TAD §10) clearly states the private reporting process before the project goes public.

---

## 8. Releases & versioning

- **Versioning: Semantic Versioning** (`MAJOR.MINOR.PATCH`, e.g. `1.0.0`).
  - `MAJOR` — breaking changes or a fundamentally new capability (e.g. adding editing in a future version).
  - `MINOR` — new features added without breaking existing behavior.
  - `PATCH` — bug fixes only.
- **Release style:** **one v1.0.0 release** once **Stage 1 (FTL fully `Passed`)** and **Stage 2 (real-user stress test, PRD §9)** are both complete. Before that point, work happens on `main` without public version tags (or pre-release tags like `0.x.x` / `v1.0.0-rc1` if useful internally).
- **After v1.0.0:** move to **regular smaller releases** (e.g. `1.1.0`, `1.2.0`) as features and fixes accumulate, each still gated by its linked FTL tests passing.

**Acceptance check:** no `1.0.0` tag exists until the FTL is fully `Passed` and Stage 2 feedback has been addressed; releases after that follow Semantic Versioning consistently.

---

## 9. Contributors & credit

To make contributing worthwhile for colleagues and future open-source contributors:

- **README contributors section** — everyone who has a merged PR is listed by name/GitHub username.
- **Release notes** — each release credits the contributors whose work is included.
- **Earned roles** — a contributor who consistently submits quality, trustworthy PRs may be named a **maintainer** (with merge rights, per Section 1) and recognized as such in the README.
- Contribution here is real-world, verifiable work: public commit history under their name, on a working production-grade tool — usable on a resume or portfolio regardless of future employment.

**Acceptance check:** the README has a visible, kept-current contributors section; release notes credit contributors for that release's included work.

---

## 10. Summary — the day-to-day loop

1. Pick an item from the **FTL** (or an Issue).
2. Branch: `feature/TRS-###-short-description`.
3. Build it, following the **PRD/TAD/FSD/DVS**.
4. Open a PR referencing the FTL ID(s); CI runs tests.
5. Complete the **security checklist**.
6. Self-merge (solo stage) or get approval (once a second reviewer exists).
7. Manager confirms the FTL row(s) as `Passed`.
8. Repeat until the FTL is fully `Passed` → Stage 2 stress test → `v1.0.0` release.
9. After v1.0.0: same loop, smaller regular releases.

---

*End of WFD v1.0.*
