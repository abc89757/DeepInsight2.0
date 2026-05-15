const API_BASE_URL = "http://127.0.0.1:8000/api";
const TASK_POLL_INTERVAL = 1800;

const queryInput = document.getElementById("queryInput");
const charCounter = document.getElementById("charCounter");
const startAnalyzeBtn = document.getElementById("startAnalyzeBtn");
const databaseSelect = document.getElementById("databaseSelect");
const openDbModalBtn = document.getElementById("openDbModalBtn");
const closeDbModalBtn = document.getElementById("closeDbModalBtn");
const dbModal = document.getElementById("dbModal");
const dbForm = document.getElementById("dbForm");
const testDbBtn = document.getElementById("testDbBtn");
const saveDbBtn = dbForm.querySelector("button[type='submit']");
const dbStatus = document.getElementById("dbStatus");
const toast = document.getElementById("toast");

const dbType = document.getElementById("dbType");
const dbAlias = document.getElementById("dbAlias");
const dbHost = document.getElementById("dbHost");
const dbPort = document.getElementById("dbPort");
const dbUser = document.getElementById("dbUser");
const dbPassword = document.getElementById("dbPassword");
const dbName = document.getElementById("dbName");

const historyList = document.getElementById("historyList");
const taskView = document.getElementById("taskView");
const backHomeBtn = document.getElementById("backHomeBtn");

const taskTitle = document.getElementById("taskTitle");
const taskQuestion = document.getElementById("taskQuestion");
const taskStatus = document.getElementById("taskStatus");
const taskStage = document.getElementById("taskStage");
const taskUpdatedAt = document.getElementById("taskUpdatedAt");
const stepsList = document.getElementById("stepsList");
const sqlBlock = document.getElementById("sqlBlock");
const reportContent = document.getElementById("reportContent");
const resultRowCount = document.getElementById("resultRowCount");
const resultTable = document.getElementById("resultTable");

const heroSection = document.querySelector(".hero-section");
const featureStrip = document.querySelector(".feature-strip");

let toastTimer = null;
let currentTaskId = null;
let taskPollTimer = null;
let databaseConnections = [];
const connectionDetailCache = new Map();

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
    const result = await getJson(`${API_BASE_URL}/databases/list`);
    databaseConnections = Array.isArray(result.connections) ? result.connections : [];
    renderDatabaseOptions();
  } catch (error) {
    databaseConnections = [];
    renderDatabaseOptions();
    showToast(`加载数据库连接失败：${error.message}`);
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
  dbAlias.focus();
}

