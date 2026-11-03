"use strict";

const state = { csrf: "", status: null };
const byId = (id) => document.getElementById(id);

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;"
  })[character]);
}

function notice(message, error = false) {
  const element = byId("notice");
  element.textContent = message;
  element.classList.toggle("error", error);
  element.hidden = false;
  window.setTimeout(() => { element.hidden = true; }, 5000);
}

async function request(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (options.method === "POST") {
    headers["Content-Type"] = "application/json";
    headers["X-Personal-Vault-CSRF"] = state.csrf;
  }
  const response = await fetch(path, { ...options, headers, cache: "no-store" });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || `HTTP_${response.status}`);
  return payload;
}

function showPanel(name) {
  document.querySelectorAll(".panel").forEach((panel) => panel.classList.toggle("active", panel.id === `panel-${name}`));
  document.querySelectorAll(".nav-button").forEach((button) => button.classList.toggle("active", button.dataset.panel === name));
}

function renderLevels(levels) {
  const maximum = Math.max(1, ...Object.values(levels));
  byId("level-bars").innerHTML = Object.entries(levels).map(([level, count]) => `
    <div class="level-row"><strong>${escapeHtml(level.toUpperCase())}</strong><progress class="level-progress" max="${maximum}" value="${count}" aria-label="${escapeHtml(level.toUpperCase())}: ${count}"></progress><span>${count}</span></div>
  `).join("");
}

function visibilityText(value) {
  return ({ PRIVATE: "私有", PUBLIC: "公开", INTERNAL: "内部", UNVERIFIED: "未验证" })[value] || value;
}

function proposalStatus(value) {
  return ({ pending: "待审核", approved: "已通过", rejected: "已拒绝" })[value] || value;
}

function integrationText(item) {
  if (!item.enabled) return "未启用";
  if (!item.available) return "依赖缺失";
  return item.status === "ok" ? "已更新" : "等待首次运行";
}

function renderStatus(payload) {
  state.status = payload;
  state.csrf = payload._csrf;
  byId("formal-pages").textContent = payload.vault.formal_pages;
  byId("source-count").textContent = `${payload.sources.enabled}/${payload.sources.total}`;
  byId("pending-count").textContent = payload.proposals.pending;
  byId("github-visibility").textContent = visibilityText(payload.integrations.github.visibility);
  byId("vault-path").textContent = payload.vault.path;
  byId("raw-pages").textContent = `${payload.vault.raw_pages} 页`;
  byId("qmd-status").textContent = integrationText(payload.integrations.qmd);
  byId("backup-status").textContent = integrationText(payload.integrations.restic);
  byId("qmd-detail").textContent = integrationText(payload.integrations.qmd);
  byId("backup-detail").textContent = integrationText(payload.integrations.restic);
  byId("github-detail").textContent = visibilityText(payload.integrations.github.visibility);
  byId("health-label").textContent = payload.vault.exists ? "本地可用" : "Vault 缺失";
  byId("health-dot").classList.toggle("ok", payload.vault.exists);
  renderLevels(payload.knowledge_map);
}

function sourceActionButton(source) {
  if (source.enabled) return `<button class="button button-danger source-action" data-action="disable" data-id="${escapeHtml(source.id)}">停用</button>`;
  return `<button class="button button-secondary source-action" data-action="enable" data-id="${escapeHtml(source.id)}" data-kind="${escapeHtml(source.kind)}">启用</button>`;
}

async function loadSources() {
  const sources = await request("/api/sources");
  byId("source-summary").textContent = `${sources.filter((item) => item.enabled).length}/${sources.length} 已启用`;
  byId("source-rows").innerHTML = sources.length ? sources.map((source) => `
    <tr><td data-label="ID">${escapeHtml(source.id)}</td><td data-label="类型">${escapeHtml(source.kind)}</td><td data-label="路径">${escapeHtml(source.path)}</td><td data-label="状态">${source.enabled ? "已启用" : "未启用"}</td><td data-label="操作"><div class="inline-actions">${sourceActionButton(source)}</div></td></tr>
  `).join("") : `<tr><td class="empty-row" colspan="5">暂无授权来源</td></tr>`;
  document.querySelectorAll(".source-action").forEach((button) => button.addEventListener("click", () => changeSource(button)));
}

