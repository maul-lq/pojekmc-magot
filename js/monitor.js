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

initShell("/monitor");

function renderTable(readings) {
  document.querySelector("#monitor-table").innerHTML = readings.length
    ? readings
        .slice(0, 25)
        .map((item) => {
          const status = readingStatus(item);
          return `<tr><td>${formatDateTime(item.received_at)}</td><td>${formatNumber(item.temperature)}°C</td><td>${formatNumber(item.humidity)}%</td><td>${formatInteger(item.gas)}</td><td>${item.buzzer}</td><td><span class="status-badge ${status.className}">${status.label}</span></td></tr>`;
        })
        .join("")
    : `<tr><td colspan="6" class="text-center">Belum ada data sensor.</td></tr>`;
}

async function refresh() {
  try {
    const [latest, history] = await Promise.all([
      apiFetch("/api/sensors/latest"),
      apiFetch("/api/sensors/history?limit=120"),
    ]);
    setStatusBadge(document.querySelector("#monitor-status"), dataStatus(latest.data_status));
    const reading = latest.latest_reading;
    document.querySelector("#last-update").textContent = formatDateTime(reading?.received_at);
    document.querySelector("#monitor-buzzer").textContent = reading?.buzzer || "—";
    setStatusBadge(document.querySelector("#monitor-condition"), readingStatus(reading));
    renderLineChart(document.querySelector("#temperature-chart"), history.readings, [
      { key: "temperature", label: "Suhu °C", color: "#159a69" },
    ]);
    renderLineChart(document.querySelector("#humidity-chart"), history.readings, [
      { key: "humidity", label: "Kelembapan %", color: "#41a8d8" },
    ]);
    renderLineChart(document.querySelector("#gas-chart"), history.readings, [
      { key: "gas", label: "Gas MQ", color: "#e99b2e" },
    ]);
    renderTable(history.readings);
  } catch (error) {
    setStatusBadge(document.querySelector("#monitor-status"), { label: "Backend tidak tersedia", className: "status-danger" });
    ["#temperature-chart", "#humidity-chart", "#gas-chart"].forEach((id) =>
      showError(document.querySelector(id), error.message),
    );
  }
}

startPolling(refresh, 2000);
