import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const dashboard = JSON.parse(
  await readFile(
    new URL("../ops/monitoring/grafana-dashboard.json", import.meta.url),
    "utf8",
  ),
);

test("monitoring dashboard has importable data source and unique panel layout", () => {
  assert.equal(dashboard.uid, "tynys-operations");
  assert.equal(dashboard.__inputs[0].name, "DS_PROMETHEUS");
  assert.equal(dashboard.__inputs[0].pluginId, "prometheus");
  assert.equal(
    new Set(dashboard.panels.map(({ id }) => id)).size,
    dashboard.panels.length,
  );
  assert.ok(
    dashboard.panels.every(({ gridPos }) => gridPos.x + gridPos.w <= 24),
  );
  const job = dashboard.templating.list.find(({ name }) => name === "job");
  assert.equal(job.current.value, "tynys-api");
  for (const panel of dashboard.panels.filter(({ type }) => type !== "text")) {
    assert.equal(panel.datasource.uid, "${DS_PROMETHEUS}");
    assert.equal(panel.fieldConfig.defaults.noValue, "No data");
    assert.ok(panel.targets.every(({ expr }) => expr.includes('job="$job"')));
    assert.equal(panel.transformations, undefined);
    if (panel.type === "timeseries")
      assert.equal(panel.fieldConfig.defaults.custom.spanNulls, false);
  }
});

test("operational panels keep missing telemetry distinct from empty queues and require scheduler heartbeat", () => {
  const expressions = dashboard.panels.flatMap(({ targets = [] }) =>
    targets.map(({ expr }) => expr),
  );
  assert.ok(
    expressions.some((expr) => expr.includes('worker="payment_scheduler"')),
  );
  assert.ok(
    expressions.some((expr) =>
      expr.includes("tynys_metrics_snapshot_timestamp_seconds"),
    ),
  );
  assert.ok(
    expressions.some((expr) => expr.includes("tynys_database_max_connections")),
  );
  assert.ok(
    expressions.every(
      (expr) =>
        !/\brate\(|histogram_quantile\(|or\s+(on\([^)]*\)\s+)?vector\(0\)/.test(
          expr,
        ),
    ),
  );
  const text = JSON.stringify(dashboard);
  assert.equal(
    /xapi_|xdev_|Authorization|Bearer\s+[a-zA-Z0-9_-]{20}/.test(text),
    false,
  );
});
