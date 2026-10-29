#!/bin/sh
# Build the owner service and its guardian against a reviewed manifest.
# Usage: build.sh <owner_manifest.c> <output directory>
# Builds only: it installs nothing, starts nothing and needs no root. Installing the two
# binaries root-owned, provisioning the accounts and the cgroup subtree, and running the
# guardian under the host's supervisor are the administrator's steps in README.md.
set -eu
if [ "$#" -ne 2 ]; then
    echo "usage: $0 <owner_manifest.c> <output directory>" >&2
    exit 64
fi
manifest=$1
output=$2
here=$(cd "$(dirname "$0")" && pwd)
src="$here/src"
cc=${CC:-cc}
flags="-std=c11 -pthread -O2 -Wall -Wextra -Werror -I$src"
owner="$src/native_owner.c $src/native_owner_lease.c $src/native_launch_linux.c $src/native_child_linux.c $src/native_relay_linux.c"
peer="$src/service_peer_linux.c"
mkdir -p "$output"
# shellcheck disable=SC2086  # reason: flag and source lists are intentionally word-split
$cc $flags $owner $peer "$src/native_service.c" "$src/service_policy.c" "$src/service_bootstrap_linux.c" \
    "$src/service_main.c" \
    "$manifest" -o "$output/owner_service"
# shellcheck disable=SC2086  # reason: flag and source lists are intentionally word-split
$cc $flags $owner $peer "$src/guardian_main.c" "$src/guardian_epoch_linux.c" "$src/guardian_journal.c" \
    "$src/guardian_forward_linux.c" "$src/guardian_seccomp_linux.c" "$src/guardian_purge_linux.c" "$manifest" -o "$output/owner_guardian"
echo "built $output/owner_service and $output/owner_guardian (gate closed: no NO_PROTECTED_ACCEPTANCE)"
