<script setup>
import { useI18n } from "vue-i18n";
import {
  computed,
  onMounted,
  onBeforeUnmount,
  reactive,
  ref,
  useId,
  watch,
} from "vue";
import { useRouter } from "vue-router";
import { StaffShell } from "@/widgets/staff-shell";
import { useSessionStore } from "@/entities/session";
import { useResortStore } from "@/entities/resort";
import { useBookingStore } from "@/entities/booking";
import { request } from "@/shared/api";
import { money, dateLabel } from "@/shared/lib";
import { isDemo } from "@/shared/config";
import { localeTag } from "@/shared/i18n";
import {
  metricOptions as metricDefinitions,
  comparison as compareValues,
  csvCell,
  reportDateAfter,
} from "../model/format.js";
import "./analytics.css";
const { t } = useI18n();
const session = useSessionStore(),
  router = useRouter(),
  catalog = useResortStore(),
  bookings = useBookingStore();
const filters = reactive({
  start: reportDateAfter(-27),
  end: reportDateAfter(),
  resortId: "",
  granularity: "day",
});
const preset = ref("28"),
  metricKey = ref("bookingCount"),
  grouping = ref(session.isAdmin ? "byResort" : "byRoom"),
  search = ref(""),
  chartType = ref("line"),
  showChart = ref(true),
  compare = ref(true),
  data = ref(null),
  loading = ref(false),
  error = ref(""),
  sortKey = ref("bookingCount"),
  descending = ref(true);
const chartTitle = useId();
const metricOptions = computed(() =>
  metricDefinitions.map((item) => ({
    ...item,
    label: t(`staff.${item.labelKey}`),
    description: t(`staff.${item.descriptionKey}`),
  })),
);
const comparison = (current, previous) =>
  compareValues(current, previous, {
    locale: localeTag(),
    unchanged: t("staff.noChange"),
    noBaseline: t("staff.noComparison"),
  });
const metric = computed(() =>
  metricOptions.value.find((m) => m.key === metricKey.value),
);
const format = (value, key = metricKey.value) =>
  ["grossReceived", "refunds", "netReceived", "bookedAmount"].includes(key)
    ? money(value)
    : key === "averageRating"
      ? value == null
        ? "—"
        : new Intl.NumberFormat(localeTag(), {
            minimumFractionDigits: 1,
            maximumFractionDigits: 1,
          }).format(value)
      : new Intl.NumberFormat(localeTag()).format(value || 0);
const activePeriod = computed(() => data.value?.period);
const periodText = computed(() =>
  activePeriod.value
    ? `${dateLabel(activePeriod.value.start)} — ${dateLabel(activePeriod.value.end)}`
    : "",
);
const scopeName = computed(
  () =>
    data.value?.resorts?.find((r) => r.id === activeScope.value)?.name ||
    (session.isAdmin && !activeScope.value
      ? t("staff.allResorts")
      : t("staff.assignedResort")),
);
const activeScope = ref("");
const points = computed(() =>
  (data.value?.series || []).map((item) => ({
    ...item,
    value: Number(item[metricKey.value]) || 0,
  })),
);
const extrema = computed(() => {
  const values = points.value.map((p) => p.value);
  const min = Math.min(0, ...values),
    max = Math.max(0, ...values);
  return {
    min,
    max:
      metric.value.unit === "count"
        ? Math.max(4, Math.ceil(max / 4) * 4)
        : max === min
          ? min + 1
          : max,
  };
});
const plot = {
  left: 74,
  right: 924,
  top: 28,
  bottom: 268,
  width: 960,
  height: 310,
};
const x = (index) =>
  points.value.length <= 1
    ? (plot.left + plot.right) / 2
    : plot.left +
      (index / (points.value.length - 1)) * (plot.right - plot.left);
const y = (value) =>
  plot.bottom -
  ((value - extrema.value.min) / (extrema.value.max - extrema.value.min)) *
    (plot.bottom - plot.top);
