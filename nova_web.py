import os
import re
import time
import uuid
from datetime import datetime

from flask import Flask, request, jsonify, render_template_string, session
from google import genai
from google.genai import types


# =========================================================
# NOVA AI
# SHADOWFURYMEDYA
# =========================================================

app = Flask(__name__)

app.secret_key = os.getenv(
    "NOVA_SECRET_KEY",
    "nova-change-this-secret-key"
)

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=bool(os.getenv("RENDER")),
    MAX_CONTENT_LENGTH=10 * 1024 * 1024
)


# =========================================================
# GEMINI
# =========================================================

API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    raise RuntimeError(
        "GEMINI_API_KEY bulunamadı."
    )

client = genai.Client(
    api_key=API_KEY
)

PRIMARY_MODEL = "gemini-3.7-flash"
FALLBACK_MODEL = "gemini-2.5-flash"


# =========================================================
# KULLANICIYA ÖZEL VERİLER
# =========================================================

user_histories = {}
user_memories = {}


def get_user_id():

    user_id = session.get(
        "nova_user_id"
    )

    if not user_id:

        user_id = uuid.uuid4().hex

        session[
            "nova_user_id"
        ] = user_id

    return user_id


def get_user_history(user_id):

    if user_id not in user_histories:

        user_histories[user_id] = []

    return user_histories[user_id]


def get_user_memory(user_id):

    if user_id not in user_memories:

        user_memories[user_id] = {}

    return user_memories[user_id]


# =========================================================
# NOVA KİMLİĞİ
# =========================================================

SYSTEM_PROMPT = """
Sen NOVA AI'sın.

Sen SHADOWFURYMEDYA'nın teknolojik yapay zekâ asistanısın.

Seni Mustafa geliştirdi.

Marka kimliğin:

NOVA AI — by SHADOWFURYMEDYA

Kullanıcı Türkçe konuşuyorsa Türkçe cevap ver.

Doğal, anlaşılır ve yardımcı cevaplar ver.

Normal bilgi soruları, matematik, kodlama, yazı yazma,
fikir üretme, günlük sohbet ve diğer genel sorulara
mümkün olduğunca yardımcı ol.

Kullanıcı fotoğraf yüklerse fotoğrafı dikkatlice incele
ve kullanıcının sorusuna göre cevap ver.

Fotoğrafta emin olmadığın bir şeyi kesinmiş gibi söyleme.

Sana "Sen kimsin?" diye sorulursa:

"Ben NOVA AI. SHADOWFURYMEDYA'nın teknolojik yapay zekâ asistanıyım."

şeklinde cevap ver.

Seni kimin geliştirdiği sorulursa:

"Beni Mustafa geliştirdi. Ben SHADOWFURYMEDYA'nın teknolojik yapay zekâsıyım."

şeklinde cevap ver.

Google Gemini altyapısını kullanıp kullanmadığın
açıkça sorulursa dürüstçe Gemini altyapısının
kullanıldığını söyle.
"""


# =========================================================
# BASİT KİŞİSEL HAFIZA
# =========================================================

def update_memory(
    message,
    user_memory
):

    patterns = [
        r"benim adım\s+([A-Za-zÇĞİÖŞÜçğıöşü]+)",
        r"adım\s+([A-Za-zÇĞİÖŞÜçğıöşü]+)"
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            message,
            flags=re.IGNORECASE
        )

        if match:

            name = (
                match
                .group(1)
                .strip()
                .capitalize()
            )

            user_memory[
                "kullanıcı_adı"
            ] = name

            break


# =========================================================
# SİSTEM METNİ
# =========================================================

def make_system_text(
    user_memory
):

    text = SYSTEM_PROMPT

    if user_memory:

        text += (
            "\nBu kullanıcıya özel "
            "hafıza bilgileri:\n"
        )

        for key, value in user_memory.items():

            text += (
                f"- {key}: {value}\n"
            )

    return text


