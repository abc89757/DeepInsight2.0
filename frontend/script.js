const API_BASE_URL = "http://127.0.0.1:8000/api";
const TASK_POLL_INTERVAL = 1800;
const LOGO_FULL_SRC = "./assets/Logo2.png";
const LOGO_MARK_SRC = "./assets/Logo3.png";

const appShell = document.querySelector(".app-shell");
const queryInput = document.getElementById("queryInput");
const charCounter = document.getElementById("charCounter");
const startAnalyzeBtn = document.getElementById("startAnalyzeBtn");
const databaseSelect = document.getElementById("databaseSelect");
const openDbModalBtn = document.getElementById("openDbModalBtn");
const brandHomeBtn = document.getElementById("brandHomeBtn");
const brandLogo = document.querySelector(".brand-logo");
const sidebarCollapseBtn = document.getElementById("sidebarCollapseBtn");
const closeDbModalBtn = document.getElementById("closeDbModalBtn");
const dbModal = document.getElementById("dbModal");
const dbModalTitle = document.getElementById("dbModalTitle");
const dbModalSubtitle = document.getElementById("dbModalSubtitle");
const dbManageView = document.getElementById("dbManageView");
const dbFormView = document.getElementById("dbFormView");
const connectionList = document.getElementById("connectionList");
const addConnectionBtn = document.getElementById("addConnectionBtn");
const backToDbListBtn = document.getElementById("backToDbListBtn");
const dbForm = document.getElementById("dbForm");
const testDbBtn = document.getElementById("testDbBtn");
const clearDbFormBtn = document.getElementById("clearDbFormBtn");
const saveDbBtn = dbForm.querySelector("button[type='submit']");
const dbStatus = document.getElementById("dbStatus");
const toast = document.getElementById("toast");

const dbType = document.getElementById("dbType");
const dbAlias = document.getElementById("dbAlias");
const dbHost = document.getElementById("dbHost");
const dbPort = document.getElementById("dbPort");
const dbUser = document.getElementById("dbUser");
const dbPassword = document.getElementById("dbPassword");
const dbNameGroup = document.getElementById("dbNameGroup");
const dbName = document.getElementById("dbName");

const historyList = document.getElementById("historyList");
const taskView = document.getElementById("taskView");
const backHomeBtn = document.getElementById("backHomeBtn");

const taskTitle = document.getElementById("taskTitle");
const taskQuestion = document.getElementById("taskQuestion");
const taskStatus = document.getElementById("taskStatus");
const taskStage = document.getElementById("taskStage");
const taskUpdatedAt = document.getElementById("taskUpdatedAt");
const progressSection = document.getElementById("progressSection");
const progressToggleBtn = document.getElementById("progressToggleBtn");
const stepsList = document.getElementById("stepsList");
const reportSection = document.getElementById("reportSection");
const reportDownloadPdfBtn = document.getElementById("reportDownloadPdfBtn");
const reportContent = document.getElementById("reportContent");

const heroSection = document.querySelector(".hero-section");
const featureStrip = document.querySelector(".feature-strip");

let toastTimer = null;
let currentTaskId = null;
let taskPollTimer = null;
let taskEventSource = null;
let taskEventSourceClosedExpected = false;
let liveTaskSteps = [];
let currentReportMarkdown = "";
let databaseConnections = [];
let managedConnections = [];
let isSidebarCollapsed = false;
let isProgressCollapsed = false;
const collapsedStepSummaries = new Set();
const connectionDetailCache = new Map();
const STAGE_ORDER_MAP = {
  waiting: 0,
  database_precheck: 1,
  load_schema: 2,
  skill_advisor: 3,
  skill_loader: 4,
  chief_analyst: 5,
  evidence_planner: 6,
  sql_engineer: 7,
  audit_sql: 8,
  execute_sql: 9,
  data_processor: 10,
  insight_analyst: 11,
  report_writer: 12,
  finished: 13,
};
const STAGE_TITLE_MAP = {
  waiting: "等待执行",
  database_precheck: "数据库连接检查",
  load_schema: "读取数据库 Schema",
  skill_advisor: "选择 Skill",
  skill_loader: "加载 Skill",
  chief_analyst: "首席分析师决策",
  evidence_planner: "规划证据",
  sql_engineer: "生成 SQL",
  audit_sql: "SQL 审计",
  execute_sql: "执行 SQL",
  data_processor: "处理数据",
  insight_analyst: "分析洞察",
  report_writer: "生成报告",
  finished: "任务完成",
};
const TRASH_ICON = `
  <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
    <path d="M3 6h18"></path>
    <path d="M8 6V4h8v2"></path>
    <path d="M6.5 6l1 15h9l1-15"></path>
    <path d="M10 11v6"></path>
    <path d="M14 11v6"></path>
  </svg>
`;

/* =========================
   通用请求函数
========================= */

async function getJson(url) {
  const response = await fetch(url);

  let data = null;
  try {
    data = await response.json();
  } catch (error) {
    throw new Error("后端没有返回合法 JSON");
  }

  if (!response.ok) {
    const detail = data && data.detail ? data.detail : `请求失败：${response.status}`;
    throw new Error(detail);
  }

  return data;
}

async function postJson(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });

  let data = null;
  try {
    data = await response.json();
  } catch (error) {
    throw new Error("后端没有返回合法 JSON");
  }

  if (!response.ok) {
    const detail = data && data.detail ? data.detail : `请求失败：${response.status}`;
    throw new Error(detail);
  }

  return data;
}

async function deleteJson(url) {
  const response = await fetch(url, {
    method: "DELETE",
  });

  let data = null;
  try {
    data = await response.json();
  } catch (error) {
    throw new Error("后端没有返回合法 JSON");
  }

  if (!response.ok) {
    const detail = data && data.detail ? data.detail : `请求失败：${response.status}`;
    throw new Error(detail);
  }

  return data;
}

/* =========================
   数据库连接相关
========================= */

function getConnections() {
  return databaseConnections;
}

function getConnectionById(id) {
  return connectionDetailCache.get(id) || getConnections().find((item) => item.id === id) || null;
}

function getSelectedConnection() {
  return getConnectionById(databaseSelect.value);
}

async function loadDatabaseConnections() {
  try {
    const result = await getJson(`${API_BASE_URL}/databases/available_list`);
    databaseConnections = Array.isArray(result.connections) ? result.connections : [];
    renderDatabaseOptions();
  } catch (error) {
    databaseConnections = [];
    renderDatabaseOptions();
    showToast(`加载数据库连接失败：${error.message}`);
  }
}

