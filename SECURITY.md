# Security Policy

## Reporting a vulnerability

Please report vulnerabilities privately. Do not open a public issue, pull request, or discussion with exploit details.

- On GitHub, open this repository's **Security** tab, choose **Report a vulnerability**, and submit the private report.
- If that button is unavailable, email datumlabs@eulercartan.com.

Include the affected version, the behavior you observed, minimal reproduction steps, and the likely impact. Do not include live credentials or private source data. We will investigate through a private channel and coordinate any public disclosure after a fix is available. No response time is promised in this release candidate.

## Supported versions

Supported versions: only the latest release gets security fixes.

## Scope

Tarsier reads connected user data. Its optional PostGIS trigger installer is an explicit, separately authorized action that writes trigger objects to the selected source. Tarsier also writes its own local state, caches, snapshots, and logs. Treat a breach of these boundaries, secret exposure, or an unsafe default as a security issue.
