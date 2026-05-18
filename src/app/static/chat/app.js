const STORAGE_KEY = "wa_store_chat_settings";

const els = {
  messages: document.getElementById("messages"),
  input: document.getElementById("messageInput"),
  sendBtn: document.getElementById("sendBtn"),
  typing: document.getElementById("typing"),
  storeTitle: document.getElementById("storeTitle"),
  storeSubtitle: document.getElementById("storeSubtitle"),
  settingsBtn: document.getElementById("settingsBtn"),
  settingsPanel: document.getElementById("settingsPanel"),
  phoneInput: document.getElementById("phoneInput"),
  storeSelect: document.getElementById("storeSelect"),
};

function loadSettings() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
  } catch {
    return {};
  }
}

function saveSettings() {
  localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify({
      phone: els.phoneInput.value.trim(),
      storeId: els.storeSelect.value,
    })
  );
  updateHeader();
}

function updateHeader() {
  const sid = els.storeSelect.value;
  const label = sid.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
  els.storeTitle.textContent = label || "Store";
  els.storeSubtitle.textContent = "Online · test chat";
}

function formatTime(date = new Date()) {
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function stripMarkdown(text) {
  return (text || "").replace(/\*\*/g, "");
}

function scrollToBottom() {
  els.messages.scrollTop = els.messages.scrollHeight;
}

function appendMessage(text, direction, { error = false, images = [] } = {}) {
  const welcome = els.messages.querySelector(".welcome");
  if (welcome) welcome.remove();

  const row = document.createElement("div");
  row.className = "msg-row " + direction;

  const bubble = document.createElement("div");
  bubble.className = "bubble" + (error ? " error" : "");

  if (images && images.length) {
    const grid = document.createElement("div");
    grid.className = "image-grid" + (images.length === 1 ? " single" : "");
    for (const img of images) {
      const wrap = document.createElement("figure");
      wrap.className = "product-thumb";
      const el = document.createElement("img");
      el.src = img.url;
      el.alt = img.caption || img.sku || "Product";
      el.loading = "lazy";
      el.addEventListener("error", () => {
        wrap.classList.add("broken");
        el.remove();
      });
      wrap.appendChild(el);
      if (img.caption) {
        const cap = document.createElement("figcaption");
        cap.textContent = img.caption;
        wrap.appendChild(cap);
      }
      grid.appendChild(wrap);
    }
    bubble.appendChild(grid);
  }

  const body = document.createElement("div");
  body.className = "bubble-body";
  body.textContent = stripMarkdown(text);
  bubble.appendChild(body);

  const time = document.createElement("span");
  time.className = "time";
  time.textContent = formatTime();
  bubble.appendChild(time);

  row.appendChild(bubble);
  els.messages.appendChild(row);
  scrollToBottom();
}

function setTyping(visible) {
  els.typing.classList.toggle("visible", visible);
  if (visible) scrollToBottom();
}

function setSending(busy) {
  els.sendBtn.disabled = busy;
  els.input.disabled = busy;
}

async function sendMessage() {
  const text = els.input.value.trim();
  if (!text) return;

  const phone = els.phoneInput.value.trim() || "+919876543210";
  const storeId = els.storeSelect.value || "store_north";

  appendMessage(text, "out");
  els.input.value = "";
  els.input.style.height = "auto";
  setSending(true);
  setTyping(true);

  try {
    const res = await fetch("/webhook/whatsapp", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        intent: "question",
        phone,
        store_id: storeId,
        message: text,
      }),
    });

    const data = await res.json().catch(() => ({}));

    if (!res.ok) {
      const detail = data.detail || res.statusText || "Request failed";
      appendMessage(typeof detail === "string" ? detail : JSON.stringify(detail), "in", {
        error: true,
      });
      return;
    }

    if (data.reply) {
      appendMessage(data.reply, "in", { images: data.images || [] });
    } else if (data.status === "ok") {
      appendMessage("(Message accepted — no reply text in dev mode.)", "in");
    } else {
      appendMessage(JSON.stringify(data, null, 2), "in");
    }
  } catch (err) {
    appendMessage("Could not reach the server. Is uvicorn running?", "in", { error: true });
    console.error(err);
  } finally {
    setTyping(false);
    setSending(false);
    els.input.focus();
  }
}

function init() {
  const saved = loadSettings();
  els.phoneInput.value = saved.phone || "+919876543210";
  if (saved.storeId) {
    els.storeSelect.value = saved.storeId;
  }
  updateHeader();

  els.settingsBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    els.settingsPanel.classList.toggle("open");
  });

  document.addEventListener("click", () => {
    els.settingsPanel.classList.remove("open");
  });

  els.settingsPanel.addEventListener("click", (e) => e.stopPropagation());

  els.phoneInput.addEventListener("change", saveSettings);
  els.storeSelect.addEventListener("change", saveSettings);

  els.sendBtn.addEventListener("click", sendMessage);

  els.input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  els.input.addEventListener("input", () => {
    els.input.style.height = "auto";
    els.input.style.height = Math.min(els.input.scrollHeight, 120) + "px";
  });

  els.input.focus();
}

init();
