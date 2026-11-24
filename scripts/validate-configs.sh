#!/usr/bin/env bash
# Validate the service configuration files with the same images used by
# compose.yaml, and check that the Helm chart's dashboard copy is identical.
#
# Usage: scripts/validate-configs.sh [RENDERED_HELM_MANIFESTS]
#   RENDERED_HELM_MANIFESTS  optional output of `helm template`; when given,
#                            the Collector and Tempo configurations rendered
#                            by the chart are validated too.
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
config_dir="$project_dir/config"
rendered="${1:-}"

compose_json="$(docker compose \
    --project-directory "$project_dir" \
    --env-file "$project_dir/.env.example" \
    config --format json)"

image() {
    jq -er --arg service "$1" '.services[$service].image' <<<"$compose_json"
}

echo "==> Dashboard copies"
cmp "$project_dir/dashboards/stowmark-overview.json" \
    "$project_dir/charts/stowmark-observability/dashboards/stowmark-overview.json"
echo "Dashboards are identical"

echo "==> OpenTelemetry Collector ($(image otel-collector))"
docker run --rm \
    -v "$config_dir/otel-collector.yaml:/etc/otelcol/config.yaml:ro" \
    "$(image otel-collector)" validate --config=/etc/otelcol/config.yaml
echo "Collector configuration is valid"

echo "==> Prometheus ($(image prometheus))"
docker run --rm --entrypoint promtool \
    -v "$config_dir/prometheus.yaml:/etc/prometheus/prometheus.yaml:ro" \
    "$(image prometheus)" check config /etc/prometheus/prometheus.yaml

echo "==> Loki ($(image loki))"
docker run --rm \
    -v "$config_dir/loki.yaml:/etc/loki/config.yaml:ro" \
    "$(image loki)" -config.file=/etc/loki/config.yaml -verify-config

echo "==> Tempo ($(image tempo))"
# -config.verify needs an explicit value; without it Tempo prints the usage.
docker run --rm \
    -v "$config_dir/tempo.yaml:/etc/tempo/config.yaml:ro" \
    "$(image tempo)" -config.file=/etc/tempo/config.yaml -config.verify=true
echo "Tempo configuration is valid"

if [[ -n "$rendered" ]]; then
    tmp_dir="$(mktemp -d)"
    trap 'rm -rf "$tmp_dir"' EXIT

    # extract CONFIGMAP KEY OUTPUT: write data.KEY of a rendered ConfigMap.
    # -r prints the raw string with both mikefarah/yq v4 (GitHub runners) and
    # the Python yq wrapper around jq (Debian/Ubuntu package).
    extract() {
        if command -v yq >/dev/null 2>&1; then
            yq -r "select(.kind == \"ConfigMap\" and .metadata.name == \"$1\") | .data[\"$2\"]" \
                "$rendered" > "$3"
        else
            python3 -I -c '
import sys, yaml
for doc in yaml.safe_load_all(open(sys.argv[1])):
    if doc and doc.get("kind") == "ConfigMap" and doc["metadata"]["name"] == sys.argv[2]:
        sys.stdout.write(doc["data"][sys.argv[3]])
' "$rendered" "$1" "$2" > "$3"
        fi
        test -s "$3"
        chmod 0644 "$3"
    }

    echo "==> Helm Collector configuration ($rendered)"
    extract stowmark-otel-collector relay "$tmp_dir/otelcol.yaml"
    docker run --rm \
        -v "$tmp_dir/otelcol.yaml:/etc/otelcol/config.yaml:ro" \
        "$(image otel-collector)" validate --config=/etc/otelcol/config.yaml
    echo "Helm Collector configuration is valid"

    # The Tempo chart names its ConfigMap "tempo" (chart name, not fullname)
    # and mounts it on /conf.
    echo "==> Helm Tempo configuration ($rendered)"
    mkdir "$tmp_dir/tempo"
    extract tempo tempo.yaml "$tmp_dir/tempo/tempo.yaml"
    extract tempo overrides.yaml "$tmp_dir/tempo/overrides.yaml"
    chmod 0755 "$tmp_dir" "$tmp_dir/tempo"
    docker run --rm \
        -v "$tmp_dir/tempo:/conf:ro" \
        "$(image tempo)" -config.file=/conf/tempo.yaml -config.verify=true
    echo "Helm Tempo configuration is valid"
fi
