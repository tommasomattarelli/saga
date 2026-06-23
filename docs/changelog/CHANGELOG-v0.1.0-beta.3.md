# SAGA v0.1.0-beta.3 — 2026-06-24

## Highlights

### Installer

- Each release now attaches the install scripts (`install_saga.bat`, `install_saga.sh`) as downloadable assets, so a non-technical user can grab the installer straight from a specific release page.


## Internal

### Added
- `release.sh` uploads the two installer scripts as release assets after creating the GitHub Release (`gh release upload`), reflected in the `--dry-run` command preview.
