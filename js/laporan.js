import { apiFetch, formatDateTime, formatInteger, formatNumber, initShell, readingStatus } from "./app.js";

initShell("/laporan");

const startInput = document.querySelector("#start-date");
const endInput = document.querySelector("#end-date");
const form = document.querySelector("#report-form");
let currentPage = 1;

const today = new Intl.DateTimeFormat("en-CA").format(new Date());
startInput.value = today;
endInput.value = today;

function query(page = 1) {
  return `start_date=${encodeURIComponent(startInput.value)}&end_date=${encodeURIComponent(endInput.value)}&page=${page}&page_size=100`;
}

function setText(id, value) {
  document.querySelector(id).textContent = value;
}

function renderSummary(data) {
  for (const sensor of ["temperature", "humidity", "gas"]) {
    const values = data.statistics[sensor];
    const suffix = sensor === "temperature" ? "°C" : sensor === "humidity" ? "%" : "";
    setText(`#${sensor}-average`, `${formatNumber(values.average)}${suffix}`);
    setText(`#${sensor}-range`, `${formatNumber(values.minimum)} – ${formatNumber(values.maximum)}${suffix}`);
  }
  setText("#report-total", formatInteger(data.counts.total_readings));
  setText("#report-abnormal", formatInteger(data.counts.temperature_abnormal + data.counts.gas_abnormal + data.counts.dht_problem));
  setText("#report-buzzer", formatInteger(data.counts.buzzer_active));
}

function renderReadings(data) {
  document.querySelector("#report-table").innerHTML = data.readings.length
    ? data.readings
        .map((item) => {
          const status = readingStatus(item);
          return `<tr><td>${formatDateTime(item.received_at)}</td><td>${formatNumber(item.temperature)}°C</td><td>${formatNumber(item.humidity)}%</td><td>${formatInteger(item.gas)}</td><td>${item.buzzer}</td><td><span class="status-badge ${status.className}">${status.label}</span></td></tr>`;
        })
        .join("")
    : `<tr><td colspan="6" class="text-center">Tidak ada data pada rentang ini.</td></tr>`;
  const pagination = data.pagination;
  setText("#page-info", `Halaman ${pagination.page} dari ${Math.max(1, pagination.total_pages)} · ${formatInteger(pagination.total_items)} data`);
  document.querySelector("#prev-page").disabled = pagination.page <= 1;
  document.querySelector("#next-page").disabled = pagination.page >= pagination.total_pages;
}

async function load(page = 1) {
  currentPage = page;
  const errorHost = document.querySelector("#report-error");
  errorHost.classList.add("hidden");
  try {
    const [summary, readings] = await Promise.all([
      apiFetch(`/api/reports/summary?${query(page)}`),
      apiFetch(`/api/reports/readings?${query(page)}`),
    ]);
    renderSummary(summary);
    renderReadings(readings);
  } catch (error) {
    errorHost.textContent = error.message;
    errorHost.classList.remove("hidden");
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  load(1);
});
document.querySelector("#prev-page").addEventListener("click", () => load(currentPage - 1));
document.querySelector("#next-page").addEventListener("click", () => load(currentPage + 1));
document.querySelector("#export-pdf").addEventListener("click", () => {
  window.location.href = `/api/reports/export.pdf?${query(currentPage)}`;
});
document.querySelector("#export-excel").addEventListener("click", () => {
  window.location.href = `/api/reports/export.xlsx?${query(currentPage)}`;
});

load();
