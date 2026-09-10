import os
import json
import re
import uuid
import time
from datetime import datetime

from flask import Flask, request, jsonify, render_template_string, session
from google import genai
from google.genai import types


# =========================================================
# NOVA AI
# SHADOWFURYMEDYA
# =========================================================

app = Flask(__name__)

app.secret_key = os.getenv("NOVA_SECRET_KEY") or "CHANGE-ME-IN-RENDER"

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("RENDER") == "true",
)

API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    raise RuntimeError("GEMINI_API_KEY bulunamadı.")

client = genai.Client(api_key=API_KEY)

PRIMARY_MODEL = "gemini-3.7-flash"
FALLBACK_MODEL = "gemini-2.5-flash"

MEMORY_FILE = "nova_memory.json"
HISTORY_FILE = "nova_history.json"


# =========================================================
# JSON YARDIMCILARI
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


# =========================================================
# KULLANICIYA ÖZEL SOHBET VE HAFIZA
# =========================================================

loaded_histories = load_json(HISTORY_FILE, {})
loaded_memories = load_json(MEMORY_FILE, {})

if not isinstance(loaded_histories, dict):
    loaded_histories = {}

if not isinstance(loaded_memories, dict):
    loaded_memories = {}

user_histories = loaded_histories
user_memories = loaded_memories


def get_user_id():
    user_id = session.get("nova_user_id")

    if not user_id:
        user_id = uuid.uuid4().hex
        session["nova_user_id"] = user_id

    return user_id


def get_user_history(user_id):
    history = user_histories.get(user_id)

    if not isinstance(history, list):
        history = []
        user_histories[user_id] = history

    return history


def get_user_memory(user_id):
    memory = user_memories.get(user_id)

    if not isinstance(memory, dict):
        memory = {}
        user_memories[user_id] = memory

    return memory


# =========================================================
# NOVA KİMLİĞİ
# =========================================================

SYSTEM_PROMPT = """
Senin adın NOVA AI.

Sen SHADOWFURYMEDYA tarafından geliştirilen teknolojik yapay zekâ asistanısın.
Kurucun Mustafa'dır.

Marka kimliğin:
NOVA AI — by SHADOWFURYMEDYA

Kullanıcı Türkçe konuşuyorsa Türkçe cevap ver.
Doğal, kısa, net ve yardımcı konuş.
Kullanıcı ayrıntı isterse ayrıntılı anlat.

Sana kim olduğun sorulursa NOVA AI olduğunu söyle.

Seni kimin yaptığı veya kurduğu sorulursa:
"Beni Mustafa kurdu. Ben SHADOWFURYMEDYA'nın teknolojik yapay zekâsıyım."
şeklinde cevap ver.

Google Gemini altyapısını kullanıp kullanmadığın açıkça sorulursa dürüstçe
Google Gemini altyapısını kullandığını söyle.
"""


# =========================================================
# BASİT KİŞİSEL HAFIZA
# =========================================================

def update_memory(message, user_id, user_memory):
    text = message.strip()

    patterns = [
        r"benim adım\s+([A-Za-zÇĞİÖŞÜçğıöşü]+)",
        r"adım\s+([A-Za-zÇĞİÖŞÜçğıöşü]+)"
    ]

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)

        if match:
            name = match.group(1).strip().capitalize()

            user_memory["kullanıcı_adı"] = name
            user_memories[user_id] = user_memory

            save_json(MEMORY_FILE, user_memories)
            break


# =========================================================
# GEMINI
# =========================================================

def build_contents(user_history, message):
    contents = []

    for item in user_history[-20:]:
        role = item.get("role", "")
        text = str(item.get("text", "")).strip()

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
                parts=[types.Part(text=text)]
            )
        )

    contents.append(
        types.Content(
            role="user",
            parts=[types.Part(text=message)]
        )
    )

    return contents


