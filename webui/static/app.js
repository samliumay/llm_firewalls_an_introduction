"use strict";

const $ = (id) => document.getElementById(id);
const newId = () =>
  (window.crypto && crypto.randomUUID)
    ? crypto.randomUUID()
    : String(Date.now()) + Math.random().toString(16).slice(2);

let sessionId = newId();

const VERDICT_LABELS = {
  allowed: "ALLOWED",
  blocked: "BLOCKED",
  not_inspected: "NOT INSPECTED",
};

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function clearEmptyState() {
  const empty = document.querySelector(".messages .empty");
  if (empty) empty.remove();
}

function addMessage(kind, who, text) {
  clearEmptyState();
  const wrap = el("div", "msg " + kind);
  wrap.append(el("div", "who", who), el("div", "bubble", text));
  $("messages").append(wrap);
  $("messages").scrollTop = $("messages").scrollHeight;
  return wrap;
}

function rowsTable(rows) {
  const columns = Object.keys(rows[0] || {});
  const table = el("table");
  const head = table.createTHead().insertRow();
  columns.forEach((c) => head.append(el("th", "", c)));
  const body = table.createTBody();
  rows.forEach((row) => {
    const tr = body.insertRow();
    columns.forEach((c) => tr.append(el("td", "", row[c] === null ? "NULL" : String(row[c]))));
  });
  const wrap = el("div", "table-wrap");
  wrap.append(table);
  return wrap;
}

function renderEvent(event, index) {
  const box = el("div", "event");
  const head = el("div", "event-head");
  head.append(
    el("span", "", "Tool call " + (index + 1)),
    el("span", "verdict " + event.verdict, VERDICT_LABELS[event.verdict] || event.verdict),
    el("span", "", event.firewall_enabled ? "firewall on" : "firewall off"),
  );
  box.append(head, el("pre", "", event.sql));

  if (event.reason) {
    box.append(el("div", "detail bad", event.reason));
  }
  if (event.database_error) {
    box.append(el("div", "detail bad", "Database error: " + event.database_error));
  }
  if (typeof event.row_count === "number") {
    const shown = event.rows ? event.rows.length : 0;
    let label = event.row_count + " row(s) returned";
    if (shown < event.row_count) label += ", showing first " + shown;
    box.append(el("div", "detail", label));
    if (shown) box.append(rowsTable(event.rows));
  }
  if (typeof event.affected_rows === "number") {
    box.append(el("div", "detail", event.affected_rows + " row(s) affected"));
  }
  return box;
}

function attachEvents(messageNode, events) {
  if (!events || !events.length) {
    messageNode.append(el("div", "event-head", "No SQL was generated for this turn."));
    return;
  }
  const list = el("div", "events");
  events.forEach((e, i) => list.append(renderEvent(e, i)));
  messageNode.append(list);
}

async function postJson(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  let data;
  try {
    data = await response.json();
  } catch {
    data = { error: "The server returned HTTP " + response.status + "." };
  }
  return data;
}

async function sendPrompt(text) {
  addMessage("user", "You", text);
  const pending = addMessage("assistant pending", "Assistant", "Thinking... (the model may call the database tool several times)");
  $("send").disabled = true;

  try {
    const data = await postJson("/api/chat", {
      session_id: sessionId,
      message: text,
      model: $("model").value.trim(),
      firewall: $("firewall").checked,
    });
    pending.remove();
    let node;
    if (data.error) {
      node = addMessage("error", "Error", data.error);
    } else {
      node = addMessage("assistant", "Assistant (" + data.model + ")", data.answer || "(empty answer)");
    }
    attachEvents(node, data.firewall_events);
  } catch (err) {
    pending.remove();
    addMessage("error", "Error", "Could not reach the web server: " + err.message);
  } finally {
    $("send").disabled = false;
    $("messages").scrollTop = $("messages").scrollHeight;
  }
}

async function resetConversation(note) {
  const old = sessionId;
  sessionId = newId();
  $("messages").replaceChildren();
  if (note) addMessage("assistant", "System", note);
  try { await postJson("/api/reset", { session_id: old }); } catch { /* ignore */ }
}

function updateModeUi() {
  const on = $("firewall").checked;
  $("firewall-label").textContent = on ? "Firewall on (protected)" : "Firewall off (unprotected)";
  $("unprotected-banner").hidden = on;
}

async function loadStatus() {
  const pill = $("ollama-status");
  try {
    const data = await (await fetch("/api/status")).json();
    if (!$("model").value) $("model").value = data.default_model;
    const list = $("model-list");
    list.replaceChildren();
    data.models.filter((m) => m.tools).forEach((m) => {
      const option = document.createElement("option");
      option.value = m.name;
      list.append(option);
    });
    if (data.ollama === "ok") {
      pill.textContent = "Ollama connected";
      pill.className = "pill ok";
      const names = data.models.map((m) => m.name);
      if (!names.includes($("model").value)) {
        pill.textContent = "Ollama connected; model '" + $("model").value + "' not installed";
        pill.className = "pill bad";
      }
    } else {
      pill.textContent = "Ollama unreachable";
      pill.title = data.ollama_error || "";
      pill.className = "pill bad";
    }
  } catch {
    pill.textContent = "Status unavailable";
    pill.className = "pill bad";
  }
}

$("chat-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const text = $("prompt").value.trim();
  if (!text || $("send").disabled) return;
  $("prompt").value = "";
  sendPrompt(text);
});

$("prompt").addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    $("chat-form").requestSubmit();
  }
});

document.querySelectorAll(".example").forEach((button) => {
  button.addEventListener("click", () => {
    $("prompt").value = button.textContent;
    $("prompt").focus();
  });
});

$("firewall").addEventListener("change", () => {
  if (!$("firewall").checked &&
      !confirm("Unprotected mode lets model-generated SQL modify the demo database. Continue?")) {
    $("firewall").checked = true;
    return;
  }
  updateModeUi();
  resetConversation("Started a new conversation in " +
    ($("firewall").checked ? "protected" : "unprotected") + " mode.");
});

$("model").addEventListener("change", () => {
  loadStatus();
  resetConversation("Started a new conversation with model " + $("model").value.trim() + ".");
});

$("reset").addEventListener("click", () => resetConversation());

$("sql-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const out = $("sql-result");
  out.replaceChildren();
  try {
    const data = await postJson("/api/firewall/check", { query: $("sql").value });
    out.append(
      el("span", "verdict " + data.verdict, VERDICT_LABELS[data.verdict] || "ERROR"),
      el("div", "detail", data.reason || data.error || ""),
    );
  } catch (err) {
    out.append(el("div", "detail bad", "Request failed: " + err.message));
  }
});

updateModeUi();
loadStatus();
