"use strict";

const POLL_MS = 5000;
// nosemgrep: codacy.javascript.security.hard-coded-password
// This is the sessionStorage SLOT NAME for the bearer token, not the
// token itself. Codacy/Semgrep's hardcoded-password pattern fires on
// any literal that contains the word "token"; the value here is a
// public storage key (visible in DevTools) and never a credential.
const TOKEN_STORAGE_KEY = "ac-rest-token";  // NOSONAR
const PANELS = ["diagnostics", "sessions", "inspector", "usb", "audit"];

const tokenInput = document.getElementById("token");
const saveBtn = document.getElementById("save-token");
const serverInfo = document.getElementById("server-info");

let pollTimer = null;

document.addEventListener("DOMContentLoaded", () => {
  const cached = sessionStorage.getItem(TOKEN_STORAGE_KEY);
  if (cached) {
    tokenInput.value = cached;
  }
  saveBtn.addEventListener("click", () => {
    sessionStorage.setItem(TOKEN_STORAGE_KEY, tokenInput.value.trim());
    refreshAll();
  });
  serverInfo.textContent = `${location.protocol}//${location.host}`;
  refreshAll();
  pollTimer = setInterval(refreshAll, POLL_MS);
});

function getToken() {
  return tokenInput.value.trim() || sessionStorage.getItem(TOKEN_STORAGE_KEY) || "";
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
    clearChildren(rows);
  }
}

function clearChildren(node) {
  while (node.firstChild) {
    node.firstChild.remove();
  }
}

// Build a <tr> from cell descriptors and append it to ``tbody``. Each
// cell is either a string (rendered via textContent so any HTML in the
// payload is treated as literal text) or an object {text, className}.
// Using createElement + textContent eliminates the innerHTML/escapeHtml
// dance that tripped Codacy's no-unsanitized-property and Sonar
// insecure-innerhtml rules — there is no template parsing here, so an
// attacker-controlled value can never become DOM markup.
function appendRow(tbody, cells) {
  const tr = document.createElement("tr");
  for (const cell of cells) {
    const td = document.createElement("td");
    if (cell && typeof cell === "object") {
      td.textContent = cell.text == null ? "" : String(cell.text);
      if (cell.className) td.className = cell.className;
    } else {
      td.textContent = cell == null ? "" : String(cell);
    }
    tr.appendChild(td);
  }
  tbody.appendChild(tr);
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
    clearChildren(tbody);
    for (const check of data.checks) {
      appendRow(tbody, [
        check.name,
        { text: check.severity, className: `sev-${check.severity}` },
        check.detail,
      ]);
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
    clearChildren(tbody);
    for (const [metric, stats] of Object.entries(data.metrics || {})) {
      appendRow(tbody, [
        metric,
        formatStat(stats.last),
        formatStat(stats.avg),
        formatStat(stats.p95),
      ]);
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
    clearChildren(tbody);
    for (const dev of data.devices) {
      appendRow(tbody, [
        dev.vendor_id || "-",
        dev.product_id || "-",
        dev.manufacturer || "",
        dev.product || "",
      ]);
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
    clearChildren(tbody);
    for (const row of data.rows) {
      appendRow(tbody, [
        row.ts || "",
        row.event_type || "",
        row.host_id || "",
        row.detail || "",
      ]);
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