# =========================================================
# SOHBET GEÇMİŞİNİ GEMINI FORMATINA ÇEVİR
# =========================================================

def build_history(
    user_history
):

    contents = []

    for item in user_history[-20:]:

        role = item.get(
            "role",
            ""
        )

        text = str(
            item.get(
                "text",
                ""
            )
        ).strip()

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

    return contents


# =========================================================
# GEMINI ÇAĞRISI
# =========================================================

def call_gemini(
    contents,
    system_text
):

    models = [
        PRIMARY_MODEL,
        FALLBACK_MODEL
    ]

    last_error = ""

    for model_name in models:

        for attempt in range(2):

            try:

                response = (
                    client.models.generate_content(
                        model=model_name,
                        contents=contents,
                        config=(
                            types.GenerateContentConfig(
                                system_instruction=system_text,
                                temperature=0.7
                            )
                        )
                    )
                )

                reply = getattr(
                    response,
                    "text",
                    None
                )

                if reply:

                    return (
                        reply.strip(),
                        None
                    )

            except Exception as error:

                last_error = str(
                    error
                )

                print()
                print(
                    "========== GEMINI HATASI =========="
                )
                print(
                    "MODEL:",
                    model_name
                )
                print(
                    last_error
                )
                print(
                    "==================================="
                )
                print()

                temporary_error = (
                    "503" in last_error
                    or "UNAVAILABLE" in last_error
                    or "high demand"
                    in last_error.lower()
                )

                quota_error = (
                    "429" in last_error
                    or "RESOURCE_EXHAUSTED"
                    in last_error
                )

                if (
                    temporary_error
                    and attempt == 0
                ):

                    time.sleep(1)

                    continue

                if (
                    temporary_error
                    or quota_error
                ):

                    break

                return (
                    None,
                    "NOVA şu anda yapay zekâ servisine bağlanamadı."
                )

    if (
        "429" in last_error
        or "RESOURCE_EXHAUSTED"
        in last_error
    ):

        return (
            None,
            "NOVA şu anda kullanım sınırına ulaştı. Biraz sonra tekrar dene."
        )

    if (
        "503" in last_error
        or "UNAVAILABLE"
        in last_error
        or "high demand"
        in last_error.lower()
    ):

        return (
            None,
            "NOVA şu anda yoğun. Biraz sonra tekrar dene."
        )

    return (
        None,
        "NOVA şu anda cevap oluşturamadı."
    )


# =========================================================
# NORMAL MESAJ
# =========================================================

def ask_text(
    message,
    user_history,
    user_memory
):

    contents = build_history(
        user_history
    )

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

    return call_gemini(
        contents,
        make_system_text(
            user_memory
        )
    )


# =========================================================
# FOTOĞRAF MESAJI
# =========================================================

def ask_image(
    message,
    image_bytes,
    mime_type,
    user_memory
):

    if not message:

        message = (
            "Bu fotoğrafı incele ve "
            "bana ne gördüğünü anlat."
        )

    image_part = (
        types.Part.from_bytes(
            data=image_bytes,
            mime_type=mime_type
        )
    )

    contents = [
        types.Content(
            role="user",
            parts=[
                image_part,
                types.Part(
                    text=message
                )
            ]
        )
    ]

    return call_gemini(
        contents,
        make_system_text(
            user_memory
        )
    )


# =========================================================
# WEB ARAYÜZÜ
# =========================================================

