# Security policy

## Reporting a vulnerability

Please report it privately through GitHub: **Security → Report a vulnerability** on this repository. Don't open a public issue or pull request for it.

Include what an attacker can do, the steps or a request that shows it, and the commit you tested. You'll get an acknowledgement, and then a fix or an explanation. This is a one-maintainer project, so responses are best effort.

## Supported versions

Only the latest `main` gets fixes. There are no release branches.

## Scope

In scope: the Django API, the SPA, the nginx config, the Docker images and compose files, and the CI workflows in this repository.

Out of scope: the public demo's seeded data, which is reset nightly. So are findings that need an already-compromised staff account or host, and rate-limit or denial-of-service findings that don't come with a concrete amplification.

## What is already in place

Each control is listed with the test that proves it. [docs/SECURITY_MODEL.md](docs/SECURITY_MODEL.md) covers passwords, MFA, sessions, hashed integration keys, security headers and the audit log. [docs/CHANNELS.md](docs/CHANNELS.md) covers signed action links, webhook signatures and the SSRF guard. [docs/TENANCY.md](docs/TENANCY.md) says what is and isn't isolated. Every pull request runs pip-audit, npm audit and Trivy (lockfiles, Dockerfiles, committed secrets and the built images), and the build publishes CycloneDX SBOMs.
