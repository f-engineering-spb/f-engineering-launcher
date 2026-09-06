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
  operationControllers: [],
  renderedPages: [],
  activePageUrl: "",
  activePageKey: "",
  activeNativePath: "",
  excelWorkbook: null,
  excelWorkbooks: [],
  excelWorkbookIndex: 0,
  excelSheetIndex: 0,
  excelScale: 1,
  highQualityPages: new Map(),
  pdfPairIndex: new Map(),
  diffStatus: new Map(),
  diffRemovedNodes: [],
  diffSummary: null,
  diffFilter: false,
  diffPollTimer: null,
  // Deduplicate the double-click vs the two parent click events that precede
  // it: without this, one dblclick can launch the same file twice.
  lastOpenPath: "",
  lastOpenAt: 0,
  viewMode: "standard",
  view: {
    scale: 1,
    fitScale: 1,
    rotation: 0,
    panX: 0,
    panY: 0,
    panMode: true,
    dragging: false,
    dragStartX: 0,
    dragStartY: 0,
    dragPanX: 0,
    dragPanY: 0,
  },
  modal: {
    activeTab: "quick",
    currentBrowsePath: "",
    browseData: null,
  },
};

const els = {
  shell: document.querySelector(".shell"),
  load: document.getElementById("loadObject"),
  loadModal: document.getElementById("loadModal"),
  closeLoadModal: document.getElementById("closeLoadModal"),
  tabQuick: document.getElementById("tabQuick"),
  tabBrowse: document.getElementById("tabBrowse"),
  tabPath: document.getElementById("tabPath"),
  paneQuick: document.getElementById("paneQuick"),
  paneBrowse: document.getElementById("paneBrowse"),
  panePath: document.getElementById("panePath"),
  quickProjectsList: document.getElementById("quickProjectsList"),
  drivesBar: document.getElementById("drivesBar"),
  browserBreadcrumbs: document.getElementById("browserBreadcrumbs"),
  browserFoldersList: document.getElementById("browserFoldersList"),
  browserStats: document.getElementById("browserStats"),
  browserFilesList: document.getElementById("browserFilesList"),
  btnLoadBrowsedFolder: document.getElementById("btnLoadBrowsedFolder"),
  btnOpenInWindowsExplorer: document.getElementById("btnOpenInWindowsExplorer"),
  manualPathInput: document.getElementById("manualPathInput"),
  btnLoadManualPath: document.getElementById("btnLoadManualPath"),
  btnTriggerSystemPicker: document.getElementById("btnTriggerSystemPicker"),
  systemPickerStatus: document.getElementById("systemPickerStatus"),
  modalDropZone: document.getElementById("modalDropZone"),
  refresh: document.getElementById("refreshObject"),
  display: document.getElementById("displayObject"),
  exclude: document.getElementById("excludeObject"),
  cancel: document.getElementById("cancelOperation"),
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
  backToTree: document.getElementById("backToTree"),
  treeSearch: document.getElementById("treeSearch"),
  formatStrip: document.getElementById("formatStrip"),
  selectionSummary: document.getElementById("selectionSummary"),
  objectTree: document.getElementById("objectTree"),
  pdfThumbs: document.getElementById("pdfThumbs"),
  pdfViewer: document.getElementById("pdfViewer"),
  pdfStage: document.getElementById("pdfStage"),
  pdfPageImage: document.getElementById("pdfPageImage"),
  excelViewer: document.getElementById("excelViewer"),
  excelBookTitle: document.getElementById("excelBookTitle"),
  excelTabs: document.getElementById("excelTabs"),
  excelTabsLeft: document.getElementById("excelTabsLeft"),
  excelTabsRight: document.getElementById("excelTabsRight"),
  excelSheetFrame: document.getElementById("excelSheetFrame"),
  viewerEmpty: document.getElementById("viewerEmpty"),
  viewerControls: document.getElementById("viewerControls"),
  qualityBadge: document.getElementById("qualityBadge"),
  viewZoomOut: document.getElementById("viewZoomOut"),
  viewZoomIn: document.getElementById("viewZoomIn"),
  viewFit: document.getElementById("viewFit"),
  viewRotate: document.getElementById("viewRotate"),
  viewPanMode: document.getElementById("viewPanMode"),
  openNativeFile: document.getElementById("openNativeFile"),
  viewStandardMode: document.getElementById("viewStandardMode"),
  viewMediumMode: document.getElementById("viewMediumMode"),
  viewFullMode: document.getElementById("viewFullMode"),
  diffSummary: document.getElementById("diffSummary"),
  diffFilterToggle: document.getElementById("diffFilterToggle"),
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
  els.shell.classList.toggle("tree-browse", false);
  if (els.backToTree) els.backToTree.disabled = true;
  updateObjectButtons();
}

function setTreeBrowseMode(enabled) {
  els.shell.classList.toggle("tree-browse", Boolean(enabled));
  if (els.backToTree) els.backToTree.disabled = Boolean(enabled) || !state.currentManifest?.tree;
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
    row.dataset.objectId = object.id;
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
      updateObjectListSelection();
      updateObjectButtons();
      updateObjectStats();
    });
    row.addEventListener("dblclick", (event) => {
      event.stopPropagation();
      state.selectedObjectId = object.id;
      updateObjectListSelection();
      updateObjectButtons();
      updateObjectStats();
      openSelectedObject().catch(showOperationError);
    });
    els.objectList.append(row);
  });
  updateObjectStats();
  updateObjectButtons();
}

function updateObjectListSelection() {
  [...els.objectList.querySelectorAll(".object-row")].forEach((row) => {
    row.classList.toggle("selected", row.dataset.objectId === state.selectedObjectId);
  });
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
  if (abortRequest && state.operationControllers.length) {
    state.operationControllers.forEach((controller) => controller.abort());
    state.operationControllers = [];
  }
  els.progressPanel.hidden = true;
}

function showOperationError(error) {
  if (error?.name === "AbortError") return;
  // Never disguise a failed render as a completed 100% operation.  Keep the
  // factual error on screen long enough for both the user and QA to see it.
  if (state.progressTimer) clearInterval(state.progressTimer);
  state.progressTimer = null;
  state.operationController = null;
  els.progressLabel.textContent = "Операция не выполнена";
  els.progressDetail.textContent = `Ошибка: ${error.message || error}`;
  els.progressValue.textContent = "Ошибка";
  els.progressFill.style.width = "100%";
  els.progressFill.classList.add("is-error");
  setTimeout(() => {
    if (!state.progressTimer) {
      els.progressPanel.hidden = true;
      els.progressFill.classList.remove("is-error");
    }
  }, 8000);
}

// Non-blocking warning (not an error): shows why a command may have silently
// misbehaved, e.g. a Windows long-path limit, without failing the operation.
function showNotice(message) {
  if (state.progressTimer) clearInterval(state.progressTimer);
  state.progressTimer = null;
  els.progressLabel.textContent = "Предупреждение";
  els.progressDetail.textContent = message;
  els.progressValue.textContent = "";
  els.progressFill.style.width = "100%";
  els.progressPanel.hidden = false;
  setTimeout(() => {
    if (!state.progressTimer) {
      els.progressPanel.hidden = true;
    }
  }, 9000);
}



function getNativeAppLabel(ext = "") {
  const e = String(ext).toUpperCase().replace(/^\./, "");
  switch (e) {
    case "DWG":
    case "DXF": return "ZWCAD";
    case "PDF": return "ONLYOFFICE / PDF";
    case "DOC":
    case "DOCX":
    case "RTF":
    case "ODT": return "Word";
    case "XLS":
    case "XLSX":
    case "XLSM":
    case "XLSB":
    case "CSV":
    case "ODS": return "Excel";
    case "GDOC": return "Google Docs";
    case "GSHEET": return "Google Таблицах";
    case "GSLIDES": return "Google Презентациях";
    case "JPG":
    case "JPEG":
    case "PNG":
    case "BMP":
    case "WEBP":
    case "SVG":
    case "TIF":
    case "TIFF":
    case "GIF":
    case "ICO": return "Просмотре фото";
    case "MP4":
    case "AVI":
    case "MOV":
    case "MKV":
    case "WMV":
    case "MP3":
    case "WAV": return "Медиаплеере (VLC)";
    case "ZIP":
    case "RAR":
    case "7Z":
    case "TAR":
    case "GZ": return "Архиваторе";
    case "TXT":
    case "LOG":
    case "INI":
    case "CFG":
    case "JSON":
    case "XML":
    case "YAML":
    case "YML": return "Блокноте";
    default: return e ? `${e}` : "программе";
  }
}

function fileExtensionFromPath(path = "") {
  const dotIndex = path.lastIndexOf(".");
  return dotIndex >= 0 ? path.slice(dotIndex + 1).toUpperCase() : "";
}

