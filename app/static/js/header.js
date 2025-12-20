// Фиксированная шапка с анимацией
function initFixedHeader() {
    const header = document.querySelector('header');
    if (!header) return;

    let lastScroll = 0;
    const headerHeight = header.offsetHeight;

    document.documentElement.style.setProperty(
        '--header-height',
        `${headerHeight}px`
    );

    window.addEventListener('scroll', function() {
        const currentScroll = window.pageYOffset;

        if (currentScroll > lastScroll && currentScroll > 100) {
            header.classList.add('header-hidden');
        } else {
            header.classList.remove('header-hidden');
        }

        lastScroll = currentScroll;
    });
}

document.addEventListener('DOMContentLoaded', initFixedHeader);

document.addEventListener("DOMContentLoaded", () => {
    const btn = document.getElementById("chatbot-button");
    const windowChat = document.getElementById("chatbot-window");
    const closeBtn = document.getElementById("chatbot-close");
    const sendBtn = document.getElementById("chatbot-send");
    const input = document.getElementById("chatbot-input");
    const messages = document.getElementById("chatbot-messages");
    const typingIndicator = document.getElementById("typing-indicator");

    const soundUser = document.getElementById("sound-user");
    const soundBot = document.getElementById("sound-bot");

    // --- Открытие / закрытие ---
    btn.addEventListener("click", () => {
        windowChat.classList.toggle("active");

        // Если открываем — убираем свечение
        if (windowChat.classList.contains("active")) {
            btn.classList.remove("glow");
        }
    });

    closeBtn.addEventListener("click", () => {
        windowChat.classList.remove("active");
    });

    // Закрытие при клике вне окна
    document.addEventListener("click", (event) => {
        const isClickInside = windowChat.contains(event.target);
        const isButton = btn.contains(event.target);
        if (!isClickInside && !isButton) {
            windowChat.classList.remove("active");
        }
    });

    // --- Отправка ---
    sendBtn.addEventListener("click", () => sendMessage());
    input.addEventListener("keypress", (e) => {
        if (e.key === "Enter") sendMessage();
    });

    function sendMessage() {
        const text = input.value.trim();
        if (!text) return;

        addMessage("user", text);
        input.value = "";

        soundUser.play();

        typingIndicator.style.display = "block";

        fetch("/chatbot", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message: text })
        })
        .then(res => res.json())
        .then(data => {
            setTimeout(() => {
                typingIndicator.style.display = "none";
                addMessage("bot", data.answer);
                soundBot.play();

                // если чат закрыт — подсвечиваем кнопку
                if (!windowChat.classList.contains("active")) {
                    btn.classList.add("glow");
                }
            }, 700);
        });
    }

    function addMessage(type, text) {
        const div = document.createElement("div");
        div.classList.add("chat-msg", type === "user" ? "msg-user" : "msg-bot");

        const avatar = document.createElement("img");
        avatar.classList.add("avatar");
        avatar.src = type === "user"
            ? "/static/img/user.png"
            : "/static/img/bot.png";

        const span = document.createElement("span");
        span.textContent = text;

        div.appendChild(avatar);
        div.appendChild(span);

        messages.appendChild(div);
        messages.scrollTop = messages.scrollHeight;
    }
});
