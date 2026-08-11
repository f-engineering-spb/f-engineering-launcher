const state = {
  objects: [],
  selectedObjectId: null,
  currentManifest: null,
  activeFilter: "",
  selectedPaths: new Set(),
  lastSelectedIndex: null,
  visibleRows: [],
  collapsedFolders: new Set(),
  progressTimer: null,
  progressCancelled: false,
  operationController: null,
};

const els = {
  load: document.getElementById("loadObject"),
  refresh: document.getElementById("refreshObject"),
  display: document.getElementById("displayObject"),
  exclude: document.getElementById("excludeObject"),
  cancel: document.getElementById("cancelOperation"),
  path: document.getElementById("objectPath"),
  progressPanel: document.getElementById("progressPanel"),
  progressLabel: document.getElementById("progressLabel"),
  progressValue: document.getElementById("progressValue"),
  progressFill: document.getElementById("progressFill"),
  progressDetail: document.getElementById("progressDetail"),
  objectListState: document.getElementById("objectListState"),
  treeState: document.getElementById("treeState"),
  objectList: document.getElementById("objectList"),
  objectStats: document.getElementById("objectStats"),
  backToObjects: document.getElementById("backToObjects"),
  treeSearch: document.getElementById("treeSearch"),
  formatStrip: document.getElementById("formatStrip"),
  selectionSummary: document.getElementById("selectionSummary"),
  objectTree: document.getElementById("objectTree"),
};

function text(value, fallback = "") {
  return value == null ? fallback : String(value);
}

function formatExtensions(extensions = {}) {
  const entries = Object.entries(extensions).sort((left, right) => left[0].localeCompare(right[0], "ru"));
  return entries.length ? entries.map(([ext, count]) => `${ext}: ${count}`).join(" · ") : "форматов нет";
}

function selectedObject() {
  return state.objects.find((item) => item.id === state.selectedObjectId) || null;
}

function inTreeMode() {
  return els.treeState.classList.contains("active");
}

function setMode(mode) {
  els.objectListState.classList.toggle("active", mode === "objects");
  els.treeState.classList.toggle("active", mode === "tree");
  updateObjectButtons();
}

function updateObjectButtons() {
  const hasSelection = Boolean(state.selectedObjectId);
  const tree = inTreeMode();
  els.load.disabled = tree;
  els.refresh.disabled = !hasSelection;
  els.display.disabled = !hasSelection && !tree;
  els.exclude.disabled = tree || !hasSelection;
}

function updateObjectStats() {
  const object = selectedObject();
  if (!object) {
    els.objectStats.textContent = "Объект не выбран";
    return;
  }
  els.objectStats.innerHTML = [
    `<strong>${text(object.name)}</strong>`,
    `Папок: ${object.statistics?.folders || 0}`,
    `Файлов: ${object.statistics?.files || 0}`,
    formatExtensions(object.statistics?.extensions || {}),
    text(object.rootPath),
  ].join("<br>");
}

function renderObjectList() {
  els.objectList.replaceChildren();
  if (!state.objects.length) {
    const empty = document.createElement("div");
    empty.className = "empty-note";
    empty.textContent = "Объекты ещё не загружены.";
    els.objectList.append(empty);
    updateObjectStats();
    updateObjectButtons();
    return;
  }

  state.objects.forEach((object) => {
    const row = document.createElement("div");
    row.className = "object-row";
    row.classList.toggle("selected", object.id === state.selectedObjectId);
    row.title = object.rootPath;

    const title = document.createElement("strong");
    title.textContent = object.name;
    const meta = document.createElement("span");
    meta.textContent = `${object.statistics?.files || 0} файлов · ${object.rootPath}`;
    row.append(title, meta);

    row.addEventListener("click", (event) => {
      event.stopPropagation();
      state.selectedObjectId = state.selectedObjectId === object.id ? null : object.id;
      renderObjectList();
    });
    row.addEventListener("dblclick", (event) => {
      event.stopPropagation();
      state.selectedObjectId = object.id;
      openSelectedObject().catch(showOperationError);
    });
    els.objectList.append(row);
  });
  updateObjectStats();
  updateObjectButtons();
}