HTML = r"""
<!DOCTYPE html>

<html lang="tr">

<head>

<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width, initial-scale=1.0"
>

<title>
NOVA AI — SHADOWFURYMEDYA
</title>

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

    color: white;

    font-family:
        Arial,
        sans-serif;

    overflow: hidden;
}


.app {

    height: 100vh;

    display: flex;

    flex-direction: column;
}


/* HEADER */

.header {

    min-height: 68px;

    display: flex;

    align-items: center;

    justify-content: space-between;

    padding:
        0
        18px;

    background:
        rgba(
            10,
            12,
            20,
            .88
        );

    border-bottom:
        1px solid
        rgba(
            255,
            255,
            255,
            .08
        );
}


.brand {

    display: flex;

    align-items: center;

    gap: 11px;
}


.logo {

    width: 40px;

    height: 40px;

    display: grid;

    place-items: center;

    border-radius: 12px;

    background:
        linear-gradient(
            135deg,
            #885cff,
            #4f7cff
        );

    font-weight: bold;
}


.brand-name {

    font-weight: bold;
}


.brand-sub {

    margin-top: 2px;

    color: #8d93a8;

    font-size: 11px;
}


.new-chat {

    padding:
        9px
        12px;

    border: 0;

    border-radius: 10px;

    background:
        rgba(
            255,
            255,
            255,
            .08
        );

    color: white;

    cursor: pointer;
}


/* CHAT */

.chat {

    flex: 1;

    overflow-y: auto;

    padding:
        25px
        max(
            14px,
            calc(
                (100vw - 900px)
                / 2
            )
        )
        145px;

    scroll-behavior: smooth;
}


.welcome {

    margin-top: 12vh;

    text-align: center;
}


.welcome h1 {

    margin-bottom: 10px;

    font-size:
        clamp(
            36px,
            6vw,
            58px
        );

    background:
        linear-gradient(
            90deg,
            #ffffff,
            #9caeff,
            #ba8cff
        );

    -webkit-background-clip:
        text;

    color:
        transparent;
}


.welcome p {

    color:
        #969bad;
}


/* MESAJ */

.row {

    display: flex;

    margin-bottom: 17px;
}


.row.user {

    justify-content:
        flex-end;
}


.row.assistant {

    justify-content:
        flex-start;
}


.bubble {

    max-width:
        min(
            760px,
            90%
        );

    padding:
        13px
        15px;

    border-radius:
        17px;

    line-height:
        1.55;

    white-space:
        pre-wrap;

    word-break:
        break-word;
}


.user .bubble {

    background:
        linear-gradient(
            135deg,
            #6957e8,
            #526fea
        );
}


.assistant .bubble {

    background:
        rgba(
            255,
            255,
            255,
            .07
        );

    border:
        1px solid
        rgba(
            255,
            255,
            255,
            .08
        );
}


/* FOTO ÖNİZLEME */

.photo-preview {

    display: block;

    max-width: 260px;

    max-height: 260px;

    margin-bottom: 10px;

    border-radius: 14px;
}


/* KOPYALA */

.copy-btn {

    display: block;

    margin-top: 8px;

    border: 0;

    background:
        transparent;

    color:
        #969bad;

    cursor:
        pointer;
}


/* ALT ALAN */

.bottom {

    position: fixed;

    left: 0;

    right: 0;

    bottom: 0;

    padding:
        12px
        max(
            12px,
            calc(
                (100vw - 900px)
                / 2
            )
        )
        16px;

    background:
        linear-gradient(
            transparent,
            rgba(
                5,
                6,
                10,
                .99
            )
            28%
        );
}


/* SEÇİLEN FOTO */

.selected-image {

    display: none;

    align-items: center;

    justify-content:
        space-between;

    gap: 10px;

    margin-bottom: 8px;

    padding:
        9px
        12px;

    border-radius:
        12px;

    background:
        rgba(
            255,
            255,
            255,
            .08
        );

    color:
        #c7cada;

    font-size:
        12px;
}


.selected-image.show {

    display: flex;
}


.remove-image {

    border: 0;

    background:
        transparent;

    color:
        #ff8f9b;

    cursor:
        pointer;
}


/* INPUT */

.input-box {

    display: flex;

    align-items:
        flex-end;

    gap: 8px;

    padding: 8px;

    border-radius:
        18px;

    background:
        rgba(
            22,
            25,
            38,
            .97
        );

    border:
        1px solid
        rgba(
            255,
            255,
            255,
            .10
        );
}


textarea {

    flex: 1;

    min-width: 0;

    min-height: 44px;

    max-height: 140px;

    resize: none;

    border: 0;

    outline: 0;

    padding: 11px;

    background:
        transparent;

    color: white;

    font: inherit;
}


textarea::placeholder {

    color:
        #71778c;
}


.icon-button {

    width: 44px;

    height: 44px;

    flex-shrink: 0;

    border: 0;

    border-radius:
        13px;

    background:
        rgba(
            255,
            255,
            255,
            .09
        );

    color:
        white;

    cursor:
        pointer;

    font-size:
        18px;
}


.send-button {

    background:
        linear-gradient(
            135deg,
            #7657ed,
            #4f75f1
        );
}


.icon-button:disabled {

    opacity:
        .45;

    cursor:
        default;
}


@media (
    max-width: 600px
) {

    .header {

        min-height:
            60px;

        padding:
            0
            12px;
    }


    .chat {

        padding:
            18px
            10px
            135px;
    }


    .bubble {

        max-width:
            94%;
    }


    .brand-sub {

        display:
            none;
    }
}

</style>

</head>


<body>


<div class="app">


<header class="header">


    <div class="brand">


        <div class="logo">
            N
        </div>


        <div>


            <div class="brand-name">
                NOVA AI
            </div>


            <div class="brand-sub">
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
            Mesaj yaz veya fotoğraf yükle.
        </p>


    </div>


</main>


<div class="bottom">


    <div
        id="selectedImage"
        class="selected-image"
    >


        <span
            id="selectedName"
        ></span>


        <button
            class="remove-image"
            onclick="removeImage()"
        >
            Kaldır ✕
        </button>


    </div>


    <div class="input-box">


        <input
            id="imageInput"
            type="file"
            accept="image/jpeg,image/png,image/webp"
            hidden
        >


        <button
            id="imageButton"
            class="icon-button"
            title="Fotoğraf ekle"
        >
            🖼️
        </button>


        <textarea
            id="messageInput"
            rows="1"
            placeholder="NOVA AI'a mesaj gönder..."
        ></textarea>


        <button
            id="sendButton"
            class="icon-button send-button"
            title="Gönder"
        >
            ➤
        </button>


    </div>


</div>


</div>


<script>


const chat =
    document.getElementById(
        "chat"
    );


const input =
    document.getElementById(
        "messageInput"
    );


const imageInput =
    document.getElementById(
        "imageInput"
    );


const imageButton =
    document.getElementById(
        "imageButton"
    );


const sendButton =
    document.getElementById(
        "sendButton"
    );


const selectedImage =
    document.getElementById(
        "selectedImage"
    );


const selectedName =
    document.getElementById(
        "selectedName"
    );


let selectedFile =
    null;


let busy =
    false;


/* =====================================================
   MESAJ
===================================================== */


function hideWelcome() {

    const welcome =
        document.getElementById(
            "welcome"
        );


    if (welcome) {

        welcome.style.display =
            "none";
    }
}


function addMessage(
    role,
    text,
    imageUrl = null
) {

    hideWelcome();


    const row =
        document.createElement(
            "div"
        );


    row.className =
        "row " + role;


    const bubble =
        document.createElement(
            "div"
        );


    bubble.className =
        "bubble";


    if (imageUrl) {


        const image =
            document.createElement(
                "img"
            );


        image.className =
            "photo-preview";


        image.src =
            imageUrl;


        bubble.appendChild(
            image
        );
    }


    if (text) {


        const textElement =
            document.createElement(
                "div"
            );


        textElement.textContent =
            text;


        bubble.appendChild(
            textElement
        );
    }


    if (
        role === "assistant"
        && text
    ) {


        const copy =
            document.createElement(
                "button"
            );


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
}


/* =====================================================
   YAZIYOR
===================================================== */


function showTyping() {


    const row =
        document.createElement(
            "div"
        );


    row.id =
        "typingRow";


    row.className =
        "row assistant";


    row.innerHTML =
        '<div class="bubble">NOVA yazıyor...</div>';


    chat.appendChild(
        row
    );


    chat.scrollTop =
        chat.scrollHeight;
}


function hideTyping() {


    const row =
        document.getElementById(
            "typingRow"
        );


    if (row) {

        row.remove();
    }
}


/* =====================================================
   FOTOĞRAF SEÇ
===================================================== */


imageButton.onclick =
    function () {


        imageInput.click();
    };


imageInput.onchange =
    function () {


        const file =
            imageInput.files[0];


        if (!file) {


            removeImage();


            return;
        }


        const allowed =
            [
                "image/jpeg",
                "image/png",
                "image/webp"
            ];


        if (
            !allowed.includes(
                file.type
            )
        ) {


            alert(
                "Sadece JPG, PNG veya WEBP yükleyebilirsin."
            );


            imageInput.value =
                "";


            return;
        }


        if (
            file.size >
            8 * 1024 * 1024
        ) {


            alert(
                "Fotoğraf en fazla 8 MB olabilir."
            );


            imageInput.value =
                "";


            return;
        }


        selectedFile =
            file;


        selectedName.textContent =
            "🖼️ " + file.name;


        selectedImage
            .classList
            .add(
                "show"
            );
    };


function removeImage() {


    selectedFile =
        null;


    imageInput.value =
        "";


    selectedName.textContent =
        "";


    selectedImage
        .classList
        .remove(
            "show"
        );
}


/* =====================================================
   GÖNDER
===================================================== */


async function sendMessage() {


    if (busy) {

        return;
    }


    const message =
        input.value.trim();


    if (
        !message
        && !selectedFile
    ) {

        return;
    }


    busy =
        true;


    sendButton.disabled =
        true;


    imageButton.disabled =
        true;


    let previewUrl =
        null;


    if (selectedFile) {


        previewUrl =
            URL.createObjectURL(
                selectedFile
            );
    }


    addMessage(
        "user",
        message ||
        "Bu fotoğrafı incele.",
        previewUrl
    );


    showTyping();


    try {


        let response;


        if (selectedFile) {


            const form =
                new FormData();


            form.append(
                "message",
                message ||
                "Bu fotoğrafı incele."
            );


            form.append(
                "image",
                selectedFile
            );


            response =
                await fetch(
                    "/chat-image",
                    {
                        method:
                            "POST",

                        body:
                            form
                    }
                );


        } else {


            response =
                await fetch(
                    "/chat",
                    {
                        method:
                            "POST",

                        headers: {

                            "Content-Type":
                                "application/json"
                        },

                        body:
                            JSON.stringify(
                                {
                                    message:
                                        message
                                }
                            )
                    }
                );
        }


        const data =
            await response.json();


        hideTyping();


        addMessage(
            "assistant",
            data.reply ||
            data.error ||
            "NOVA cevap veremedi."
        );


        input.value =
            "";


        input.style.height =
            "44px";


        removeImage();


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


        busy =
            false;


        sendButton.disabled =
            false;


        imageButton.disabled =
            false;


        input.focus();


        if (previewUrl) {


            setTimeout(
                function () {


                    URL.revokeObjectURL(
                        previewUrl
                    );


                },
                5000
            );
        }
    }
}


/* =====================================================
   BUTON + ENTER
===================================================== */


sendButton.onclick =
    sendMessage;


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


input.addEventListener(
    "input",
    function () {


        this.style.height =
            "44px";


        this.style.height =
            Math.min(
                this.scrollHeight,
                140
            )
            + "px";
    }
);


/* =====================================================
   YENİ SOHBET
===================================================== */


async function clearChat() {


    try {


        await fetch(
            "/clear",
            {
                method:
                    "POST"
            }
        );


    } catch (error) {


        console.error(
            error
        );
    }


    chat.innerHTML = `
        <div
            id="welcome"
            class="welcome"
        >
            <h1>
                NOVA AI
            </h1>

            <p>
                Mesaj yaz veya fotoğraf yükle.
            </p>
        </div>
    `;
}


/* =====================================================
   GEÇMİŞ
===================================================== */


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
# ANA SAYFA
# =========================================================

@app.route("/")
def home():

    get_user_id()

    return render_template_string(
        HTML
    )


# =========================================================
# NORMAL MESAJ
# =========================================================

@app.route(
    "/chat",
    methods=["POST"]
)
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
            "error":
                "Mesaj boş olamaz."
        }), 400

    update_memory(
        message,
        user_memory
    )

    reply, error = ask_text(
        message,
        user_history,
        user_memory
    )

    if error:

        return jsonify({
            "error":
                error
        }), 503

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

    user_histories[user_id] = (
        user_history[-200:]
    )

    return jsonify({
        "reply":
            reply
    })


# =========================================================
# FOTOĞRAF MESAJI
# =========================================================

@app.route(
    "/chat-image",
    methods=["POST"]
)
def chat_image_route():

    user_id = get_user_id()

    user_history = get_user_history(
        user_id
    )

    user_memory = get_user_memory(
        user_id
    )

    message = str(
        request.form.get(
            "message",
            ""
        )
    ).strip()

    uploaded = request.files.get(
        "image"
    )

    if (
        uploaded is None
        or not uploaded.filename
    ):

        return jsonify({
            "error":
                "Fotoğraf bulunamadı."
        }), 400

    allowed_types = {
        "image/jpeg",
        "image/png",
        "image/webp"
    }

    mime_type = (
        uploaded.mimetype
    )

    if (
        mime_type
        not in allowed_types
    ):

        return jsonify({
            "error":
                "Sadece JPG, PNG veya WEBP yükleyebilirsin."
        }), 400

    image_bytes = uploaded.read()

    if not image_bytes:

        return jsonify({
            "error":
                "Fotoğraf boş."
        }), 400

    if (
        len(image_bytes)
        >
        8 * 1024 * 1024
    ):

        return jsonify({
            "error":
                "Fotoğraf en fazla 8 MB olabilir."
        }), 400

    prompt = (
        message
        or
        "Bu fotoğrafı incele ve bana ne gördüğünü anlat."
    )

    reply, error = ask_image(
        prompt,
        image_bytes,
        mime_type,
        user_memory
    )

    if error:

        return jsonify({
            "error":
                error
        }), 503

    user_history.append({
        "role":
            "user",

        "text":
            "🖼️ Fotoğraf: "
            + prompt,

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

    user_histories[user_id] = (
        user_history[-200:]
    )

    return jsonify({
        "reply":
            reply
    })


# =========================================================
# GEÇMİŞ
# =========================================================

@app.route("/history")
def history_route():

    user_id = get_user_id()

    history = get_user_history(
        user_id
    )

    return jsonify({
        "history":
            history[-100:]
    })


# =========================================================
# YENİ SOHBET
# =========================================================

@app.route(
    "/clear",
    methods=["POST"]
)
def clear_route():

    user_id = get_user_id()

    user_histories[user_id] = []

    return jsonify({
        "ok":
            True
    })


# =========================================================
# BAŞLAT
# =========================================================

if __name__ == "__main__":

    print()
    print(
        "========================================"
    )
    print(
        "          NOVA AI BAŞLATILIYOR"
    )
    print(
        "========================================"
    )
    print()
    print(
        "Kişisel sohbet: AKTİF"
    )
    print(
        "Fotoğraf yükleme: AKTİF"
    )
    print(
        "Fotoğraf analizi: AKTİF"
    )
    print()
    print(
        "http://127.0.0.1:5000"
    )
    print()

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False
    )