async function openFileByPath(path) {
  if (!path) return;
  const ext = fileExtensionFromPath(path);
  const appLabel = getNativeAppLabel(ext);
  console.log(`[Launcher] Opening in ${appLabel}:`, path);
  startProgress(`Открытие в ${appLabel}`, path);
  try {
    const response = await fetch("/api/open-file", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Файл не открыт");
    finishProgress(`Файл открыт: ${appLabel}`);
    if (payload.longPathWarning) showNotice(payload.longPathWarning);
  } catch (error) {
    console.error("[Launcher] Failed to open native file:", error);
    showOperationError(error);
  }
}

// window (~800 ms) between two launches of the same path.  A double-click
// produces click + click + dblclick; without this the file opens twice.
function openFileByPathDeduped(path) {
  if (!path) return;
  const now = Date.now();
  if (path === state.lastOpenPath && now - state.lastOpenAt < 800) return;
  state.lastOpenPath = path;
  state.lastOpenAt = now;
  openFileByPath(path).catch(showOperationError);
}

function escapeHtml(value = "") {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function openLoadModal() {
  if (!els.loadModal) return;
  els.loadModal.hidden = false;
  switchModalTab(state.modal.activeTab || "quick");
  refreshBrowseData(state.modal.currentBrowsePath || "").catch(console.error);
}

function closeLoadModal() {
  if (!els.loadModal) return;
  els.loadModal.hidden = true;
  if (els.systemPickerStatus) {
    els.systemPickerStatus.hidden = true;
    els.systemPickerStatus.textContent = "";
  }
}

function switchModalTab(tabName) {
  state.modal.activeTab = tabName;
  const tabs = [
    { name: "quick", btn: els.tabQuick, pane: els.paneQuick },
    { name: "browse", btn: els.tabBrowse, pane: els.paneBrowse },
    { name: "path", btn: els.tabPath, pane: els.panePath },
  ];
  tabs.forEach((t) => {
    if (t.btn && t.pane) {
      if (t.name === tabName) {
        t.btn.classList.add("active");
        t.pane.classList.add("active");
      } else {
        t.btn.classList.remove("active");
        t.pane.classList.remove("active");
      }
    }
  });
  if (tabName === "path" && els.manualPathInput) {
    setTimeout(() => els.manualPathInput.focus(), 50);
  }
}

async function refreshBrowseData(targetPath = "") {
  try {
    const url = targetPath ? `/api/browse?path=${encodeURIComponent(targetPath)}` : "/api/browse";
    const response = await fetch(url);
    if (!response.ok) return;
    const data = await response.json();
    state.modal.browseData = data;
    state.modal.currentBrowsePath = data.current || targetPath;

    renderQuickProjects(data.quickProjects || []);
    renderBrowserDrives(data.drives || [], data.current || "");
    renderBrowserBreadcrumbs(data.current || "");
    renderBrowserFolders(data.folders || [], data.parent);
    renderBrowserPreview(data.files || [], data.stats || {}, data.current || "");
  } catch (err) {
    console.warn("Failed to refresh browse data:", err);
  }
}

function renderQuickProjects(projects) {
  if (!els.quickProjectsList) return;
  if (!projects.length) {
    els.quickProjectsList.innerHTML = '<div class="loading-spin">Проекты не найдены. Воспользуйтесь проводником по папкам.</div>';
    return;
  }
  els.quickProjectsList.innerHTML = projects.map((proj) => `
    <div class="quick-project-card">
      <div class="quick-project-info">
        <div class="quick-project-name">📁 ${escapeHtml(proj.name)}</div>
        <div class="quick-project-path" title="${escapeHtml(proj.path)}">${escapeHtml(proj.path)}</div>
      </div>
      <button class="primary-btn quick-load-btn" data-path="${escapeHtml(proj.path)}" type="button">Загрузить</button>
    </div>
  `).join("");

  els.quickProjectsList.querySelectorAll(".quick-load-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const p = btn.getAttribute("data-path");
      if (p) importObjectByPath(p).catch(showOperationError);
    });
  });
}

function renderBrowserDrives(drives, currentPath) {
  if (!els.drivesBar) return;
  els.drivesBar.innerHTML = drives.map((d) => {
    const isActive = currentPath.toLowerCase().startsWith(d.path.toLowerCase());
    return `<button class="drive-btn ${isActive ? 'active' : ''}" data-path="${escapeHtml(d.path)}" type="button">${escapeHtml(d.label || d.letter)}</button>`;
  }).join("");

  els.drivesBar.querySelectorAll(".drive-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const p = btn.getAttribute("data-path");
      if (p) refreshBrowseData(p).catch(console.error);
    });
  });
}

function renderBrowserBreadcrumbs(currentPath) {
  if (!els.browserBreadcrumbs) return;
  if (!currentPath) {
    els.browserBreadcrumbs.innerHTML = "";
    return;
  }
  const parts = currentPath.split(/[/\\]+/).filter(Boolean);
  let accumulated = "";
  const crumbs = [];

  parts.forEach((part, index) => {
    if (index === 0 && currentPath.includes(":\\\\")) {
      accumulated = part + "\\\\";
    } else {
      accumulated += (accumulated.endsWith("\\\\") ? "" : "\\\\") + part;
    }
    crumbs.push({ name: part, path: accumulated });
  });

  els.browserBreadcrumbs.innerHTML = crumbs.map((crumb, i) => `
    ${i > 0 ? '<span class="breadcrumb-sep">›</span>' : ''}
    <button class="breadcrumb-crumb" data-path="${escapeHtml(crumb.path)}" type="button">${escapeHtml(crumb.name)}</button>
  `).join("");

  els.browserBreadcrumbs.querySelectorAll(".breadcrumb-crumb").forEach((btn) => {
    btn.addEventListener("click", () => {
      const p = btn.getAttribute("data-path");
      if (p) refreshBrowseData(p).catch(console.error);
    });
  });
}

function renderBrowserFolders(folders, parentPath) {
  if (!els.browserFoldersList) return;
  const items = [];
  if (parentPath) {
    items.push(`<div class="browser-folder-item" data-path="${escapeHtml(parentPath)}">📁 <strong>.. (Вверх)</strong></div>`);
  }
  folders.forEach((f) => {
    items.push(`<div class="browser-folder-item" data-path="${escapeHtml(f.path)}">📁 ${escapeHtml(f.name)}</div>`);
  });

  if (!items.length) {
    els.browserFoldersList.innerHTML = '<div class="loading-spin">Папка пуста</div>';
    return;
  }

  els.browserFoldersList.innerHTML = items.join("");
  els.browserFoldersList.querySelectorAll(".browser-folder-item").forEach((item) => {
    item.addEventListener("click", () => {
      const p = item.getAttribute("data-path");
      if (p) refreshBrowseData(p).catch(console.error);
    });
  });
}

function renderBrowserPreview(files, stats, currentPath) {
  if (els.browserStats) {
    const parts = [];
    if (stats.dwg) parts.push(`DWG: ${stats.dwg}`);
    if (stats.pdf) parts.push(`PDF: ${stats.pdf}`);
    if (stats.excel) parts.push(`Excel: ${stats.excel}`);
    if (stats.word) parts.push(`Word: ${stats.word}`);
    const summary = parts.length ? parts.join(" · ") : "Файлов проекта не обнаружено";
    els.browserStats.textContent = `${summary} (всего файлов: ${files.length})`;
  }
  if (els.browserFilesList) {
    if (!files.length) {
      els.browserFilesList.innerHTML = '<div class="loading-spin">Нет файлов</div>';
      return;
    }
    els.browserFilesList.innerHTML = files.slice(0, 30).map((f) => `
      <div class="browser-file-item" title="${escapeHtml(f.name)}">📄 ${escapeHtml(f.name)}</div>
    `).join("");
  }
}

async function openInWindowsExplorer(path) {
  if (!path) return;
  try {
    await fetch("/api/open-explorer", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path }),
    });
  } catch (err) {
    console.warn("Could not open explorer:", err);
  }
}

async function triggerSystemPicker() {
  if (!els.systemPickerStatus) return;
  els.systemPickerStatus.hidden = false;
  els.systemPickerStatus.textContent = "⏳ Ожидание выбора в стандартном окне Windows…";
  try {
    const res = await fetch("/api/choose-folder", { method: "POST" });
    const data = await res.json();
    if (data.path) {
      els.systemPickerStatus.textContent = `Выбрано: ${data.path}`;
      await importObjectByPath(data.path);
    } else if (data.error) {
      els.systemPickerStatus.textContent = data.error;
    } else {
      els.systemPickerStatus.textContent = "Выбор отменён.";
    }
  } catch (err) {
    els.systemPickerStatus.textContent = `Ошибка: ${err.message}`;
  }
}

