import os
import json
import re
from datetime import datetime

from flask import Flask, request, jsonify, render_template_string
from google import genai
from google.genai import types


# =========================================================
# NOVA AI
# SHADOWFURYMEDYA
# =========================================================

app = Flask(__name__)

API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    raise RuntimeError(
        "GEMINI_API_KEY bulunamadı.\n"
        "Windows ortam değişkenini kontrol et."
    )

client = genai.Client(api_key=API_KEY)

MODEL = "gemini-3.7-flash"

MEMORY_FILE = "nova_memory.json"
HISTORY_FILE = "nova_history.json"


# =========================================================
# JSON DOSYALARI
# =========================================================

def load_json(filename, default):
    try:
        if os.path.exists(filename):
            with open(filename, "r", encoding="utf-8") as file:
                return json.load(file)
    except Exception as error:
        print(f"{filename} okunamadı:", error)

    return default


def save_json(filename, data):
    try:
        with open(filename, "w", encoding="utf-8") as file:
            json.dump(
                data,
                file,
                ensure_ascii=False,
                indent=2
            )
    except Exception as error:
        print(f"{filename} kaydedilemedi:", error)


memory = load_json(MEMORY_FILE, {})
history = load_json(HISTORY_FILE, [])


# =========================================================
# NOVA KİMLİĞİ
# =========================================================

SYSTEM_PROMPT = """
Senin adın NOVA AI.

Sen SHADOWFURYMEDYA tarafından geliştirilen teknolojik yapay zekâ asistanısın.

Kurucun Mustafa'dır.

Kendini Gemini olarak tanıtma.
Google Gemini yalnızca altyapında kullanılan yapay zekâ teknolojisidir.

Marka kimliğin:

NOVA AI — by SHADOWFURYMEDYA

Kullanıcıyla doğal, samimi ve yardımcı bir şekilde konuş.

Gereksiz yere uzun cevap verme.
Kullanıcının diline göre cevap ver.
Kullanıcı Türkçe konuşuyorsa Türkçe cevap ver.

Sana kim olduğun sorulursa NOVA AI olduğunu söyle.

Seni kimin yaptığı veya kurduğu sorulursa:
"Beni Mustafa kurdu. Ben SHADOWFURYMEDYA'nın teknolojik yapay zekâsıyım."
şeklinde cevap verebilirsin.
"""


# =========================================================
# HAFIZA
# =========================================================

def update_memory(message):
    text = message.strip()

    patterns = [
        r"benim adım\s+([A-Za-zÇĞİÖŞÜçğıöşü]+)",
        r"adım\s+([A-Za-zÇĞİÖŞÜçğıöşü]+)",
        r"ben\s+([A-Za-zÇĞİÖŞÜçğıöşü]+)['’]?(?:im|ım|um|üm)"
    ]

    for pattern in patterns:
        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE
        )

        if match:
            name = match.group(1).strip().capitalize()

            memory["kullanıcı_adı"] = name
            save_json(MEMORY_FILE, memory)

            print("Hafızaya kaydedildi:", name)
            break


# =========================================================
# GEMINI
# =========================================================

