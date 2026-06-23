#!/usr/bin/env bash
# SAGA release automation: version-in -> release-out.
#
# Promotes CHANGELOG.md [Unreleased] into a per-version changelog file,
# resets [Unreleased], bumps the installer REF, then (real run only) commits,
# tags, pushes main, and publishes a GitHub Release. --dry-run generates and
# shows everything, prints the exact git/gh commands, then reverts — no trace.
#
# Manifest versions (backend/pyproject.toml, frontend/package.json) are
# intentionally NOT bumped: both sit at the base version and a pre-release
# suffix diverges between PEP440 (0.1.0b2) and npm (0.1.0-beta.2). Revisit if a
# final (non pre-release) version ever needs the manifests in sync.
#
# Usage: scripts/release.sh <version> [--dry-run]   e.g. 0.2.0 | 0.1.0-beta.2
set -euo pipefail

# --- args -------------------------------------------------------------------
DRY_RUN=0
VERSION=""
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    -*) echo "ERROR: unknown flag '$arg'" >&2; exit 1 ;;
    *) [ -z "$VERSION" ] || { echo "ERROR: unexpected argument '$arg'" >&2; exit 1; }; VERSION="$arg" ;;
  esac
done
[ -n "$VERSION" ] || { echo "Usage: scripts/release.sh <version> [--dry-run]   e.g. 0.2.0 | 0.1.0-beta.2" >&2; exit 1; }

cd "$(git rev-parse --show-toplevel)"

# --- guards -----------------------------------------------------------------
if ! [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-(beta|rc)\.[0-9]+)?$ ]]; then
  echo "ERROR: invalid version '$VERSION'. Expected X.Y.Z, optionally -beta.N or -rc.N." >&2
  exit 1
fi
TAG="v$VERSION"
PRERELEASE=0
[[ "$VERSION" == *-* ]] && PRERELEASE=1

if git rev-parse -q --verify "refs/tags/$TAG" >/dev/null; then
  echo "ERROR: tag $TAG already exists. Version tags are immutable — pick a new version." >&2
  exit 1
fi

# on-main + clean-tree: hard-abort on a real run, warn-only on a dry-run so the
# generation can be exercised from the feature branch before it lands.
guard() {
  if [ "$DRY_RUN" = 1 ]; then
    echo "WARNING (dry-run, would abort on a real run): $1" >&2
  else
    echo "ERROR: $1" >&2
    exit 1
  fi
}
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
[ "$BRANCH" = "main" ] || guard "not on main (on '$BRANCH'); a release must run from main."
[ -z "$(git status --porcelain)" ] || guard "working tree is dirty; commit or stash so the only diff is the release."

# main must match origin/main, else the release commit won't fast-forward on push.
git fetch --quiet origin main || guard "could not fetch origin/main to check sync."
[ "$(git rev-parse main 2>/dev/null)" = "$(git rev-parse origin/main 2>/dev/null)" ] \
  || guard "local main is not in sync with origin/main; run 'git checkout main && git pull' first."

# --- paths & scratch --------------------------------------------------------
DATE="$(date +%Y-%m-%d)"
CHANGELOG="CHANGELOG.md"
CHANGELOG_FILE="docs/changelog/CHANGELOG-$TAG.md"
BAT="install/windows/install_saga.bat"
SH="install/linux-macos/install_saga.sh"

unrel="$(mktemp)"; hl_block="$(mktemp)"; int_block="$(mktemp)"
hl_grouped="$(mktemp)"; int_promoted="$(mktemp)"; notes="$(mktemp)"
trap 'rm -f "$unrel" "$hl_block" "$int_block" "$hl_grouped" "$int_promoted" "$notes"' EXIT

# --- parse [Unreleased] -----------------------------------------------------
awk '/^## \[Unreleased\]/{u=1;next} u&&/^## /{u=0} u{print}' "$CHANGELOG" > "$unrel"
awk '/^### Highlights/{h=1;next} h&&/^### /{h=0} h{print}' "$unrel" > "$hl_block"
awk '/^### Internal/{i=1;next} i&&/^### /{i=0} i{print}' "$unrel" > "$int_block"

trim_blanks() {
  awk '{l[NR]=$0} END{s=1; while(s<=NR&&l[s]~/^[ \t]*$/)s++; e=NR; while(e>=s&&l[e]~/^[ \t]*$/)e--; for(i=s;i<=e;i++)print l[i]}'
}

# Collapse trailing blank lines to a single final newline — pre-commit's
# end-of-file-fixer rejects (and rewrites) files that end with extra blanks.
finalize_newline() { printf '%s\n' "$(cat "$1")" > "$1.tmp" && mv "$1.tmp" "$1"; }