async function loadObjectSummaries() {
  const response = await fetch("/api/objects");
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "Список объектов не получен");
  state.objects = payload.items || [];
  if (state.selectedObjectId && !state.objects.some((item) => item.id === state.selectedObjectId)) {
    state.selectedObjectId = null;
  }
  renderObjectList();
}

function createOperationController() {
  if (state.operationController) state.operationController.abort();
  state.operationController = new AbortController();
  return state.operationController;
}

function startProgress(label, detail) {
  stopProgress(false, false);
  state.progressCancelled = false;
  let value = 0;
  els.progressPanel.hidden = false;
  els.progressLabel.textContent = label;
  els.progressDetail.textContent = detail;
  els.progressValue.textContent = "0%";
  els.progressFill.style.width = "0%";
  state.progressTimer = setInterval(() => {
    value = Math.min(92, value + Math.max(1, Math.round((95 - value) / 9)));
    els.progressValue.textContent = `${value}%`;
    els.progressFill.style.width = `${value}%`;
  }, 180);
}

function finishProgress(detail = "Готово") {
  if (state.progressTimer) clearInterval(state.progressTimer);
  state.progressTimer = null;
  state.operationController = null;
  els.progressDetail.textContent = detail;
  els.progressValue.textContent = "100%";
  els.progressFill.style.width = "100%";
  setTimeout(() => {
    if (!state.progressTimer) els.progressPanel.hidden = true;
  }, 350);
}

function stopProgress(cancelled = true, abortRequest = true) {
  if (state.progressTimer) clearInterval(state.progressTimer);
  state.progressTimer = null;
  state.progressCancelled = cancelled;
  if (abortRequest && state.operationController) {
    state.operationController.abort();
    state.operationController = null;
  }
  els.progressPanel.hidden = true;
}

function showOperationError(error) {
  if (error?.name === "AbortError") return;
  finishProgress(`Ошибка: ${error.message || error}`);
}

async function chooseFolderPath() {
  const typed = els.path.value.trim();
  if (typed) return typed;
  const controller = createOperationController();
  const response = await fetch("/api/choose-folder", { method: "POST", signal: controller.signal });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "Не удалось выбрать папку");
  return payload.path || "";
}

async function importObject(forceRefresh = false) {
  const object = selectedObject();
  const path = forceRefresh ? object?.rootPath : await chooseFolderPath();
  if (!path) return;

  const controller = createOperationController();
  startProgress(forceRefresh ? "Обновление объекта" : "Загрузка объекта", path);
  const response = await fetch("/api/objects/import", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path }),
    signal: controller.signal,
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "Объект не загружен");
  if (state.progressCancelled) return;
  state.selectedObjectId = payload.id;
  els.path.value = payload.rootPath;
  await loadObjectSummaries();
  finishProgress(forceRefresh ? "Объект обновлён" : "Объект загружен");
}

async function excludeSelectedObject() {
  const object = selectedObject();
  if (!object) return;
  const controller = createOperationController();
  startProgress("Исключение объекта", object.name);
  const response = await fetch("/api/objects/exclude", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: object.id }),
    signal: controller.signal,
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "Объект не исключён");
  state.selectedObjectId = null;
  state.currentManifest = null;
  await loadObjectSummaries();
  finishProgress("Объект исключён");
}

function nodeMatches(node) {
  const query = els.treeSearch.value.trim().toLocaleLowerCase("ru");
  const filter = state.activeFilter;
  const value = `${node.name} ${node.extension || ""} ${node.path || ""}`.toLocaleLowerCase("ru");
  const searchOk = !query || value.includes(query);
  const formatOk = !filter || node.type === "folder" || node.extension === filter;
  if (node.type === "file") return searchOk && formatOk;
  return (node.children || []).some((child) => nodeMatches(child)) || searchOk;
}

