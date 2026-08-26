# Stowmark Observability

Stowmark Observability is a self-contained monitoring stack for
[Stowmark](https://github.com/bruli-lab/stowmark). It receives OpenTelemetry
logs, metrics, and traces from the Stowmark CLI and provides a preconfigured
Grafana dashboard for inspecting snapshot creation, restore operations,
failures, performance, and recent activity.

The project can run on a single host with Docker Compose, as a Debian package
managed by `systemd`, or in Kubernetes using the included Helm chart.

## What it provides

- An OTLP receiver for logs, metrics, and traces over HTTP or gRPC.
- A provisioned Grafana instance with Stowmark data sources and dashboards.
- Loki for log storage and search.
- Tempo for distributed traces and TraceQL metrics.
- Prometheus for application and collector metrics.
- Persistent Docker volumes for all stored telemetry.
- A Debian package that installs and registers the stack as a system service.
- A Helm chart for Kubernetes deployments and disposable cluster tests.
- Automated semantic releases with the generated `.deb` and Helm `.tgz`
  attached to each GitHub Release.

The Stowmark dashboard currently includes:

- snapshot creation executions;
- application errors;
- p95 operation duration;
- command duration by execution;
- snapshot file count and size;
- restored and failed file counts;
- recent logs and traces;
- a highlighted count of failed restore files.

## Architecture

```text
                     ┌──────────────┐
                     │   Stowmark   │
                     └──────┬───────┘
                            │ OTLP
                     HTTP :4318 / gRPC :4317
                            │
                ┌───────────▼────────────┐
                │ OpenTelemetry Collector│
                └──────┬──────┬──────┬──┘
                       │      │      │
                    logs   metrics  traces
                       │      │      │
                  ┌────▼─┐ ┌──▼───┐ ┌▼──────┐
                  │ Loki │ │Prometheus│ Tempo │
                  └────┬─┘ └──┬───┘ └┬──────┘
                       │      │      │
                       └──────┼──────┘
                              │
                        ┌─────▼──────┐
                        │  Grafana   │ :3000
                        └────────────┘
```

With Docker Compose, only Grafana and the OTLP receiver are published on the
host. Loki, Tempo, and Prometheus remain inside the Compose network. The Helm
chart exposes the same components as internal Kubernetes services by default.

## Requirements

- Docker Engine
- Docker Compose v2 (`docker compose`)
- Kubernetes and Helm 3 (for Helm deployments)
- `kubectl` configured for the target cluster (for Helm deployments)
- [Task](https://taskfile.dev/) (optional, for convenience commands)

Building a Debian package additionally requires `dpkg-deb`.

## Run with Docker Compose

Create the local environment and start the stack:

```bash
cp .env.example .env
docker compose up -d
```

The equivalent Task command creates `.env` automatically when necessary:

```bash
task up
```

Open Grafana at <http://localhost:3000>. The initial credentials are configured
in `.env`. Change `GRAFANA_ADMIN_PASSWORD` before exposing Grafana outside the
local machine.

Configure Stowmark to export telemetry using OTLP/HTTP:

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
export OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
export OTEL_SERVICE_NAME=stowmark
```

For OTLP/gRPC, use:

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
export OTEL_EXPORTER_OTLP_PROTOCOL=grpc
export OTEL_SERVICE_NAME=stowmark
```

## Configuration

The runtime settings are read from `.env` when using Docker Compose and from
`/etc/default/stowmark-observability` when installed as a Debian package.

| Variable | Default | Description |
| --- | --- | --- |
| `BIND_ADDRESS` | `127.0.0.1` | Address used for published host ports. |
| `GRAFANA_PORT` | `3000` | Grafana HTTP port. |
| `GRAFANA_ADMIN_USER` | `admin` | Initial Grafana administrator. |
| `GRAFANA_ADMIN_PASSWORD` | `change-me` | Initial Grafana password. |
| `GRAFANA_ANONYMOUS_ENABLED` | `false` | Enables anonymous Grafana access. |
| `OTLP_GRPC_PORT` | `4317` | OTLP/gRPC receiver port. |
| `OTLP_HTTP_PORT` | `4318` | OTLP/HTTP receiver port. |
| `PROMETHEUS_RETENTION` | `15d` | Prometheus data retention period. |

Set `BIND_ADDRESS=0.0.0.0` only when remote access is required. Protect Grafana
and the OTLP endpoints with a firewall, VPN, or authenticated reverse proxy.

## Endpoints

| Service | Default address | Published |
| --- | --- | --- |
| Grafana | `http://localhost:3000` | Yes |
| OTLP/gRPC | `localhost:4317` | Yes |
| OTLP/HTTP | `http://localhost:4318` | Yes |
| Loki | `http://loki:3100` | Compose network only |
| Tempo | `http://tempo:3200` | Compose network only |
| Prometheus | `http://prometheus:9090` | Compose network only |

## Operations

```bash
task validate  # Validate the resolved Compose configuration
task status    # Show container status
task logs      # Follow logs from all services
task down      # Stop the stack and preserve data
task clean     # Stop the stack and permanently remove telemetry volumes
```

Docker volumes persist Grafana, Loki, Tempo, and Prometheus data. Loki retains
seven days and Prometheus retains fifteen days by default. Tempo runs in
monolithic mode with local persistent storage.

## Helm chart

The chart in `charts/stowmark-observability` deploys Grafana, Loki, Tempo,
Prometheus, and the OpenTelemetry Collector. It provisions the Stowmark
dashboard and Grafana data sources automatically.

### Install from the repository

Restore the dependency versions recorded in `Chart.lock`:

```bash
helm dependency build charts/stowmark-observability
```

Validate and inspect the rendered manifests before installing:

```bash
helm lint charts/stowmark-observability

helm template stowmark \
  charts/stowmark-observability \
  --namespace stowmark \
  > /tmp/stowmark.yaml
```

Install the stack:

```bash
helm upgrade --install stowmark \
  charts/stowmark-observability \
  --namespace stowmark \
  --create-namespace \
  --wait \
  --timeout 15m
```

### Install a packaged release

Download `stowmark-observability-<version>.tgz` from the corresponding GitHub
Release and install it directly:

```bash
helm upgrade --install stowmark \
  ./stowmark-observability-0.1.0.tgz \
  --namespace stowmark \
  --create-namespace \
  --wait \
  --timeout 15m
```

The packaged chart already contains its dependencies, so it does not require
`helm dependency build`.

### Persistence and cluster configuration

Persistence is enabled by default without selecting a storage class. Kubernetes
therefore uses the default `StorageClass` of the target cluster. Cluster-specific
settings should be kept in a separate file rather than added to `values.yaml`:

```yaml
# values-production.yaml
grafana:
  persistence:
    storageClassName: longhorn

loki:
  singleBinary:
    persistence:
      storageClass: longhorn

tempo:
  persistence:
    storageClassName: longhorn

prometheus:
  server:
    persistentVolume:
      storageClass: longhorn
```

Apply the additional configuration with:

```bash
helm upgrade --install stowmark \
  charts/stowmark-observability \
  --namespace stowmark \
  --create-namespace \
  --values values-production.yaml
```

### Temporary test installation

`values-test.yaml` disables persistent volumes so the complete installation can
be removed without retaining telemetry data:

```bash
task helm:verify
task helm:dry-run
task helm:install
task helm:status
```

The equivalent installation command is:

```bash
helm upgrade --install stowmark-test \
  charts/stowmark-observability \
  --namespace stowmark-test \
  --create-namespace \
  --values charts/stowmark-observability/values-test.yaml \
  --wait \
  --timeout 15m
```

### Access Grafana and OTLP

Forward Grafana to <http://localhost:3000>:

```bash
task helm:grafana
```

Or use `kubectl` directly:

```bash
kubectl port-forward \
  --namespace stowmark-test \
  service/stowmark-grafana \
  3000:80
```

Retrieve the generated Grafana administrator password:

```bash
kubectl get secret stowmark-grafana \
  --namespace stowmark-test \
  --output jsonpath='{.data.admin-password}' \
  | base64 --decode

echo
```

Forward both OTLP receiver ports:

```bash
task helm:otlp
```

Configure a Stowmark process running outside the cluster:

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
export OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
export OTEL_SERVICE_NAME=stowmark
```

A Stowmark workload in the same Kubernetes namespace can use the internal
Collector service directly:

```bash
export OTEL_EXPORTER_OTLP_ENDPOINT=http://stowmark-otel-collector:4318
export OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
export OTEL_SERVICE_NAME=stowmark
```

### Diagnose the deployment

```bash
helm status stowmark-test --namespace stowmark-test
kubectl get pods,services,pvc --namespace stowmark-test
task helm:collector-logs
```

To inspect a failing workload:

```bash
kubectl describe pod <pod-name> --namespace stowmark-test
kubectl logs <pod-name> --namespace stowmark-test --all-containers
```

### Package the chart locally

```bash
task helm:package VERSION=0.1.0
```

The version is injected into both `version` and `appVersion` inside the
generated `dist/stowmark-observability-0.1.0.tgz`.

### Uninstall

Remove a normal release:

```bash
helm uninstall stowmark --namespace stowmark
```

Depending on the storage provisioner and subchart retention policies, PVCs may
remain after uninstalling. Inspect them before deleting any stored telemetry:

```bash
kubectl get pvc --namespace stowmark
```

Remove the disposable test release and its namespace:

```bash
task helm:uninstall
```

## Debian package

Build a package locally with an explicit semantic version:

```bash
task package VERSION=0.1.0
```

The package is written to `dist/` and can be installed with:

```bash
sudo apt install ./dist/stowmark-observability_0.1.0_all.deb
sudo systemctl start stowmark-observability
```

The package installs:

| Path | Purpose |
| --- | --- |
| `/opt/stowmark-observability` | Compose file, service configuration, and dashboards. |
| `/etc/default/stowmark-observability` | Editable runtime environment. |
| `/etc/systemd/system/stowmark-observability.service` | System service definition. |

The service is enabled during installation but is not started automatically,
so `apt` does not unexpectedly download container images. The first start can
take several minutes while Docker downloads them. A successful start leaves the
oneshot unit in the expected `active (exited)` state while the containers
continue running.

### Service management

```bash
sudo systemctl start stowmark-observability
sudo systemctl stop stowmark-observability
sudo systemctl restart stowmark-observability
sudo systemctl reload stowmark-observability
systemctl status stowmark-observability
journalctl -u stowmark-observability
```

Inspect the managed containers with:

```bash
sudo docker compose \
  --env-file /etc/default/stowmark-observability \
  -f /opt/stowmark-observability/compose.yaml \
  ps
```

### Uninstall

Remove the package while preserving Docker volumes and telemetry data:

```bash
sudo apt purge stowmark-observability
```

To remove all telemetry permanently, delete the volumes before purging the
package:

```bash
sudo docker compose \
  --env-file /etc/default/stowmark-observability \
  -f /opt/stowmark-observability/compose.yaml \
  down --volumes

sudo apt purge stowmark-observability
```

## Automated releases

Pushes to `main` run semantic-release. Conventional Commits determine the next
version:

| Commit type | Version change |
| --- | --- |
| `fix:` | Patch |
| `feat:` | Minor |
| `BREAKING CHANGE:` | Major |

When a release is required, the GitHub Actions workflow:

1. validates JSON files, scripts, Docker Compose, and the Helm chart;
2. installs the locked release dependencies;
3. calculates the semantic version;
4. builds `stowmark-observability_<version>_all.deb`;
5. builds `stowmark-observability-<version>.tgz`;
6. creates the Git tag and GitHub Release;
7. attaches both packages to the release.

For a project that should begin below `1.0.0`, create and push a `v0.0.0` tag
on the bootstrap commit before merging the first `feat:` change. The first
feature release will then be `v0.1.0`.