async function loadManagedConnections() {
  try {
    connectionList.innerHTML = `<div class="connection-empty">正在加载数据库连接...</div>`;
    const result = await getJson(`${API_BASE_URL}/databases/saved_list`);
    managedConnections = Array.isArray(result.connections) ? result.connections : [];
    renderManagedConnections();
  } catch (error) {
    managedConnections = [];
    connectionList.innerHTML = `<div class="connection-empty error">数据库连接列表加载失败：${escapeHtml(error.message)}</div>`;
  }
}

function renderDatabaseOptions() {
  const connections = getConnections();
  const currentValue = databaseSelect.value;

  databaseSelect.innerHTML = "";

  if (connections.length === 0) {
    const emptyOption = document.createElement("option");
    emptyOption.value = "";
    emptyOption.textContent = "请先连接数据库";
    databaseSelect.appendChild(emptyOption);
    return;
  }

  connections.forEach((item) => {
    const option = document.createElement("option");
    option.value = item.id;
    option.textContent = item.database_name ? `${item.alias}（${item.database_name}）` : item.alias;
    databaseSelect.appendChild(option);
  });

  const exists = [...databaseSelect.options].some((option) => option.value === currentValue);
  if (exists) {
    databaseSelect.value = currentValue;
  }
}

function openModal() {
  dbModal.classList.remove("hidden");
  showManageConnectionsView();
  loadManagedConnections();
}

function closeModal() {
  dbModal.classList.add("hidden");
}

function showManageConnectionsView() {
  dbModalTitle.textContent = "数据库连接管理";
  dbModalSubtitle.textContent = "管理您的数据库连接，选择连接进行数据分析";
  dbManageView.classList.remove("hidden");
  dbFormView.classList.add("hidden");
}

function showAddConnectionView() {
  dbModalTitle.textContent = "新增数据库连接";
  dbModalSubtitle.textContent = "填写服务器信息，先查询数据库，再选择一个库保存为分析数据源";
  dbManageView.classList.add("hidden");
  dbFormView.classList.remove("hidden");
  dbAlias.focus();
}

function setDbStatus(message, type = "normal") {
  dbStatus.textContent = message;
  dbStatus.classList.remove("success", "error");

  if (type === "success") {
    dbStatus.classList.add("success");
  }

  if (type === "error") {
    dbStatus.classList.add("error");
  }
}

function getDatabaseTypeLabel(type) {
  const map = {
    mysql: "MySQL",
    postgresql: "PostgreSQL",
    neo4j: "Neo4j",
  };
  return map[type] || type || "-";
}

function getDatabaseTypeIcon(type) {
  const map = {
    mysql: "◎",
    postgresql: "♙",
    neo4j: "⌁",
  };
  return map[type] || "◎";
}

function getConnectionStatusText(status) {
  if (status === "available") return "已连接";
  if (status === "unavailable") return "已失效";
  return "未检测";
}

function getConnectionStatusClass(status) {
  if (status === "available") return "available";
  if (status === "unavailable") return "unavailable";
  return "unknown";
}

function renderManagedConnections() {
  connectionList.innerHTML = "";

  if (!managedConnections.length) {
    connectionList.innerHTML = `
      <div class="connection-empty">
        暂无数据库连接，点击右上角新增连接后，可以在这里管理和刷新状态。
      </div>
    `;
    return;
  }

  managedConnections.forEach((connection) => {
    const item = document.createElement("article");
    item.className = "connection-card";
    item.dataset.connectionId = connection.id;

    const status = connection.status || "unknown";
    const lastError = connection.last_error ? ` title="${escapeHtml(connection.last_error)}"` : "";

    item.innerHTML = `
      <div class="connection-logo" aria-hidden="true">${getDatabaseTypeIcon(connection.db_type)}</div>
      <div class="connection-info">
        <strong>${escapeHtml(connection.alias || "未命名连接")}</strong>
        <span>${escapeHtml(getDatabaseTypeLabel(connection.db_type))}</span>
        <small>${escapeHtml(connection.database_name || "未选择数据库")}</small>
      </div>
      <span class="connection-status ${getConnectionStatusClass(status)}"${lastError}>
        <i></i>${getConnectionStatusText(status)}
      </span>
      <div class="connection-actions">
        <button type="button" class="connection-icon refresh-connection" aria-label="刷新连接状态" title="刷新连接状态">↻</button>
        <button type="button" class="connection-icon delete-connection" aria-label="删除连接" title="删除连接">${TRASH_ICON}</button>
      </div>
    `;

    item.querySelector(".refresh-connection").addEventListener("click", () => {
      refreshManagedConnection(connection.id);
    });

    item.querySelector(".delete-connection").addEventListener("click", () => {
      deleteManagedConnection(connection.id, connection.alias);
    });

    connectionList.appendChild(item);
  });
}

async function refreshManagedConnection(connectionId) {
  const card = connectionList.querySelector(`[data-connection-id="${connectionId}"]`);
  const button = card?.querySelector(".refresh-connection");

  if (button) {
    button.disabled = true;
  }

  try {
    const result = await postJson(`${API_BASE_URL}/databases/${connectionId}/test`, {});
    showToast(result.success ? "连接可用" : "连接已失效");
    await loadManagedConnections();
    await loadDatabaseConnections();
  } catch (error) {
    showToast(`刷新连接失败：${error.message}`);
    await loadManagedConnections();
    await loadDatabaseConnections();
  } finally {
    if (button) {
      button.disabled = false;
    }
  }
}

async function deleteManagedConnection(connectionId, alias) {
  const confirmed = window.confirm(`确定删除数据库连接「${alias || connectionId}」吗？`);
  if (!confirmed) return;

  try {
    await deleteJson(`${API_BASE_URL}/databases/${connectionId}`);
    showToast("数据库连接已删除");
    await loadManagedConnections();
    await loadDatabaseConnections();
  } catch (error) {
    showToast(`删除连接失败：${error.message}`);
  }
}

function updatePortByType() {
  const portMap = {
    mysql: "3306",
    postgresql: "5432",
    neo4j: "7687",
  };
  dbPort.value = portMap[dbType.value] || "3306";
  clearDiscoveredDatabases();
}

function getFormData() {
  return {
    type: dbType.value.trim(),
    alias: dbAlias.value.trim(),
    host: dbHost.value.trim(),
    port: Number(dbPort.value),
    user: dbUser.value.trim(),
    password: dbPassword.value,
    database: dbName.value,
  };
}