# Group "- [Area] text" bullets under "### Area" headers, canonical order first,
# unknown areas appended (with a warning). The [Area] tag is stripped.
awk '
  /^- \[/ {
    a=$0; sub(/^- \[/,"",a); idx=index(a,"]")
    if (idx==0) next
    area=substr(a,1,idx-1); text=substr(a,idx+1); sub(/^[ \t]+/,"",text)
    if (!(area in seen)) { order[++n]=area; seen[area]=1 }
    items[area]=items[area] "- " text "\n"
  }
  END {
    nc=split("Gameplay|World & DM|UI|Installer|Memory & AI|Infra", canon, "|")
    for (i=1;i<=nc;i++){ c=canon[i]; if (c in seen){ printf "### %s\n\n%s\n", c, items[c]; done[c]=1 } }
    for (i=1;i<=n;i++){ a=order[i]; if (!(a in done)){ printf "### %s\n\n%s\n", a, items[a]; print "WARNING: unknown area \x27" a "\x27 (appended; not in the canonical list)" > "/dev/stderr" } }
  }
' "$hl_block" | trim_blanks > "$hl_grouped"

# Internal copied as-is, headings promoted one level (#### -> ###) so the
# archive is consistent under "## Internal".
sed -E 's/^#### /### /' "$int_block" | trim_blanks > "$int_promoted"

# --- write the per-version changelog ---------------------------------------
{
  printf '# SAGA %s — %s\n\n' "$TAG" "$DATE"
  if [ -s "$hl_grouped" ]; then printf '## Highlights\n\n'; cat "$hl_grouped"; printf '\n\n'; fi
  if [ -s "$int_promoted" ]; then printf '## Internal\n\n'; cat "$int_promoted"; printf '\n'; fi
} > "$CHANGELOG_FILE"
finalize_newline "$CHANGELOG_FILE"

# --- reset [Unreleased] to empty (keep the preamble) ------------------------
awk '/^## \[Unreleased\]/{print; print ""; exit} {print}' "$CHANGELOG" > "$CHANGELOG.tmp"
mv "$CHANGELOG.tmp" "$CHANGELOG"
finalize_newline "$CHANGELOG"

# --- bump installer REF -----------------------------------------------------
bat_expr='s/^set "REF=v[^"]*"/set "REF='"$TAG"'"/'
sh_expr='s/^REF="\$\{SAGA_REF:-v[^}]*\}"/REF="${SAGA_REF:-'"$TAG"'}"/'
sed -E "$bat_expr" "$BAT" > "$BAT.tmp" && mv "$BAT.tmp" "$BAT"
sed -E "$sh_expr" "$SH"  > "$SH.tmp"  && mv "$SH.tmp"  "$SH"
grep -q "REF=$TAG\"" "$BAT" || { echo "ERROR: REF bump did not take in $BAT" >&2; exit 1; }
grep -q "SAGA_REF:-$TAG}" "$SH" || { echo "ERROR: REF bump did not take in $SH" >&2; exit 1; }

# --- release notes (the Highlights body) ------------------------------------
if [ -s "$hl_grouped" ]; then cat "$hl_grouped" > "$notes"; else echo "See \`$CHANGELOG_FILE\`." > "$notes"; fi

# --- dry-run: show everything, print commands, revert -----------------------
if [ "$DRY_RUN" = 1 ]; then
  echo "===== generated changelog ($CHANGELOG_FILE) ====="
  cat "$CHANGELOG_FILE"
  echo "===== diff (tracked files) ====="
  git --no-pager diff -- "$CHANGELOG" "$BAT" "$SH"
  echo "===== commands the real run would execute ====="
  echo "git add \"$CHANGELOG_FILE\" \"$CHANGELOG\" \"$BAT\" \"$SH\""
  echo "git commit -m \"docs(changelog): promote to $TAG\""
  echo "git tag -a \"$TAG\" -m \"SAGA $TAG\""
  echo "git push origin main --follow-tags"
  if [ "$PRERELEASE" = 1 ]; then
    echo "gh release create \"$TAG\" --target main --prerelease --title \"SAGA $TAG\" --notes-file <highlights>"
  else
    echo "gh release create \"$TAG\" --target main --title \"SAGA $TAG\" --notes-file <highlights>"
  fi
  echo "gh release upload \"$TAG\" \"$BAT\" \"$SH\""
  echo "===== reverting (dry-run leaves no changes) ====="
  git checkout -- "$CHANGELOG" "$BAT" "$SH"
  rm -f "$CHANGELOG_FILE"
  echo "Dry-run complete for $TAG."
  exit 0
fi

# --- real run: outward actions, last and in order ---------------------------
git add "$CHANGELOG_FILE" "$CHANGELOG" "$BAT" "$SH"
git commit -m "docs(changelog): promote to $TAG"
git tag -a "$TAG" -m "SAGA $TAG"
git push origin main --follow-tags
if [ "$PRERELEASE" = 1 ]; then
  gh release create "$TAG" --target main --prerelease --title "SAGA $TAG" --notes-file "$notes"
else
  gh release create "$TAG" --target main --title "SAGA $TAG" --notes-file "$notes"
fi
gh release upload "$TAG" "$BAT" "$SH"
echo "Released $TAG."
