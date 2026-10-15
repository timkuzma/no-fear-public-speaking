# Repository credential audit

Date: 15 October 2026. Target: `timkuzma/no-fear-public-speaking`, published `main` and `frentend` branches.

## Scope and results

The initial audit at revision `da9c9d1` covered all 187 tracked files and all 63 reachable commits (521 historical file blobs). Ignored local databases, recordings, backups and environment files were not exported or uploaded. Both published GitHub branches pointed to the audited revision.

- Gitleaks 8.30.1 scanned the current tracked-file export and all reachable Git history, with output redacted and inline suppression comments ignored. Its single finding in each scan was the SHA-256 entry for `docs/api-contract.md` in `evals/speech-feedback/baseline/manifest.json`. The `api` filename caused a generic API-key heuristic to match a file checksum. This is not a credential; the immutable baseline was preserved and no broad scanner exclusion was added.
- TruffleHog 3.95.6 independently scanned Git history with credential verification and update checks disabled. It reported no credential findings and no scan errors. No candidate credentials were transmitted to providers for verification.
- Additional inspection of historical text blobs found no private-key headers or URLs with embedded passwords or access-token query parameters. Credential-like filenames contained only the safe `.env.example`; no actual environment, credential, certificate-private-key, database or media files were tracked in the audited history. Literal passwords and tokens found in test fixtures are synthetic test values.
- Git commit metadata was also checked by Gitleaks with no findings.

These are bounded repository checks, not a guarantee against every possible secret format. Scanner reports remain outside the repository; detected values are never included in this document. Public hostnames, provider model aliases, image IDs and file hashes do not grant access.

## Distribution rules

`.gitignore` and `.dockerignore` exclude common private credential/key files and the generated interview reader plus source-backed interview conclusions. Git ignore rules prevent accidental additions but do not remove files already tracked or present in history; the interview artifacts require the separately authorized history cleanup of both GitHub branches.

Use the hidden-input launcher or private process configuration for provider keys. `.env.example` is documentation, not an automatically loaded environment file. Deployment secrets belong outside the checkout. Before publishing, scan both the tracked tree and history, inspect findings without exposing values, and confirm the target Git refs. If an actual secret is discovered, revoke or rotate it; deleting Git history alone does not revoke access.