function getServerFormData() {
  return {
    type: dbType.value.trim(),
    host: dbHost.value.trim(),
    port: Number(dbPort.value),
    user: dbUser.value.trim(),
    password: dbPassword.value,
  };
}

function validateServerForm(data) {
  if (!data.host) return "请填写主机地址";
  if (!data.port || Number.isNaN(data.port)) return "请填写正确的端口";
  if (!data.user) return "请填写用户名";
  if (!data.password) return "请填写密码";
  return "";
}

function validateConnectionForm(data) {
  const serverError = validateServerForm(data);
  if (!data.alias) return "请填写连接名称";
  if (serverError) return serverError;
  if (!data.database) return "请先查询并选择数据库";
  return "";
}

function clearDiscoveredDatabases() {
  dbName.innerHTML = `<option value="">请先查询数据库</option>`;
  dbNameGroup.classList.add("hidden");
}

function renderDiscoveredDatabases(databases) {
  dbName.innerHTML = "";

  if (!databases.length) {
    dbName.innerHTML = `<option value="">当前账号没有可用数据库</option>`;
    dbNameGroup.classList.remove("hidden");
    return;
  }

  databases.forEach((name) => {
    const option = document.createElement("option");
    option.value = name;
    option.textContent = name;
    dbName.appendChild(option);
  });

  dbNameGroup.classList.remove("hidden");
}

function clearConnectionForm() {
  dbForm.reset();
  dbPort.value = "3306";
  clearDiscoveredDatabases();
  setDbStatus("请先填写连接信息并查询数据库。");
}

async function discoverDatabases() {
  const data = getServerFormData();
  const errorMessage = validateServerForm(data);

  if (errorMessage) {
    setDbStatus(errorMessage, "error");
    return;
  }

  testDbBtn.disabled = true;
  setDbStatus("正在查询可用数据库...", "normal");
  clearDiscoveredDatabases();

  try {
    const result = await postJson(`${API_BASE_URL}/databases/discover_databases`, data);
    const databases = Array.isArray(result.databases) ? result.databases : [];

    renderDiscoveredDatabases(databases);

    if (databases.length) {
      const versionText = result.server_info ? `，版本：${result.server_info}` : "";
      setDbStatus(`查询成功，发现 ${databases.length} 个可用数据库${versionText}`, "success");
      showToast("数据库列表获取成功");
    } else {
      setDbStatus("连接成功，但当前账号没有可用业务数据库。", "error");
      showToast("没有可用数据库");
    }
  } catch (error) {
    setDbStatus(`查询数据库失败：${error.message}`, "error");
    showToast("数据库列表获取失败");
  } finally {
    testDbBtn.disabled = false;
  }
}

async function saveConnection(event) {
  event.preventDefault();

  const data = getFormData();
  const errorMessage = validateConnectionForm(data);

  if (errorMessage) {
    setDbStatus(errorMessage, "error");
    return;
  }

  saveDbBtn.disabled = true;
  setDbStatus("正在保存连接配置...", "normal");

  try {
    const result = await postJson(`${API_BASE_URL}/databases/save`, data);
    const savedConnection = result.connection;

    if (!savedConnection || !savedConnection.id) {
      throw new Error("后端没有返回连接 ID");
    }

    connectionDetailCache.set(savedConnection.id, {
      ...data,
      id: savedConnection.id,
      database_name: savedConnection.database_name,
    });

    databaseConnections = [
      savedConnection,
      ...databaseConnections.filter(
        (item) => item.id !== savedConnection.id && item.alias !== savedConnection.alias
      ),
    ];

    renderDatabaseOptions();
    databaseSelect.value = savedConnection.id;

    showToast("数据库连接配置已保存");
    clearConnectionForm();
    showManageConnectionsView();
    await loadManagedConnections();
  } catch (error) {
    setDbStatus(`保存失败：${error.message}`, "error");
    showToast("数据库连接配置保存失败");
  } finally {
    saveDbBtn.disabled = false;
  }
}

/* =========================
   Toast
========================= */

function showToast(message) {
  toast.textContent = message;
  toast.classList.remove("hidden");

  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    toast.classList.add("hidden");
  }, 2800);
}

/* =========================
   页面切换
========================= */

function setSidebarCollapsed(collapsed) {
  isSidebarCollapsed = collapsed;
  appShell.classList.toggle("sidebar-collapsed", collapsed);
  brandLogo.src = collapsed ? LOGO_MARK_SRC : LOGO_FULL_SRC;
  brandHomeBtn.setAttribute("aria-label", collapsed ? "展开边栏" : "返回首页");
  brandHomeBtn.title = collapsed ? "展开边栏" : "返回首页";
  sidebarCollapseBtn.setAttribute("aria-expanded", String(!collapsed));
}

function setProgressCollapsed(collapsed) {
  isProgressCollapsed = collapsed;
  progressSection.classList.toggle("collapsed", collapsed);
  progressToggleBtn.setAttribute("aria-expanded", String(!collapsed));
  progressToggleBtn.setAttribute("aria-label", collapsed ? "展开执行进度" : "收起执行进度");
}

function isTaskFinishedForReport(task, stage) {
  const status = task?.status;
  return status === "succeeded" || status === "failed" || stage === "finished";
}

function handleBrandClick() {
  if (isSidebarCollapsed) {
    setSidebarCollapsed(false);
    return;
  }

  showHomeView();
}

function showHomeView() {
  currentTaskId = null;
  stopTaskPolling();
  stopTaskEvents();
  liveTaskSteps = [];

  queryInput.value = "";
  charCounter.textContent = "0 / 2000";

  heroSection.classList.remove("hidden");
  featureStrip.classList.remove("hidden");
  taskView.classList.add("hidden");

  clearActiveTaskCard();
}

function showTaskView() {
  heroSection.classList.add("hidden");
  featureStrip.classList.add("hidden");
  taskView.classList.remove("hidden");
}

/* =========================
   任务列表
========================= */

function normalizeTask(raw) {
  const stage =
    raw.stage ||
    (raw.current_stage && raw.current_stage !== "waiting" ? raw.current_stage : "") ||
    raw.current_stage ||
    "";

  return {
    id: raw.id || raw.task_id,
    title: raw.title || raw.question || "未命名分析任务",
    question: raw.question || "",
    status: raw.status || "pending",
    current_stage: stage,
    stage,
    message: raw.message || "",
    created_at: raw.created_at || "",
    updated_at: raw.updated_at || "",
  };
}

function getStatusText(status) {
  const map = {
    pending: "等待中",
    running: "执行中",
    succeeded: "已完成",
    failed: "失败",
    cancelled: "已取消",
    created: "已创建",
  };
  return map[status] || status || "-";
}