async function importObjectByPath(path, forceRefresh = false) {
  if (!path || !path.trim()) return;
  closeLoadModal();
  const controller = createOperationController();
  startProgress(forceRefresh ? "Обновление объекта" : "Загрузка объекта", path);
  try {
    const response = await fetch("/api/objects/import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: path.trim() }),
      signal: controller.signal,
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Объект не загружен");
    if (state.progressCancelled) return;
    state.selectedObjectId = payload.id;
    await loadObjectSummaries();
    finishProgress(forceRefresh ? "Объект обновлён" : "Объект загружен");
  } catch (error) {
    showOperationError(error);
  }
}

async function importObject(forceRefresh = false) {
  if (forceRefresh) {
    const object = selectedObject();
    if (object?.rootPath) {
      await importObjectByPath(object.rootPath, true);
    }
  } else {
    openLoadModal();
  }
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

function flattenTree(node, result = []) {
  result.push(node);
  for (const child of node.children || []) flattenTree(child, result);
  return result;
}

function fileStem(name = "") {
  const value = String(name);
  const dotIndex = value.lastIndexOf(".");
  return dotIndex > 0 ? value.slice(0, dotIndex) : value;
}

function normalizePairName(name = "") {
  return fileStem(name)
    .toLocaleLowerCase("ru")
    .replace(/ё/g, "е")
    .replace(/\b(?:ap|ar)\s*(?=\d)/g, "ар")
    .replace(/ар\s*(?=\d)/g, "ар ")
    .replace(/проеомв/g, "проемов")
    .replace(/срп\s*[_-]?\s*7/g, " ")
    .replace(/лист/g, " ")
    .replace(/[+]/g, " ")
    .replace(/[_\-.()[\]{},]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function pairTokens(name = "") {
  return normalizePairName(name)
    .split(" ")
    .map((token) => token.trim())
    .filter((token) => token.length > 1)
    .filter((token) => !["срп", "для", "всех", "отм", "осях", "оси", "на"].includes(token));
}

function escapeRegExp(value = "") {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function extractCodeParts(normalized = "") {
  const codeMatch = normalized.match(/(?:^|\s)ар\s*(\d)\s+(\d)\s+(\d)(?=\s|$)/u)
    || normalized.match(/(?:^|\s)ар\s*(\d)\s+(\d)(?=\s|$)/u);
  return codeMatch ? codeMatch.slice(1).filter(Boolean) : [];
}

function stripPairServiceNoise(normalized = "") {
  let value = normalized
    .replace(/\bсрп\s*7\b/g, " ")
    .replace(/\bлист\b/g, " ");
  const codeParts = extractCodeParts(value);
  if (codeParts.length) {
    const codePattern = new RegExp(`(?:^|\\s)ар\\s*${codeParts.map(escapeRegExp).join("\\s+")}(?=\\s|$)`, "g");
    value = value.replace(codePattern, " ");
  }
  return value
    .replace(/\b50\s+\d{1,3}\b/g, " ")
    .replace(/^\s*\d{1,3}\s+/, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function stemPairToken(token = "") {
  if (token.length <= 4) return token;
  return token.replace(/(иями|ями|ами|ого|его|ому|ему|ыми|ими|ых|их|ая|яя|ое|ее|ые|ие|ый|ий|ой|ую|юю|ом|ем|ах|ях|ов|ев|ей|ам|ям|а|я|ы|и|е|у|ю|о)$/u, "");
}

function semanticPairTokens(normalized = "") {
  return stripPairServiceNoise(normalized)
    .split(" ")
    .map((token) => stemPairToken(token.trim()))
    .filter((token) => token.length > 1)
    .filter((token) => !["срп", "для", "всех", "отм", "осях", "оси", "на"].includes(token));
}

function tokenBigrams(tokens = []) {
  const result = new Set();
  for (let index = 0; index < tokens.length - 1; index += 1) {
    result.add(`${tokens[index]} ${tokens[index + 1]}`);
  }
  return result;
}

function longestCommonTokenRun(left = [], right = []) {
  let best = 0;
  const previous = new Array(right.length + 1).fill(0);
  const current = new Array(right.length + 1).fill(0);
  for (let leftIndex = 1; leftIndex <= left.length; leftIndex += 1) {
    for (let rightIndex = 1; rightIndex <= right.length; rightIndex += 1) {
      current[rightIndex] = left[leftIndex - 1] === right[rightIndex - 1] ? previous[rightIndex - 1] + 1 : 0;
      if (current[rightIndex] > best) best = current[rightIndex];
    }
    previous.splice(0, previous.length, ...current);
    current.fill(0);
  }
  return best;
}

function longestCommonSubstringLength(left = "", right = "") {
  if (!left || !right) return 0;
  let best = 0;
  const previous = new Array(right.length + 1).fill(0);
  const current = new Array(right.length + 1).fill(0);
  for (let leftIndex = 1; leftIndex <= left.length; leftIndex += 1) {
    for (let rightIndex = 1; rightIndex <= right.length; rightIndex += 1) {
      current[rightIndex] = left[leftIndex - 1] === right[rightIndex - 1] ? previous[rightIndex - 1] + 1 : 0;
      if (current[rightIndex] > best) best = current[rightIndex];
    }
    previous.splice(0, previous.length, ...current);
    current.fill(0);
  }
  return best;
}

function pairFingerprint(name = "") {
  const normalized = normalizePairName(name);
  const codeParts = extractCodeParts(normalized);
  const code = codeParts.length ? `ар${codeParts.join(".")}` : "";
  const sheetMatch = normalized.match(/\b50\s+(\d{1,3})\b/);
  const sheet = sheetMatch ? String(Number(sheetMatch[1])) : "";
  const codeNumberPattern = codeParts.length
    ? new RegExp(`(?:^|\\s)ар\\s*${codeParts.join("\\s+")}\\s+(\\d{1,3})(?=\\s|$)`, "u")
    : /(?:^|\s)ар\s*(?:\d\s*)+\s+(\d{1,3})(?=\s|$)/u;
  const codeNumberMatch = normalized.match(codeNumberPattern);
  const codeNumber = codeNumberMatch ? String(Number(codeNumberMatch[1])) : "";
  const detailMatches = [...normalized.matchAll(/(?:^|\s)(узел|сечение|часть)\s+([a-zа-я0-9]+(?:\s*[-–]\s*[a-zа-я0-9]+)?)(?=\s|$)/gu)]
    .map((match) => `${match[1]} ${match[2].replace(/\s+/g, "")}`);
  const details = new Set(detailMatches);
  const floorMatch = normalized.match(/\b(\d+\s*[-–]\s*\d+|\d+)\s+(?:го\s+)?этаж/u);
  const floor = floorMatch ? floorMatch[1].replace(/\s+/g, "") : "";
  const technical = /техническ|тех\s*пространств/u.test(normalized);
  const types = new Set();
  if (/маркировочный\s+план/u.test(normalized)) types.add("маркировочный план");
  if (/общие\s+данные/u.test(normalized)) types.add("общие данные");
  if (/ведомост/u.test(normalized) && /отделк/u.test(normalized)) types.add("ведомость отделки");
  if (/экспликац/u.test(normalized) && /полов/u.test(normalized)) types.add("экспликация полов");
  if (/схем/u.test(normalized) && /двер/u.test(normalized)) types.add("схемы дверей");
  if (/колористическ/u.test(normalized)) types.add("колористическое решение");
  if (/фасад/u.test(normalized)) types.add("фасад");
  const axisTokens = new Set([...normalized.matchAll(/\b7\s+2\s+[0-9а-я]+\b/gu)].map((match) => match[0].replace(/\s+/g, ".")));
  const tokens = new Set(pairTokens(name));
  const semanticText = stripPairServiceNoise(normalized);
  const semanticTokensList = semanticPairTokens(normalized);
  const semanticTokensSet = new Set(semanticTokensList);
  return {
    normalizedName: normalized,
    semanticText,
    semanticTokensList,
    semanticTokensSet,
    semanticBigrams: tokenBigrams(semanticTokensList),
    code,
    sheet: sheet || codeNumber,
    details,
    floor,
    technical,
    types,
    axisTokens,
    tokens,
  };
}

function buildPdfPairIndex(nodes) {
  return nodes
    .filter((node) => node.type === "file" && node.extension === "PDF")
    .map((node) => ({
      node,
      fingerprint: pairFingerprint(node.name),
    }));
}

function intersectionSize(left, right) {
  let count = 0;
  for (const item of left) {
    if (right.has(item)) count += 1;
  }
  return count;
}

function comparePairFingerprints(dwg, pdf) {
  if (dwg.normalizedName === pdf.normalizedName) return { score: 100, confidence: "exact" };
  if (dwg.code && pdf.code && dwg.code !== pdf.code) return null;
  const detailOverlap = intersectionSize(dwg.details, pdf.details);
  if (dwg.details.size && pdf.details.size && detailOverlap === 0) return null;

  let score = 0;
  if (dwg.code && pdf.code && dwg.code === pdf.code) score += 32;
  if (dwg.sheet && pdf.sheet && dwg.sheet === pdf.sheet) score += 8;
  if (dwg.sheet && pdf.sheet && dwg.sheet !== pdf.sheet) score -= 4;
  if (detailOverlap) score += 34;
  if (dwg.floor && pdf.floor && dwg.floor === pdf.floor) score += 28;
  if (dwg.technical && pdf.technical) score += 28;

  const typeOverlap = intersectionSize(dwg.types, pdf.types);
  score += typeOverlap * 16;

  const axisOverlap = intersectionSize(dwg.axisTokens, pdf.axisTokens);
  score += Math.min(18, axisOverlap * 6);

  const sharedTokens = intersectionSize(dwg.tokens, pdf.tokens);
  const tokenRatio = sharedTokens / Math.max(dwg.tokens.size, pdf.tokens.size, 1);
  score += Math.round(tokenRatio * 28);

  const semanticOverlap = intersectionSize(dwg.semanticTokensSet, pdf.semanticTokensSet);
  const semanticRatio = semanticOverlap / Math.max(dwg.semanticTokensSet.size, pdf.semanticTokensSet.size, 1);
  score += Math.round(semanticRatio * 46);

  const bigramOverlap = intersectionSize(dwg.semanticBigrams, pdf.semanticBigrams);
  score += Math.min(36, bigramOverlap * 12);

  const commonRun = longestCommonTokenRun(dwg.semanticTokensList, pdf.semanticTokensList);
  if (commonRun >= 5) score += 42;
  else if (commonRun >= 4) score += 32;
  else if (commonRun >= 3) score += 22;

  const commonSubstring = longestCommonSubstringLength(dwg.semanticText, pdf.semanticText);
  if (commonSubstring >= 32) score += 32;
  else if (commonSubstring >= 22) score += 22;
  else if (commonSubstring >= 16) score += 12;

  if (dwg.semanticText && pdf.semanticText && dwg.semanticText === pdf.semanticText) score += 52;

  const hasSemanticAnchor = Boolean(
    detailOverlap
    || (dwg.floor && pdf.floor && dwg.floor === pdf.floor)
    || (dwg.technical && pdf.technical)
    || typeOverlap >= 1
    || axisOverlap >= 2
    || semanticRatio >= 0.5
    || bigramOverlap >= 1
    || commonRun >= 3
    || commonSubstring >= 22
  );
  if (!hasSemanticAnchor && score < 82) return null;
  if (score < 68) return null;
  return { score, confidence: score >= 78 ? "strong" : "probable" };
}

function findPdfPairForDwg(dwgNode, pdfIndex) {
  if (!dwgNode || dwgNode.extension !== "DWG") return null;
  const dwgFingerprint = pairFingerprint(dwgNode.name);
  let best = null;
  for (const candidate of pdfIndex) {
    const comparison = comparePairFingerprints(dwgFingerprint, candidate.fingerprint);
    if (comparison && (!best || comparison.score > best.score)) best = { node: candidate.node, ...comparison };
  }
  return best;
}

function nodeMatches(node) {
  const query = els.treeSearch.value.trim().toLocaleLowerCase("ru");
  const filter = state.activeFilter;
  const value = `${node.name} ${node.extension || ""} ${node.path || ""}`.toLocaleLowerCase("ru");
  const searchOk = !query || value.includes(query);
  const formatOk = !filter || node.type === "folder" || node.extension === filter;
  if (node.type === "file") {
    if (state.diffFilter && !state.diffStatus.has(node.path)) return false;
    return searchOk && formatOk;
  }
  const childMatch = (node.children || []).some((child) => nodeMatches(child));
  if (state.diffFilter) return childMatch;
  return childMatch || searchOk;
}

function nodeHasDiff(node) {
  if (state.diffStatus.has(node.path)) return true;
  if (node.type === "folder") return (node.children || []).some((child) => nodeHasDiff(child));
  return false;
}

function countDiffDescendants(node, result = { added: 0, changed: 0, removed: 0 }) {
  for (const child of node.children || []) {
    if (child.type === "file") {
      const status = state.diffStatus.get(child.path);
      if (status && status in result) result[status] += 1;
    } else {
      countDiffDescendants(child, result);
    }
  }
  return result;
}

function diffStatusText(status) {
  return status === "added" ? "новый" : status === "changed" ? "изменён" : "удалён";
}

function buildDiffState(manifest, previousManifest) {
  state.diffStatus.clear();
  state.diffRemovedNodes = [];
  state.diffSummary = null;
  const diff = manifest?.lastDiff;
  if (!diff) return;
  for (const path of diff.added || []) state.diffStatus.set(path, "added");
  for (const path of diff.changed || []) state.diffStatus.set(path, "changed");
  const removedSet = new Set(diff.removed || []);
  if (previousManifest?.tree && removedSet.size) {
    flattenTree(previousManifest.tree, []).forEach((node) => {
      if (node.type === "file" && removedSet.has(node.path)) {
        state.diffStatus.set(node.path, "removed");
        state.diffRemovedNodes.push(node);
      }
    });
  }
  state.diffSummary = {
    added: (diff.added || []).length,
    changed: (diff.changed || []).length,
    removed: state.diffRemovedNodes.length,
    unchanged: (diff.unchanged || []).length,
  };
}

function renderDiffSummary() {
  const summary = state.diffSummary;
  if (!summary || !(summary.added || summary.changed || summary.removed)) {
    if (els.diffSummary) els.diffSummary.hidden = true;
    if (els.diffFilterToggle) els.diffFilterToggle.hidden = true;
    return;
  }
  if (els.diffSummary) {
    els.diffSummary.hidden = false;
    els.diffSummary.textContent =
      `Добавлено: ${summary.added} · Изменено: ${summary.changed} · Удалено: ${summary.removed}`;
    els.diffSummary.title = `Без изменений: ${summary.unchanged}`;
  }
  if (els.diffFilterToggle) {
    els.diffFilterToggle.hidden = false;
    els.diffFilterToggle.classList.toggle("active", state.diffFilter);
  }
}

function toggleDiffFilter() {
  state.diffFilter = !state.diffFilter;
  renderDiffSummary();
  renderTree();
}

function startDiffPolling() {
  stopDiffPolling();
  if (!state.selectedObjectId) return;
  state.diffPollTimer = setInterval(async () => {
    if (!inTreeMode() || !state.currentManifest) return;
    try {
      const controller = new AbortController();
      const response = await fetch("/api/objects/diff", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: state.selectedObjectId }),
        signal: controller.signal,
      });
      const payload = await response.json();
      if (!response.ok || state.progressCancelled) return;
      const diff = payload.lastDiff;
      const hasChanges = diff && ((diff.added || []).length || (diff.changed || []).length || (diff.removed || []).length);
      if (hasChanges) await refreshObjectInPlace();
    } catch (error) {
      if (error.name === "AbortError") return;
      console.warn("Diff polling error", error);
    }
  }, DIFF_POLL_INTERVAL_MS);
}

function stopDiffPolling() {
  if (state.diffPollTimer) {
    clearInterval(state.diffPollTimer);
    state.diffPollTimer = null;
  }
}

async function refreshObjectInPlace() {
  const object = selectedObject();
  if (!object) return;
  const previousManifest = state.currentManifest;
  const controller = createOperationController();
  startProgress("Проверка изменений", object.name);
  const response = await fetch("/api/objects/import", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path: object.rootPath }),
    signal: controller.signal,
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "Объект не обновлён");
  if (state.progressCancelled) return;
  state.selectedObjectId = payload.id;
  state.currentManifest = payload;
  const removedPaths = new Set((previousManifest?.lastDiff?.removed || []).map((p) => p.casefold ? p.toLocaleLowerCase("ru") : p));
  state.selectedPaths = new Set([...state.selectedPaths].filter((path) => !removedPaths.has(path.toLocaleLowerCase("ru"))));
  buildDiffState(payload, previousManifest);
  await loadObjectSummaries();
  renderFormats();
  renderTree();
  renderDiffSummary();
  finishProgress(hasDiffChanges(payload) ? "Обнаружены изменения" : "Изменений нет");
  if (state.renderedPages.length && state.selectedPaths.size) {
    renderSelectedFiles().catch(showOperationError);
  }
}

function hasDiffChanges(manifest) {
  const diff = manifest?.lastDiff;
  return Boolean(diff && ((diff.added || []).length || (diff.changed || []).length || (diff.removed || []).length));
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

  if (selected.length === 1 && selectedNodes.length === 1 && selectedNodes[0].type === "file") {
    const singleNode = selectedNodes[0];
    const appLabel = getNativeAppLabel(singleNode.extension);
    els.selectionSummary.innerHTML = `
      <div class="summary-single">
        <span class="summary-file-name" title="${escapeHtml(singleNode.name)}">${escapeHtml(singleNode.name)}</span>
        <button class="summary-open-btn" id="summaryOpenBtn" type="button" title="Открыть файл в ${escapeHtml(appLabel)}">
          ↗ ${escapeHtml(appLabel)}
        </button>
      </div>
    `;
    const btn = els.selectionSummary.querySelector("#summaryOpenBtn");
    if (btn) {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        openFileByPath(singleNode.path).catch(showOperationError);
      });
    }
    return;
  }

  const dwgFiles = selectedNodes.filter((item) => item.type === "file" && item.extension === "DWG");
  const dwgWithPdf = dwgFiles.filter((item) => findPdfPairForDwg(item, state.pdfPairIndex)).length;
  const dwgText = dwgFiles.length ? ` · DWG с PDF: ${dwgWithPdf}/${dwgFiles.length}` : "";
  els.selectionSummary.textContent = `Выбрано: ${selected.length} · файлов: ${files} · папок: ${folders}${dwgText}`;
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
  if (state.selectedPaths.size === 1) {
    const selectedPath = Array.from(state.selectedPaths)[0];
    const selectedItem = state.visibleRows.find((item) => item.path === selectedPath);
    if (selectedItem && selectedItem.type === "file") {
      setActiveNativePath(selectedItem.path);
    } else {
      setActiveNativePath("");
    }
  } else {
    setActiveNativePath("");
  }
  renderTree();
}

