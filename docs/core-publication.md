# EmpneonCore Publication

`PandaBakers/Empneon` remains the private source of truth for Core, Cloud, business plans,
prospects, and working context. Publishing a GitHub release whose tag is `core-vX.Y.Z` copies only
the tracked files allowed by `.github/core-publication.toml` to the public
`PandaBakers/EmpneonCore` repository.

The exporter rejects databases, environment files, logs, certificates, private keys, common
credential formats, and symlinks even if a manifest pattern includes them. Each release replaces
the destination snapshot, so deletions are synchronized too; the private Git history is never
copied.

## One-time setup

1. Create public `PandaBakers/EmpneonCore`, initialized with a README so its `main` branch exists.
2. Create a fine-grained GitHub token limited to `EmpneonCore` with **Contents: Read and write**
   and **Workflows: Read and write**.
3. Add it to private `Empneon` as the Actions secret `REPOSITORY_SYNC_TOKEN`.
4. After the first publication, protect `EmpneonCore/main` while allowing the token owner to push.

## Validate locally

```powershell
py -3.12 scripts/test_export_core.py
```

## Publish

Create a GitHub release from a commit already merged into `main`, using a tag such as
`core-v0.3.0`. From the command line, the equivalent is:

```powershell
gh release create core-v0.3.0 --generate-notes
```

The destination gets tag `v0.3.0`. Tags without the `core-v` prefix do not publish anything.
Never move or reuse a published release tag; increment the version instead.