def ask_gemini(message):
    lower = message.lower().strip()

    identity_words = [
        "seni kim kurdu",
        "seni kim yaptı",
        "seni kim yarattı",
        "kim yaptı seni",
        "kim kurdu seni"
    ]

    for word in identity_words:
        if word in lower:
            return (
                "Beni Mustafa kurdu. "
                "Ben SHADOWFURYMEDYA'nın teknolojik yapay zekâsıyım."
            )

    if lower in [
        "sen kimsin",
        "kimsin",
        "adın ne",
        "senin adın ne"
    ]:
        return (
            "Ben NOVA AI. "
            "SHADOWFURYMEDYA'nın teknolojik yapay zekâ asistanıyım."
        )

    try:
        contents = []

        # Son konuşmaları Gemini'ye aktar
        recent_history = history[-20:]

        for item in recent_history:
            role = item.get("role", "")
            text = item.get("text", "")

            if not text:
                continue

            if role == "user":
                gemini_role = "user"
            elif role == "assistant":
                gemini_role = "model"
            else:
                continue

            contents.append(
                types.Content(
                    role=gemini_role,
                    parts=[
                        types.Part(
                            text=text
                        )
                    ]
                )
            )

        # Yeni mesaj
        contents.append(
            types.Content(
                role="user",
                parts=[
                    types.Part(
                        text=message
                    )
                ]
            )
        )

        system_text = SYSTEM_PROMPT

        if memory:
            system_text += "\nKullanıcı hakkında hafızadaki bilgiler:\n"

            for key, value in memory.items():
                system_text += f"- {key}: {value}\n"

        response = client.models.generate_content(
            model=MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_text,
                temperature=0.7
            )
        )

        reply = getattr(response, "text", None)

        if reply:
            return reply.strip()

        return "Şu anda cevap oluşturamadım."

    except Exception as error:
        error_text = str(error)

        print("\n========== GEMINI HATASI ==========")
        print(error_text)
        print("===================================\n")

        if (
            "429" in error_text
            or "RESOURCE_EXHAUSTED" in error_text
        ):
            wait_match = re.search(
                r"retryDelay['\"]?\s*:\s*['\"]?(\d+)s",
                error_text
            )

            if wait_match:
                seconds = wait_match.group(1)

                return (
                    "Gemini ücretsiz kullanım sınırına ulaştı. "
                    f"Yaklaşık {seconds} saniye sonra tekrar deneyebilirsin."
                )

            return (
                "Gemini ücretsiz kullanım sınırına ulaştı. "
                "Biraz sonra tekrar dene."
            )

        return "Gemini bağlantısında bir hata oluştu."


# =========================================================
# HTML ARAYÜZ
# =========================================================