async function copyPathToClipboard(path) {
  if (!path) return;
  try {
    await navigator.clipboard.writeText(path);
    els.selectionSummary.textContent = "Путь скопирован";
  } catch {
    const fallback = document.createElement("textarea");
    fallback.value = path;
    fallback.setAttribute("readonly", "");
    fallback.style.position = "fixed";
    fallback.style.left = "-9999px";
    document.body.append(fallback);
    fallback.select();
    document.execCommand("copy");
    fallback.remove();
    els.selectionSummary.textContent = "Путь скопирован";
  }
  window.setTimeout(updateSelectionSummary, 1100);
}

function renderTreeNode(node, parent) {
  if (!nodeMatches(node)) return;
  const row = document.createElement("div");
  row.className = `tree-row ${node.type}`;
  row.dataset.path = node.path;
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
  metaEl.textContent = node.type === "file" ? "" : (node.children || []).length;
  const diffStatus = state.diffStatus.get(node.path);
  if (node.type === "file" && diffStatus) {
    const diffBadge = document.createElement("span");
    diffBadge.className = `diff-badge diff-${diffStatus}`;
    diffBadge.textContent = diffStatusText(diffStatus);
    nameEl.append(" ", diffBadge);
  }
  if (node.type === "folder" && state.diffSummary) {
    const counts = countDiffDescendants(node);
    const parts = [];
    if (counts.added) parts.push(`+${counts.added}`);
    if (counts.changed) parts.push(`~${counts.changed}`);
    if (counts.removed) parts.push(`-${counts.removed}`);
    if (parts.length) {
      const diffFolderBadge = document.createElement("span");
      diffFolderBadge.className = "diff-badge diff-folder";
      diffFolderBadge.textContent = parts.join(" ");
      nameEl.append(" ", diffFolderBadge);
    }
  }
  if (node.type === "file" && node.extension === "DWG") {
    const pdfPair = findPdfPairForDwg(node, state.pdfPairIndex);
    if (pdfPair) {
      const pairBadge = document.createElement("span");
      pairBadge.className = "pair-badge";
      pairBadge.textContent = "↔";
      pairBadge.title = `Связан с PDF-превью: ${pdfPair.node.name}${pdfPair.confidence === "probable" ? " (вероятная пара)" : ""}`;
      nameEl.append(" ", pairBadge);
    }
  }
  const copyButton = document.createElement("button");
  copyButton.type = "button";
  copyButton.className = "copy-path-button";
  copyButton.textContent = "⧉";
  copyButton.title = "Скопировать полный путь";
  copyButton.setAttribute("aria-label", "Скопировать полный путь");

  let openButton = null;
  if (node.type === "file") {
    openButton = document.createElement("button");
    openButton.type = "button";
    openButton.className = "open-native-row-button";
    openButton.textContent = "↗";
    const appLabel = getNativeAppLabel(node.extension);
    openButton.title = `Открыть в ${appLabel}`;
    openButton.setAttribute("aria-label", openButton.title);
    openButton.addEventListener("click", (event) => {
      event.stopPropagation();
      event.preventDefault();
      openFileByPath(node.path).catch(showOperationError);
    });
  }

  row.append(iconEl, nameEl, metaEl, copyButton);
  if (openButton) row.append(openButton);

  row.addEventListener("click", (event) => {
    event.stopPropagation();
    selectNode(node, event);
  });
  copyButton.addEventListener("click", (event) => {
    event.stopPropagation();
    copyPathToClipboard(node.path);
  });
  row.addEventListener("dblclick", (event) => {
    event.stopPropagation();
    if (node.type === "folder") {
      if (state.collapsedFolders.has(node.path)) state.collapsedFolders.delete(node.path);
      else state.collapsedFolders.add(node.path);
      renderTree();
      return;
    }
    const index = state.visibleRows.findIndex((item) => item.path === node.path);
    state.selectedPaths.clear();
    state.selectedPaths.add(node.path);
    state.lastSelectedIndex = index;
    renderTree();
    openFileByPathDeduped(node.path);
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
  const preferred = ["PDF", "DWG", "XLSX", "XLS", "XLSM", "GSHEET", "DOCX", "DOC", "GDOC", "TXT", "PNG", "JPG", "JPEG", "PPTX", "SVG"];
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
    button.title = `Выбрать все ${ext}. Повторное нажатие снимает выбор и фильтр.`;
    button.addEventListener("click", () => {
      state.selectedPaths.clear();
      if (state.activeFilter === ext) {
        state.activeFilter = "";
      } else {
        state.activeFilter = ext;
        if (state.currentManifest?.tree) {
          flattenTree(state.currentManifest.tree, [])
            .filter((node) => node.type === "file" && node.extension === ext)
            .forEach((node) => state.selectedPaths.add(node.path));
        }
      }
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
  state.pdfPairIndex = buildPdfPairIndex(flattenTree(state.currentManifest.tree, []));
  renderTreeNode(state.currentManifest.tree, els.objectTree);
  if (state.diffRemovedNodes.length && !state.diffFilter) {
    const removedTitle = document.createElement("div");
    removedTitle.className = "diff-removed-title";
    removedTitle.textContent = "Удалённые файлы";
    els.objectTree.append(removedTitle);
    state.diffRemovedNodes.forEach((node) => {
      const row = document.createElement("div");
      row.className = "tree-row file diff-removed-row";
      row.dataset.path = node.path;
      row.title = `${node.path}\nФайл удалён из исходной папки, но превью сохранено.`;
      const iconEl = document.createElement("span");
      iconEl.textContent = "•";
      const nameEl = document.createElement("span");
      nameEl.className = "tree-name";
      nameEl.textContent = node.name;
      const badge = document.createElement("span");
      badge.className = "diff-badge diff-removed";
      badge.textContent = "удалён";
      nameEl.append(" ", badge);
      row.append(iconEl, nameEl);
      row.addEventListener("click", (event) => {
        event.stopPropagation();
        selectNode(node, event);
      });
      els.objectTree.append(row);
      state.visibleRows.push(node);
    });
  }
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
  state.diffFilter = false;
  state.collapsedFolders.clear();
  state.renderedPages = [];
  buildDiffState(manifest, null);
  renderDiffSummary();
  setMode("tree");
  setTreeBrowseMode(true);
  renderFormats();
  renderTree();
  startDiffPolling();
  finishProgress("Структура открыта");
}

function collectPreviewFilesForDisplay() {
  if (!state.currentManifest?.tree) return [];
  const allNodes = flattenTree(state.currentManifest.tree, []);
  const selectedNodes = allNodes.filter((node) => state.selectedPaths.has(node.path));
  const pdfIndex = buildPdfPairIndex(allNodes);
  const result = [];
  const directPdfPaths = new Set();
  const directSourcePaths = new Set();

  function addPreviewFile(node) {
    if (!node || node.type !== "file") return;
    if (node.name.startsWith("~$") || node.name.startsWith(".~")) return;
    const ext = (node.extension || "").toUpperCase();

    if (ext === "PDF" && !directPdfPaths.has(node.path)) {
      directPdfPaths.add(node.path);
      result.push(node);
    } else if (["DOC", "DOCX", "RTF"].includes(ext) && !directSourcePaths.has(node.path)) {
      directSourcePaths.add(node.path);
      result.push({
        ...node,
        previewType: "WORD",
        previewFor: {
          type: ext,
          name: node.name,
          path: node.path,
        },
      });
    } else if (["XLS", "XLSX", "XLSM", "CSV"].includes(ext) && !directSourcePaths.has(node.path)) {
      directSourcePaths.add(node.path);
      result.push({
        ...node,
        previewType: "EXCEL",
        previewFor: {
          type: ext,
          name: node.name,
          path: node.path,
        },
      });
    } else if (ext === "DWG") {
      const pair = findPdfPairForDwg(node, pdfIndex);
      if (pair) {
        result.push({
          ...pair.node,
          previewFor: {
            type: "DWG",
            name: node.name,
            path: node.path,
            confidence: pair.confidence,
          },
        });
      } else {
        result.push({
          ...node,
          previewType: "DWG_MODEL",
          previewFor: {
            type: "DWG",
            name: node.name,
            path: node.path,
          },
        });
      }
    } else if (["JPG", "JPEG", "PNG", "BMP", "WEBP", "SVG", "GIF"].includes(ext) && !directSourcePaths.has(node.path)) {
      directSourcePaths.add(node.path);
      result.push({
        ...node,
        previewType: "IMAGE",
        url: `/api/file/raw?path=${encodeURIComponent(node.path)}`,
        previewFor: {
          type: ext,
          name: node.name,
          path: node.path,
        },
      });
    } else if (["GDOC", "GSHEET", "GSLIDES"].includes(ext) && !directSourcePaths.has(node.path)) {
      directSourcePaths.add(node.path);
      const isSheet = ext === "GSHEET";
      const isSlides = ext === "GSLIDES";
      const label = isSheet ? "Google Sheets" : (isSlides ? "Google Slides" : "Google Docs");
      result.push({
        type: "native-file",
        name: node.name,
        documentPath: node.path,
        sourcePath: node.path,
        sourceType: ext,
        message: `${label}: документ Google Drive. Нажмите кнопку, чтобы открыть в браузере.`,
      });
    } else if (["ZIP", "RAR", "7Z", "TAR", "GZ"].includes(ext) && !directSourcePaths.has(node.path)) {
      directSourcePaths.add(node.path);
      result.push({
        type: "native-file",
        name: node.name,
        documentPath: node.path,
        sourcePath: node.path,
        sourceType: ext,
        message: `Архив ${ext}: нажмите кнопку, чтобы открыть в Проводнике Windows или архиваторе.`,
      });
    } else if (!directSourcePaths.has(node.path)) {
      directSourcePaths.add(node.path);
      result.push({
        type: "native-file",
        name: node.name,
        documentPath: node.path,
        sourcePath: node.path,
        sourceType: ext,
        message: `Файл .${ext.toLowerCase()}: нажмите кнопку для открытия в программе Windows по умолчанию.`,
      });
    }
  }

  if (selectedNodes.length) {
    selectedNodes.forEach((node) => {
      if (node.type === "file") addPreviewFile(node);
      if (node.type === "folder") {
        allNodes
          .filter((candidate) => candidate.path !== node.path && candidate.path.startsWith(node.path))
          .forEach(addPreviewFile);
      }
    });
  }

  return result;
}

function clearExcelViewer() {
  state.excelWorkbook = null;
  state.excelWorkbooks = [];
  state.excelWorkbookIndex = 0;
  state.excelSheetIndex = 0;
  state.excelScale = 1;
  state.view.rotation = 0;
  els.excelViewer.hidden = true;
  els.excelBookTitle.textContent = "";
  els.excelBookTitle.title = "";
  els.excelTabs.replaceChildren();
  els.excelSheetFrame.removeAttribute("src");
}

function resetPdfPreview() {
  state.activePageKey = "";
  state.activePageUrl = "";
  state.renderedPages = [];
  els.pdfPageImage.hidden = true;
  els.pdfPageImage.removeAttribute("src");
  els.viewerEmpty.hidden = true;
  els.viewerEmpty.textContent = "";
  setQualityBadge("");
  updateViewTransform();
}

async function activateExcelSheet(index) {
  const workbook = state.excelWorkbook;
  const sheet = workbook?.sheets?.[index];
  if (!sheet) return;
  if (sheet.warming) await sheet.warming;
  if (!sheet.url) {
    const response = await fetch("/api/excel/sheet", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ file: workbook.path, sheetIndex: index }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Лист Excel не подготовлен");
    Object.assign(sheet, payload);
  }
  state.excelSheetIndex = index;
  [...els.excelTabs.querySelectorAll(".excel-tab")].forEach((tab) => {
    tab.classList.toggle("active", Number(tab.dataset.sheetIndex) === index);
  });
  els.excelSheetFrame.src = sheet.url;
}

async function warmExcelWorkbook(workbook, activeIndex) {
  // The first sheet is shown immediately.  The remaining tabs are prepared
  // one by one in the background, so normal tab switches use only the cache.
  for (let index = 0; index < (workbook.sheets || []).length; index += 1) {
    if (index === activeIndex) continue;
    const sheet = workbook.sheets[index];
    if (!sheet || sheet.url || sheet.warming) continue;
    sheet.warming = fetch("/api/excel/sheet", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ file: workbook.path, sheetIndex: index }),
    })
      .then(async (response) => {
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.error || "Excel sheet preparation failed");
        Object.assign(sheet, payload);
      })
      .catch((error) => console.warn("Excel background sheet preparation failed", error))
      .finally(() => { delete sheet.warming; });
    await sheet.warming;
  }
}