function updateSelectionSummary() {
  const selected = [...state.selectedPaths];
  if (!selected.length) {
    els.selectionSummary.textContent = "Выделение пустое";
    return;
  }
  const selectedNodes = state.visibleRows.filter((item) => state.selectedPaths.has(item.path));
  const files = selectedNodes.filter((item) => item.type === "file").length;
  const folders = selectedNodes.filter((item) => item.type === "folder").length;
  els.selectionSummary.textContent = `Выбрано: ${selected.length} · файлов: ${files} · папок: ${folders}`;
}

function selectNode(node, event) {
  const index = state.visibleRows.findIndex((item) => item.path === node.path);
  if (event.shiftKey && state.lastSelectedIndex !== null) {
    const start = Math.min(state.lastSelectedIndex, index);
    const end = Math.max(state.lastSelectedIndex, index);
    state.selectedPaths.clear();
    state.visibleRows.slice(start, end + 1).forEach((item) => state.selectedPaths.add(item.path));
  } else if (event.ctrlKey || event.metaKey) {
    if (state.selectedPaths.has(node.path)) state.selectedPaths.delete(node.path);
    else state.selectedPaths.add(node.path);
    state.lastSelectedIndex = index;
  } else {
    if (state.selectedPaths.size === 1 && state.selectedPaths.has(node.path)) state.selectedPaths.clear();
    else {
      state.selectedPaths.clear();
      state.selectedPaths.add(node.path);
      state.lastSelectedIndex = index;
    }
  }
  renderTree();
}

function renderTreeNode(node, parent) {
  if (!nodeMatches(node)) return;
  const row = document.createElement("div");
  row.className = `tree-row ${node.type}`;
  row.classList.toggle("selected", state.selectedPaths.has(node.path));
  row.title = node.path;
  const collapsed = state.collapsedFolders.has(node.path);
  const icon = node.type === "folder" ? (collapsed ? "›" : "⌄") : "•";

  const iconEl = document.createElement("span");
  iconEl.textContent = icon;
  const nameEl = document.createElement("span");
  nameEl.className = "tree-name";
  nameEl.textContent = node.name;
  const metaEl = document.createElement("span");
  metaEl.className = "tree-meta";
  metaEl.textContent = node.type === "file" ? node.extension : (node.children || []).length;
  row.append(iconEl, nameEl, metaEl);

  row.addEventListener("click", (event) => {
    event.stopPropagation();
    selectNode(node, event);
  });
  row.addEventListener("dblclick", (event) => {
    event.stopPropagation();
    if (node.type === "folder") {
      if (state.collapsedFolders.has(node.path)) state.collapsedFolders.delete(node.path);
      else state.collapsedFolders.add(node.path);
      renderTree();
    }
  });
  parent.append(row);
  state.visibleRows.push(node);

  if (node.type === "folder" && node.children?.length && !collapsed) {
    const children = document.createElement("div");
    children.className = "tree-children";
    node.children.forEach((child) => renderTreeNode(child, children));
    parent.append(children);
  }
}

function renderFormats() {
  els.formatStrip.replaceChildren();
  const extensions = state.currentManifest?.statistics?.extensions || {};
  const preferred = ["PDF", "DWG", "XLSX", "XLS", "DOCX", "DOC", "TXT", "PNG", "JPG", "JPEG", "PPTX", "SVG"];
  const all = Object.keys(extensions).sort((a, b) => a.localeCompare(b, "ru"));
  const formats = [...new Set([...preferred.filter((ext) => ext in extensions), ...all])];
  if (!formats.length) {
    const empty = document.createElement("span");
    empty.className = "format-empty";
    empty.textContent = "Форматов нет";
    els.formatStrip.append(empty);
    return;
  }
  formats.forEach((ext) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "format-chip";
    button.classList.toggle("active", state.activeFilter === ext);
    button.textContent = `${ext} ${extensions[ext] || 0}`;
    button.title = `Фильтр ${ext}. Повторное нажатие выключает фильтр.`;
    button.addEventListener("click", () => {
      state.activeFilter = state.activeFilter === ext ? "" : ext;
      state.selectedPaths.clear();
      renderFormats();
      renderTree();
    });
    els.formatStrip.append(button);
  });
}