const linePath = computed(() =>
  points.value
    .map((p, i) => `${i ? "L" : "M"} ${x(i)} ${y(p.value)}`)
    .join(" "),
);
const ticks = computed(() =>
  Array.from(
    { length: 5 },
    (_, i) =>
      extrema.value.min + ((extrema.value.max - extrema.value.min) * i) / 4,
  ),
);
const dateTicks = computed(() => {
  const indexes = new Set([
    0,
    Math.floor((points.value.length - 1) / 3),
    Math.floor(((points.value.length - 1) * 2) / 3),
    points.value.length - 1,
  ]);
  return [...indexes]
    .filter((i) => i >= 0)
    .map((i) => ({ index: i, date: points.value[i]?.date }));
});
const axisNumber = (value) =>
  new Intl.NumberFormat(localeTag(), {
    notation: Math.abs(value) >= 10000 ? "compact" : "standard",
    maximumFractionDigits: 1,
  }).format(value);
const shortDate = (value) => {
  if (!value) return "";
  if (localeTag() === "kk-KZ") {
    const [, month, day] = value.split("-");
    return `${day}.${month}`;
  }
  return new Intl.DateTimeFormat(localeTag(), {
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  }).format(new Date(value));
};
const rowLabel = (row) =>
  grouping.value === "series"
    ? dateLabel(row.date)
    : grouping.value === "byRoom"
      ? `№ ${row.number} · ${row.name}`
      : row.name;
