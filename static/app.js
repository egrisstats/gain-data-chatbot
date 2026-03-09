const loadForm = document.getElementById("loadForm");
const loadStatus = document.getElementById("loadStatus");
const loadDefaultBtn = document.getElementById("loadDefault");
const chatForm = document.getElementById("chatForm");
const chatLog = document.getElementById("chatLog");
const questionInput = document.getElementById("question");

function appendMessage(role, text, sql = null) {
  const box = document.createElement("div");
  box.className = `msg ${role}`;
  const p = document.createElement("p");
  p.textContent = text;
  box.appendChild(p);
  if (sql) {
    const pre = document.createElement("pre");
    pre.textContent = sql;
    box.appendChild(pre);
  }
  chatLog.appendChild(box);
  chatLog.scrollTop = chatLog.scrollHeight;
}

loadForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const mainFile = document.getElementById("mainFile").files[0];
  const groupFile = document.getElementById("groupFile").files[0];
  if (!mainFile || !groupFile) {
    loadStatus.textContent = "Please choose both files.";
    return;
  }
  const formData = new FormData();
  formData.append("main_roster_file", mainFile);
  formData.append("group_roster_file", groupFile);
  loadStatus.textContent = "Loading uploaded files...";

  try {
    const res = await fetch("/load-data", { method: "POST", body: formData });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Load failed");
    loadStatus.textContent = data.message;
  } catch (err) {
    loadStatus.textContent = err.message;
  }
});

loadDefaultBtn.addEventListener("click", async () => {
  loadStatus.textContent = "Loading default data paths...";
  try {
    const res = await fetch("/load-data", { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Load failed");
    loadStatus.textContent = data.message;
  } catch (err) {
    loadStatus.textContent = err.message;
  }
});

chatForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const message = questionInput.value.trim();
  if (!message) return;

  appendMessage("user", message);
  questionInput.value = "";

  try {
    const res = await fetch("/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Chat failed");
    appendMessage("assistant", `${data.answer}\n\nRows returned: ${data.rows}`, data.sql);
  } catch (err) {
    appendMessage("assistant", `Error: ${err.message}`);
  }
});
