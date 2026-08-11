async function checkHealth() {
  const statusText = document.getElementById("statusText");
  const statusDot = document.getElementById("statusDot");

  try {
    const response = await fetch("/api/health");
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Сервер вернул ошибку");
    statusDot.classList.add("ok");
    statusText.textContent = `Сервер работает · ${payload.version}`;
  } catch (error) {
    statusText.textContent = `Сервер v3 не отвечает: ${error.message}`;
  }
}

let currentManifest = null;

function formatExtensions(extensions) {
  const entries = Object.entries(extensions || {}).sort((left, right) => left[0].localeCompare(right[0], "ru"));
  if (!entries.length) return "форматов нет";
  return entries.map(([ext, count]) => `${ext}: ${count}`).join(" · ");
}

function updateStats(manifest) {
  const stats = document.getElementById("objectStats");
  if (!manifest) {
    stats.textContent = "Объект не загружен";
    return;
  }
  stats.innerHTML = [
    `<strong>${manifest.name}</strong>`,
    `Папок: ${manifest.statistics.folders}`,
    `Файлов: ${manifest.statistics.files}`,
    formatExtensions(manifest.statistics.extensions),
  ].join("<br>");
}

function renderTreeNode(node) {
  const wrapper = document.createElement("div");
  const row = document.createElement("div");
  row.className = "tree-row";

  const icon = document.createElement("span");
  icon.textContent = node.type === "folder" ? "▸" : "•";

  const name = document.createElement("span");
  name.className = "tree-name";
  name.textContent = node.name;
  name.title = node.path;

  const meta = document.createElement("span");
  meta.className = "tree-meta";
  meta.textContent = node.type === "file" ? node.extension : `${(node.children || []).length}`;

  row.append(icon, name, meta);
  wrapper.append(row);

  if (node.type === "folder" && node.children?.length) {
    const children = document.createElement("div");
    children.className = "tree-children";
    node.children.forEach((child) => children.append(renderTreeNode(child)));
    wrapper.append(children);
  }

  return wrapper;
}

function renderTree(manifest) {
  const tree = document.getElementById("objectTree");
  tree.replaceChildren();
  if (!manifest?.tree) {
    const empty = document.createElement("div");
    empty.className = "tree-empty";
    empty.textContent = "Здесь появится дерево после загрузки объекта.";
    tree.append(empty);
    return;
  }
  tree.append(renderTreeNode(manifest.tree));
}

async function importObject(forceRefresh = false) {
  const pathInput = document.getElementById("objectPath");
  const statusText = document.getElementById("statusText");
  const path = pathInput.value.trim();
  if (!path) {
    statusText.textContent = "Вставь путь к папке объекта.";
    return;
  }

  statusText.textContent = forceRefresh ? "Обновляю объект…" : "Загружаю объект…";
  const response = await fetch("/api/objects/import", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path }),
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "Объект не загружен");

  currentManifest = payload;
  pathInput.value = payload.rootPath;
  document.getElementById("refreshObject").disabled = false;
  document.getElementById("excludeObject").disabled = false;
  updateStats(payload);
  renderTree(payload);
  statusText.textContent = `${forceRefresh ? "Объект обновлён" : "Объект загружен"} · ${payload.statistics.files} файлов`;
}

async function excludeObject() {
  if (!currentManifest) return;
  const response = await fetch("/api/objects/exclude", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: currentManifest.id }),
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || "Объект не исключён");
  currentManifest = null;
  document.getElementById("refreshObject").disabled = true;
  document.getElementById("excludeObject").disabled = true;
  updateStats(null);
  renderTree(null);
  document.getElementById("statusText").textContent = "Объект исключён из локального manifest-хранилища.";
}

document.getElementById("loadObject").addEventListener("click", () => {
  importObject(false).catch((error) => {
    document.getElementById("statusText").textContent = `Ошибка загрузки: ${error.message}`;
  });
});

document.getElementById("refreshObject").addEventListener("click", () => {
  importObject(true).catch((error) => {
    document.getElementById("statusText").textContent = `Ошибка обновления: ${error.message}`;
  });
});

document.getElementById("excludeObject").addEventListener("click", () => {
  excludeObject().catch((error) => {
    document.getElementById("statusText").textContent = `Ошибка исключения: ${error.message}`;
  });
});

renderTree(null);
checkHealth();
