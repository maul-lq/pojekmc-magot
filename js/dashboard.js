import {
  apiFetch,
  dataStatus,
  formatDateTime,
  formatInteger,
  formatNumber,
  initShell,
  readingStatus,
  renderLineChart,
  setStatusBadge,
  showError,
  startPolling,
} from "./app.js";

initShell("/dashboard");

const setText = (id, value) => {
  const node = document.querySelector(id);
  if (node) node.textContent = value;
};

function renderLatest(reading) {
  setText("#temperature-value", `${formatNumber(reading?.temperature)}°C`);
  setText("#humidity-value", `${formatNumber(reading?.humidity)}%`);
  setText("#gas-value", formatInteger(reading?.gas));
  setText("#buzzer-value", reading?.buzzer || "—");
  const status = readingStatus(reading);
  document.querySelectorAll("[data-reading-status]").forEach((node) => setStatusBadge(node, status));
}

function renderSummary(data) {
  renderLatest(data.latest_reading);
  setStatusBadge(document.querySelector("#data-status"), dataStatus(data.data_status));
  const stats = data.today_statistics;
  setText("#avg-temperature", `${formatNumber(stats.temperature_avg)}°C`);
  setText("#avg-humidity", `${formatNumber(stats.humidity_avg)}%`);
  setText("#abnormal-total", formatInteger(data.abnormal_counts.temperature + data.abnormal_counts.gas + data.abnormal_counts.dht_problem));

  const notificationHost = document.querySelector("#notification-list");
  notificationHost.innerHTML = data.notifications.length
    ? data.notifications
        .map(
          (item) => `<li class="flex gap-3 rounded-xl bg-slate-50 p-3">
            <span class="mt-1 h-2.5 w-2.5 shrink-0 rounded-full ${item.severity === "danger" ? "bg-red-500" : "bg-amber-500"}"></span>
            <div><p class="text-sm font-semibold text-slate-700">${item.message}</p><p class="mt-1 text-xs text-slate-400">${formatDateTime(item.created_at)}</p></div>
          </li>`,
        )
        .join("")
    : `<li class="empty-state">Belum ada notifikasi kondisi abnormal.</li>`;

  const table = document.querySelector("#recent-table");
  table.innerHTML = data.recent_readings.length
    ? data.recent_readings
        .map((item) => {
          const status = readingStatus(item);
          return `<tr><td>${formatDateTime(item.received_at)}</td><td>${formatNumber(item.temperature)}°C</td><td>${formatNumber(item.humidity)}%</td><td>${formatInteger(item.gas)}</td><td><span class="status-badge ${status.className}">${status.label}</span></td></tr>`;
        })
        .join("")
    : `<tr><td colspan="5" class="text-center">Belum ada data.</td></tr>`;
}

async function refresh() {
  try {
    const [summary, history] = await Promise.all([
      apiFetch("/api/dashboard/summary"),
      apiFetch("/api/sensors/history?limit=40"),
    ]);
    renderSummary(summary);
    renderLineChart(document.querySelector("#dashboard-chart"), history.readings, [
      { key: "temperature", label: "Suhu", color: "#159a69" },
      { key: "humidity", label: "Kelembapan", color: "#41a8d8" },
    ]);
  } catch (error) {
    showError(document.querySelector("#dashboard-chart"), error.message);
    setStatusBadge(document.querySelector("#data-status"), { label: "Backend tidak tersedia", className: "status-danger" });
  }
}

startPolling(refresh, 2000);
