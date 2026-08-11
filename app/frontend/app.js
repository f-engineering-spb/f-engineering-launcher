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
  highQualityPages: new Map(),
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
};

const els = {
  shell: document.querySelector(".shell"),
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
  pdfThumbs: document.getElementById("pdfThumbs"),
  pdfStage: document.getElementById("pdfStage"),
  pdfPageImage: document.getElementById("pdfPageImage"),
  viewerEmpty: document.getElementById("viewerEmpty"),
  viewerControls: document.getElementById("viewerControls"),
  qualityBadge: document.getElementById("qualityBadge"),
  viewZoomOut: document.getElementById("viewZoomOut"),
  viewZoomIn: document.getElementById("viewZoomIn"),
  viewFit: document.getElementById("viewFit"),
  viewRotate: document.getElementById("viewRotate"),
  viewPanMode: document.getElementById("viewPanMode"),
  viewStandardMode: document.getElementById("viewStandardMode"),
  viewMediumMode: document.getElementById("viewMediumMode"),
  viewFullMode: document.getElementById("viewFullMode"),
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
  updateObjectButtons();
}

function setTreeBrowseMode(enabled) {
  els.shell.classList.toggle("tree-browse", Boolean(enabled));
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
  if (abortRequest && state.operationControllers.length) {
    state.operationControllers.forEach((controller) => controller.abort());
    state.operationControllers = [];
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

function flattenTree(node, result = []) {
  result.push(node);
  for (const child of node.children || []) flattenTree(child, result);
  return result;
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
  setTreeBrowseMode(true);
  renderFormats();
  renderTree();
  finishProgress("Структура открыта");
}

function collectPdfFilesForDisplay() {
  if (!state.currentManifest?.tree) return [];
  const allNodes = flattenTree(state.currentManifest.tree, []);
  const selectedNodes = allNodes.filter((node) => state.selectedPaths.has(node.path));
  const result = new Map();

  function addPdf(node) {
    if (node.type === "file" && node.extension === "PDF") result.set(node.path, node);
  }

  if (selectedNodes.length) {
    selectedNodes.forEach((node) => {
      if (node.type === "file") addPdf(node);
      if (node.type === "folder") {
        allNodes
          .filter((candidate) => candidate.path !== node.path && candidate.path.startsWith(node.path))
          .forEach(addPdf);
      }
    });
  } else {
    state.visibleRows.forEach(addPdf);
  }

  return [...result.values()];
}

function renderPdfViewer(pages) {
  state.renderedPages = pages;
  els.pdfThumbs.replaceChildren();
  if (!pages.length) {
    els.pdfPageImage.hidden = true;
    els.viewerEmpty.hidden = false;
    els.viewerEmpty.textContent = "PDF-страницы не отрендерены.";
    setQualityBadge("");
    return;
  }

  pages.forEach((page, index) => {
    const thumb = document.createElement("button");
    thumb.type = "button";
    thumb.className = "pdf-thumb";
    thumb.classList.toggle("active", index === 0);
    thumb.title = page.name;

    const img = document.createElement("img");
    img.src = page.url;
    img.alt = page.name;
    const label = document.createElement("span");
    label.textContent = page.name;
    thumb.append(img, label);
    thumb.addEventListener("click", () => showPdfPage(page));
    els.pdfThumbs.append(thumb);
  });
  showPdfPage(pages[0]);
}

function pageKey(page) {
  return `${page.documentPath || ""}|${page.page || ""}`;
}

function setQualityBadge(textValue, mode = "") {
  els.qualityBadge.hidden = !textValue;
  els.qualityBadge.textContent = textValue || "";
  els.qualityBadge.classList.toggle("loading", mode === "loading");
  els.qualityBadge.classList.toggle("ready", mode === "ready");
}

async function requestHighQualityPage(page) {
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
    const response = await fetch("/api/pdf/page", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ file: page.documentPath, page: page.page, dpi: PDF_QUALITY_DPI }),
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
  const highPage = state.highQualityPages.get(key);
  const displayPage = highPage || page;
  state.activePageKey = key;
  state.activePageUrl = displayPage.url;
  els.pdfPageImage.src = displayPage.url;
  els.pdfPageImage.hidden = false;
  els.viewerEmpty.hidden = true;
  els.viewerControls.hidden = false;
  setQualityBadge(
    displayPage.dpi >= PDF_QUALITY_DPI
      ? `Качество ${displayPage.dpi} DPI`
      : `Обзор ${displayPage.dpi || PDF_PREVIEW_DPI} DPI`,
    displayPage.dpi >= PDF_QUALITY_DPI ? "ready" : "",
  );
  [...els.pdfThumbs.querySelectorAll(".pdf-thumb")].forEach((thumb) => {
    const img = thumb.querySelector("img");
    thumb.classList.toggle("active", img?.getAttribute("src") === page.url);
  });
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
}

function fitPdfPage() {
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
const PDF_PREVIEW_DPI = 150;
const PDF_QUALITY_DPI = 300;

async function renderSelectedPdfFiles() {
  const pdfFiles = collectPdfFilesForDisplay();
  if (!pdfFiles.length) {
    startProgress("PDF не выбран", "Выберите PDF-файл, папку с PDF или включите фильтр PDF.");
    finishProgress("PDF не выбран");
    return;
  }

  setTreeBrowseMode(false);
  setViewerMode("standard");

  const batches = chunkItems(pdfFiles, 1);
  const pageGroups = Array.from({ length: batches.length }, () => []);
  const allErrors = [];
  let totalPages = 0;
  let renderedPages = 0;
  let nextBatchIndex = 0;
  let completedBatches = 0;

  startProgress("Рендер PDF", `${pdfFiles.length} PDF · быстрый обзор ${PDF_PREVIEW_DPI} DPI · качество ${PDF_QUALITY_DPI} DPI по клику`);

  function refreshRenderProgress() {
    const percent = Math.min(99, Math.round((completedBatches / batches.length) * 100));
    els.progressValue.textContent = `${percent}%`;
    els.progressFill.style.width = `${percent}%`;
    els.progressDetail.textContent = `${pdfFiles.length} PDF · готово ${completedBatches} из ${batches.length} · стр. ${renderedPages}`;
    renderPdfViewer(pageGroups.flat());
  }

  async function renderBatch(batchIndex) {
    const batch = batches[batchIndex];
    let controller = null;
    try {
      controller = new AbortController();
      state.operationControllers.push(controller);
      const timeoutId = setTimeout(() => controller.abort(), PDF_FETCH_TIMEOUT_MS);
      const response = await fetch("/api/pdf/render", {
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
      } else {
        totalPages += payload.totalPages || 0;
        renderedPages += payload.renderedPages || 0;
        allErrors.push(...(payload.errors || []));
        pageGroups[batchIndex] = payload.documents.flatMap((document) =>
          document.items.map((page) => ({
            ...page,
            name: `${document.name} · стр. ${page.page}`,
            documentPath: document.path,
            dpi: payload.dpi,
            cacheHit: document.cacheHit,
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

  const workerCount = Math.min(PDF_RENDER_CONCURRENCY, batches.length);
  await Promise.all(Array.from({ length: workerCount }, () => worker()));
  if (state.progressCancelled) return;

  const errorCount = allErrors.length;
  const detail = errorCount
    ? `Показано: ${renderedPages} из ${totalPages} стр. · ошибок: ${errorCount}`
    : `Готово: ${totalPages} стр. · ${pdfFiles.length} PDF · обзор ${PDF_PREVIEW_DPI} DPI`;
  finishProgress(detail);
  if (errorCount) {
    console.warn("PDF render partial errors", allErrors);
  }
}

els.load.addEventListener("click", () => importObject(false).catch(showOperationError));
els.refresh.addEventListener("click", () => {
  if (inTreeMode()) importObject(true).then(openSelectedObject).catch(showOperationError);
  else importObject(true).catch(showOperationError);
});
els.display.addEventListener("click", () => {
  if (inTreeMode()) renderSelectedPdfFiles().catch(showOperationError);
  else openSelectedObject().catch(showOperationError);
});
els.exclude.addEventListener("click", () => excludeSelectedObject().catch(showOperationError));
els.cancel.addEventListener("click", () => stopProgress(true));
els.backToObjects.addEventListener("click", () => setMode("objects"));
els.treeSearch.addEventListener("input", () => {
  state.selectedPaths.clear();
  renderTree();
});
els.pdfPageImage.addEventListener("load", () => fitPdfPage());
els.viewZoomOut.addEventListener("click", () => zoomPdf(0.82));
els.viewZoomIn.addEventListener("click", () => zoomPdf(1.22));
els.viewFit.addEventListener("click", () => fitPdfPage());
els.viewRotate.addEventListener("click", () => {
  state.view.rotation = (state.view.rotation + 90) % 360;
  fitPdfPage();
});
els.viewPanMode.addEventListener("click", () => {
  state.view.panMode = !state.view.panMode;
  updateViewTransform();
});
els.viewStandardMode.addEventListener("click", () => setViewerMode("standard"));
els.viewMediumMode.addEventListener("click", () => setViewerMode("medium"));
els.viewFullMode.addEventListener("click", () => setViewerMode("full"));

els.pdfStage.addEventListener("wheel", (event) => {
  if (event.target.closest(".viewer-controls")) return;
  if (!event.ctrlKey || els.pdfPageImage.hidden) return;
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