function renderExcelWorkbookRail() {
  els.pdfThumbs.replaceChildren();
  state.excelWorkbooks.forEach((workbook, index) => {
    const thumb = document.createElement("button");
    thumb.type = "button";
    thumb.className = "pdf-thumb excel-book-thumb";
    thumb.classList.toggle("active", index === state.excelWorkbookIndex);
    thumb.title = workbook.name;
    const preview = document.createElement("div");
    preview.className = "excel-book-preview";
    const frame = document.createElement("iframe");
    frame.src = workbook.thumbnailUrl || "about:blank";
    frame.title = `Миниатюра ${workbook.name}`;
    frame.tabIndex = -1;
    preview.append(frame);
    const label = document.createElement("span");
    label.textContent = workbook.name;
    thumb.append(preview, label);
    thumb.addEventListener("click", () => activateExcelWorkbook(index).catch(showOperationError));
    els.pdfThumbs.append(thumb);
  });
}

async function activateExcelWorkbook(index) {
  const workbook = state.excelWorkbooks[index];
  if (!workbook) return;
  state.excelWorkbook = workbook;
  state.excelWorkbookIndex = index;
  state.excelSheetIndex = 0;
  state.excelScale = 1;
  els.excelBookTitle.textContent = workbook.name;
  els.excelBookTitle.title = workbook.name;
  renderExcelWorkbookRail();
  els.pdfViewer.classList.remove("empty");
  els.pdfPageImage.hidden = true;
  els.pdfPageImage.removeAttribute("src");
  els.viewerEmpty.hidden = true;
  els.qualityBadge.hidden = true;
  els.excelTabs.replaceChildren();
  (workbook.sheets || []).forEach((sheet) => {
    const tab = document.createElement("button");
    tab.type = "button";
    tab.className = "excel-tab";
    tab.dataset.sheetIndex = String(sheet.index);
    tab.title = `${sheet.name} · ${sheet.rows} строк · ${sheet.columns} столбцов`;
    tab.textContent = sheet.name;
    tab.addEventListener("click", () => activateExcelSheet(sheet.index).catch(showOperationError));
    els.excelTabs.append(tab);
  });
  els.excelViewer.hidden = false;
  els.viewerControls.hidden = false;
  els.viewRotate.hidden = false;
  els.viewPanMode.hidden = false;
  setActiveNativePath(workbook.path);
  updateViewTransform();
  await activateExcelSheet(0);
  window.setTimeout(() => warmExcelWorkbook(workbook, 0), 250);
}

