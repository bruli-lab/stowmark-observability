# Stowmark Observability

Stowmark Observability is a self-contained monitoring stack for
[Stowmark](https://github.com/bruli-lab/stowmark). It receives OpenTelemetry
logs, metrics, and traces from the Stowmark CLI and provides a preconfigured
Grafana dashboard for inspecting snapshot creation, restore operations,
failures, performance, and recent activity.

The project is designed for a single host and can run directly with Docker
Compose or as a Debian package managed by `systemd`.

## What it provides

- An OTLP receiver for logs, metrics, and traces over HTTP or gRPC.
- A provisioned Grafana instance with Stowmark data sources and dashboards.
- Loki for log storage and search.
- Tempo for distributed traces and TraceQL metrics.
- Prometheus for application and collector metrics.
- Persistent Docker volumes for all stored telemetry.
- A Debian package that installs and registers the stack as a system service.
- Automated semantic releases with the generated `.deb` attached to each
  GitHub Release.

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

Only Grafana and the OTLP receiver are published on the host. Loki, Tempo, and
Prometheus remain inside the Compose network.

## Requirements

- Docker Engine
- Docker Compose v2 (`docker compose`)
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

1. installs the locked release dependencies;
2. validates the Docker Compose configuration;
3. calculates the semantic version;
4. builds `stowmark-observability_<version>_all.deb`;
5. creates the Git tag and GitHub Release;
6. attaches the Debian package to the release.

For a project that should begin below `1.0.0`, create and push a `v0.0.0` tag
on the bootstrap commit before merging the first `feat:` change. The first
feature release will then be `v0.1.0`.
