#!/usr/bin/env bash
# Usage : scripts/release.sh 1.0.1 "Description du changement"
# Incrémente la version, complète le CHANGELOG, commit, tag et push.
# Home Assistant détecte la nouvelle version et propose la mise à jour.
set -euo pipefail
cd "$(dirname "$0")/.."
VERSION="${1:?Version attendue, ex. 1.0.1}"
MSG="${2:-Mise à jour}"
CFG=mcz_maestro/config.yaml
CL=mcz_maestro/CHANGELOG.md

sed -i.bak -E "s/^version: .*/version: \"${VERSION}\"/" "$CFG" && rm -f "$CFG.bak"
{ head -n 2 "$CL"; printf '## %s\n\n- %s\n\n' "$VERSION" "$MSG"; tail -n +3 "$CL"; } > "$CL.tmp" && mv "$CL.tmp" "$CL"

git add -A
git commit -m "v${VERSION} : ${MSG}"
git tag "v${VERSION}"
git push && git push --tags
echo "✅ v${VERSION} publiée — dans HA : Paramètres › Apps › Boutique › ⋮ › Rechercher des mises à jour"