def ask_gemini(message, user_history, user_memory):
    lower = message.lower().strip()

    identity_words = [
        "seni kim kurdu",
        "seni kim yaptı",
        "seni kim yarattı",
        "kim yaptı seni",
        "kim kurdu seni"
    ]

    if any(word in lower for word in identity_words):
        return (
            "Beni Mustafa kurdu. "
            "Ben SHADOWFURYMEDYA'nın teknolojik yapay zekâsıyım."
        )

    if lower in {"sen kimsin", "kimsin", "adın ne", "senin adın ne"}:
        return (
            "Ben NOVA AI. "
            "SHADOWFURYMEDYA'nın teknolojik yapay zekâ asistanıyım."
        )

    contents = build_contents(user_history, message)

    system_text = SYSTEM_PROMPT

    if user_memory:
        system_text += "\nKullanıcı hakkında yalnızca bu oturuma ait bilgiler:\n"

        for key, value in user_memory.items():
            system_text += f"- {key}: {value}\n"

    models_to_try = [PRIMARY_MODEL, FALLBACK_MODEL]
    last_error = ""

    for model_name in models_to_try:
        for attempt in range(2):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=system_text,
                        temperature=0.7
                    )
                )

                reply = getattr(response, "text", None)

                if reply:
                    return reply.strip()

                last_error = "Model boş yanıt verdi."

            except Exception as error:
                last_error = str(error)

                print()
                print("========== GEMINI HATASI ==========")
                print("MODEL:", model_name)
                print("DENEME:", attempt + 1)
                print(last_error)
                print("===================================")
                print()

                temporary_error = (
                    "503" in last_error
                    or "UNAVAILABLE" in last_error
                    or "high demand" in last_error.lower()
                )

                quota_error = (
                    "429" in last_error
                    or "RESOURCE_EXHAUSTED" in last_error
                )

                if temporary_error and attempt == 0:
                    time.sleep(1)
                    continue

                if temporary_error or quota_error:
                    break

                return (
                    "NOVA şu anda yapay zekâ servisine bağlanamadı. "
                    "Biraz sonra tekrar dene."
                )

    if "429" in last_error or "RESOURCE_EXHAUSTED" in last_error:
        return (
            "NOVA şu anda kullanım sınırına ulaştı. "
            "Biraz sonra tekrar dene."
        )

    if (
        "503" in last_error
        or "UNAVAILABLE" in last_error
        or "high demand" in last_error.lower()
    ):
        return (
            "NOVA şu anda yoğunluk nedeniyle cevap veremiyor. "
            "Biraz sonra tekrar dene."
        )

    return "NOVA şu anda cevap oluşturamadı."


# =========================================================
# WEB ARAYÜZÜ
# =========================================================