const rows = computed(() =>
  [...(data.value?.[grouping.value] || [])]
    .filter((row) =>
      rowLabel(row)
        ?.toLocaleLowerCase()
        .includes(search.value.toLocaleLowerCase()),
    )
    .sort(
      (a, b) =>
        (descending.value ? -1 : 1) *
        ((Number(a[sortKey.value]) || 0) - (Number(b[sortKey.value]) || 0)),
    ),
);
const hasActivity = computed(() => points.value.some((p) => p.value !== 0));
const tableMetrics = computed(() => [
  ...metricOptions.value,
  { key: "bookedAmount", label: t("staff.bookedAmount") },
  { key: "averageRating", label: t("staff.averageRating") },
]);
let generation = 0;
async function load() {
  error.value = "";
  if (
    !/^\d{4}-\d{2}-\d{2}$/.test(filters.start) ||
    !/^\d{4}-\d{2}-\d{2}$/.test(filters.end) ||
    filters.end < filters.start ||
    (Date.parse(filters.end) - Date.parse(filters.start)) / 86400000 >= 366
  ) {
    error.value = t("staff.invalidPeriod");
    return;
  }
  const run = ++generation;
  loading.value = true;
  const params = new URLSearchParams({
    start: filters.start,
    end: filters.end,
    granularity: filters.granularity,
  });
  const scope = session.isAdmin ? filters.resortId : session.user?.resortId;
  if (scope) params.set("resortId", scope);
  try {
    const result = await request("GET", "/analytics?" + params);
    if (run !== generation) return;
    data.value = result;
    activeScope.value = scope || "";
  } catch (e) {
    if (run === generation) error.value = e.message;
  } finally {
    if (run === generation) loading.value = false;
  }
}
function setPreset() {
  if (preset.value !== "custom") {
    filters.end = reportDateAfter();
    filters.start = reportDateAfter(1 - Number(preset.value));
  }
}
function setSort(key) {
  if (sortKey.value === key) descending.value = !descending.value;
  else {
    sortKey.value = key;
    descending.value = true;
  }
}
async function logout() {
  try {
    await session.logout();
    catalog.clear();
    bookings.items = [];
    router.push("/staff/login");
  } catch (e) {
    error.value = e.message;
  }
}
function download() {
  const header = [
    grouping.value === "series"
      ? t("staff.period")
      : grouping.value === "byRoom"
        ? t("staff.room")
        : t("staff.resort"),
    ...tableMetrics.value.map((m) => m.label),
    t("staff.paymentMode"),
  ];
  const lines = [
    header.map(csvCell).join(";"),
    ...rows.value.map((row) =>
      [
        rowLabel(row),
        ...tableMetrics.value.map((m) => row[m.key] ?? ""),
        t("staff.demo"),
      ]
        .map(csvCell)
        .join(";"),
    ),
  ];
  const url = URL.createObjectURL(
    new Blob(["\uFEFF" + lines.join("\r\n")], {
      type: "text/csv;charset=utf-8",
    }),
  );
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `tynys-analytics-${activePeriod.value.start}-${activePeriod.value.end}.csv`;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
watch(metricKey, (key) => {
  sortKey.value = key;
  descending.value = true;
});
onMounted(load);
onBeforeUnmount(() => {
  generation++;
});
</script>
<template>
  <StaffShell section="analytics" @logout="logout"
    ><main class="work-main analytics-main">
      <div v-if="isDemo" class="demo-strip">
        <span class="demo-dot"></span>{{ t("staff.demoBrowserData") }}
      </div>
      <div class="work-title">
        <div>
          <span class="eyebrow">{{ t("staff.analyticsEyebrow") }}</span>
          <h1>{{ t("staff.analytics") }}</h1>
          <p>{{ t("staff.analyticsSubtitle") }}</p>
        </div>
        <button
          class="secondary"
          :disabled="loading || !data || !rows.length"
          @click="download"
        >
          {{ t("staff.downloadCsv") }}
        </button>
      </div>
      <div class="analytics-layout">
        <aside class="analytics-filters">
          <form @submit.prevent="load">
            <h2>{{ t("staff.reportSettings") }}</h2>
            <label
              >{{ t("staff.resort")
              }}<select v-model="filters.resortId" :disabled="!session.isAdmin">
                <option v-if="session.isAdmin" value="">
                  {{ t("staff.allResorts") }}
                </option>
                <option v-else value="">
                  {{ data?.resorts?.[0]?.name || t("staff.assignedResort") }}
                </option>
                <option
                  v-if="session.isAdmin"
                  v-for="resort in data?.resorts || []"
                  :key="resort.id"
                  :value="resort.id"
                >
                  {{ resort.name }}
                </option>
              </select></label
            ><label
              >{{ t("staff.period")
              }}<select v-model="preset" @change="setPreset">
                <option value="7">{{ t("staff.last7Days") }}</option>
                <option value="28">{{ t("staff.last28Days") }}</option>
                <option value="90">{{ t("staff.last90Days") }}</option>
                <option value="custom">{{ t("staff.customPeriod") }}</option>
              </select></label
            >
            <div class="analytics-date-pair">
              <label
                >{{ t("staff.from")
                }}<input
                  v-model="filters.start"
                  type="date"
                  required
                  @change="preset = 'custom'" /></label
              ><label
                >{{ t("staff.to")
                }}<input
                  v-model="filters.end"
                  type="date"
                  :min="filters.start"
                  required
                  @change="preset = 'custom'"
              /></label>
            </div>
            <button class="primary" :disabled="loading">
              {{ loading ? t("staff.loading") : t("staff.apply") }}</button
            ><label class="analytics-check"
              ><input v-model="compare" type="checkbox" />{{
                t("staff.comparePrevious")
              }}</label
            >
            <div class="analytics-filter-divider"></div>
            <label
              >{{ t("staff.metric")
              }}<select v-model="metricKey">
                <option
                  v-for="option in metricOptions"
                  :key="option.key"
                  :value="option.key"
                >
                  {{ option.label }}
                </option>
              </select></label
            ><label
              >{{ t("staff.tableBreakdown")
              }}<select v-model="grouping">
                <option value="byResort">{{ t("staff.byResort") }}</option>
                <option value="byRoom">{{ t("staff.byRoom") }}</option>
                <option value="series">{{ t("staff.byTime") }}</option>
              </select></label
            ><label
              >{{ t("staff.searchTable")
              }}<input
                v-model="search"
                type="search"
                :placeholder="t('staff.searchNameRoom')"
            /></label>
          </form>
          <p class="analytics-filter-note">
            {{
              t("staff.eventTimeNote", {
                zone: data?.period.timeZone || "Asia/Almaty",
              })
            }}
          </p>
        </aside>
        <section
          class="analytics-report"
          :aria-label="t('staff.analyticsReport')"
          :aria-busy="loading"
        >
          <div v-if="error" class="analytics-feedback error" role="alert">
            <h2>{{ t("staff.reportFailed") }}</h2>
            <p>{{ error }}</p>
            <button class="secondary" :disabled="loading" @click="load">
              {{ t("staff.retry") }}
            </button>
          </div>
          <div v-if="loading" class="analytics-loading" role="status">
            {{ t("staff.gatheringReport") }}
          </div>
          <template v-if="data"
            ><header class="analytics-report-heading">
              <div>
                <span class="eyebrow">{{ scopeName }}</span>
                <h2>{{ metric.label }}</h2>
                <p>{{ periodText }}</p>
              </div>
              <label class="analytics-check"
                ><input v-model="showChart" type="checkbox" />{{
                  t("staff.showChart")
                }}</label
              >
            </header>
            <p class="analytics-payment-note">
              {{ t("staff.analyticsDemoNote") }}
            </p>
            <p v-if="data.refundDataIncomplete" class="analytics-payment-note">
              {{ t("staff.legacyRefundNote") }}
            </p>
            <div class="analytics-kpis">
              <button
                v-for="m in metricOptions"
                :key="m.key"
                :class="['analytics-kpi', { selected: metricKey === m.key }]"
                :aria-pressed="metricKey === m.key"
                @click="metricKey = m.key"
              >
                <span>{{ m.label }}</span
                ><strong>{{ format(data.totals[m.key], m.key) }}</strong
                ><small v-if="compare"
                  >{{
                    comparison(
                      data.totals[m.key] || 0,
                      data.previousTotals[m.key] || 0,
                    )
                  }}<span class="analytics-previous"
                    >{{ t("staff.previous") }}
                    {{ format(data.previousTotals[m.key], m.key) }}</span
                  ></small
                >
              </button>
            </div>
            <p v-if="compare" class="analytics-compare-period">
              {{ t("staff.comparison") }}
              {{ dateLabel(data.previousPeriod.start) }} —
              {{ dateLabel(data.previousPeriod.end) }}
            </p>
            <section
              v-if="showChart"
              class="analytics-chart-section"
              :aria-label="t('staff.metricTrend')"
            >
              <div class="analytics-chart-toolbar">
                <p>{{ metric.description }}</p>
                <label
                  ><span class="sr-only">{{ t("staff.chartType") }}</span
                  ><select v-model="chartType">
                    <option value="line">{{ t("staff.lineChart") }}</option>
                    <option value="bar">{{ t("staff.bars") }}</option>
                  </select></label
                ><label
                  ><span class="sr-only">{{ t("staff.timeGrouping") }}</span
                  ><select
                    v-model="filters.granularity"
                    :disabled="loading"
                    @change="load"
                  >
                    <option value="day">{{ t("staff.byDay") }}</option>
                    <option value="week">{{ t("staff.byWeek") }}</option>
                    <option value="month">{{ t("staff.byMonth") }}</option>
                  </select></label
                >
              </div>
              <div
                class="analytics-chart-scroll"
                role="region"
                tabindex="0"
                :aria-label="t('staff.chartRegion')"
              >
                <svg
                  class="analytics-chart"
                  :viewBox="`0 0 ${plot.width} ${plot.height}`"
                  role="img"
                  :aria-labelledby="chartTitle"
                >
                  <title :id="chartTitle">
                    {{
                      t("staff.chartSummary", {
                        metric: metric.label,
                        period: periodText,
                      })
                    }}
                    {{
                      hasActivity
                        ? t("staff.chartValuesHint")
                        : t("staff.noMetricEvents")
                    }}
                  </title>
                  <g v-for="tick in ticks" :key="tick">
                    <line
                      :x1="plot.left"
                      :x2="plot.right"
                      :y1="y(tick)"
                      :y2="y(tick)"
                      stroke="#e3e8e0"
                    />
                    <text
                      :x="plot.left - 12"
                      :y="y(tick) + 4"
                      text-anchor="end"
                    >
                      {{ axisNumber(tick) }}
                    </text>
                  </g>
                  <path
                    v-if="chartType === 'line' && points.length > 1"
                    :d="linePath"
                    fill="none"
                    stroke="#245c4a"
                    stroke-width="2.5"
                    stroke-linejoin="round"
                  />
                  <g v-for="(point, index) in points" :key="point.date">
                    <circle
                      v-if="
                        chartType === 'line' &&
                        (points.length <= 45 || point.value !== 0)
                      "
                      :cx="x(index)"
                      :cy="y(point.value)"
                      r="3.5"
                      fill="#245c4a"
                    >
                      <title>
                        {{ dateLabel(point.date) }}: {{ format(point.value) }}
                      </title>
                    </circle>
                    <rect
                      v-if="chartType === 'bar'"
                      :x="
                        x(index) -
                        Math.max(1, Math.min(20, 650 / points.length)) / 2
                      "
                      :y="Math.min(y(0), y(point.value))"
                      :width="Math.max(1, Math.min(20, 650 / points.length))"
                      :height="Math.max(0.8, Math.abs(y(0) - y(point.value)))"
                      fill="#4a7960"
                    >
                      <title>
                        {{ dateLabel(point.date) }}: {{ format(point.value) }}
                      </title>
                    </rect>
                  </g>
                  <text
                    v-for="tick in dateTicks"
                    :key="tick.index"
                    :x="x(tick.index)"
                    :y="plot.bottom + 27"
                    :text-anchor="
                      tick.index === 0
                        ? 'start'
                        : tick.index === points.length - 1
                          ? 'end'
                          : 'middle'
                    "
                  >
                    {{ shortDate(tick.date) }}
                  </text>
                </svg>
              </div>
              <p
                v-if="!hasActivity"
                class="analytics-empty-chart"
                role="status"
              >
                {{ t("staff.emptyChart", { metric: metric.label }) }}
              </p>
            </section>
            <section
              class="analytics-table-section"
              :aria-label="t('staff.reportData')"
            >
              <div class="analytics-table-heading">
                <h2>
                  {{
                    {
                      byResort: t("staff.byResort"),
                      byRoom: t("staff.byRoom"),
                      series: t("staff.byTime"),
                    }[grouping]
                  }}
                </h2>
                <span>{{ t("staff.rows") }} {{ rows.length }}</span>
              </div>
              <p
                v-if="data.truncated?.[grouping]"
                class="analytics-payment-note"
              >
                {{ t("staff.truncatedReport") }}
              </p>
              <div
                class="analytics-table-scroll"
                role="region"
                tabindex="0"
                :aria-label="t('staff.analyticsTable')"
              >
                <table class="analytics-table">
                  <thead>
                    <tr>
                      <th scope="col">
                        {{
                          grouping === "series"
                            ? t("staff.period")
                            : grouping === "byRoom"
                              ? t("staff.room")
                              : t("staff.resort")
                        }}
                      </th>
                      <th
                        v-for="m in tableMetrics"
                        :key="m.key"
                        scope="col"
                        :aria-sort="
                          sortKey === m.key
                            ? descending
                              ? 'descending'
                              : 'ascending'
                            : undefined
                        "
                      >
                        <button @click="setSort(m.key)">
                          {{ m.label
                          }}<span v-if="sortKey === m.key" aria-hidden="true">
                            {{ descending ? "↓" : "↑" }}</span
                          >
                        </button>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr class="analytics-total">
                      <th scope="row">{{ t("staff.periodTotal") }}</th>
                      <td v-for="m in tableMetrics" :key="m.key">
                        {{ format(data.totals[m.key], m.key) }}
                      </td>
                    </tr>
                    <tr
                      v-for="(row, index) in rows"
                      :key="row.roomId || row.resortId || row.date || index"
                    >
                      <th scope="row">{{ rowLabel(row) }}</th>
                      <td v-for="m in tableMetrics" :key="m.key">
                        {{ format(row[m.key], m.key) }}
                      </td>
                    </tr>
                    <tr v-if="!rows.length">
                      <td
                        :colspan="tableMetrics.length + 1"
                        class="analytics-empty-table"
                      >
                        {{ t("staff.noReportRows") }}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <p class="analytics-footnote">
                {{ t("staff.analyticsFootnote") }}
              </p>
            </section>
          </template>
          <div v-else-if="!loading && !error" class="analytics-feedback">
            <h2>{{ t("staff.reportNotBuilt") }}</h2>
            <p>{{ t("staff.reportStartHint") }}</p>
          </div>
        </section>
      </div>
    </main></StaffShell
  >
</template>
