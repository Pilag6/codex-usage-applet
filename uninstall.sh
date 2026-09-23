#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
TARGET="${HOME}/.local/share/cinnamon/applets/codex-usage@pila"
if [[ -L "$TARGET" && "$(readlink -- "$TARGET")" == "$ROOT/src" ]]; then
    unlink -- "$TARGET"
    printf 'Development symlink removed. Cache and Cinnamon preferences retained.\n'
elif [[ -e "$TARGET" || -L "$TARGET" ]]; then
    printf 'Refusing to remove an installation not owned by this checkout.\n' >&2
    exit 1
else
    printf 'Applet is not installed from this checkout.\n'
fi
