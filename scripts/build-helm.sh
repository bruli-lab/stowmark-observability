#!/usr/bin/env bash
set -euo pipefail

version="${1:?Usage: $0 VERSION}"
project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
chart_dir="$project_dir/charts/stowmark-observability"
output_dir="$project_dir/dist"

install -d "$output_dir"

if helm dependency list "$chart_dir" | grep -Eq 'missing|wrong version'; then
    echo "Helm dependencies are incomplete; run helm dependency build $chart_dir" >&2
    exit 1
fi

helm lint "$chart_dir" --values "$chart_dir/values-test.yaml"
helm package "$chart_dir" \
    --version "$version" \
    --app-version "$version" \
    --destination "$output_dir"

output_file="$output_dir/stowmark-observability-${version}.tgz"
test -f "$output_file"
echo "Built $output_file"