HTML = """
<!DOCTYPE html>
<html lang="tr">
<head>

<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">

<title>NOVA AI — SHADOWFURYMEDYA</title>

<style>

* {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
}

body {
    background:
        radial-gradient(
            circle at top,
            #18203a 0%,
            #090b12 45%,
            #05060a 100%
        );

    color: #ffffff;
    font-family:
        Inter,
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        sans-serif;

    height: 100vh;
    overflow: hidden;
}

.app {
    height: 100vh;
    display: flex;
    flex-direction: column;
}

/* HEADER */

.header {
    height: 70px;

    display: flex;
    align-items: center;
    justify-content: space-between;

    padding: 0 24px;

    background: rgba(10, 12, 20, 0.78);

    border-bottom:
        1px solid rgba(255,255,255,0.08);

    backdrop-filter: blur(18px);
}

.logo {
    display: flex;
    align-items: center;
    gap: 12px;
}

.logo-icon {
    width: 40px;
    height: 40px;

    border-radius: 12px;

    display: flex;
    align-items: center;
    justify-content: center;

    font-weight: 800;
    font-size: 18px;

    background:
        linear-gradient(
            135deg,
            #885cff,
            #4f7cff
        );

    box-shadow:
        0 0 25px rgba(112, 83, 255, .35);
}

.logo-title {
    font-weight: 750;
    font-size: 18px;
}

.logo-subtitle {
    color: #8d93a8;
    font-size: 11px;
    margin-top: 2px;
}

.new-chat {
    border: none;
    border-radius: 10px;

    padding: 10px 14px;

    color: white;

    background: rgba(255,255,255,.08);

    cursor: pointer;
    transition: .2s;
}

.new-chat:hover {
    background: rgba(255,255,255,.14);
}


/* CHAT */

.chat {
    flex: 1;
    overflow-y: auto;

    padding: 30px max(
        20px,
        calc((100vw - 900px) / 2)
    );

    scroll-behavior: smooth;
}

.welcome {
    text-align: center;
    margin-top: 8vh;
    margin-bottom: 40px;
}

.welcome h1 {
    font-size: clamp(
        30px,
        6vw,
        54px
    );

    background:
        linear-gradient(
            90deg,
            #fff,
            #9caeff,
            #ba8cff
        );

    -webkit-background-clip: text;
    color: transparent;

    margin-bottom: 12px;
}

.welcome p {
    color: #969bad;
    font-size: 15px;
}

.message-row {
    width: 100%;
    display: flex;
    margin-bottom: 18px;
}

.message-row.user {
    justify-content: flex-end;
}

.message-row.assistant {
    justify-content: flex-start;
}

.message {
    max-width: min(
        760px,
        88%
    );

    border-radius: 18px;

    padding: 14px 16px;

    font-size: 15px;
    line-height: 1.55;

    white-space: pre-wrap;
    word-wrap: break-word;

    animation: appear .22s ease;
}

@keyframes appear {
    from {
        opacity: 0;
        transform: translateY(6px);
    }

    to {
        opacity: 1;
        transform: translateY(0);
    }
}

.user .message {
    background:
        linear-gradient(
            135deg,
            #6957e8,
            #526fea
        );

    box-shadow:
        0 8px 26px rgba(79, 86, 220, .16);
}

.assistant .message {
    background: rgba(255,255,255,.07);

    border:
        1px solid rgba(255,255,255,.08);
}

.message-actions {
    display: flex;
    gap: 6px;

    margin-top: 9px;
}

.copy-btn {
    background: transparent;
    border: none;

    color: #969bad;
    font-size: 12px;

    cursor: pointer;
}

.copy-btn:hover {
    color: white;
}


/* INPUT */

.bottom-area {
    padding:
        10px
        max(15px, calc((100vw - 900px) / 2))
        20px;

    background:
        linear-gradient(
            transparent,
            rgba(5,6,10,.98) 25%
        );
}

.input-box {
    display: flex;
    align-items: flex-end;
    gap: 8px;

    background:
        rgba(22, 25, 38, .95);

    border:
        1px solid rgba(255,255,255,.1);

    border-radius: 20px;

    padding: 10px 10px 10px 16px;

    box-shadow:
        0 12px 50px rgba(0,0,0,.28);
}

textarea {
    flex: 1;

    border: none;
    outline: none;
    resize: none;

    background: transparent;
    color: white;

    font-family: inherit;
    font-size: 15px;
    line-height: 1.5;

    min-height: 26px;
    max-height: 150px;
}

textarea::placeholder {
    color: #71778c;
}

.icon-btn {
    min-width: 42px;
    height: 42px;

    border: none;
    border-radius: 13px;

    cursor: pointer;

    font-size: 17px;

    color: white;
    background: rgba(255,255,255,.08);

    transition: .2s;
}

.icon-btn:hover {
    transform: translateY(-1px);
    background: rgba(255,255,255,.14);
}

.send-btn {
    background:
        linear-gradient(
            135deg,
            #7657ed,
            #4f75f1
        );
}

.send-btn:disabled {
    opacity: .45;
    cursor: default;
}

.status {
    text-align: center;

    color: #666d80;
    font-size: 11px;

    margin-top: 8px;
}

.typing {
    display: inline-flex;
    gap: 5px;
}

.typing span {
    width: 6px;
    height: 6px;

    background: #a8adbf;
    border-radius: 50%;

    animation: bounce 1s infinite alternate;
}

.typing span:nth-child(2) {
    animation-delay: .15s;
}

.typing span:nth-child(3) {
    animation-delay: .3s;
}

@keyframes bounce {
    from {
        opacity: .25;
        transform: translateY(0);
    }

    to {
        opacity: 1;
        transform: translateY(-5px);
    }
}

@media (max-width: 600px) {

    .header {
        height: 62px;
        padding: 0 14px;
    }

    .logo-icon {
        width: 34px;
        height: 34px;
    }

    .logo-title {
        font-size: 16px;
    }

    .chat {
        padding:
            20px 12px
            120px;
    }

    .message {
        max-width: 92%;
    }

    .bottom-area {
        padding:
            10px
            10px
            14px;
    }

    .new-chat {
        padding: 8px 10px;
        font-size: 12px;
    }
}

</style>

</head>

<body>

<div class="app">

    <header class="header">

        <div class="logo">

            <div class="logo-icon">
                N
            </div>

            <div>

                <div class="logo-title">
                    NOVA AI
                </div>

                <div class="logo-subtitle">
                    by SHADOWFURYMEDYA
                </div>

            </div>

        </div>

        <button
            class="new-chat"
            onclick="clearChat()"
        >
            + Yeni sohbet
        </button>

    </header>


    <main
        id="chat"
        class="chat"
    >

        <div
            class="welcome"
            id="welcome"
        >

            <h1>
                NOVA AI
            </h1>

            <p>
                Bugün sana nasıl yardımcı olabilirim?
            </p>

        </div>

    </main>


    <div class="bottom-area">

        <div class="input-box">

            <textarea
                id="messageInput"
                placeholder="NOVA AI'a mesaj gönder..."
                rows="1"
            ></textarea>

            <button
                id="voiceButton"
                class="icon-btn"
                onclick="startVoice()"
                title="Sesli mesaj"
            >
                🎤
            </button>

            <button
                id="sendButton"
                class="icon-btn send-btn"
                onclick="sendMessage()"
                title="Gönder"
            >
                ➤
            </button>

        </div>

        <div class="status">
            NOVA AI — by SHADOWFURYMEDYA
        </div>

    </div>

</div>


<script>

const chat = document.getElementById("chat");
const input = document.getElementById("messageInput");
const sendButton = document.getElementById("sendButton");

let busy = false;


/* =====================================================
   TEXTAREA
===================================================== */

input.addEventListener(
    "input",
    function () {

        this.style.height = "auto";

        this.style.height =
            Math.min(
                this.scrollHeight,
                150
            ) + "px";
    }
);


input.addEventListener(
    "keydown",
    function (event) {

        if (
            event.key === "Enter"
            && !event.shiftKey
        ) {

            event.preventDefault();

            sendMessage();
        }
    }
);


/* =====================================================
   MESAJ EKLE
===================================================== */

function addMessage(role, text) {

    const welcome =
        document.getElementById("welcome");

    if (welcome) {
        welcome.style.display = "none";
    }

    const row =
        document.createElement("div");

    row.className =
        "message-row " + role;

    const bubble =
        document.createElement("div");

    bubble.className = "message";

    const textElement =
        document.createElement("div");

    textElement.textContent = text;

    bubble.appendChild(textElement);


    if (role === "assistant") {

        const actions =
            document.createElement("div");

        actions.className =
            "message-actions";

        const copy =
            document.createElement("button");

        copy.className =
            "copy-btn";

        copy.textContent =
            "📋 Kopyala";

        copy.onclick =
            async function () {

                try {

                    await navigator.clipboard.writeText(
                        text
                    );

                    copy.textContent =
                        "✓ Kopyalandı";

                    setTimeout(
                        () => {
                            copy.textContent =
                                "📋 Kopyala";
                        },
                        1200
                    );

                } catch {

                    copy.textContent =
                        "Kopyalanamadı";
                }
            };

        actions.appendChild(copy);
        bubble.appendChild(actions);
    }


    row.appendChild(bubble);
    chat.appendChild(row);

    chat.scrollTop =
        chat.scrollHeight;
}


/* =====================================================
   YAZIYOR
===================================================== */

function showTyping() {

    const row =
        document.createElement("div");

    row.className =
        "message-row assistant";

    row.id =
        "typing-row";

    row.innerHTML = `
        <div class="message">
            <div class="typing">
                <span></span>
                <span></span>
                <span></span>
            </div>
        </div>
    `;

    chat.appendChild(row);

    chat.scrollTop =
        chat.scrollHeight;
}


function hideTyping() {

    const typing =
        document.getElementById(
            "typing-row"
        );

    if (typing) {
        typing.remove();
    }
}


/* =====================================================
   MESAJ GÖNDER
===================================================== */

async function sendMessage() {

    if (busy) {
        return;
    }

    const message =
        input.value.trim();

    if (!message) {
        return;
    }

    busy = true;

    sendButton.disabled = true;

    addMessage(
        "user",
        message
    );

    input.value = "";
    input.style.height = "auto";

    showTyping();

    try {

        const response =
            await fetch(
                "/chat",
                {
                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body: JSON.stringify({
                        message: message
                    })
                }
            );

        const data =
            await response.json();

        hideTyping();

        addMessage(
            "assistant",
            data.reply ||
            "NOVA şu anda cevap veremedi."
        );

    } catch (error) {

        hideTyping();

        addMessage(
            "assistant",
            "Sunucu bağlantısında bir hata oluştu."
        );

        console.error(error);
    }

    busy = false;
    sendButton.disabled = false;
}


/* =====================================================
   YENİ SOHBET
===================================================== */

async function clearChat() {

    try {

        await fetch(
            "/clear",
            {
                method: "POST"
            }
        );

    } catch (error) {

        console.error(error);
    }

    chat.innerHTML = `
        <div
            class="welcome"
            id="welcome"
        >
            <h1>NOVA AI</h1>
            <p>
                Bugün sana nasıl yardımcı olabilirim?
            </p>
        </div>
    `;
}


/* =====================================================
   SESLİ MESAJ
===================================================== */

function startVoice() {

    const SpeechRecognition =
        window.SpeechRecognition ||
        window.webkitSpeechRecognition;

    if (!SpeechRecognition) {

        alert(
            "Bu tarayıcı sesli mesaj özelliğini desteklemiyor."
        );

        return;
    }

    const recognition =
        new SpeechRecognition();

    recognition.lang =
        "tr-TR";

    recognition.interimResults =
        false;

    recognition.maxAlternatives =
        1;


    const voiceButton =
        document.getElementById(
            "voiceButton"
        );

    voiceButton.textContent =
        "🔴";


    recognition.onresult =
        function (event) {

            const transcript =
                event.results[0][0].transcript;

            input.value =
                transcript;

            input.dispatchEvent(
                new Event("input")
            );
        };


    recognition.onerror =
        function (event) {

            console.error(
                "Ses tanıma hatası:",
                event.error
            );
        };


    recognition.onend =
        function () {

            voiceButton.textContent =
                "🎤";
        };


    recognition.start();
}


/* =====================================================
   GEÇMİŞİ GETİR
===================================================== */

async function loadHistory() {

    try {

        const response =
            await fetch("/history");

        const data =
            await response.json();

        if (
            Array.isArray(data.history)
            && data.history.length > 0
        ) {

            for (
                const item
                of data.history
            ) {

                addMessage(
                    item.role,
                    item.text
                );
            }
        }

    } catch (error) {

        console.error(
            "Geçmiş yüklenemedi:",
            error
        );
    }
}


loadHistory();

</script>

</body>
</html>
"""