function getStatusClass(status) {
  if (status === "succeeded") return "success";
  if (status === "failed") return "error";
  if (status === "running") return "running";
  if (status === "pending" || status === "created") return "pending";
  return "normal";
}

function formatTime(value) {
  if (!value) return "-";

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;

  const year = date.getFullYear();
  const month = `${date.getMonth() + 1}`.padStart(2, "0");
  const day = `${date.getDate()}`.padStart(2, "0");
  const hour = `${date.getHours()}`.padStart(2, "0");
  const minute = `${date.getMinutes()}`.padStart(2, "0");

  return `${year}-${month}-${day} ${hour}:${minute}`;
}

function clearActiveTaskCard() {
  document.querySelectorAll(".history-card").forEach((card) => {
    card.classList.remove("active");
  });
}

function setActiveTaskCard(taskId) {
  clearActiveTaskCard();
  const card = document.querySelector(`.history-card[data-task-id="${taskId}"]`);
  if (card) {
    card.classList.add("active");
  }
}

function renderTaskList(tasks) {
  historyList.innerHTML = "";

  if (!tasks || tasks.length === 0) {
    const empty = document.createElement("div");
    empty.className = "history-empty";
    empty.textContent = "暂无分析任务";
    historyList.appendChild(empty);
    return;
  }

  tasks.forEach((rawTask) => {
    const task = normalizeTask(rawTask);

    const card = document.createElement("article");
    card.className = "history-card";
    card.dataset.taskId = task.id;

    card.innerHTML = `
      <span class="file-icon">▤</span>
      <div class="history-info">
        <strong title="${escapeHtml(task.title)}">${escapeHtml(task.title)}</strong>
        <span>${formatTime(task.created_at)}</span>
        <em class="history-status ${getStatusClass(task.status)}">${getStatusText(task.status)}</em>
      </div>
      <button type="button" class="history-delete" aria-label="删除历史报告" title="删除历史报告">${TRASH_ICON}</button>
    `;

    card.addEventListener("click", (event) => {
      const deleteButton = event.target.closest(".history-delete");
      if (deleteButton) {
        event.stopPropagation();
        deleteAnalysisTask(task.id, task.title);
        return;
      }

      selectTask(task.id);
    });

    historyList.appendChild(card);
  });

  if (currentTaskId) {
    setActiveTaskCard(currentTaskId);
  }
}

async function loadTaskList() {
  try {
    const result = await getJson(`${API_BASE_URL}/analyst_task/tasks_list`);
    const tasks = result.tasks || result.data || [];
    renderTaskList(tasks);
  } catch (error) {
    historyList.innerHTML = `<div class="history-empty error">任务列表加载失败</div>`;
    console.error("任务列表加载失败：", error);
  }
}

async function deleteAnalysisTask(taskId, title) {
  const confirmed = window.confirm(`确定删除历史报告「${title || taskId}」吗？`);
  if (!confirmed) return;

  try {
    await deleteJson(`${API_BASE_URL}/analyst_task/tasks_info/${taskId}`);
    showToast("历史报告已删除");

    if (currentTaskId === taskId) {
      showHomeView();
    }

    await loadTaskList();
  } catch (error) {
    showToast(`删除历史报告失败：${error.message}`);
  }
}

/* =========================
   创建任务
========================= */

async function createAnalyzeTask() {
  const question = queryInput.value.trim();

  if (!question) {
    showToast("请先输入数据分析需求");
    queryInput.focus();
    return;
  }

  const selectedConnection = getSelectedConnection();
  if (!selectedConnection) {
    showToast("请先保存并选择一个数据库连接");
    openModal();
    return;
  }

  startAnalyzeBtn.disabled = true;
  startAnalyzeBtn.innerHTML = "<span>⌛</span><span>正在创建任务</span>";

  try {
    const result = await postJson(`${API_BASE_URL}/analyst_task/create_task`, {
      question,
      connection_id: selectedConnection.id,
      scene: "general",
      report_depth: "standard",
    });

    const taskId = result.task_id || result.id || (result.task && (result.task.id || result.task.task_id));

    showToast(`分析任务创建成功：${taskId}`);

    await loadTaskList();

    if (taskId) {
      await selectTask(taskId);
    }
  } catch (error) {
    showToast(`创建分析任务失败：${error.message}`);
  } finally {
    startAnalyzeBtn.disabled = false;
    startAnalyzeBtn.innerHTML = "<span>✦</span><span>开始分析</span>";
  }
}

/* =========================
   任务详情
========================= */

function normalizeTaskDetail(result) {
  return {
    task: result.task || result.data?.task || result,
    steps: result.steps || result.data?.steps || [],
    query_result: result.query_result || result.data?.query_result || null,
    report: result.report || result.data?.report || null,
    artifacts: result.artifacts || result.data?.artifacts || [],
  };
}

async function selectTask(taskId) {
  if (!taskId) return;

  stopTaskEvents();
  stopTaskPolling();
  currentTaskId = taskId;
  liveTaskSteps = [];
  setActiveTaskCard(taskId);
  showTaskView();

  renderLoadingTaskDetail();

  try {
    const detail = await loadTaskDetail(taskId);
    const task = normalizeTask(detail.task || {});
    const stage = detail.task?.stage || detail.task?.current_stage;
    if (!isTaskFinishedForReport(task, stage)) {
      startTaskEvents(taskId);
    }
  } catch (error) {
    showToast(`任务详情加载失败：${error.message}`);
    console.error("任务详情加载失败：", error);
  }
}

async function loadTaskDetail(taskId) {
  const result = await getJson(`${API_BASE_URL}/analyst_task/tasks_info/${taskId}`);
  const detail = normalizeTaskDetail(result);

  renderTaskDetail(detail, { preserveLiveSteps: Boolean(taskEventSource) });

  const status = detail.task?.status;
  const stage = detail.task?.stage || detail.task?.current_stage;

  if (
    status === "succeeded" ||
    status === "failed" ||
    status === "cancelled" ||
    stage === "finished"
  ) {
    stopTaskPolling();
    stopTaskEvents();
  }
  return detail;
}

function renderLoadingTaskDetail() {
  taskTitle.textContent = "正在加载任务...";
  taskQuestion.textContent = "-";
  taskStatus.textContent = "-";
  taskStage.textContent = "-";
  taskUpdatedAt.textContent = "-";
  stepsList.innerHTML = `<div class="empty-block">正在加载步骤信息...</div>`;
  reportSection.classList.add("hidden");
  reportContent.innerHTML = "";
  currentReportMarkdown = "";
  reportDownloadPdfBtn.classList.add("hidden");
}

