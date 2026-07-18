# Product Publication

`mf-rl/Empneon` is the private monorepo and source of truth. Each product root is independently
buildable and is exported without private Git history:

| Release tag | Source | Destination |
|---|---|---|
| `core-vX.Y.Z` | `core/` | `mf-rl/EmpneonCore` |
| `thesims4_vX.Y.Z` | `adapters/thesims4/` | `mf-rl/EmpneonTheSims4` |
| `godot-vX.Y.Z` | `adapters/godot/` | `mf-rl/EmpneonGodot` |

The exporter strips the product directory prefix and overlays the shared license, contribution
guide, code of conduct, attributes, and GitHub community templates. It rejects databases,
environment files, logs, certificates, private keys, common credential formats, and symlinks.
Each publication replaces the destination snapshot, so deletions are synchronized too.

## One-time setup

1. Create each destination repository with an initial `main` branch.
2. Give the fine-grained token **Contents: Read and write** and **Workflows: Read and write** for
   every destination repository.
3. Store it in private Empneon as `REPOSITORY_SYNC_TOKEN`.
4. Protect each destination `main` branch while allowing the token owner to push.

## Validate locally

```powershell
py -3.12 scripts/test_export_products.py
```

Export one product for inspection:

```powershell
py -3.12 scripts/export_product.py --product core --output .\core-export
```

## Publish

Create a release from a commit already merged into `main`:

```powershell
gh release create core-v0.4.0 --generate-notes
gh release create thesims4_v0.1.0 --generate-notes
gh release create godot-v0.1.0 --generate-notes
```

The destination tag drops the product prefix, producing `v0.4.0` or `v0.1.0`. Never move or reuse
a published release tag; increment the version instead.