async function showExcelWorkbooks(workbooks) {
  state.excelWorkbooks = workbooks;
  await activateExcelWorkbook(0);
}

function renderPdfViewer(pages) {
  clearExcelViewer();
  els.viewRotate.hidden = false;
  els.viewPanMode.hidden = false;
  state.renderedPages = pages;
  els.pdfThumbs.replaceChildren();
  els.pdfViewer.classList.toggle("empty", !pages.length);
  if (!pages.length) {
    if (!state.activePageKey) {
      els.pdfPageImage.hidden = true;
    }
    els.viewerEmpty.hidden = true;
    els.viewerEmpty.textContent = "";
    setQualityBadge("");
    return;
  }
  els.viewerEmpty.hidden = true;

  pages.forEach((page) => {
    const key = pageKey(page);
    const thumb = document.createElement("button");
    thumb.type = "button";
    thumb.className = "pdf-thumb";
    thumb.classList.toggle("missing-preview", page.type === "missing-preview");
    thumb.dataset.pageKey = key;
    thumb.classList.toggle("active", key === state.activePageKey);
    thumb.title = page.name;

    if (page.type === "missing-preview" || page.type === "native-file") {
      const missing = document.createElement("div");
      missing.className = "missing-preview-card";
      const ext = (page.sourceType || "").toUpperCase();
      let icon = "📄";
      if (ext === "GDOC") icon = "🌐";
      else if (ext === "GSHEET") icon = "📊";
      else if (ext === "GSLIDES") icon = "📽️";
      else if (["ZIP", "RAR", "7Z"].includes(ext)) icon = "📦";
      else if (ext === "DWG") icon = "📐";
      missing.textContent = `${icon} ${ext || "Файл"}`;
      thumb.append(missing);
    } else {
      const img = document.createElement("img");
      img.src = page.url;
      img.alt = page.name;
      img.draggable = false;
      thumb.append(img);
    }
    const label = document.createElement("span");
    label.textContent = page.name;
    thumb.append(label);
    thumb.addEventListener("click", () => showPdfPage(page));
    els.pdfThumbs.append(thumb);
  });

  const currentPage = pages.find((page) => pageKey(page) === state.activePageKey);
  if (currentPage) {
    updateActivePdfThumb();
    return;
  }
  // The active page belongs to a previous file selection.  Show the first
  // page of the newly rendered set and drop the stale large image so the
  // viewer never keeps showing the old document.
  showPdfPage(pages[0]);
}

function pageKey(page) {
  if (page.type === "missing-preview" || page.type === "native-file") return `native|${page.sourcePath || page.documentPath || page.name}`;
  return `${page.documentPath || ""}|${page.page || ""}`;
}

function updateActivePdfThumb() {
  [...els.pdfThumbs.querySelectorAll(".pdf-thumb")].forEach((thumb) => {
    thumb.classList.toggle("active", thumb.dataset.pageKey === state.activePageKey);
  });
}

function setQualityBadge(textValue, mode = "") {
  els.qualityBadge.hidden = !textValue;
  els.qualityBadge.textContent = textValue || "";
  els.qualityBadge.classList.toggle("loading", mode === "loading");
  els.qualityBadge.classList.toggle("ready", mode === "ready");
}

function setActiveNativePath(path) {
  state.activeNativePath = path || "";
  els.openNativeFile.hidden = !state.activeNativePath;
  if (!state.activeNativePath) return;

  const ext = fileExtensionFromPath(state.activeNativePath);
  const appLabel = getNativeAppLabel(ext);
  els.openNativeFile.textContent = "Открыть";
  els.openNativeFile.title = `Открыть исходный файл в ${appLabel} (${state.activeNativePath})`;
  if (els.viewerControls) els.viewerControls.hidden = false;
}

async function openActiveNativeFile() {
  if (!state.activeNativePath) return;
  await openFileByPath(state.activeNativePath);
}

async function requestHighQualityPage(page) {
  // A0 Model Space maps can exceed 100 million pixels at 300 DPI.  They are
  // intentionally an orientation preview; exact inspection belongs to the
  // native DWG application.  Do not make every card click wait a minute.
  if (page.previewType === "DWG_MODEL") {
    if (state.activePageKey === pageKey(page)) {
      setQualityBadge(`Model Space · обзор ${page.dpi || PDF_PREVIEW_DPI} DPI`);
    }
    return;
  }
  if (!page.documentPath || !page.page || page.dpi >= PDF_QUALITY_DPI) return;
  const key = pageKey(page);
  if (state.highQualityPages.has(key)) {
    const cached = state.highQualityPages.get(key);
    if (state.activePageKey === key) {
      state.activePageUrl = cached.url;
      els.pdfPageImage.src = cached.url;
      setQualityBadge(`Качество ${PDF_QUALITY_DPI} DPI`, "ready");
    }
    return;
  }
  if (state.activePageKey === key) {
    setQualityBadge(`Качество ${PDF_QUALITY_DPI} DPI загружается…`, "loading");
  }
  try {
    const endpoint = page.previewType === "WORD"
      ? "/api/word/page"
      : page.previewType === "DWG_MODEL"
        ? "/api/dwg/model-page"
        : page.previewType === "EXCEL"
          ? "/api/excel/page"
          : "/api/pdf/page";
    const sourceFile = ["WORD", "DWG_MODEL", "EXCEL"].includes(page.previewType)
      ? page.previewFor?.path
      : page.documentPath;
    const response = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ file: sourceFile, page: page.page, dpi: PDF_QUALITY_DPI }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "PDF page render failed");
    const highPage = {
      ...page,
      ...payload.item,
      documentPath: payload.path,
      dpi: payload.dpi,
      cacheHit: payload.cacheHit,
    };
    state.highQualityPages.set(key, highPage);
    if (state.activePageKey === key) {
      state.activePageUrl = highPage.url;
      els.pdfPageImage.src = highPage.url;
      setQualityBadge(`Качество ${PDF_QUALITY_DPI} DPI`, "ready");
    }
  } catch (error) {
    console.warn("High quality PDF page render failed", { page, error });
    if (state.activePageKey === key) {
      setQualityBadge(`Обзор ${page.dpi || PDF_PREVIEW_DPI} DPI · качество недоступно`, "");
    }
  }
}