HTML = r"""
<!DOCTYPE html>
<html lang="tr">
<head>

<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">

<title>NOVA AI — SHADOWFURYMEDYA</title>

<style>

* {
    box-sizing: border-box;
}

html,
body {
    margin: 0;
    width: 100%;
    height: 100%;
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
        Arial,
        sans-serif;

    overflow: hidden;
}

.app {
    height: 100vh;

    display: flex;
    flex-direction: column;
}

.header {
    height: 70px;
    flex-shrink: 0;

    display: flex;
    align-items: center;
    justify-content: space-between;

    padding: 0 24px;

    background: rgba(10, 12, 20, 0.82);

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

    display: grid;
    place-items: center;

    font-weight: 800;

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
    font-size: 18px;
    font-weight: 800;
}

.logo-subtitle {
    margin-top: 2px;

    color: #8d93a8;

    font-size: 11px;
}

.new-chat {
    border: 0;

    border-radius: 10px;

    padding: 10px 14px;

    background: rgba(255,255,255,.08);

    color: white;

    cursor: pointer;
}

.new-chat:hover {
    background: rgba(255,255,255,.14);
}

.chat {
    flex: 1;

    overflow-y: auto;

    padding:
        30px
        max(20px, calc((100vw - 900px) / 2))
        120px;

    scroll-behavior: smooth;
}

.welcome {
    margin-top: 12vh;

    text-align: center;
}

.welcome h1 {
    margin: 0 0 12px;

    font-size:
        clamp(
            34px,
            6vw,
            58px
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
}

.welcome p {
    color: #969bad;
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
    max-width:
        min(
            760px,
            88%
        );

    padding: 14px 16px;

    border-radius: 18px;

    font-size: 15px;

    line-height: 1.55;

    white-space: pre-wrap;

    word-break: break-word;
}

.user .message {
    background:
        linear-gradient(
            135deg,
            #6957e8,
            #526fea
        );
}

.assistant .message {
    background: rgba(255,255,255,.07);

    border:
        1px solid rgba(255,255,255,.08);
}

.copy-btn {
    margin-top: 9px;

    border: 0;

    background: transparent;

    color: #969bad;

    cursor: pointer;
}

.copy-btn:hover {
    color: white;
}

.bottom-area {
    position: fixed;

    left: 0;
    right: 0;
    bottom: 0;

    padding:
        12px
        max(15px, calc((100vw - 900px) / 2))
        18px;

    background:
        linear-gradient(
            transparent,
            rgba(5,6,10,.98) 30%
        );
}

.input-box {
    display: flex;

    align-items: flex-end;

    gap: 8px;

    padding: 9px;

    border-radius: 20px;

    background: rgba(22,25,38,.96);

    border:
        1px solid rgba(255,255,255,.1);
}

textarea {
    flex: 1;

    min-height: 42px;
    max-height: 150px;

    resize: none;

    border: 0;
    outline: 0;

    padding: 10px;

    background: transparent;

    color: white;

    font: inherit;
}

textarea::placeholder {
    color: #71778c;
}

.icon-btn {
    width: 44px;
    height: 44px;

    flex-shrink: 0;

    border: 0;

    border-radius: 13px;

    background: rgba(255,255,255,.08);

    color: white;

    cursor: pointer;

    font-size: 17px;
}

.send-btn {
    background:
        linear-gradient(
            135deg,
            #7657ed,
            #4f75f1
        );
}

.icon-btn:disabled {
    opacity: .45;

    cursor: default;
}

.status {
    margin-top: 8px;

    text-align: center;

    color: #666d80;

    font-size: 11px;
}

.typing {
    opacity: .7;

    font-style: italic;
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
            20px
            12px
            120px;
    }

    .message {
        max-width: 92%;
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
        id="welcome"
        class="welcome"
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

        <button
            id="voiceButton"
            class="icon-btn"
            onclick="startVoice()"
            title="Sesli mesaj"
        >
            🎤
        </button>


        <textarea
            id="messageInput"
            rows="1"
            placeholder="NOVA AI'a mesaj gönder..."
        ></textarea>


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

const chat =
    document.getElementById("chat");

const input =
    document.getElementById("messageInput");

const sendButton =
    document.getElementById("sendButton");

const voiceButton =
    document.getElementById("voiceButton");

let busy = false;


function hideWelcome() {

    const welcome =
        document.getElementById("welcome");

    if (welcome) {
        welcome.style.display = "none";
    }
}


function addMessage(role, text) {

    hideWelcome();

    const row =
        document.createElement("div");

    row.className =
        "message-row " + role;


    const bubble =
        document.createElement("div");

    bubble.className =
        "message";


    const textElement =
        document.createElement("div");

    textElement.textContent =
        text;


    bubble.appendChild(
        textElement
    );


    if (role === "assistant") {

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
                        function () {

                            copy.textContent =
                                "📋 Kopyala";

                        },
                        1200
                    );

                } catch (error) {

                    copy.textContent =
                        "Kopyalanamadı";
                }

            };


        bubble.appendChild(
            copy
        );
    }


    row.appendChild(
        bubble
    );

    chat.appendChild(
        row
    );

    chat.scrollTop =
        chat.scrollHeight;


    return row;
}


function showTyping() {

    const row =
        addMessage(
            "assistant",
            "NOVA yazıyor..."
        );

    row.id =
        "typing-row";


    row
        .querySelector(".message")
        .classList
        .add("typing");
}


function hideTyping() {

    const row =
        document.getElementById(
            "typing-row"
        );

    if (row) {
        row.remove();
    }
}


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

    voiceButton.disabled = true;


    addMessage(
        "user",
        message
    );


    input.value = "";

    input.style.height =
        "42px";


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

                    body:
                        JSON.stringify({
                            message:
                                message
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


        console.error(
            error
        );


    } finally {

        busy = false;

        sendButton.disabled = false;

        voiceButton.disabled = false;

        input.focus();
    }

}


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
            id="welcome"
            class="welcome"
        >
            <h1>NOVA AI</h1>
            <p>
                Bugün sana nasıl yardımcı olabilirim?
            </p>
        </div>
    `;
}


async function loadHistory() {

    try {

        const response =
            await fetch(
                "/history"
            );


        const data =
            await response.json();


        if (
            Array.isArray(
                data.history
            )
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


input.addEventListener(
    "input",
    function () {

        this.style.height =
            "42px";

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
            &&
            !event.shiftKey
        ) {

            event.preventDefault();

            sendMessage();
        }
    }
);


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


    voiceButton.textContent =
        "🔴";


    recognition.onresult =
        function (event) {

            const transcript =
                event.results[0][0]
                    .transcript;


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
    get_user_id()

    return render_template_string(
        HTML
    )


@app.route("/chat", methods=["POST"])
def chat_route():
    user_id = get_user_id()

    user_history = get_user_history(
        user_id
    )

    user_memory = get_user_memory(
        user_id
    )


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
        }), 400


    update_memory(
        message,
        user_id,
        user_memory
    )


    reply = ask_gemini(
        message,
        user_history,
        user_memory
    )


    user_history.append({
        "role":
            "user",

        "text":
            message,

        "time":
            datetime.now().isoformat()
    })


    user_history.append({
        "role":
            "assistant",

        "text":
            reply,

        "time":
            datetime.now().isoformat()
    })


    user_history = user_history[-200:]

    user_histories[user_id] =
        user_history


    save_json(
        HISTORY_FILE,
        user_histories
    )


    return jsonify({
        "reply":
            reply
    })


@app.route("/history")
def history_route():
    user_id = get_user_id()

    user_history = get_user_history(
        user_id
    )


    return jsonify({
        "history":
            user_history[-100:]
    })


@app.route("/clear", methods=["POST"])
def clear_route():
    user_id = get_user_id()

    user_histories[user_id] = []

    save_json(
        HISTORY_FILE,
        user_histories
    )


    return jsonify({
        "ok":
            True
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
    print("Kullanıcı izolasyonu: AKTİF")
    print("Kişisel sohbet geçmişi: AKTİF")
    print("Kişisel hafıza: AKTİF")

    print()
    print("http://127.0.0.1:5000")
    print()


    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False
    )
