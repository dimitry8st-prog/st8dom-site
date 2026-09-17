/* Плавающий поиск: история, ссылки на портал, эскалация в заявку и Telegram. */

(function () {
  "use strict";

  const root = document.getElementById("site-chat");
  if (!root) return;

  const launcher = document.getElementById("chat-launcher");
  const widget = document.getElementById("chat-widget");
  const closeBtn = document.getElementById("chat-close");
  const messagesEl = document.getElementById("chat-messages");
  const form = document.getElementById("chat-form");
  const inputEl = document.getElementById("chat-input");
  const sendBtn = document.getElementById("chat-send");

  const chatUrl = root.getAttribute("data-chat-url") || "/chat/";
  const contactUrl = root.getAttribute("data-contact-url") || "/contact/";
  const telegramUrl = root.getAttribute("data-telegram-url") || "/telegram/";
  const csrf = root.getAttribute("data-csrf") || "";

  const GREETING =
    "Привет! Я Дис, цифровой помощник портала. Найду статьи, рубрики, проекты, кейсы, услуги и контакты. Просто напишите, что ищете.";

  let isSending = false;
  let greeted = false;

  function track(eventName, payload) {
    if (typeof window.st8domTrack === "function") {
      window.st8domTrack(eventName, payload || {});
    }
  }

  function appendMessage(text, from, actions, results) {
    const wrap = document.createElement("div");
    wrap.className = "chat-message " + from;

    const body = document.createElement("p");
    body.className = "chat-message-text";
    body.textContent = text;
    wrap.appendChild(body);

    if (Array.isArray(results) && results.length) {
      const list = document.createElement("div");
      list.className = "chat-results";
      results.forEach(function (result) {
        if (!result || typeof result.url !== "string" || result.url.charAt(0) !== "/") {
          return;
        }
        const link = document.createElement("a");
        link.className = "chat-result";
        link.href = result.url;

        const kind = document.createElement("span");
        kind.className = "chat-result-kind";
        kind.textContent = result.kind || "Материал";

        const title = document.createElement("span");
        title.className = "chat-result-title";
        title.textContent = result.title || "Открыть";

        link.appendChild(kind);
        link.appendChild(title);
        link.addEventListener("click", function () {
          track("chat_result_click", { url: result.url });
        });
        list.appendChild(link);
      });
      if (list.childElementCount) wrap.appendChild(list);
    }

    if (actions) {
      const row = document.createElement("div");
      row.className = "chat-actions";

      const contact = document.createElement("a");
      contact.className = "btn btn-primary btn-sm";
      contact.href = contactUrl;
      contact.textContent = "Оставить заявку";
      contact.addEventListener("click", function () {
        track("chat_contact_click");
      });

      const telegram = document.createElement("a");
      telegram.className = "btn btn-tg btn-sm";
      telegram.href = telegramUrl;
      telegram.textContent = "Telegram-бот готовится";
      telegram.addEventListener("click", function () {
        track("chat_telegram_click");
      });

      row.appendChild(contact);
      row.appendChild(telegram);
      wrap.appendChild(row);
    }

    messagesEl.appendChild(wrap);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function appendTyping() {
    const div = document.createElement("div");
    div.className = "chat-message bot";
    div.id = "chat-typing";
    div.setAttribute("aria-label", "Печатает");
    div.innerHTML =
      '<span class="typing-indicator"><span class="dot"></span><span class="dot"></span><span class="dot"></span></span>';
    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function removeTyping() {
    const el = document.getElementById("chat-typing");
    if (el) el.remove();
  }

  function openWidget() {
    widget.hidden = false;
    launcher.setAttribute("aria-expanded", "true");
    launcher.classList.add("is-hidden");
    if (!greeted) {
      appendMessage(GREETING, "bot");
      greeted = true;
    }
    track("chat_open");
    window.setTimeout(function () {
      inputEl.focus();
    }, 50);
  }

  function closeWidget() {
    widget.hidden = true;
    launcher.setAttribute("aria-expanded", "false");
    launcher.classList.remove("is-hidden");
    launcher.focus();
  }

  function setBusy(busy) {
    isSending = busy;
    sendBtn.disabled = busy;
    inputEl.disabled = busy;
  }

  async function sendMessage() {
    if (isSending) return;
    const text = inputEl.value.trim();
    if (!text) return;

    appendMessage(text, "user");
    inputEl.value = "";
    setBusy(true);
    appendTyping();
    track("chat_send");

    try {
      const res = await fetch(chatUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrf,
        },
        body: JSON.stringify({ message: text }),
      });
      const data = await res.json().catch(function () {
        return {};
      });
      removeTyping();
      const answer =
        data.answer || "Не удалось получить ответ. Оставьте заявку через форму.";
      const escalated = Boolean(data.escalated) || !res.ok;
      appendMessage(answer, "bot", escalated, data.results);
      if (escalated) track("chat_escalate");
    } catch (err) {
      console.error(err);
      removeTyping();
      appendMessage(
        "Связь с сервером не удалась. Оставьте заявку через форму.",
        "bot",
        true
      );
    } finally {
      setBusy(false);
      inputEl.focus();
    }
  }

  launcher.addEventListener("click", openWidget);
  closeBtn.addEventListener("click", closeWidget);
  form.addEventListener("submit", function (event) {
    event.preventDefault();
    sendMessage();
  });
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && !widget.hidden) {
      closeWidget();
    }
  });
})();
