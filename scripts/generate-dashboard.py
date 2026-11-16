#!/usr/bin/env python3
"""Generate dashboards/stowmark-overview.json (and the Helm chart copy).

The dashboard is written as code so that queries, layout and conventions stay
consistent. Run it after changing this file:

    python3 scripts/generate-dashboard.py

Data sources (provisioned uids): prometheus, loki, tempo.

Design notes
- Counts, rates and durations come from Prometheus. The Collector turns the
  per-run cumulative counters of the Stowmark CLI into running totals
  (cumulative_to_delta + delta_to_cumulative), so increase() works across runs.
- Per-snapshot and per-restore details come from Tempo search results
  (span attributes via select()). Tempo search is limited to 7 days; TraceQL
  metrics (limited to 24 hours) are not used.
- Partial restores keep the span status "unset" and set
  snapshot.is_success=false; the metrics count them as successful, so restore
  health comes from Tempo.
- Stowmark records stowmark.operation.duration in seconds with the SDK's
  default bucket boundaries (0, 5, 10, ...), so histogram quantiles are not
  meaningful; durations use sum/count and span durations instead.
"""

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUTPUTS = [
    ROOT / "dashboards" / "stowmark-overview.json",
    ROOT / "charts" / "stowmark-observability" / "dashboards" / "stowmark-overview.json",
]

PROM = {"type": "prometheus", "uid": "prometheus"}
LOKI = {"type": "loki", "uid": "loki"}
TEMPO = {"type": "tempo", "uid": "tempo"}

SVC = 'service_name="$service"'
OP = 'operation_name=~"${operation:regex}"'
EXEC = "stowmark_operation_executions_total"
DUR = "stowmark_operation_duration_seconds"
TQL_SVC = 'resource.service.name = "$service"'

GREEN, RED, ORANGE, BLUE, YELLOW = "green", "red", "orange", "blue", "yellow"

_next_id = 0


def pid():
    global _next_id
    _next_id += 1
    return _next_id


def thresholds(*steps):
    """steps: (value or None, color) pairs; the first value must be None."""
    return {
        "mode": "absolute",
        "steps": [{"color": color, "value": value} for value, color in steps],
    }


def prom(expr, ref="A", legend="", instant=False, fmt=None):
    target = {
        "refId": ref,
        "datasource": PROM,
        "expr": expr,
        "legendFormat": legend or "__auto",
        "range": not instant,
        "instant": instant,
    }
    if fmt:
        target["format"] = fmt
    return target


def loki(expr, ref="A", legend="", query_type="range"):
    return {
        "refId": ref,
        "datasource": LOKI,
        "expr": expr,
        "legendFormat": legend,
        "queryType": query_type,
    }


def tempo_spans(query, ref="A", limit=100):
    return {
        "refId": ref,
        "datasource": TEMPO,
        "queryType": "traceql",
        "query": query,
        "tableType": "spans",
        "limit": limit,
        "spss": 1,
    }


def tempo_traces(query, ref="A", limit=20):
    return {
        "refId": ref,
        "datasource": TEMPO,
        "queryType": "traceql",
        "query": query,
        "tableType": "traces",
        "limit": limit,
    }


def row(title, y):
    return {
        "id": pid(),
        "type": "row",
        "title": title,
        "collapsed": False,
        "gridPos": {"h": 1, "w": 24, "x": 0, "y": y},
        "panels": [],
    }


def stat(title, description, targets, grid, unit="short", steps=None,
         calc="lastNotNull", fields="", no_value=None, transformations=None,
         decimals=None, color_mode="background", mappings=None):
    defaults = {
        "unit": unit,
        "color": {"mode": "thresholds"},
        "thresholds": thresholds(*(steps or [(None, BLUE)])),
        "mappings": mappings or [],
    }
    if no_value is not None:
        defaults["noValue"] = no_value
    if decimals is not None:
        defaults["decimals"] = decimals
    return {
        "id": pid(),
        "type": "stat",
        "title": title,
        "description": description,
        "datasource": targets[0]["datasource"],
        "gridPos": grid,
        "targets": targets,
        "transformations": transformations or [],
        "fieldConfig": {"defaults": defaults, "overrides": []},
        "options": {
            "reduceOptions": {"calcs": [calc], "fields": fields, "values": False},
            "colorMode": color_mode,
            "graphMode": "none",
            "justifyMode": "center",
            "textMode": "value",
            "orientation": "auto",
            "showPercentChange": False,
            "wideLayout": True,
        },
    }