async function changeSource(button) {
  const action = button.dataset.action;
  const id = button.dataset.id;
  let confirmation = "";
  if (action === "enable") {
    const kind = button.dataset.kind;
    confirmation = ["agent_history", "weflow", "qq"].includes(kind) ? `AUTHORIZE:${id}:${kind}` : `ENABLE:${id}`;
    if (!window.confirm(`确认启用来源 ${id}？`)) return;
  } else if (!window.confirm(`确认停用来源 ${id}？`)) return;
  try {
    await request("/api/actions/source", { method: "POST", body: JSON.stringify({ action, id, confirmation }) });
    await Promise.all([loadSources(), loadStatus()]);
    notice("来源配置已更新");
  } catch (error) { notice(error.message, true); }
}

async function loadProposals() {
  const proposals = await request("/api/proposals");
  const pending = proposals.filter((item) => item.status === "pending");
  byId("review-summary").textContent = `${pending.length} 条待审核`;
  byId("proposal-rows").innerHTML = proposals.length ? proposals.map((proposal) => `
    <tr><td data-label="标题">${escapeHtml(proposal.title)}</td><td data-label="类型">${escapeHtml(proposal.knowledge_type)}</td><td data-label="置信度">${Number(proposal.confidence).toFixed(2)}</td><td data-label="目标">${escapeHtml(proposal.target)}</td><td data-label="状态">${escapeHtml(proposalStatus(proposal.status))}</td><td data-label="操作">${proposal.status === "pending" ? `<div class="inline-actions"><button class="button button-primary review-action" data-action="promote" data-id="${escapeHtml(proposal.id)}">通过</button><button class="button button-danger review-action" data-action="reject" data-id="${escapeHtml(proposal.id)}">拒绝</button></div>` : "-"}</td></tr>
  `).join("") : `<tr><td class="empty-row" colspan="6">暂无知识提案</td></tr>`;
  document.querySelectorAll(".review-action").forEach((button) => button.addEventListener("click", () => reviewProposal(button)));
}

async function reviewProposal(button) {
  const action = button.dataset.action;
  const id = button.dataset.id;
  if (!window.confirm(`${action === "promote" ? "通过" : "拒绝"} ${id}？`)) return;
  const prefix = action === "promote" ? "PROMOTE" : "REJECT";
  try {
    await request("/api/actions/review", { method: "POST", body: JSON.stringify({ action, id, confirmation: `${prefix}:${id}` }) });
    await Promise.all([loadProposals(), loadStatus()]);
    notice("审核状态已更新");
  } catch (error) { notice(error.message, true); }
}

async function loadStatus() {
  renderStatus(await request("/api/status"));
}

async function refreshAll() {
  try {
    await loadStatus();
    await Promise.all([loadSources(), loadProposals()]);
  } catch (error) { notice(error.message, true); }
}

async function runAction(button) {
  const action = button.dataset.action;
  const mode = button.dataset.mode;
  const write = mode !== "preview";
  if (write && !window.confirm(`确认执行 ${action}？`)) return;
  button.disabled = true;
  try {
    const result = await request(`/api/actions/${action}`, { method: "POST", body: JSON.stringify({ mode, confirm: write }) });
    byId("action-output").textContent = JSON.stringify(result, null, 2);
    await refreshAll();
    notice(mode === "preview" ? "预览完成" : "执行完成");
  } catch (error) {
    byId("action-output").textContent = JSON.stringify({ error: error.message }, null, 2);
    notice(error.message, true);
  } finally { button.disabled = false; }
}

document.querySelectorAll(".nav-button").forEach((button) => button.addEventListener("click", () => showPanel(button.dataset.panel)));
document.querySelectorAll(".action").forEach((button) => button.addEventListener("click", () => runAction(button)));
byId("refresh").addEventListener("click", refreshAll);
byId("source-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = { action: "add", id: byId("source-id").value.trim(), kind: byId("source-kind").value, path: byId("source-path").value.trim() };
  try {
    await request("/api/actions/source", { method: "POST", body: JSON.stringify(payload) });
    event.target.reset();
    await Promise.all([loadSources(), loadStatus()]);
    notice("来源已添加，默认保持停用");
  } catch (error) { notice(error.message, true); }
});
byId("search-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const query = byId("search-query").value.trim();
  try {
    const results = await request(`/api/search?q=${encodeURIComponent(query)}`);
    byId("search-count").textContent = `${results.length} 条结果`;
    byId("search-results").innerHTML = results.length ? results.map((result) => `
      <article class="search-item"><h3>${escapeHtml(result.title)}</h3><p>${escapeHtml(result.snippet)}</p><span class="search-path">${escapeHtml(result.path)}</span></article>
    `).join("") : `<div class="empty-row">没有匹配的正式知识</div>`;
  } catch (error) { notice(error.message, true); }
});

refreshAll();
