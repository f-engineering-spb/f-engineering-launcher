async function checkHealth() {
  const statusText = document.getElementById("statusText");
  const healthBox = document.getElementById("healthBox");
  const statusDot = document.getElementById("statusDot");

  try {
    const response = await fetch("/api/health");
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Сервер вернул ошибку");
    statusDot.classList.add("ok");
    statusText.textContent = "Локальный сервер v3 работает. Можно собирать следующий кирпичик.";
    healthBox.textContent = JSON.stringify(payload, null, 2);
  } catch (error) {
    statusText.textContent = `Сервер v3 не отвечает: ${error.message}`;
    healthBox.textContent = "";
  }
}

checkHealth();