function renderTaskDetail(detail, options = {}) {
  const rawTask = detail.task || {};
  const task = normalizeTask(rawTask);

  const sourceSteps = detail.steps && detail.steps.length > 0
    ? detail.steps
    : buildStepsFromTask(rawTask);
  if (!options.preserveLiveSteps || liveTaskSteps.length === 0) {
    liveTaskSteps = cloneSteps(sourceSteps);
  }
  const steps = options.preserveLiveSteps && liveTaskSteps.length > 0
    ? liveTaskSteps
    : sourceSteps;

  const report = detail.report || buildReportFromTask(rawTask);

  taskTitle.textContent = task.title;
  taskQuestion.textContent = task.question || "暂无任务问题";
  taskStatus.textContent = getStatusText(task.status);
  taskStatus.className = getStatusClass(task.status);
  taskStage.textContent = task.message || task.current_stage || "暂无当前阶段";
  taskUpdatedAt.textContent = `更新时间：${formatTime(task.updated_at || rawTask.finished_at || rawTask.created_at)}`;

  renderSteps(steps);

  if (isTaskFinishedForReport(task, rawTask.stage || rawTask.current_stage)) {
    reportSection.classList.remove("hidden");
    renderReport(report, task.status);
  } else {
    reportSection.classList.add("hidden");
    reportContent.innerHTML = "";
    currentReportMarkdown = "";
    reportDownloadPdfBtn.classList.add("hidden");
  }

}

function renderSteps(steps) {
  stepsList.innerHTML = "";

  if (!steps || steps.length === 0) {
    stepsList.innerHTML = `<div class="empty-block">暂无步骤信息</div>`;
    return;
  }

  steps
    .slice()
    .sort((a, b) => (a.step_order || 0) - (b.step_order || 0))
    .forEach((step, index) => {
      const item = document.createElement("article");
      const stepKey = getStepKey(step, index);
      const isSummaryExpanded = !collapsedStepSummaries.has(stepKey);
      item.className = `step-item ${getStatusClass(step.status)}${isSummaryExpanded ? " summary-expanded" : ""}`;
      item.dataset.stepKey = stepKey;
      item.dataset.stepOrder = String(step.step_order || "");
      item.dataset.stepName = step.step_name || "";

      const summary = step.output_summary || step.input_summary || "暂无阶段摘要";

      item.innerHTML = `
        <div class="step-index">${step.step_order || "-"}</div>
        <div class="step-body">
          <div class="step-top">
            <div class="step-name-row">
              <strong>${escapeHtml(step.step_title || step.step_name || "未命名步骤")}</strong>
              <button
                class="step-summary-toggle"
                type="button"
                aria-label="${isSummaryExpanded ? "收起总结" : "展开完整总结"}"
                aria-expanded="${isSummaryExpanded}"
                title="${isSummaryExpanded ? "收起总结" : "展开完整总结"}"
              ></button>
            </div>
            <span>${getStatusText(step.status)}</span>
          </div>
          <div class="step-summary markdown-content">${simpleMarkdownToHtml(summary)}</div>
          <div class="step-extra">${renderStepExtraHtml(step)}</div>
          ${step.error_message ? `<div class="step-error">${escapeHtml(step.error_message)}</div>` : ""}
        </div>
      `;

      item.querySelector(".step-summary-toggle").addEventListener("click", (event) => {
        event.stopPropagation();
        if (collapsedStepSummaries.has(stepKey)) {
          collapsedStepSummaries.delete(stepKey);
          item.classList.add("summary-expanded");
          event.currentTarget.setAttribute("aria-expanded", "true");
          event.currentTarget.setAttribute("aria-label", "收起总结");
          event.currentTarget.title = "收起总结";
        } else {
          collapsedStepSummaries.add(stepKey);
          item.classList.remove("summary-expanded");
          event.currentTarget.setAttribute("aria-expanded", "false");
          event.currentTarget.setAttribute("aria-label", "展开完整总结");
          event.currentTarget.title = "展开完整总结";
        }
      });

      stepsList.appendChild(item);
    });

  requestAnimationFrame(updateStepSummaryToggles);
}

function getStepOutput(step) {
  if (!step || !step.output_json) return null;
  return typeof step.output_json === "string"
    ? safeParseJson(step.output_json)
    : step.output_json;
}

function getStepSql(step) {
  if (!step || step.step_name !== "sql_engineer") return "";
  const output = getStepOutput(step);
  return output && output.sql ? String(output.sql).trim() : "";
}

function renderStepExtraHtml(step) {
  const sql = getStepSql(step);
  if (!sql) return "";

  return `
    <div class="step-sql">
      <div class="step-sql-title">本次生成 SQL</div>
      <pre class="step-sql-block"><code>${escapeHtml(sql)}</code></pre>
    </div>
  `;
}

function getStepKey(step, index = 0) {
  return `${currentTaskId || "task"}-${step.step_order || index}-${step.step_name || step.step_title || "step"}`;
}

function updateRenderedStep(step) {
  const item = step.step_order
    ? stepsList.querySelector(`[data-step-order="${step.step_order}"]`)
    : stepsList.querySelector(`[data-step-name="${step.step_name || ""}"]`);
  if (!item) {
    return false;
  }

  const stepKey = item.dataset.stepKey || getStepKey(step);
  const isSummaryExpanded = !collapsedStepSummaries.has(stepKey);
  item.className = `step-item ${getStatusClass(step.status)}${isSummaryExpanded ? " summary-expanded" : ""}`;
  item.dataset.stepKey = stepKey;
  item.dataset.stepOrder = String(step.step_order || "");
  item.dataset.stepName = step.step_name || "";

  const index = item.querySelector(".step-index");
  if (index) {
    index.textContent = step.step_order || "-";
  }

  const title = item.querySelector(".step-name-row strong");
  if (title) {
    title.textContent = step.step_title || step.step_name || "未命名步骤";
  }

  const status = item.querySelector(".step-top > span");
  if (status) {
    status.textContent = getStatusText(step.status);
  }

  const summary = item.querySelector(".step-summary");
  if (summary) {
    summary.innerHTML = simpleMarkdownToHtml(step.output_summary || step.input_summary || "暂无阶段摘要");
  }

  const extra = item.querySelector(".step-extra");
  if (extra) {
    extra.innerHTML = renderStepExtraHtml(step);
  }

  const body = item.querySelector(".step-body");
  let error = item.querySelector(".step-error");
  if (step.error_message) {
    if (!error && body) {
      error = document.createElement("div");
      error.className = "step-error";
      body.appendChild(error);
    }
    if (error) {
      error.textContent = step.error_message;
    }
  } else if (error) {
    error.remove();
  }

  requestAnimationFrame(updateStepSummaryToggles);
  return true;
}

