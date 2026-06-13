export async function apiFetch(url, options = {}) {
  const response = await fetch(url, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });

  if (response.status === 401) {
    window.location.href = "/login";
    throw new Error("Sesi telah berakhir.");
  }

  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json") ? await response.json() : null;
  if (!response.ok) {
    throw new Error(payload?.error?.message || "Permintaan gagal diproses.");
  }
  return payload?.data;
}

export function formatNumber(value, digits = 1) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
  return new Intl.NumberFormat("id-ID", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(Number(value));
}

export function formatInteger(value) {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("id-ID").format(Number(value));
}

export function formatDateTime(value) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("id-ID", {
    dateStyle: "medium",
    timeStyle: "medium",
  }).format(new Date(value));
}

export function readingStatus(reading) {
  if (!reading) return { label: "Belum ada data", className: "status-neutral" };
  if (reading.has_problem) return { label: "DHT bermasalah", className: "status-warning" };
  if (reading.temperature_abnormal || reading.gas_abnormal) {
    return { label: "Kondisi abnormal", className: "status-danger" };
  }
  if (reading.buzzer_inconsistent) return { label: "Buzzer tidak konsisten", className: "status-warning" };
  return { label: "Kondisi normal", className: "status-normal" };
}

export function dataStatus(status) {
  const states = {
    online: ["Sistem online", "status-normal"],
    stale: ["Data terlambat", "status-warning"],
    no_data: ["Belum ada data", "status-neutral"],
  };
  const [label, className] = states[status?.state] || ["Tidak diketahui", "status-neutral"];
  const age = status?.age_seconds == null ? "" : ` · ${status.age_seconds} detik lalu`;
  return { label: `${label}${age}`, className };
}

export function setStatusBadge(element, status) {
  element.className = `status-badge ${status.className}`;
  element.innerHTML = `<span class="h-2 w-2 rounded-full bg-current"></span>${status.label}`;
}

export function initShell(activePath) {
  document.querySelectorAll("[data-nav]").forEach((link) => {
    if (link.getAttribute("href") === activePath) link.classList.add("active");
  });

  const sidebar = document.querySelector("#sidebar");
  const overlay = document.querySelector("#mobile-overlay");
  const closeMenu = () => {
    sidebar?.classList.remove("open");
    overlay?.classList.remove("open");
  };
  document.querySelector("#menu-button")?.addEventListener("click", () => {
    sidebar?.classList.add("open");
    overlay?.classList.add("open");
  });
  overlay?.addEventListener("click", closeMenu);
  document.querySelector("#close-menu")?.addEventListener("click", closeMenu);

  document.querySelector("#logout-button")?.addEventListener("click", async () => {
    try {
      await apiFetch("/api/auth/logout", { method: "POST", body: "{}" });
    } finally {
      window.location.href = "/login";
    }
  });

  apiFetch("/api/auth/me")
    .then((user) => {
      document.querySelectorAll("[data-username]").forEach((node) => {
        node.textContent = user.username;
      });
    })
    .catch(() => {});
}

export function startPolling(callback, interval = 2000) {
  let timer = null;
  const run = async () => {
    if (document.hidden) return;
    try {
      await callback();
    } catch (error) {
      console.error(error);
    }
  };
  run();
  timer = window.setInterval(run, interval);
  document.addEventListener("visibilitychange", run);
  return () => window.clearInterval(timer);
}

export function renderLineChart(element, readings, series) {
  if (!element) return;
  if (!readings?.length) {
    element.innerHTML = `<div class="empty-state">Belum ada data sensor untuk divisualisasikan.</div>`;
    return;
  }
  const ordered = [...readings].reverse();
  const width = Math.max(element.clientWidth || 700, 420);
  const height = 270;
  const padding = { top: 24, right: 20, bottom: 35, left: 46 };
  const allValues = series.flatMap((item) =>
    ordered.map((reading) => Number(reading[item.key])).filter(Number.isFinite),
  );
  let min = Math.min(...allValues);
  let max = Math.max(...allValues);
  if (min === max) {
    min -= 1;
    max += 1;
  }
  const x = (index) =>
    padding.left + (index / Math.max(1, ordered.length - 1)) * (width - padding.left - padding.right);
  const y = (value) =>
    padding.top + ((max - value) / (max - min)) * (height - padding.top - padding.bottom);
  const grid = Array.from({ length: 5 }, (_, index) => {
    const value = max - ((max - min) * index) / 4;
    const yPos = padding.top + ((height - padding.top - padding.bottom) * index) / 4;
    return `<line x1="${padding.left}" x2="${width - padding.right}" y1="${yPos}" y2="${yPos}" stroke="#dfece3" stroke-dasharray="4 5"/>
      <text x="${padding.left - 8}" y="${yPos + 4}" text-anchor="end" fill="#789184" font-size="10">${formatNumber(value, 0)}</text>`;
  }).join("");
  const lines = series
    .map((item) => {
      const points = ordered
        .map((reading, index) => `${x(index)},${y(Number(reading[item.key]))}`)
        .join(" ");
      return `<polyline points="${points}" fill="none" stroke="${item.color}" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
      ${ordered
        .map(
          (reading, index) =>
            `<circle cx="${x(index)}" cy="${y(Number(reading[item.key]))}" r="2.4" fill="${item.color}"><title>${item.label}: ${reading[item.key]} · ${formatDateTime(reading.received_at)}</title></circle>`,
        )
        .join("")}`;
    })
    .join("");
  const legend = series
    .map(
      (item, index) =>
        `<g transform="translate(${padding.left + index * 135},${height - 8})"><circle r="4" fill="${item.color}"/><text x="9" y="4" fill="#52675b" font-size="11">${item.label}</text></g>`,
    )
    .join("");
  element.innerHTML = `<svg viewBox="0 0 ${width} ${height}" class="h-full w-full" role="img" aria-label="Grafik sensor">${grid}${lines}${legend}</svg>`;
}

export function showError(element, message) {
  if (element) element.innerHTML = `<div class="empty-state"><b class="mb-1 text-red-600">Data tidak dapat dimuat</b>${message}</div>`;
}