function renderTree() {
  els.objectTree.replaceChildren();
  state.visibleRows = [];
  if (!state.currentManifest?.tree) {
    const empty = document.createElement("div");
    empty.className = "empty-note";
    empty.textContent = "Дерево ещё не открыто.";
    els.objectTree.append(empty);
    updateSelectionSummary();
    return;
  }
  renderTreeNode(state.currentManifest.tree, els.objectTree);
  if (!state.visibleRows.length) {
    const empty = document.createElement("div");
    empty.className = "empty-note";
    empty.textContent = "Поиск или фильтр ничего не нашли.";
    els.objectTree.append(empty);
  }
  updateSelectionSummary();
}

async function openSelectedObject() {
  const object = selectedObject();
  if (!object) return;
  const controller = createOperationController();
  startProgress("Открытие структуры", object.name);
  const response = await fetch(`/api/objects/${encodeURIComponent(object.id)}`, { signal: controller.signal });
  const manifest = await response.json();
  if (!response.ok) throw new Error(manifest.error || "Объект не открыт");
  state.currentManifest = manifest;
  state.selectedPaths.clear();
  state.activeFilter = "";
  state.collapsedFolders.clear();
  setMode("tree");
  renderFormats();
  renderTree();
  finishProgress("Структура открыта");
}

function simulateDisplaySelection() {
  const visibleFiles = state.visibleRows.filter((item) => item.type === "file");
  const selectedNodes = state.visibleRows.filter((item) => state.selectedPaths.has(item.path));
  const selectedFiles = selectedNodes.filter((item) => item.type === "file");
  const count = selectedFiles.length || visibleFiles.length;
  startProgress("Имитация отображения", `${count} элементов · render-заглушка`);
  setTimeout(() => {
    if (!state.progressCancelled) finishProgress("Заглушка отображения завершена");
  }, Math.min(2600, 600 + count * 45));
}

els.load.addEventListener("click", () => importObject(false).catch(showOperationError));
els.refresh.addEventListener("click", () => {
  if (inTreeMode()) importObject(true).then(openSelectedObject).catch(showOperationError);
  else importObject(true).catch(showOperationError);
});
els.display.addEventListener("click", () => {
  if (inTreeMode()) simulateDisplaySelection();
  else openSelectedObject().catch(showOperationError);
});
els.exclude.addEventListener("click", () => excludeSelectedObject().catch(showOperationError));
els.cancel.addEventListener("click", () => stopProgress(true));
els.backToObjects.addEventListener("click", () => setMode("objects"));
els.treeSearch.addEventListener("input", () => {
  state.selectedPaths.clear();
  renderTree();
});

document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  state.selectedPaths.clear();
  if (inTreeMode()) renderTree();
  else {
    state.selectedObjectId = null;
    renderObjectList();
  }
});

document.addEventListener("click", (event) => {
  if (els.objectListState.classList.contains("active") && !event.target.closest(".object-row, button, textarea")) {
    state.selectedObjectId = null;
    renderObjectList();
  }
  if (inTreeMode() && !event.target.closest(".tree-row, button, input")) {
    state.selectedPaths.clear();
    renderTree();
  }
});

setMode("objects");
loadObjectSummaries().catch((error) => {
  els.objectList.innerHTML = `<div class="empty-note">Ошибка загрузки списка: ${error.message}</div>`;
});