function updateStepSummaryToggles() {
  stepsList.querySelectorAll(".step-item").forEach((item) => {
    const summary = item.querySelector(".step-summary");
    const toggle = item.querySelector(".step-summary-toggle");
    if (!summary || !toggle) return;

    const isExpanded = item.classList.contains("summary-expanded");
    const stepKey = item.dataset.stepKey || "";
    if (isExpanded) {
      item.classList.add("summary-toggle-visible");
      return;
    }

    const needsToggle = summary.scrollHeight > summary.clientHeight + 2;
    item.classList.toggle("summary-toggle-visible", needsToggle || collapsedStepSummaries.has(stepKey));
  });
}

function renderReport(report, taskStatusValue) {
  if (!report || !report.markdown_content) {
    const text = taskStatusValue === "succeeded"
      ? "任务已完成，但后端暂未返回报告内容。"
      : "任务完成后将在这里展示 Markdown 报告。";

    reportContent.innerHTML = `<div class="empty-block">${text}</div>`;
    currentReportMarkdown = "";
    reportDownloadPdfBtn.classList.add("hidden");
    return;
  }

  currentReportMarkdown = report.markdown_content;
  reportContent.innerHTML = simpleMarkdownToHtml(report.markdown_content);
  reportDownloadPdfBtn.classList.remove("hidden");
}

function downloadReportPdf() {
  if (!currentReportMarkdown || !reportContent.innerHTML.trim()) {
    showToast("当前没有可下载的报告内容");
    return;
  }

  const printWindow = window.open("", "_blank");
  if (!printWindow) {
    showToast("浏览器阻止了下载窗口，请允许弹出窗口后重试");
    return;
  }

  const reportTitleText = taskTitle.textContent || "DeepInsight 分析报告";
  const html = `
    <!doctype html>
    <html lang="zh-CN">
      <head>
        <meta charset="utf-8" />
        <title>${escapeHtml(reportTitleText)}</title>
        <style>
          @page { size: A4; margin: 16mm 14mm; }
          body {
            margin: 0;
            color: #172b52;
            font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", Arial, sans-serif;
            font-size: 13px;
            line-height: 1.72;
            background: #fff;
          }
          h1, h2, h3, h4 { color: #0f2d63; page-break-after: avoid; }
          h1 { font-size: 24px; margin: 0 0 14px; }
          h2 { font-size: 19px; margin: 20px 0 10px; }
          h3 { font-size: 16px; margin: 16px 0 8px; }
          p { margin: 8px 0; }
          table { width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 11px; page-break-inside: avoid; }
          th, td { border: 1px solid #d9e3f2; padding: 7px 8px; text-align: left; vertical-align: top; }
          th { background: #f2f6fc; color: #0f2d63; }
          img { display: block; max-width: 100%; max-height: 150mm; object-fit: contain; page-break-inside: avoid; }
          figure { margin: 14px 0; page-break-inside: avoid; }
          figcaption { margin-top: 6px; color: #5e6f89; font-size: 11px; }
          blockquote { margin: 10px 0; padding: 8px 12px; border-left: 3px solid #9fc4ff; background: #f7faff; color: #4d607d; }
          code { padding: 1px 4px; border-radius: 4px; background: #edf4ff; color: #0f3f8c; }
          .pdf-header { margin-bottom: 18px; padding-bottom: 10px; border-bottom: 1px solid #dce6f5; }
          .pdf-subtitle { margin: 0; color: #64748b; font-size: 12px; }
        </style>
      </head>
      <body>
        <section class="pdf-header">
          <h1>${escapeHtml(reportTitleText)}</h1>
          <p class="pdf-subtitle">${escapeHtml(taskQuestion.textContent || "")}</p>
        </section>
        <main>${reportContent.innerHTML}</main>
      </body>
    </html>
  `;

  printWindow.document.open();
  printWindow.document.write(html);
  printWindow.document.close();

  const triggerPrint = () => {
    const images = Array.from(printWindow.document.images || []);
    Promise.all(
      images.map((image) => {
        if (image.complete) return Promise.resolve();
        return new Promise((resolve) => {
          image.onload = resolve;
          image.onerror = resolve;
        });
      })
    ).then(() => {
      printWindow.focus();
      printWindow.print();
    });
  };

  if (printWindow.document.readyState === "complete") {
    triggerPrint();
  } else {
    printWindow.onload = triggerPrint;
  }
}

/* =========================
   SSE 实时事件
========================= */

function startTaskEvents(taskId) {
  stopTaskEvents();

  if (!window.EventSource) {
    console.error("当前浏览器不支持 EventSource，无法使用 SSE 实时更新。");
    return;
  }

  taskEventSourceClosedExpected = false;
  taskEventSource = new EventSource(`${API_BASE_URL}/analyst_task/tasks_info/${taskId}/events`);

  taskEventSource.addEventListener("task_started", handleTaskEvent);
  taskEventSource.addEventListener("node_started", handleTaskEvent);
  taskEventSource.addEventListener("agent_delta", handleTaskEvent);
  taskEventSource.addEventListener("agent_message", handleTaskEvent);
  taskEventSource.addEventListener("node_finished", handleTaskEvent);
  taskEventSource.addEventListener("node_failed", handleTaskEvent);
  taskEventSource.addEventListener("task_finished", handleTaskEvent);
  taskEventSource.addEventListener("task_failed", handleTaskEvent);
  taskEventSource.addEventListener("task_cancelled", handleTaskEvent);

  taskEventSource.onerror = () => {
    if (taskEventSourceClosedExpected || !currentTaskId || currentTaskId !== taskId) {
      return;
    }
    console.error("SSE 连接异常，已停止实时更新。");
    stopTaskEvents();
  };
}

function stopTaskEvents() {
  taskEventSourceClosedExpected = true;
  if (taskEventSource) {
    taskEventSource.close();
    taskEventSource = null;
  }
}

