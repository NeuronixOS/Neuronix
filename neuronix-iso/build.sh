#!/usr/bin/env bash
# Run from Build/neuronix-iso; live-build cwd from default/metadata/debian.env.

set -euo pipefail
SCRIPT_ROOT="$(cd "$(dirname "$0")" && pwd)"
METADATA="$(cd "$SCRIPT_ROOT/../default/metadata" && pwd)"
# shellcheck source=/dev/null
source "$METADATA/debian.env"
if [[ -r "$SCRIPT_ROOT/../personalize/metadata/debian.env" ]]; then
  # shellcheck source=/dev/null
  source "$SCRIPT_ROOT/../personalize/metadata/debian.env"
fi
_build_var="${NEURONIX_BUILD_ROOT_VAR}"
BUILD_ROOT="${!_build_var:-$NEURONIX_BUILD_ROOT_DEFAULT}"

if [[ ! -d "$BUILD_ROOT/config" ]]; then
  echo "No live-build config — run first: cd $SCRIPT_ROOT && ./setup.sh" >&2
  exit 1
fi

if [[ ! -f "$BUILD_ROOT/.build/config" ]]; then
  echo "Missing stage file $BUILD_ROOT/.build/config." >&2
  echo "Fix: cd $SCRIPT_ROOT && ./setup.sh" >&2
  exit 1
fi

# Drop all binary stage markers so binary_chroot/binary_rootfs/iso always match
# the current chroot. Stale binary_chroot (after ./setup.sh reset chroot, or a
# failed build) caused: mksquashfs "Cannot stat source directory \"chroot\"".
shopt -s nullglob
_stale=( "$BUILD_ROOT"/.build/binary_* )
shopt -u nullglob
for _f in "${_stale[@]}"; do
  rm -f "$_f" 2>/dev/null || sudo rm -f "$_f"
done

cd "$BUILD_ROOT"
exec sudo lb build "$@"