def timeseries(title, description, targets, grid, unit="short", draw="bars",
               stack=True, interval=None, overrides=None, transformations=None,
               legend_calcs=None, palette="palette-classic", points=False,
               legend_mode="list"):
    custom = {
        "drawStyle": draw,
        "lineWidth": 1,
        "fillOpacity": 80 if draw == "bars" else 10,
        "barAlignment": 0,
        "showPoints": "always" if points else "auto",
        "pointSize": 6,
        "spanNulls": False,
        "stacking": {"mode": "normal" if stack else "none", "group": "A"},
        "axisPlacement": "auto",
        "axisSoftMin": 0,
        "gradientMode": "none",
        "lineInterpolation": "linear",
    }
    panel = {
        "id": pid(),
        "type": "timeseries",
        "title": title,
        "description": description,
        "datasource": targets[0]["datasource"],
        "gridPos": grid,
        "targets": targets,
        "transformations": transformations or [],
        "fieldConfig": {
            "defaults": {
                "unit": unit,
                "color": {"mode": palette},
                "custom": custom,
            },
            "overrides": overrides or [],
        },
        "options": {
            "legend": {
                "displayMode": legend_mode,
                "placement": "bottom",
                "showLegend": True,
                "calcs": legend_calcs or [],
            },
            "tooltip": {"mode": "multi", "sort": "desc"},
        },
    }
    if interval:
        panel["interval"] = interval
    return panel


def table(title, description, targets, grid, transformations=None,
          overrides=None, sort_by=None, unit=None):
    defaults = {"custom": {"align": "auto", "cellOptions": {"type": "auto"}, "filterable": True}}
    if unit:
        defaults["unit"] = unit
    panel = {
        "id": pid(),
        "type": "table",
        "title": title,
        "description": description,
        "datasource": targets[0]["datasource"],
        "gridPos": grid,
        "targets": targets,
        "transformations": transformations or [],
        "fieldConfig": {"defaults": defaults, "overrides": overrides or []},
        "options": {
            "showHeader": True,
            "cellHeight": "sm",
            "footer": {"show": False, "reducer": ["sum"], "fields": ""},
            "sortBy": sort_by or [],
        },
    }
    return panel


def override(name, *props, by="byName"):
    return {"matcher": {"id": by, "options": name},
            "properties": [{"id": k, "value": v} for k, v in props]}


def color_text(name, mapping):
    """Colour a text cell through value mappings: {value: (text, color)}."""
    return override(
        name,
        ("custom.cellOptions", {"type": "color-text"}),
        ("mappings", [{
            "type": "value",
            "options": {
                str(value): {"text": text, "color": color, "index": i}
                for i, (value, (text, color)) in enumerate(mapping.items())
            },
        }]),
    )


TRACE_LINK = {
    "title": "Open trace",
    "url": "",
    "internal": {
        "datasourceUid": "tempo",
        "datasourceName": "Tempo",
        "query": {"query": "${__value.raw}", "queryType": "traceql"},
    },
}

SPAN_STATUS = {"unset": ("OK", GREEN), "ok": ("OK", GREEN), "error": ("Error", RED)}

# Columns produced by Tempo spans tables that add nothing here.
# Grafana matches organize/sort/reduce options against display names.
TEMPO_HIDDEN = {"traceIdHidden": True, "Trace Service": True, "Trace Name": True, "service.name": True}