async function handleTaskEvent(event) {
  const data = parseSseData(event.data);
  if (!data || data.task_id !== currentTaskId) {
    return;
  }

  if (data.type === "task_started") {
    updateTaskHeaderStatus("running", data.message || "后台分析流程已启动。");
    return;
  }

  if (data.type === "node_started") {
    updateTaskHeaderStatus("running", data.summary || data.title || "节点开始执行。");
    upsertLiveStep(data.node, {
      step_number: data.step_number,
      status: "running",
      step_title: data.title,
      output_summary: data.summary || data.title || "",
    });
    return;
  }

  if (data.type === "agent_delta" || data.type === "agent_message") {
    if (data.node === "report_writer") {
      return;
    }
    upsertLiveStep(data.node, {
      step_number: data.step_number,
      status: "running",
      step_title: data.title,
      output_summary: data.summary || "",
    });
    return;
  }

  if (data.type === "node_finished") {
    upsertLiveStep(data.node, {
      step_number: data.step_number,
      status: "succeeded",
      step_title: data.title,
      output_summary: data.summary || "",
      output_json: data.output || null,
    });
    return;
  }

  if (data.type === "node_failed") {
    updateTaskHeaderStatus("failed", data.error || "节点执行失败。");
    upsertLiveStep(data.node, {
      step_number: data.step_number,
      status: "failed",
      step_title: data.title,
      error_message: data.error || "节点执行失败。",
    });
    return;
  }

  if (data.type === "task_finished") {
    updateTaskHeaderStatus("succeeded", data.message || "分析任务执行完成。");
    taskEventSourceClosedExpected = true;
    stopTaskEvents();
    await refreshFinalTaskDetail(data.task_id);
    return;
  }

  if (data.type === "task_failed" || data.type === "task_cancelled") {
    updateTaskHeaderStatus(data.type === "task_failed" ? "failed" : "cancelled", data.message || "");
    taskEventSourceClosedExpected = true;
    stopTaskEvents();
    await refreshFinalTaskDetail(data.task_id);
  }
}

function parseSseData(rawData) {
  try {
    return JSON.parse(rawData);
  } catch (error) {
    console.error("SSE 事件解析失败：", error, rawData);
    return null;
  }
}

function updateTaskHeaderStatus(status, message) {
  taskStatus.textContent = getStatusText(status);
  taskStatus.className = getStatusClass(status);
  if (message) {
    taskStage.textContent = message;
  }
  taskUpdatedAt.textContent = `更新时间：${formatTime(new Date().toISOString())}`;
}

function upsertLiveStep(nodeName, patch) {
  if (!nodeName) return;

  const runtimeStepNumber = Number(patch.step_number || 0) || null;
  const stepOrder = runtimeStepNumber || STAGE_ORDER_MAP[nodeName] || liveTaskSteps.length + 1;
  const stepTitle = patch.step_title || STAGE_TITLE_MAP[nodeName] || nodeName;
  const existingIndex = runtimeStepNumber
    ? liveTaskSteps.findIndex((step) => Number(step.step_order) === runtimeStepNumber)
    : liveTaskSteps.findIndex((step) => step.step_name === nodeName);
  const nextStep = {
    step_order: stepOrder,
    step_name: nodeName,
    step_title: stepTitle,
    status: "running",
    input_summary: "",
    output_summary: "",
    output_json: null,
    error_message: null,
    ...(existingIndex >= 0 ? liveTaskSteps[existingIndex] : {}),
    ...patch,
    step_order: stepOrder,
    step_name: nodeName,
    step_title: stepTitle,
  };
  delete nextStep.step_number;

  if (existingIndex >= 0) {
    liveTaskSteps[existingIndex] = nextStep;
  } else {
    liveTaskSteps.push(nextStep);
  }

  if (!updateRenderedStep(nextStep)) {
    const previousScrollTop = stepsList.scrollTop;
    renderSteps(liveTaskSteps);
    stepsList.scrollTop = previousScrollTop;
  }
}

async function refreshFinalTaskDetail(taskId) {
  if (!taskId || currentTaskId !== taskId) return;
  try {
    liveTaskSteps = [];
    await loadTaskDetail(taskId);
    await loadTaskList();
  } catch (error) {
    console.error("刷新最终任务详情失败：", error);
  }
}

function cloneSteps(steps) {
  return (steps || []).map((step) => ({ ...step }));
}

/* =========================
   任务轮询
========================= */

function startTaskPolling(taskId) {
  stopTaskPolling();

  taskPollTimer = setInterval(async () => {
    if (!currentTaskId || currentTaskId !== taskId) {
      stopTaskPolling();
      return;
    }

    try {
      await loadTaskDetail(taskId);
      await loadTaskList();
    } catch (error) {
      console.error("轮询任务失败：", error);
    }
  }, TASK_POLL_INTERVAL);
}

function stopTaskPolling() {
  if (taskPollTimer) {
    clearInterval(taskPollTimer);
    taskPollTimer = null;
  }
}

/* =========================
   工具函数
========================= */

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function safeParseJson(value) {
  try {
    return JSON.parse(value);
  } catch (error) {
    return null;
  }
}

function buildReportFromTask(task) {
  if (!task || !task.report) {
    return null;
  }

  if (typeof task.report === "string") {
    return {
      title: task.title || "分析报告",
      summary: "",
      markdown_content: task.report,
    };
  }

  return {
    title: task.report.title || task.title || "分析报告",
    summary: task.report.summary || "",
    markdown_content:
      task.report.markdown_content ||
      task.report.markdown ||
      task.report.content ||
      JSON.stringify(task.report, null, 2),
  };
}


function buildStepsFromTask(task) {
  if (!task) return [];

  const stage = task.stage || task.current_stage || "waiting";
  const message = task.message || "任务正在执行中";

  const currentOrder = STAGE_ORDER_MAP[stage] ?? 0;

  const steps = Object.entries(STAGE_TITLE_MAP)
    .filter(([name]) => name !== "waiting")
    .map(([name, title]) => {
      const order = STAGE_ORDER_MAP[name];

      let status = "pending";
      if (task.status === "succeeded" || stage === "finished") {
        status = "succeeded";
      } else if (task.status === "failed") {
        status = order === currentOrder ? "failed" : order < currentOrder ? "succeeded" : "pending";
      } else if (order < currentOrder) {
        status = "succeeded";
      } else if (order === currentOrder) {
        status = "running";
      }

      return {
        step_order: order,
        step_name: name,
        step_title: title,
        status,
        output_summary: order === currentOrder ? message : "",
        error_message: task.error || null,
      };
    });

  return steps;
}