function showPdfPage(page) {
  const key = pageKey(page);
  state.activePageKey = key;

  if (page.previewType === "IMAGE") {
    clearExcelViewer();
    setActiveNativePath(page.path || page.sourcePath);
    state.activePageUrl = page.url;
    els.pdfPageImage.src = page.url;
    els.pdfPageImage.hidden = false;
    els.viewerEmpty.hidden = true;
    els.pdfViewer.classList.remove("empty");
    els.viewerControls.hidden = false;
    els.viewRotate.hidden = false;
    els.viewPanMode.hidden = false;
    setQualityBadge("Изображение");
    updateActivePdfThumb();
    if (els.pdfPageImage.complete && els.pdfPageImage.naturalWidth) fitPdfPage();
    return;
  }

  if (page.type === "missing-preview" || page.type === "native-file") {
    clearExcelViewer();
    const sourcePath = page.sourcePath || page.documentPath || "";
    setActiveNativePath(sourcePath);
    state.activePageUrl = "";
    els.pdfPageImage.hidden = true;
    els.pdfPageImage.removeAttribute("src");
    els.viewerEmpty.hidden = false;

    const ext = (page.sourceType || "").toUpperCase();
    const appLabel = getNativeAppLabel(ext);
    let icon = "📄";
    if (ext === "GDOC") icon = "🌐";
    else if (ext === "GSHEET") icon = "📊";
    else if (ext === "GSLIDES") icon = "📽️";
    else if (["ZIP", "RAR", "7Z"].includes(ext)) icon = "📦";
    else if (ext === "DWG") icon = "📐";
    else if (["DOC", "DOCX"].includes(ext)) icon = "📘";
    else if (["XLS", "XLSX"].includes(ext)) icon = "📗";

    els.viewerEmpty.innerHTML = `
      <div class="native-file-card">
        <div class="native-file-icon">${icon}</div>
        <div class="native-file-name">${escapeHtml(page.name)}</div>
        <div class="native-file-message">${escapeHtml(page.message || "")}</div>
        <div class="native-file-path" title="${escapeHtml(sourcePath)}">${escapeHtml(sourcePath)}</div>
        <button class="primary-btn native-file-open-btn" id="nativeCardOpenBtn" type="button">
          ↗ Открыть в ${escapeHtml(appLabel)}
        </button>
      </div>
    `;

    const openBtn = els.viewerEmpty.querySelector("#nativeCardOpenBtn");
    if (openBtn) {
      openBtn.addEventListener("click", () => {
        openActiveNativeFile().catch(showOperationError);
      });
    }

    els.pdfViewer.classList.remove("empty");
    els.viewerControls.hidden = false;
    setQualityBadge(ext ? `Файл .${ext.toLowerCase()}` : "Файл");
    updateActivePdfThumb();
    return;
  }

  clearExcelViewer();
  const highPage = state.highQualityPages.get(key);
  const displayPage = highPage || page;
  setActiveNativePath(page.previewFor?.path || page.sourcePath || page.documentPath || "");
  state.activePageUrl = displayPage.url;
  els.pdfPageImage.src = displayPage.url;
  els.pdfPageImage.hidden = false;
  els.viewerEmpty.hidden = true;
  els.pdfViewer.classList.remove("empty");
  els.viewerControls.hidden = false;
  els.viewRotate.hidden = false;
  els.viewPanMode.hidden = false;
  setQualityBadge(
    displayPage.dpi >= PDF_QUALITY_DPI
      ? `Качество ${displayPage.dpi} DPI`
      : `Обзор ${displayPage.dpi || PDF_PREVIEW_DPI} DPI`,
    displayPage.dpi >= PDF_QUALITY_DPI ? "ready" : "",
  );
  updateActivePdfThumb();
  if (els.pdfPageImage.complete && els.pdfPageImage.naturalWidth) fitPdfPage();
  requestHighQualityPage(page);
}

function updateViewTransform() {
  const view = state.view;
  els.pdfPageImage.style.transform = [
    "translate(-50%, -50%)",
    `translate(${view.panX}px, ${view.panY}px)`,
    `rotate(${view.rotation}deg)`,
    `scale(${view.scale})`,
  ].join(" ");
  els.pdfStage.classList.toggle("pan-mode", view.panMode);
  els.pdfStage.classList.toggle("dragging", view.dragging);
  els.viewPanMode.classList.toggle("active", view.panMode);
  if (state.excelWorkbook) {
    els.excelSheetFrame.contentWindow?.postMessage({ type: "launcher-sheet-hand", value: view.panMode }, "*");
    els.excelSheetFrame.contentWindow?.postMessage({ type: "launcher-sheet-rotate", value: view.rotation }, "*");
  }
}

function fitPdfPage() {
  if (state.excelWorkbook) {
    els.excelSheetFrame.contentWindow?.postMessage({ type: "launcher-sheet-fit" }, "*");
    return;
  }
  if (!els.pdfPageImage.naturalWidth || !els.pdfPageImage.naturalHeight) return;
  const stage = els.pdfStage.getBoundingClientRect();
  const rotated = Math.abs(state.view.rotation % 180) === 90;
  const imageWidth = rotated ? els.pdfPageImage.naturalHeight : els.pdfPageImage.naturalWidth;
  const imageHeight = rotated ? els.pdfPageImage.naturalWidth : els.pdfPageImage.naturalHeight;
  const availableWidth = Math.max(100, stage.width - 36);
  const availableHeight = Math.max(100, stage.height - 86);
  const fit = Math.min(availableWidth / imageWidth, availableHeight / imageHeight);
  state.view.fitScale = fit || 1;
  state.view.scale = state.view.fitScale;
  state.view.panX = 0;
  state.view.panY = 0;
  updateViewTransform();
}

function zoomPdf(factor) {
  if (state.excelWorkbook) {
    state.excelScale = Math.min(3, Math.max(0.35, state.excelScale * factor));
    els.excelSheetFrame.contentWindow?.postMessage({ type: "launcher-sheet-zoom", value: state.excelScale }, "*");
    return;
  }
  if (els.pdfPageImage.hidden) return;
  state.view.scale = Math.min(8, Math.max(0.05, state.view.scale * factor));
  updateViewTransform();
}

function setViewerMode(mode) {
  state.viewMode = mode;
  els.shell.classList.toggle("medium-view", mode === "medium");
  els.shell.classList.toggle("full-view", mode === "full");
  els.viewStandardMode.classList.toggle("active", mode === "standard");
  els.viewMediumMode.classList.toggle("active", mode === "medium");
  els.viewFullMode.classList.toggle("active", mode === "full");
  requestAnimationFrame(() => fitPdfPage());
}

function chunkItems(items, size) {
  const chunks = [];
  for (let index = 0; index < items.length; index += size) {
    chunks.push(items.slice(index, index + size));
  }
  return chunks;
}

const PDF_RENDER_CONCURRENCY = 3;
const PDF_FETCH_TIMEOUT_MS = 90000;
const DIFF_POLL_INTERVAL_MS = 15000;
const PDF_PREVIEW_DPI = 150;
const PDF_QUALITY_DPI = 300;

async function renderExcelWorkbooks(excelFiles) {
  setTreeBrowseMode(false);
  setViewerMode("standard");
  resetPdfPreview();
  startProgress("Подготовка Excel", `${excelFiles.length} книг · HTML-просмотр без редактирования`);
  const workbooks = [];
  for (let index = 0; index < excelFiles.length; index += 1) {
    const excelFile = excelFiles[index];
    const controller = createOperationController();
    const response = await fetch("/api/excel/workbook", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ file: excelFile.path }),
      signal: controller.signal,
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || `Excel-книга не подготовлена: ${excelFile.name}`);
    workbooks.push(payload);
    const percent = Math.round(((index + 1) / excelFiles.length) * 100);
    els.progressValue.textContent = `${percent}%`;
    els.progressFill.style.width = `${percent}%`;
    els.progressDetail.textContent = `Книга ${index + 1} из ${excelFiles.length}: ${excelFile.name}`;
  }
  await showExcelWorkbooks(workbooks);
  const sheets = workbooks.reduce((total, workbook) => total + (workbook.sheets?.length || 0), 0);
  finishProgress(`${workbooks.length} книг · ${sheets} листов · лимит ${workbooks[0]?.maxRows || 2000} строк на лист`);
}

async function renderSelectedFiles() {
  const previewItems = collectPreviewFilesForDisplay();
  const excelItems = previewItems.filter((item) => item.previewType === "EXCEL");
  if (excelItems.length) {
    if (previewItems.length !== excelItems.length) {
      startProgress("Выберите файлы одного типа", "Excel-книги открываются отдельной лентой миниатюр.");
      finishProgress("Отобразите Excel отдельно от PDF, DWG и Word.");
      return;
    }
    await renderExcelWorkbooks(excelItems);
    return;
  }
  await renderSelectedPdfFiles(previewItems);
}

async function renderSelectedPdfFiles(previewItems = collectPreviewFilesForDisplay()) {
  if (!previewItems.length) {
    startProgress("Превью не найдено", "Выберите PDF, DWG или Word.");
    finishProgress("Превью не найдено");
    return;
  }

  setTreeBrowseMode(false);
  setViewerMode("standard");
  resetPdfPreview();

  const batches = chunkItems(previewItems, 1);
  const pageGroups = batches.map((batch) => {
    const item = batch[0];
    if (item?.type === "missing-preview" || item?.type === "native-file" || item?.previewType === "IMAGE") {
      return [item];
    }
    return [];
  });
  const renderableBatchCount = batches.filter((batch) => {
    const item = batch[0];
    return item?.type !== "missing-preview" && item?.type !== "native-file" && item?.previewType !== "IMAGE";
  }).length;
  const allErrors = [];
  let totalPages = 0;
  let renderedPages = 0;
  let nextBatchIndex = 0;
  let completedBatches = batches.length - renderableBatchCount;

  startProgress("Рендер превью", `${previewItems.length} элементов · быстрый обзор ${PDF_PREVIEW_DPI} DPI · качество ${PDF_QUALITY_DPI} DPI по клику`);

  function refreshRenderProgress() {
    const percent = Math.min(99, Math.round((completedBatches / batches.length) * 100));
    els.progressValue.textContent = `${percent}%`;
    els.progressFill.style.width = `${percent}%`;
    els.progressDetail.textContent = `${previewItems.length} элементов · готово ${completedBatches} из ${batches.length} · стр. ${renderedPages}`;
    renderPdfViewer(pageGroups.flat());
  }

  async function renderBatch(batchIndex) {
    const batch = batches[batchIndex];
    if (batch[0]?.type === "missing-preview" || batch[0]?.type === "native-file" || batch[0]?.previewType === "IMAGE") return;
    let controller = null;
    try {
      controller = new AbortController();
      state.operationControllers.push(controller);
      const timeoutId = setTimeout(() => controller.abort(), PDF_FETCH_TIMEOUT_MS);
      const endpoint = batch[0]?.previewType === "WORD"
        ? "/api/word/render"
        : batch[0]?.previewType === "DWG_MODEL"
          ? "/api/dwg/model-render"
          : batch[0]?.previewType === "EXCEL"
            ? "/api/excel/render"
            : "/api/pdf/render";
      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ files: batch.map((file) => file.path), dpi: PDF_PREVIEW_DPI }),
        signal: controller.signal,
      });
      clearTimeout(timeoutId);
      const payload = await response.json();
      if (!response.ok) {
        allErrors.push({
          document: batch[0]?.name || "PDF",
          path: batch[0]?.path || "",
          error: payload.error || "PDF не отрендерен",
        });
        if (batch[0]?.previewType === "EXCEL") {
          pageGroups[batchIndex] = [{
            type: "missing-preview",
            name: batch[0]?.name || "Excel",
            documentPath: batch[0]?.path || "",
            sourcePath: batch[0]?.path || "",
            sourceType: batch[0]?.extension || "EXCEL",
            message: "Excel-preview сейчас недоступен. Откройте исходную книгу в Excel.",
          }];
        }
      } else {
        totalPages += payload.totalPages || 0;
        renderedPages += payload.renderedPages || 0;
        allErrors.push(...(payload.errors || []));
        pageGroups[batchIndex] = payload.documents.flatMap((document) =>
          document.items.map((page) => ({
            ...page,
            name: `${batch[0]?.previewFor ? batch[0].previewFor.name : document.name} · стр. ${page.page}`,
            documentPath: document.path,
            dpi: payload.dpi,
            cacheHit: document.cacheHit,
            previewFor: batch[0]?.previewFor || null,
            previewType: batch[0]?.previewType || "",
          })),
        );
      }
    } catch (error) {
      if (error?.name === "AbortError") {
        allErrors.push({
          document: batch[0]?.name || "PDF",
          path: batch[0]?.path || "",
          error: "Таймаут запроса PDF. Файл пропущен, обработка продолжается.",
        });
        return;
      }
      allErrors.push({
        document: batch[0]?.name || "PDF",
        path: batch[0]?.path || "",
        error: error.message || String(error),
      });
    } finally {
      if (controller) {
        state.operationControllers = state.operationControllers.filter((item) => item !== controller);
      }
      completedBatches += 1;
      refreshRenderProgress();
    }
  }

  async function worker() {
    while (!state.progressCancelled && nextBatchIndex < batches.length) {
      const batchIndex = nextBatchIndex;
      nextBatchIndex += 1;
      await renderBatch(batchIndex);
    }
  }

  refreshRenderProgress();
  const workerCount = Math.min(PDF_RENDER_CONCURRENCY, renderableBatchCount);
  await Promise.all(Array.from({ length: workerCount }, () => worker()));
  if (state.progressCancelled) return;

  const errorCount = allErrors.length;
  const detail = errorCount
    ? `Показано: ${renderedPages} из ${totalPages} стр. · ошибок: ${errorCount}`
    : `Готово: ${totalPages} стр. · ${previewItems.length} элементов · обзор ${PDF_PREVIEW_DPI} DPI`;
  finishProgress(detail);
  if (errorCount) {
    console.warn("PDF render partial errors", allErrors);
  }
}