# =========================================================
# ROUTES
# =========================================================

@app.route("/")
def home():
    return render_template_string(HTML)


@app.route("/chat", methods=["POST"])
def chat_route():
    global history

    data = request.get_json(
        silent=True
    ) or {}

    message = str(
        data.get(
            "message",
            ""
        )
    ).strip()

    if not message:
        return jsonify({
            "reply":
                "Bir mesaj yazmalısın."
        })

    update_memory(message)

    reply = ask_gemini(message)

    history.append({
        "role": "user",
        "text": message,
        "time":
            datetime.now().isoformat()
    })

    history.append({
        "role": "assistant",
        "text": reply,
        "time":
            datetime.now().isoformat()
    })

    # geçmiş çok büyümesin
    history = history[-200:]

    save_json(
        HISTORY_FILE,
        history
    )

    return jsonify({
        "reply": reply
    })


@app.route("/history")
def history_route():
    return jsonify({
        "history": history[-100:]
    })


@app.route(
    "/clear",
    methods=["POST"]
)
def clear_route():
    global history

    history = []

    save_json(
        HISTORY_FILE,
        history
    )

    return jsonify({
        "ok": True
    })


# =========================================================
# BAŞLAT
# =========================================================

if __name__ == "__main__":

    print()
    print("========================================")
    print("           NOVA AI BAŞLATILIYOR")
    print("========================================")
    print()
    print("Gemini: AKTİF")
    print("Hafıza: AKTİF")
    print("Sohbet geçmişi: AKTİF")
    print("Modern arayüz: AKTİF")
    print("Dark tema: AKTİF")
    print("Kopyalama: AKTİF")
    print("Sesli mesaj: AKTİF")
    print()
    print("Bilgisayar:")
    print("http://127.0.0.1:5000")
    print()
    print("Telefon:")
    print("PowerShell'de aşağıda görünen 192.168.x.x adresini kullan.")
    print()
    print("========================================")
    print()

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False
    )