function simpleMarkdownToHtml(markdown) {
  const lines = String(markdown || "").replace(/\r\n/g, "\n").split("\n");
  const html = [];
  let listType = null;
  let inCodeBlock = false;
  let codeLanguage = "";
  let codeLines = [];

  const closeList = () => {
    if (listType) {
      html.push(`</${listType}>`);
      listType = null;
    }
  };

  const openList = (type) => {
    if (listType === type) return;
    closeList();
    listType = type;
    html.push(`<${type}>`);
  };

  const flushCodeBlock = () => {
    html.push(
      `<pre class="md-code-block"><code${codeLanguage ? ` class="language-${escapeHtml(codeLanguage)}"` : ""}>${escapeHtml(codeLines.join("\n"))}</code></pre>`
    );
    inCodeBlock = false;
    codeLanguage = "";
    codeLines = [];
  };

  for (let index = 0; index < lines.length; index += 1) {
    const rawLine = lines[index];
    const line = rawLine.trim();

    if (line.startsWith("```")) {
      if (inCodeBlock) {
        flushCodeBlock();
      } else {
        closeList();
        inCodeBlock = true;
        codeLanguage = line.slice(3).trim();
        codeLines = [];
      }
      continue;
    }

    if (inCodeBlock) {
      codeLines.push(rawLine);
      continue;
    }

    if (!line) {
      closeList();
      continue;
    }

    if (/^\|?.+\|.+\|?$/.test(line) && lines[index + 1] && /^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?$/.test(lines[index + 1].trim())) {
      closeList();
      const headerCells = parseMarkdownTableRow(line);
      const rows = [];
      index += 2;

      while (index < lines.length && /^\|?.+\|.+\|?$/.test(lines[index].trim())) {
        rows.push(parseMarkdownTableRow(lines[index].trim()));
        index += 1;
      }
      index -= 1;

      html.push(`
        <div class="md-table-wrap">
          <table class="md-table">
            <thead>
              <tr>${headerCells.map((cell) => `<th>${renderInlineMarkdown(cell)}</th>`).join("")}</tr>
            </thead>
            <tbody>
              ${rows.map((row) => `<tr>${headerCells.map((_, cellIndex) => `<td>${renderInlineMarkdown(row[cellIndex] || "")}</td>`).join("")}</tr>`).join("")}
            </tbody>
          </table>
        </div>
      `);
      continue;
    }

    const headingMatch = line.match(/^(#{1,6})\s+(.+)$/);
    if (headingMatch) {
      closeList();
      const level = Math.min(headingMatch[1].length, 6);
      html.push(`<h${level}>${renderInlineMarkdown(headingMatch[2])}</h${level}>`);
      continue;
    }

    if (/^---+$/.test(line)) {
      closeList();
      html.push("<hr />");
      continue;
    }

    const imageMatch = line.match(/^!\[([^\]]*)\]\(([^)]+)\)$/);
    if (imageMatch) {
      closeList();
      const alt = imageMatch[1] || "图表";
      const src = normalizeMarkdownImageSrc(imageMatch[2]);
      html.push(
        `<figure class="md-image-wrap"><img class="md-image" src="${escapeHtml(src)}" alt="${escapeHtml(alt)}" loading="lazy" /><figcaption>${escapeHtml(alt)}</figcaption></figure>`
      );
      continue;
    }

    const unorderedMatch = line.match(/^[-*+]\s+(.+)$/);
    if (unorderedMatch) {
      openList("ul");
      html.push(`<li>${renderInlineMarkdown(unorderedMatch[1])}</li>`);
      continue;
    }

    const orderedMatch = line.match(/^\d+\.\s+(.+)$/);
    if (orderedMatch) {
      openList("ol");
      html.push(`<li>${renderInlineMarkdown(orderedMatch[1])}</li>`);
      continue;
    }

    if (line.startsWith("> ")) {
      closeList();
      html.push(`<blockquote>${renderInlineMarkdown(line.slice(2))}</blockquote>`);
      continue;
    }

    closeList();
    html.push(`<p>${renderInlineMarkdown(line)}</p>`);
  }

  closeList();
  if (inCodeBlock) {
    flushCodeBlock();
  }

  return html.join("");
}

function parseMarkdownTableRow(line) {
  return line
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((cell) => cell.trim());
}

function renderInlineMarkdown(text) {
  return escapeHtml(text)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/__([^_]+)__/g, "<strong>$1</strong>")
    .replace(/\*([^*]+)\*/g, "<em>$1</em>")
    .replace(/_([^_]+)_/g, "<em>$1</em>");
}

function normalizeMarkdownImageSrc(src) {
  const rawSrc = String(src || "").trim();
  if (!rawSrc) {
    return "";
  }
  if (/^(https?:)?\/\//i.test(rawSrc) || rawSrc.startsWith("data:")) {
    return rawSrc;
  }

  const normalized = rawSrc.replace(/\\/g, "/").replace(/^\.?\//, "");
  const outputsIndex = normalized.toLowerCase().indexOf("outputs/");
  const relativePath = outputsIndex >= 0 ? normalized.slice(outputsIndex) : normalized;
  const apiOrigin = API_BASE_URL.replace(/\/api\/?$/, "");
  return `${apiOrigin}/${relativePath.split("/").map(encodeURIComponent).join("/")}`;
}

/* =========================
   事件绑定
========================= */

queryInput.addEventListener("input", () => {
  charCounter.textContent = `${queryInput.value.length} / 2000`;
});

startAnalyzeBtn.addEventListener("click", createAnalyzeTask);

openDbModalBtn.addEventListener("click", openModal);
brandHomeBtn.addEventListener("click", handleBrandClick);
sidebarCollapseBtn.addEventListener("click", () => setSidebarCollapsed(true));
progressToggleBtn.addEventListener("click", () => setProgressCollapsed(!isProgressCollapsed));
reportDownloadPdfBtn.addEventListener("click", downloadReportPdf);
closeDbModalBtn.addEventListener("click", closeModal);
addConnectionBtn.addEventListener("click", showAddConnectionView);
backToDbListBtn.addEventListener("click", showManageConnectionsView);
clearDbFormBtn.addEventListener("click", clearConnectionForm);
testDbBtn.addEventListener("click", discoverDatabases);
dbForm.addEventListener("submit", saveConnection);
dbType.addEventListener("change", updatePortByType);
[dbHost, dbPort, dbUser, dbPassword].forEach((input) => {
  input.addEventListener("input", clearDiscoveredDatabases);
});

backHomeBtn.addEventListener("click", showHomeView);

dbModal.addEventListener("click", (event) => {
  if (event.target === dbModal) {
    closeModal();
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !dbModal.classList.contains("hidden")) {
    closeModal();
  }
});

/* =========================
   初始化
========================= */

loadDatabaseConnections();
loadTaskList();
