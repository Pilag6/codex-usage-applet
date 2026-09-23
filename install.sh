#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
TARGET="${HOME}/.local/share/cinnamon/applets/codex-usage@pila"
SOURCE="$ROOT/src"
if [[ -L "$TARGET" && "$(readlink -- "$TARGET")" == "$SOURCE" ]]; then
    printf 'Development symlink already installed.\n'
elif [[ -e "$TARGET" || -L "$TARGET" ]]; then
    printf 'Refusing to overwrite an existing applet installation.\n' >&2
    exit 1
else
    mkdir -p -- "$(dirname -- "$TARGET")"
    ln -s -- "$SOURCE" "$TARGET"
    printf 'Development symlink installed.\n'
fi
printf 'Add Codex Usage through Cinnamon panel → Applets.\n'
