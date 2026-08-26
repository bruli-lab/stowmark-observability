#!/usr/bin/env bash
set -euo pipefail

version="${1:?Usage: $0 VERSION}"
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

bash "$project_dir/scripts/build-deb.sh" "$version"
bash "$project_dir/scripts/build-helm.sh" "$version"
