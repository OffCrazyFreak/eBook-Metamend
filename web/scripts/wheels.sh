#!/usr/bin/env sh
# Builds the site's two wheels into public/wheels/: the package from ../ and
# pypdf from PyPI, hash-checked. The manifest lists them in install order.
set -eu
cd "$(dirname "$0")/.."
python="${PYTHON:-python3}"
out=public/wheels
rm -rf "$out"
mkdir -p "$out"
"$python" -m pip wheel --no-deps --quiet --wheel-dir "$out" ..
"$python" -m pip download --no-deps --only-binary=:all: --require-hashes --quiet \
  --dest "$out" --requirement scripts/wheels.txt
pypdf=$(basename "$out"/pypdf-*.whl)
ours=$(basename "$out"/ebook_metamend-*.whl)
printf '["%s", "%s"]\n' "$pypdf" "$ours" > "$out/manifest.json"
cat "$out/manifest.json"
