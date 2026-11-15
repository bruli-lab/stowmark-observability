#!/usr/bin/env bash
# Add the Helm repositories that host the chart's dependencies (see
# charts/stowmark-observability/Chart.yaml). Safe to run repeatedly.
set -euo pipefail

helm repo add --force-update grafana-community https://grafana-community.github.io/helm-charts
helm repo add --force-update prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add --force-update open-telemetry https://open-telemetry.github.io/opentelemetry-helm-charts
helm repo update grafana-community prometheus-community open-telemetry