def build():
    panels = []
    y = 0

    # --------------------------------------------------------------- Status
    panels.append(row("Status", y)); y += 1
    snap_ok = f'{{ {TQL_SVC} && name = "create-snapshot" && status != error }}'
    w = 4
    panels += [
        stat(
            "Last successful snapshot",
            "Time of the last create-snapshot without errors (Tempo search, up to 7 days).",
            [tempo_spans(f"{snap_ok} | select(span.snapshot.total_size)", limit=100)],
            {"h": 4, "w": w, "x": 0, "y": y},
            unit="dateTimeFromNow", calc="max", fields="/^Start time$/",
            no_value="None in range", steps=[(None, BLUE)], color_mode="value",
        ),
        stat(
            "Successful snapshots",
            "Successful create-snapshot runs in the time range. Red when there are none.",
            [prom(f'round(sum(increase({EXEC}{{{SVC}, operation_name="create-snapshot", operation_status="success"}}[$__range])))', instant=True)],
            {"h": 4, "w": w, "x": w, "y": y},
            steps=[(None, RED), (1, GREEN)], no_value="0", decimals=0,
        ),
        stat(
            "Success rate",
            "Operations without errors over all operations (the operation filter applies).",
            [prom(
                f'sum(increase({EXEC}{{{SVC}, {OP}, operation_status="success"}}[$__range]))'
                f' / sum(increase({EXEC}{{{SVC}, {OP}}}[$__range]))', instant=True)],
            {"h": 4, "w": w, "x": 2 * w, "y": y},
            unit="percentunit", decimals=1,
            steps=[(None, RED), (0.9, ORANGE), (0.99, GREEN)],
        ),
        stat(
            "Failed operations",
            "Commands and queries that ended with an error in the time range.",
            [prom(f'round(sum(increase({EXEC}{{{SVC}, {OP}, operation_status="error"}}[$__range])))', instant=True)],
            {"h": 4, "w": w, "x": 3 * w, "y": y},
            steps=[(None, GREEN), (1, RED)], no_value="0", decimals=0,
        ),
        stat(
            "Incomplete restores",
            "restore-snapshot runs with an error or with snapshot.is_success=false (Tempo search). "
            "Partial restores do not set the span status to error.",
            [tempo_spans(
                f'{{ {TQL_SVC} && name = "restore-snapshot" && (status = error || span.snapshot.is_success = false) }}',
                limit=1000)],
            {"h": 4, "w": w, "x": 4 * w, "y": y},
            calc="count", fields="/^Span ID$/", steps=[(None, GREEN), (1, RED)], no_value="0",
        ),
        stat(
            "Last snapshot size",
            "snapshot.total_size of the last successful create-snapshot.",
            [tempo_spans(f"{snap_ok} | select(span.snapshot.total_size)", limit=100)],
            {"h": 4, "w": w, "x": 5 * w, "y": y},
            unit="bytes", calc="firstNotNull", fields="/^snapshot\\.total_size$/",
            transformations=[{"id": "sortBy", "options": {"sort": [{"field": "Start time", "desc": True}]}}],
            steps=[(None, BLUE)], color_mode="value",
        ),
    ]
    y += 4

    # ------------------------------------------------------------ Snapshots
    panels.append(row("Snapshots", y)); y += 1
    snap_all = f'{{ {TQL_SVC} && name = "create-snapshot" }}'
    panels.append(timeseries(
        "Size and files per snapshot",
        "Each point is a successful create-snapshot (Tempo search, up to 7 days).",
        [tempo_spans(f"{snap_ok} | select(span.snapshot.total_size, span.snapshot.file_count)", limit=500)],
        {"h": 8, "w": 12, "x": 0, "y": y},
        unit="bytes", draw="lines", stack=False, points=True,
        transformations=[
            {"id": "organize", "options": {"excludeByName": {
                "Span ID": True, "Name": True, "status": True, "Duration": True, **TEMPO_HIDDEN}}},
            {"id": "sortBy", "options": {"sort": [{"field": "Start time", "desc": False}]}},
        ],
        overrides=[
            override("snapshot.total_size", ("displayName", "Size"), ("unit", "bytes")),
            override("snapshot.file_count", ("displayName", "Files"), ("unit", "short"),
                     ("color", {"mode": "fixed", "fixedColor": BLUE}),
                     ("custom.axisPlacement", "right")),
        ],
        legend_calcs=["lastNotNull", "max"],
    ))
    panels.append(timeseries(
        "create-snapshot duration",
        "Duration of each create-snapshot (Tempo span); errors in red.",
        [tempo_spans(f"{snap_all} | select(status)", limit=500)],
        {"h": 8, "w": 12, "x": 12, "y": y},
        unit="ns", draw="points", stack=False, points=True,
        transformations=[
            {"id": "partitionByValues", "options": {"fields": ["status"], "keepFields": False}},
            {"id": "organize", "options": {"excludeByName": {
                "Span ID": True, "Name": True, **TEMPO_HIDDEN}}},
        ],
        overrides=[
            override("Duration error", ("color", {"mode": "fixed", "fixedColor": RED}), ("displayName", "Error")),
            override("Duration unset", ("color", {"mode": "fixed", "fixedColor": GREEN}), ("displayName", "OK")),
        ],
    ))
    y += 8
    panels.append(table(
        "Recent snapshots",
        "Latest create-snapshot runs and their attributes. Click a span to open its trace.",
        [tempo_spans(
            f"{snap_all} | select(span.snapshot.id, span.snapshot.file_count, span.snapshot.total_size, span.snapshot.skipped_files, status)",
            limit=50)],
        {"h": 8, "w": 24, "x": 0, "y": y},
        transformations=[
            {"id": "organize", "options": {
                "excludeByName": {"Name": True, **TEMPO_HIDDEN},
                "indexByName": {"Start time": 0, "snapshot.id": 1, "snapshot.file_count": 2,
                                "snapshot.total_size": 3, "snapshot.skipped_files": 4,
                                "Duration": 5, "status": 6, "Span ID": 7},
                "renameByName": {"Start time": "Start", "snapshot.id": "Snapshot",
                                 "snapshot.file_count": "Files", "snapshot.total_size": "Size",
                                 "snapshot.skipped_files": "Skipped", "Duration": "Duration",
                                 "status": "Status", "Span ID": "Span"}}},
        ],
        overrides=[
            override("Size", ("unit", "bytes")),
            override("Duration", ("unit", "ns")),
            override("Skipped", ("custom.cellOptions", {"type": "color-text"}),
                     ("thresholds", thresholds((None, GREEN), (1, ORANGE))),
                     ("color", {"mode": "thresholds"})),
            color_text("Status", SPAN_STATUS),
        ],
        sort_by=[{"displayName": "Start", "desc": True}],
    ))
    y += 8

    # ------------------------------------------------------------- Restores
    panels.append(row("Restores", y)); y += 1
    panels.append(table(
        "Recent restores",
        "restore-snapshot and restore-file runs. 'Complete' comes from snapshot.is_success: a partial "
        "restore does not set the span status to error. 'Files' is snapshot.total_files_restored.",
        [tempo_spans(
            f'{{ {TQL_SVC} && name =~ "restore-snapshot|restore-file" }}'
            " | select(span.snapshot.id, span.snapshot.total_files_restored, span.snapshot.total_files_failed, span.snapshot.is_success, status)",
            limit=50)],
        {"h": 8, "w": 24, "x": 0, "y": y},
        transformations=[
            {"id": "organize", "options": {
                "excludeByName": {**TEMPO_HIDDEN},
                "indexByName": {"Start time": 0, "Name": 1, "snapshot.id": 2,
                                "snapshot.total_files_restored": 3, "snapshot.total_files_failed": 4,
                                "snapshot.is_success": 5, "status": 6, "Duration": 7, "Span ID": 8},
                "renameByName": {"Start time": "Start", "Name": "Operation", "snapshot.id": "Snapshot",
                                 "snapshot.total_files_restored": "Files",
                                 "snapshot.total_files_failed": "Failed",
                                 "snapshot.is_success": "Complete", "status": "Status",
                                 "Duration": "Duration", "Span ID": "Span"}}},
        ],
        overrides=[
            override("Duration", ("unit", "ns")),
            override("Failed", ("custom.cellOptions", {"type": "color-text"}),
                     ("thresholds", thresholds((None, GREEN), (1, RED))),
                     ("color", {"mode": "thresholds"})),
            color_text("Complete", {"true": ("Yes", GREEN), "false": ("No", RED)}),
            color_text("Status", SPAN_STATUS),
        ],
        sort_by=[{"displayName": "Start", "desc": True}],
    ))
    y += 8

    # ----------------------------------------------------------- Operations
    panels.append(row("Operations", y)); y += 1
    panels.append(timeseries(
        "Executions by operation",
        "Command and query executions (Prometheus).",
        [prom(f'sum by (operation_name) (round(increase({EXEC}{{{SVC}, {OP}}}[$__interval]))) > 0',
              legend="{{operation_name}}")],
        {"h": 8, "w": 12, "x": 0, "y": y}, interval="5m", legend_calcs=["sum"],
        legend_mode="table",
    ))
    panels.append(timeseries(
        "Errors by operation",
        "Executions that ended with an error (Prometheus).",
        [prom(f'sum by (operation_name) (round(increase({EXEC}{{{SVC}, {OP}, operation_status="error"}}[$__interval]))) > 0',
              legend="{{operation_name}}")],
        {"h": 8, "w": 12, "x": 12, "y": y}, interval="5m", legend_calcs=["sum"],
        legend_mode="table", palette="palette-classic",
    ))
    y += 8
    by = "operation_name, operation_type"
    exec_sel = f"{EXEC}{{{SVC}, {OP}}}"
    panels.append(table(
        "Summary by operation",
        "Totals for the time range. Duration is the average (sum/count): Stowmark's histogram "
        "uses the default buckets (0, 5, 10… s), so quantiles are not meaningful.",
        [
            prom(f"round(sum by ({by}) (increase({exec_sel}[$__range])))", ref="A", instant=True, fmt="table"),
            prom(f'round(sum by ({by}) (increase({EXEC}{{{SVC}, {OP}, operation_status="error"}}[$__range])))'
                 f" or on ({by}) (0 * sum by ({by}) (increase({exec_sel}[$__range])))",
                 ref="B", instant=True, fmt="table"),
            prom(f"sum by ({by}) (increase({DUR}_sum{{{SVC}, {OP}}}[$__range]))"
                 f" / sum by ({by}) (increase({DUR}_count{{{SVC}, {OP}}}[$__range]))",
                 ref="C", instant=True, fmt="table"),
        ],
        {"h": 8, "w": 24, "x": 0, "y": y},
        transformations=[
            {"id": "merge", "options": {}},
            # Operations seen at some point but not run in this range.
            {"id": "filterByValue", "options": {
                "type": "include", "match": "any",
                "filters": [{"fieldName": "Value #A", "config": {"id": "greater", "options": {"value": 0}}}]}},
            {"id": "calculateField", "options": {
                "mode": "binary", "alias": "Error rate", "replaceFields": False,
                "binary": {"left": {"matcher": {"id": "byName", "options": "Value #B"}}, "operator": "/",
                           "right": {"matcher": {"id": "byName", "options": "Value #A"}}}}},
            {"id": "organize", "options": {
                "excludeByName": {"Time": True},
                "indexByName": {"operation_name": 0, "operation_type": 1, "Value #A": 2,
                                "Value #B": 3, "Error rate": 4, "Value #C": 5},
                "renameByName": {"operation_name": "Operation", "operation_type": "Type",
                                 "Value #A": "Executions", "Value #B": "Errors",
                                 "Value #C": "Avg duration"}}},
        ],
        overrides=[
            override("Avg duration", ("unit", "s"), ("decimals", 3)),
            override("Executions", ("decimals", 0)),
            override("Errors", ("decimals", 0), ("custom.cellOptions", {"type": "color-text"}),
                     ("thresholds", thresholds((None, GREEN), (1, RED))),
                     ("color", {"mode": "thresholds"})),
            override("Error rate", ("unit", "percentunit"), ("decimals", 1),
                     ("custom.cellOptions", {"type": "color-background", "mode": "basic"}),
                     ("thresholds", thresholds((None, GREEN), (0.01, ORANGE), (0.1, RED))),
                     ("color", {"mode": "thresholds"})),
        ],
        sort_by=[{"displayName": "Executions", "desc": True}],
    ))
    y += 8
    panels.append(timeseries(
        "Average duration by operation",
        "Sum of durations / number of executions per interval (Prometheus).",
        [prom(f"sum by (operation_name) (increase({DUR}_sum{{{SVC}, {OP}}}[$__interval]))"
              f" / sum by (operation_name) (increase({DUR}_count{{{SVC}, {OP}}}[$__interval]))",
              legend="{{operation_name}}")],
        {"h": 8, "w": 24, "x": 0, "y": y}, unit="s", draw="points", stack=False,
        interval="5m", points=True, legend_calcs=["mean", "max"], legend_mode="table",
    ))
    y += 8

    # ----------------------------------------------------------------- Logs
    panels.append(row("Logs", y)); y += 1
    level = '| detected_level=~"${level:regex}"'
    op_logs = '| command=~"${operation:regex}" or query=~"${operation:regex}"'
    level_colors = {"error": RED, "warn": YELLOW, "info": GREEN, "debug": BLUE}
    panels.append(timeseries(
        "Logs by level",
        "Log volume by detected_level (Loki).",
        [loki(f'sum by (detected_level) (count_over_time({{{SVC}}} {level} {op_logs} [$__auto]))',
              legend="{{detected_level}}")],
        {"h": 8, "w": 8, "x": 0, "y": y}, interval="5m",
        overrides=[override(lvl, ("color", {"mode": "fixed", "fixedColor": c}))
                   for lvl, c in level_colors.items()],
    ))
    panels.append(table(
        "Recent errors",
        "Error logs with the exception message. Click a trace ID to open the trace.",
        [loki(f'{{{SVC}}} | detected_level="error" {op_logs}')],
        {"h": 8, "w": 16, "x": 8, "y": y},
        transformations=[
            {"id": "extractFields", "options": {"source": "labels", "format": "json", "replace": False, "keepTime": False}},
            {"id": "organize", "options": {
                "excludeByName": {"labels": True, "id": True, "tsNs": True, "labelTypes": True,
                                  "detected_level": True, "duration_ms": True, "events": True,
                                  "flags": True, "observed_timestamp": True, "scope_name": True,
                                  "service_name": True, "severity_number": True, "severity_text": True,
                                  "span_id": True, "status": True, "telemetry_sdk_language": True,
                                  "telemetry_sdk_name": True, "telemetry_sdk_version": True,
                                  "exception_type": True, "Line": True, "line": True,
                                  "TraceID": True},
                "indexByName": {"Time": 0, "command": 1, "query": 2, "exception_message": 3, "trace_id": 4},
                "renameByName": {"Time": "Time", "command": "Command", "query": "Query",
                                 "exception_message": "Error", "trace_id": "Trace"}}},
        ],
        overrides=[override("Trace", ("links", [TRACE_LINK]))],
        sort_by=[{"displayName": "Time", "desc": True}],
    ))
    y += 8
    panels.append({
        "id": pid(),
        "type": "logs",
        "title": "Logs",
        "description": "Stowmark logs filtered by level and operation. The metadata includes trace_id.",
        "datasource": LOKI,
        "gridPos": {"h": 10, "w": 24, "x": 0, "y": y},
        "targets": [loki(f"{{{SVC}}} {level} {op_logs}")],
        "options": {
            "showTime": True, "showLabels": False, "showCommonLabels": False,
            "wrapLogMessage": True, "prettifyLogMessage": False, "enableLogDetails": True,
            "dedupStrategy": "none", "sortOrder": "Descending", "enableInfiniteScrolling": True,
        },
    })
    y += 10

    # --------------------------------------------------------------- Traces
    panels.append(row("Traces", y)); y += 1
    panels.append(table(
        "Traces with errors",
        "Traces with at least one span in error (Tempo, up to 7 days).",
        [tempo_traces(f"{{ {TQL_SVC} && status = error }}")],
        {"h": 8, "w": 12, "x": 0, "y": y},
    ))
    panels.append(table(
        "Recent traces",
        "Latest traces of the selected operations (Tempo, up to 7 days).",
        [tempo_traces(f'{{ {TQL_SVC} && name =~ "${{operation:regex}}" }}')],
        {"h": 8, "w": 12, "x": 12, "y": y},
    ))

    return {
        "uid": "stowmark-overview",
        "title": "Stowmark Overview",
        "description": "Stowmark snapshots, restores, operations, logs and traces. "
                       "Generated by scripts/generate-dashboard.py.",
        "tags": ["stowmark", "opentelemetry", "backup"],
        "timezone": "browser",
        "editable": False,
        "graphTooltip": 1,
        "time": {"from": "now-7d", "to": "now"},
        "refresh": "5m",
        "timepicker": {"refresh_intervals": ["1m", "5m", "15m", "1h"]},
        "schemaVersion": 41,
        "version": 2,
        "annotations": {"list": []},
        "links": [],
        "templating": {"list": [
            {
                "name": "service", "label": "Service", "type": "textbox",
                "query": "stowmark", "current": {"text": "stowmark", "value": "stowmark"},
                "description": "Value of service.name (OTEL_SERVICE_NAME).",
            },
            {
                "name": "operation", "label": "Operation", "type": "query",
                "datasource": PROM,
                "query": {"qryType": 1, "query": f'label_values({EXEC}{{{SVC}}}, operation_name)', "refId": "PrometheusVariableQueryEditor-VariableQuery"},
                "definition": f'label_values({EXEC}{{{SVC}}}, operation_name)',
                "refresh": 2, "sort": 1, "multi": True, "includeAll": True, "allValue": ".*",
                "current": {"text": ["All"], "value": ["$__all"]},
            },
            {
                "name": "level", "label": "Log level", "type": "custom",
                "query": "error,warn,info,debug", "multi": True, "includeAll": True, "allValue": ".*",
                "current": {"text": ["All"], "value": ["$__all"]},
                "options": [],
            },
        ]},
        "panels": panels,
    }


def main():
    text = json.dumps(build(), indent=2, ensure_ascii=False) + "\n"
    for path in OUTPUTS:
        path.write_text(text, encoding="utf-8")
        print(f"Wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