function closeModal() {
  dbModal.classList.add("hidden");
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

function updatePortByType() {
  const portMap = {
    mysql: "3306",
    postgresql: "5432",
    neo4j: "7687",
  };
  dbPort.value = portMap[dbType.value] || "3306";
}

function getFormData() {
  return {
    type: dbType.value.trim(),
    alias: dbAlias.value.trim(),
    host: dbHost.value.trim(),
    port: Number(dbPort.value),
    user: dbUser.value.trim(),
    password: dbPassword.value,
    database: dbName.value.trim(),
    createdAt: new Date().toISOString(),
  };
}

function validateConnectionForm(data) {
  if (!data.alias) return "请填写连接名称";
  if (!data.host) return "请填写主机地址";
  if (!data.port || Number.isNaN(data.port)) return "请填写正确的端口";
  if (!data.user) return "请填写用户名";
  if (!data.database && data.type !== "neo4j") return "请填写数据库名";
  return "";
}

async function testConnection() {
  const data = getFormData();
  const errorMessage = validateConnectionForm(data);

  if (errorMessage) {
    setDbStatus(errorMessage, "error");
    return;
  }

  testDbBtn.disabled = true;
  setDbStatus("正在请求后端测试连接...", "normal");

  try {
    const result = await postJson(`${API_BASE_URL}/databases/test`, data);

    if (result.success) {
      const versionText = result.server_info ? `，版本：${result.server_info}` : "";
      setDbStatus(`${result.message}${versionText}`, "success");
      showToast("数据库连接测试成功");
    } else {
      setDbStatus(result.message || "连接失败", "error");
      showToast("数据库连接测试失败");
    }
  } catch (error) {
    setDbStatus(`连接测试请求失败：${error.message}`, "error");
    showToast("请确认 FastAPI 后端已经启动");
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

    setDbStatus("连接配置已保存到系统数据库。", "success");
    showToast("数据库连接配置已保存");

    setTimeout(closeModal, 620);
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

function showHomeView() {
  currentTaskId = null;
  stopTaskPolling();

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
      <button class="history-delete" aria-label="删除历史报告" title="暂未实现删除">⌫</button>
    `;

    card.addEventListener("click", (event) => {
      if (event.target.classList.contains("history-delete")) {
        event.stopPropagation();
        showToast("删除任务功能后面再接");
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

  currentTaskId = taskId;
  setActiveTaskCard(taskId);
  showTaskView();

  renderLoadingTaskDetail();

  try {
    await loadTaskDetail(taskId);
    startTaskPolling(taskId);
  } catch (error) {
    showToast(`任务详情加载失败：${error.message}`);
    console.error("任务详情加载失败：", error);
  }
}

async function loadTaskDetail(taskId) {
  const result = await getJson(`${API_BASE_URL}/analyst_task/tasks_info/${taskId}`);
  const detail = normalizeTaskDetail(result);

  renderTaskDetail(detail);

  const status = detail.task?.status;
  const stage = detail.task?.stage || detail.task?.current_stage;

  if (
    status === "succeeded" ||
    status === "failed" ||
    status === "cancelled" ||
    stage === "finished"
  ) {
    stopTaskPolling();
  }
}

function renderLoadingTaskDetail() {
  taskTitle.textContent = "正在加载任务...";
  taskQuestion.textContent = "-";
  taskStatus.textContent = "-";
  taskStage.textContent = "-";
  taskUpdatedAt.textContent = "-";
  stepsList.innerHTML = `<div class="empty-block">正在加载步骤信息...</div>`;
  sqlBlock.textContent = "正在加载 SQL...";
  reportContent.innerHTML = `<div class="empty-block">正在加载报告...</div>`;
  renderResultTable(null);
}

function renderTaskDetail(detail) {
  const rawTask = detail.task || {};
  const task = normalizeTask(rawTask);

  const steps = detail.steps && detail.steps.length > 0
    ? detail.steps
    : buildStepsFromTask(rawTask);

  const queryResult = detail.query_result || buildQueryResultFromTask(rawTask);
  const report = detail.report || buildReportFromTask(rawTask);

  taskTitle.textContent = task.title;
  taskQuestion.textContent = task.question || "暂无任务问题";
  taskStatus.textContent = getStatusText(task.status);
  taskStatus.className = getStatusClass(task.status);
  taskStage.textContent = task.message || task.current_stage || "暂无当前阶段";
  taskUpdatedAt.textContent = `更新时间：${formatTime(task.updated_at || rawTask.finished_at || rawTask.created_at)}`;

  renderSteps(steps);
  renderSql(queryResult, steps);
  renderReport(report, task.status);
  renderResultTable(queryResult);
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
    .forEach((step) => {
      const item = document.createElement("article");
      item.className = `step-item ${getStatusClass(step.status)}`;

      item.innerHTML = `
        <div class="step-index">${step.step_order || "-"}</div>
        <div class="step-body">
          <div class="step-top">
            <strong>${escapeHtml(step.step_title || step.step_name || "未命名步骤")}</strong>
            <span>${getStatusText(step.status)}</span>
          </div>
          <p>${escapeHtml(step.output_summary || step.input_summary || "暂无阶段摘要")}</p>
          ${step.error_message ? `<div class="step-error">${escapeHtml(step.error_message)}</div>` : ""}
        </div>
      `;

      stepsList.appendChild(item);
    });
}

function renderSql(queryResult, steps) {
  if (queryResult && queryResult.sql_text) {
    sqlBlock.textContent = queryResult.sql_text;
    return;
  }

  const sqlStep = steps.find((step) => {
    const name = step.step_name || "";
    return name.includes("sql");
  });

  if (sqlStep && sqlStep.output_json) {
    const output = typeof sqlStep.output_json === "string"
      ? safeParseJson(sqlStep.output_json)
      : sqlStep.output_json;

    if (output && output.sql) {
      sqlBlock.textContent = output.sql;
      return;
    }
  }

  sqlBlock.textContent = "暂无 SQL";
}

function renderReport(report, taskStatusValue) {
  if (!report || !report.markdown_content) {
    const text = taskStatusValue === "succeeded"
      ? "任务已完成，但后端暂未返回报告内容。"
      : "任务完成后将在这里展示 Markdown 报告。";

    reportContent.innerHTML = `<div class="empty-block">${text}</div>`;
    return;
  }

  reportContent.innerHTML = simpleMarkdownToHtml(report.markdown_content);
}

function renderResultTable(queryResult) {
  const thead = resultTable.querySelector("thead");
  const tbody = resultTable.querySelector("tbody");

  thead.innerHTML = "";
  tbody.innerHTML = "";

  if (!queryResult) {
    resultRowCount.textContent = "-";
    tbody.innerHTML = `<tr><td class="empty-table-cell">暂无查询结果</td></tr>`;
    return;
  }

  const columns = normalizeJsonValue(queryResult.columns_json) || [];
  const rows = normalizeJsonValue(queryResult.preview_rows_json) || [];

  resultRowCount.textContent = queryResult.row_count != null
    ? `共 ${queryResult.row_count} 行`
    : `${rows.length} 行预览`;

  if (!columns.length || !rows.length) {
    tbody.innerHTML = `<tr><td class="empty-table-cell">暂无查询结果</td></tr>`;
    return;
  }

  const headRow = document.createElement("tr");
  columns.forEach((column) => {
    const th = document.createElement("th");
    th.textContent = column;
    headRow.appendChild(th);
  });
  thead.appendChild(headRow);

  rows.forEach((row) => {
    const tr = document.createElement("tr");

    if (Array.isArray(row)) {
      row.forEach((cell) => {
        const td = document.createElement("td");
        td.textContent = cell == null ? "" : String(cell);
        tr.appendChild(td);
      });
    } else {
      columns.forEach((column) => {
        const td = document.createElement("td");
        td.textContent = row[column] == null ? "" : String(row[column]);
        tr.appendChild(td);
      });
    }

    tbody.appendChild(tr);
  });
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

function normalizeJsonValue(value) {
  if (!value) return null;
  if (typeof value === "string") return safeParseJson(value);
  return value;
}

function buildQueryResultFromTask(task) {
  if (!task) return null;

  const sql = task.sql;
  const rows = task.result_preview || [];

  if (!sql && (!rows || rows.length === 0)) {
    return null;
  }

  let columns = [];

  if (rows.length > 0) {
    const firstRow = rows[0];

    if (Array.isArray(firstRow)) {
      columns = firstRow.map((_, index) => `col_${index + 1}`);
    } else if (typeof firstRow === "object" && firstRow !== null) {
      columns = Object.keys(firstRow);
    }
  }

  return {
    sql_text: sql || "",
    columns_json: columns,
    preview_rows_json: rows,
    row_count: task.result_row_count ?? rows.length,
    preview_row_count: rows.length,
  };
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

  const stageOrderMap = {
    waiting: 0,
    database_precheck: 1,
    load_schema: 2,
    understand_question: 3,
    plan_query: 4,
    generate_sql: 5,
    audit_sql: 6,
    execute_sql: 7,
    analyze_result: 8,
    generate_report: 9,
    finished: 10,
  };

  const stageTitleMap = {
    waiting: "等待执行",
    database_precheck: "数据库连接检查",
    load_schema: "读取数据库 Schema",
    understand_question: "需求理解",
    plan_query: "规划查询任务",
    generate_sql: "生成 SQL",
    audit_sql: "SQL 审计",
    execute_sql: "执行 SQL",
    analyze_result: "数据分析",
    generate_report: "生成报告",
    finished: "任务完成",
  };

  const currentOrder = stageOrderMap[stage] ?? 0;

  const steps = Object.entries(stageTitleMap)
    .filter(([name]) => name !== "waiting")
    .map(([name, title]) => {
      const order = stageOrderMap[name];

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
  const escaped = escapeHtml(markdown);

  return escaped
    .split("\n")
    .map((line) => {
      if (line.startsWith("### ")) {
        return `<h3>${line.slice(4)}</h3>`;
      }

      if (line.startsWith("## ")) {
        return `<h2>${line.slice(3)}</h2>`;
      }

      if (line.startsWith("# ")) {
        return `<h1>${line.slice(2)}</h1>`;
      }

      if (line.startsWith("- ")) {
        return `<p class="md-list-item">• ${line.slice(2)}</p>`;
      }

      if (!line.trim()) {
        return `<br />`;
      }

      return `<p>${line}</p>`;
    })
    .join("");
}

/* =========================
   事件绑定
========================= */

queryInput.addEventListener("input", () => {
  charCounter.textContent = `${queryInput.value.length} / 2000`;
});

startAnalyzeBtn.addEventListener("click", createAnalyzeTask);

openDbModalBtn.addEventListener("click", openModal);
closeDbModalBtn.addEventListener("click", closeModal);
testDbBtn.addEventListener("click", testConnection);
dbForm.addEventListener("submit", saveConnection);
dbType.addEventListener("change", updatePortByType);

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
