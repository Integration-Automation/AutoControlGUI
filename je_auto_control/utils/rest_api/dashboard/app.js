"use strict";

const POLL_MS = 5000;
const TOKEN_KEY = "ac-rest-token";
const PANELS = ["diagnostics", "sessions", "inspector", "usb", "audit"];

const tokenInput = document.getElementById("token");
const saveBtn = document.getElementById("save-token");
const serverInfo = document.getElementById("server-info");

let pollTimer = null;

document.addEventListener("DOMContentLoaded", () => {
  const cached = sessionStorage.getItem(TOKEN_KEY);
  if (cached) {
    tokenInput.value = cached;
  }
  saveBtn.addEventListener("click", () => {
    sessionStorage.setItem(TOKEN_KEY, tokenInput.value.trim());
    refreshAll();
  });
  serverInfo.textContent = `${location.protocol}//${location.host}`;
  refreshAll();
  pollTimer = setInterval(refreshAll, POLL_MS);
});

function getToken() {
  return tokenInput.value.trim() || sessionStorage.getItem(TOKEN_KEY) || "";
}

async function fetchJson(path) {
  const token = getToken();
  if (!token) {
    throw new Error("no bearer token set");
  }
  const resp = await fetch(path, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!resp.ok) {
    throw new Error(`HTTP ${resp.status} on ${path}`);
  }
  return resp.json();
}

function panelEl(name) {
  return document.querySelector(`section[data-panel="${name}"]`);
}

function setPanelStatus(name, message, kind) {
  const status = panelEl(name).querySelector("[data-status]");
  if (!status) return;
  status.textContent = message;
  status.className = "panel-status" + (kind ? ` ${kind}` : "");
}

function clearRows(name) {
  const rows = panelEl(name).querySelector("[data-rows]");
  if (rows.tagName === "PRE") {
    rows.textContent = "—";
  } else {
    rows.innerHTML = "";
  }
}

async function refreshAll() {
  if (!getToken()) {
    PANELS.forEach((name) => setPanelStatus(name, "set bearer token to begin", "error"));
    return;
  }
  await Promise.all([
    refreshDiagnostics(),
    refreshSessions(),
    refreshInspector(),
    refreshUsb(),
    refreshAudit(),
  ]);
}

async function refreshDiagnostics() {
  try {
    const data = await fetchJson("/diagnose");
    setPanelStatus("diagnostics",
      `${data.count} checks, ${data.failed} failed`,
      data.ok ? "ok" : "error");
    const tbody = panelEl("diagnostics").querySelector("[data-rows]");
    tbody.innerHTML = "";
    for (const check of data.checks) {
      const tr = document.createElement("tr");
      tr.innerHTML =
        `<td>${escapeHtml(check.name)}</td>` +
        `<td class="sev-${check.severity}">${escapeHtml(check.severity)}</td>` +
        `<td>${escapeHtml(check.detail)}</td>`;
      tbody.appendChild(tr);
    }
  } catch (error) {
    setPanelStatus("diagnostics", String(error.message || error), "error");
    clearRows("diagnostics");
  }
}

async function refreshSessions() {
  try {
    const data = await fetchJson("/sessions");
    panelEl("sessions").querySelector("[data-rows]").textContent =
      JSON.stringify(data, null, 2);
  } catch (error) {
    setPanelStatus("sessions", String(error.message || error), "error");
    panelEl("sessions").querySelector("[data-rows]").textContent = "—";
  }
}

async function refreshInspector() {
  try {
    const data = await fetchJson("/inspector/summary");
    setPanelStatus("inspector",
      `${data.sample_count} samples / window ${data.window_seconds.toFixed(1)}s`,
      "ok");
    const tbody = panelEl("inspector").querySelector("[data-rows]");
    tbody.innerHTML = "";
    for (const [metric, stats] of Object.entries(data.metrics || {})) {
      const tr = document.createElement("tr");
      tr.innerHTML =
        `<td>${escapeHtml(metric)}</td>` +
        `<td>${formatStat(stats.last)}</td>` +
        `<td>${formatStat(stats.avg)}</td>` +
        `<td>${formatStat(stats.p95)}</td>`;
      tbody.appendChild(tr);
    }
  } catch (error) {
    setPanelStatus("inspector", String(error.message || error), "error");
    clearRows("inspector");
  }
}

async function refreshUsb() {
  try {
    const data = await fetchJson("/usb/devices");
    setPanelStatus("usb",
      `${data.count} devices via ${data.backend}` + (data.error ? ` (${data.error})` : ""),
      data.error ? "error" : "ok");
    const tbody = panelEl("usb").querySelector("[data-rows]");
    tbody.innerHTML = "";
    for (const dev of data.devices) {
      const tr = document.createElement("tr");
      tr.innerHTML =
        `<td>${escapeHtml(dev.vendor_id || "-")}</td>` +
        `<td>${escapeHtml(dev.product_id || "-")}</td>` +
        `<td>${escapeHtml(dev.manufacturer || "")}</td>` +
        `<td>${escapeHtml(dev.product || "")}</td>`;
      tbody.appendChild(tr);
    }
  } catch (error) {
    setPanelStatus("usb", String(error.message || error), "error");
    clearRows("usb");
  }
}

async function refreshAudit() {
  try {
    const data = await fetchJson("/audit/list?limit=20");
    setPanelStatus("audit", `${data.count} most recent rows`, "ok");
    const tbody = panelEl("audit").querySelector("[data-rows]");
    tbody.innerHTML = "";
    for (const row of data.rows) {
      const tr = document.createElement("tr");
      tr.innerHTML =
        `<td>${escapeHtml(row.ts || "")}</td>` +
        `<td>${escapeHtml(row.event_type || "")}</td>` +
        `<td>${escapeHtml(row.host_id || "")}</td>` +
        `<td>${escapeHtml(row.detail || "")}</td>`;
      tbody.appendChild(tr);
    }
  } catch (error) {
    setPanelStatus("audit", String(error.message || error), "error");
    clearRows("audit");
  }
}

function formatStat(value) {
  if (value === null || value === undefined) return "-";
  return Number(value).toFixed(2);
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}