if (els.closeLoadModal) els.closeLoadModal.addEventListener("click", closeLoadModal);
if (els.tabQuick) els.tabQuick.addEventListener("click", () => switchModalTab("quick"));
if (els.tabBrowse) els.tabBrowse.addEventListener("click", () => switchModalTab("browse"));
if (els.tabPath) els.tabPath.addEventListener("click", () => switchModalTab("path"));
if (els.btnLoadBrowsedFolder) {
  els.btnLoadBrowsedFolder.addEventListener("click", () => {
    if (state.modal.currentBrowsePath) {
      importObjectByPath(state.modal.currentBrowsePath).catch(showOperationError);
    }
  });
}
if (els.btnOpenInWindowsExplorer) {
  els.btnOpenInWindowsExplorer.addEventListener("click", () => {
    if (state.modal.currentBrowsePath) {
      openInWindowsExplorer(state.modal.currentBrowsePath);
    }
  });
}
if (els.btnLoadManualPath) {
  els.btnLoadManualPath.addEventListener("click", () => {
    const val = els.manualPathInput?.value?.trim();
    if (val) importObjectByPath(val).catch(showOperationError);
  });
}
if (els.manualPathInput) {
  els.manualPathInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      const val = els.manualPathInput.value.trim();
      if (val) importObjectByPath(val).catch(showOperationError);
    }
  });
}
if (els.btnTriggerSystemPicker) {
  els.btnTriggerSystemPicker.addEventListener("click", () => {
    triggerSystemPicker().catch(console.error);
  });
}
if (els.modalDropZone) {
  els.modalDropZone.addEventListener("dragover", (e) => {
    e.preventDefault();
    els.modalDropZone.classList.add("dragover");
  });
  els.modalDropZone.addEventListener("dragleave", () => {
    els.modalDropZone.classList.remove("dragover");
  });
  els.modalDropZone.addEventListener("drop", (e) => {
    e.preventDefault();
    els.modalDropZone.classList.remove("dragover");
    if (e.dataTransfer.files && e.dataTransfer.files.length) {
      // In Chromium webkitRelativePath or path might exist
      const first = e.dataTransfer.files[0];
      const p = first.path || "";
      if (p) {
        importObjectByPath(p).catch(showOperationError);
      }
    }
  });
}

els.load.addEventListener("click", () => importObject(false).catch(showOperationError));
els.refresh.addEventListener("click", () => {
  if (inTreeMode()) refreshObjectInPlace().catch(showOperationError);
  else importObject(true).catch(showOperationError);
});
els.diffFilterToggle.addEventListener("click", () => toggleDiffFilter());
els.display.addEventListener("click", () => {
  if (inTreeMode()) renderSelectedFiles().catch(showOperationError);
  else openSelectedObject().catch(showOperationError);
});
els.exclude.addEventListener("click", () => {
  stopDiffPolling();
  excludeSelectedObject().catch(showOperationError);
});
els.cancel.addEventListener("click", () => stopProgress(true));
els.backToObjects.addEventListener("click", () => {
  stopDiffPolling();
  setMode("objects");
});
els.backToTree.addEventListener("click", () => {
  if (!state.currentManifest?.tree) return;
  setViewerMode("standard");
  setTreeBrowseMode(true);
  renderTree();
});
els.treeSearch.addEventListener("input", () => {
  renderTree();
});
els.pdfPageImage.addEventListener("load", () => fitPdfPage());
els.excelSheetFrame.addEventListener("load", () => {
  if (!state.excelWorkbook) return;
  els.excelSheetFrame.contentWindow?.postMessage({ type: "launcher-sheet-zoom", value: state.excelScale }, "*");
});
els.excelTabsLeft.addEventListener("click", () => {
  els.excelTabs.scrollBy({ left: -Math.max(180, els.excelTabs.clientWidth * .72), behavior: "smooth" });
});
els.excelTabsRight.addEventListener("click", () => {
  els.excelTabs.scrollBy({ left: Math.max(180, els.excelTabs.clientWidth * .72), behavior: "smooth" });
});
els.excelTabs.addEventListener("wheel", (event) => {
  if (!event.shiftKey || !event.deltaY) return;
  event.preventDefault();
  els.excelTabs.scrollLeft += event.deltaY;
}, { passive: false });
els.viewZoomOut.addEventListener("click", () => zoomPdf(0.82));
els.viewZoomIn.addEventListener("click", () => zoomPdf(1.22));
els.viewFit.addEventListener("click", () => fitPdfPage());
els.viewRotate.addEventListener("click", () => {
  state.view.rotation = (state.view.rotation + 90) % 360;
  if (state.excelWorkbook) {
    els.excelSheetFrame.contentWindow?.postMessage({ type: "launcher-sheet-rotate", value: state.view.rotation }, "*");
    els.excelSheetFrame.contentWindow?.postMessage({ type: "launcher-sheet-fit" }, "*");
    return;
  }
  fitPdfPage();
});
els.viewPanMode.addEventListener("click", () => {
  state.view.panMode = !state.view.panMode;
  updateViewTransform();
});
els.openNativeFile.addEventListener("click", () => {
  openActiveNativeFile().catch(showOperationError);
});
els.viewStandardMode.addEventListener("click", () => setViewerMode("standard"));
els.viewMediumMode.addEventListener("click", () => setViewerMode("medium"));
els.viewFullMode.addEventListener("click", () => setViewerMode("full"));

els.pdfStage.addEventListener("wheel", (event) => {
  if (event.target.closest(".viewer-controls")) return;
  if (!event.ctrlKey || (els.pdfPageImage.hidden && !state.excelWorkbook)) return;
  event.preventDefault();
  zoomPdf(event.deltaY < 0 ? 1.12 : 0.89);
}, { passive: false });

els.pdfStage.addEventListener("pointerdown", (event) => {
  if (event.target.closest(".viewer-controls")) return;
  if (!state.view.panMode || els.pdfPageImage.hidden || event.button !== 0) return;
  event.preventDefault();
  state.view.dragging = true;
  state.view.dragStartX = event.clientX;
  state.view.dragStartY = event.clientY;
  state.view.dragPanX = state.view.panX;
  state.view.dragPanY = state.view.panY;
  els.pdfStage.setPointerCapture(event.pointerId);
  updateViewTransform();
});

els.pdfStage.addEventListener("pointermove", (event) => {
  if (!state.view.dragging) return;
  state.view.panX = state.view.dragPanX + (event.clientX - state.view.dragStartX);
  state.view.panY = state.view.dragPanY + (event.clientY - state.view.dragStartY);
  updateViewTransform();
});

function endPdfDrag(event) {
  if (!state.view.dragging) return;
  state.view.dragging = false;
  try {
    els.pdfStage.releasePointerCapture(event.pointerId);
  } catch {
    // Pointer capture may already be released by the browser.
  }
  updateViewTransform();
}

els.pdfStage.addEventListener("pointerup", endPdfDrag);
els.pdfStage.addEventListener("pointercancel", endPdfDrag);

document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  if (els.loadModal && !els.loadModal.hidden) {
    closeLoadModal();
    return;
  }
  if (!els.pdfPageImage.hidden && state.view.dragging) {
    state.view.dragging = false;
    updateViewTransform();
    return;
  }
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
setViewerMode("standard");
loadObjectSummaries().catch((error) => {
  els.objectList.innerHTML = `<div class="empty-note">Ошибка загрузки списка: ${error.message}</div>`;
});
