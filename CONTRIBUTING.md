# Contributing

Tarsier is an Apache-2.0 project. Start with an issue describing the user-visible behavior, the source type, and a small way to reproduce it. For a security issue, follow [SECURITY.md](SECURITY.md); do not post exploit details in a public issue.

## Branches and pull requests

- Name branches `type/TRS-###-short-description`, where type is `feature`, `fix`, `chore` or `docs`. Leave out `TRS-###` only when the work has no matching [FTL](docs/FTL.md) ID.
- No direct commits to `main`. Every change arrives through a pull request.
- Name the FTL ID in every pull request.
- Every bug fix comes with a regression test.
- Include the security checklist below, filled in, in the pull request description (from [WFD section 6](docs/WFD.md)):

```markdown
- [ ] Adds no write access to a user's data source (the only exception is the optional PostGIS trigger install)
- [ ] Does not log or expose a secret in plain text, logs or error messages
- [ ] Adds no new outbound network call; or it is limited to a configured AI endpoint, SMTP server or webhook URL, with no telemetry
- [ ] Does not weaken how secrets are stored
- [ ] Keeps the trigger install optional, skippable and permission-based
- [ ] Adds no new dependency; or it is reputable and matches the stack in TAD section 3
```

## Local checks

Use Python 3.11 to 3.14 and Node.js 24. Follow the README's source install order in a fresh environment. The `requirements-py311.lock` and `requirements-py314.lock` files pin the reviewed Windows environments for 3.11 and 3.14; on 3.12 and 3.13 install without them.

Tests use a temporary folder and never touch a real Tarsier data folder. Build the frontend first, as in the README.

Backend tests (the two tests that need a running Ollama model are skipped without one):

```powershell
.\.venv\Scripts\python.exe -m pip install pytest httpx
```

```powershell
.\.venv\Scripts\python.exe -m pytest tests/backend
```

Frontend tests:

```powershell
npm run test --workspace=frontend
```

Tests that need a PostgreSQL server (not yet in this repository) read its port from `TARSIER_TEST_POSTGIS_PORT`. Set it to the port of your own test server, for example `55432`, never one that holds real data.

```powershell
$env:TARSIER_TEST_POSTGIS_PORT = "55432"
```

Build the frontend with `npm run build --workspace=frontend` before opening a pull request. State which source and operating system you actually tested; a mock is not a live connector qualification.

Keep a change focused. Do not include database credentials, personal paths, source data, private exam material, or generated app state. Normal connector activity must be read-only on user data. The optional trigger installer is an explicit user action and needs separate review.

## How a fix reaches users

A fix is merged to `main`, then released with a new version number. Users get it by running `pip install --upgrade tarsier-geo` (once Tarsier is published on PyPI).

## Licensing

Contributions are reviewed under the repository's Apache-2.0 license. Include license and attribution details for any new dependency, font, binary or copied asset in `THIRD_PARTY_NOTICES` and its linked texts.
