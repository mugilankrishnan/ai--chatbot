let sessionId = "session_" + Date.now();
let isLight = false, voiceMode = false;
let sessionTopics = {}, pinnedSessions = [], allSessions = [];
let currentModel = "llama-3.3-70b-versatile";
let isGenerating = false;
let abortController = null;

function getToken() { return localStorage.getItem("nova_token"); }
function getName() { return localStorage.getItem("nova_name"); }
function authHeaders() { return { "Content-Type": "application/json", "Authorization": "Bearer " + getToken() }; }
function checkAuth() { if (!getToken()) window.location.href = "/login"; }
function logout() { localStorage.removeItem("nova_token"); localStorage.removeItem("nova_name"); window.location.href = "/login"; }

function showUserInfo() {
    const name = getName();
    if (name) document.getElementById("userInfo").innerHTML = `Hello, <span>${name}</span>`;
}

function changeModel(model) {
    currentModel = model;
    showToast("Model changed to " + document.getElementById("modelSelect").options[document.getElementById("modelSelect").selectedIndex].text);
}

function stopGenerating() {
    if (abortController) { abortController.abort(); }
    isGenerating = false;
    document.getElementById("stopBtn").style.display = "none";
    removeTyping();
    showToast("Generation stopped");
}

function toggleSidebar() { document.getElementById("sidebar").classList.toggle("open"); }

async function loadTopics() {
    const res = await fetch("/topics", { headers: authHeaders() });
    if (res.status === 401) { logout(); return; }
    const data = await res.json();
    sessionTopics = data.topics;
}

async function loadSessions() {
    const res = await fetch("/sessions", { headers: authHeaders() });
    if (res.status === 401) { logout(); return; }
    const data = await res.json();
    allSessions = data.sessions;
    renderSessions(allSessions);
}

function renderSessions(sessions) {
    renderList("pinnedList", sessions.filter(s => pinnedSessions.includes(s)));
    renderList("sessionList", sessions.filter(s => !pinnedSessions.includes(s)));
}

function renderList(listId, sessions) {
    const list = document.getElementById(listId);
    list.innerHTML = "";
    sessions.forEach(s => {
        const item = document.createElement("div");
        item.className = "session-item" + (s === sessionId ? " active" : "");
        const name = document.createElement("div");
        name.className = "session-name";
        if (pinnedSessions.includes(s)) { const pin = document.createElement("span"); pin.className = "pin-icon"; pin.textContent = "📌"; name.appendChild(pin); }
        name.appendChild(document.createTextNode(sessionTopics[s] || "New Chat"));
        name.onclick = () => loadSession(s);
        const dots = document.createElement("button");
        dots.className = "dots-btn";
        dots.textContent = "...";
        dots.onclick = (e) => { e.stopPropagation(); toggleDropdown(s); };
        const dropdown = document.createElement("div");
        dropdown.className = "dropdown";
        dropdown.id = "drop_" + s;
        [
            { label: "Share", fn: () => shareSession(s) },
            { label: "Rename", fn: () => renameSession(s) },
            { label: pinnedSessions.includes(s) ? "Unpin" : "Pin", fn: () => togglePin(s) },
            { label: "Delete", fn: () => deleteSession(s) }
        ].forEach(a => {
            const btn = document.createElement("button");
            btn.textContent = a.label;
            btn.onclick = (e) => { e.stopPropagation(); dropdown.classList.remove("show"); a.fn(); };
            dropdown.appendChild(btn);
        });
        item.appendChild(name);
        item.appendChild(dots);
        item.appendChild(dropdown);
        list.appendChild(item);
    });
}

function toggleDropdown(s) {
    document.querySelectorAll(".dropdown").forEach(d => d.classList.remove("show"));
    const drop = document.getElementById("drop_" + s);
    if (drop) drop.classList.toggle("show");
}

document.addEventListener("click", () => document.querySelectorAll(".dropdown").forEach(d => d.classList.remove("show")));

function searchSessions() {
    const q = document.getElementById("searchBox").value.toLowerCase();
    renderSessions(allSessions.filter(s => (sessionTopics[s] || "new chat").toLowerCase().includes(q)));
}

async function loadSession(id) {
    sessionId = id;
    document.getElementById("chatBox").innerHTML = "";
    const res = await fetch("/history?session_id=" + id, { headers: authHeaders() });
    const data = await res.json();
    if (data.history.length === 0) { showWelcome(); return; }
    for (let i = 0; i < data.history.length; i++) {
        const m = data.history[i];
        if (m.role === "assistant") {
            const lastUser = data.history.slice(0, i).reverse().find(x => x.role === "user");
            await addBotMessage(m.content, lastUser ? lastUser.content : "", false);
        } else { addUserMessage(m.content); }
    }
    renderSessions(allSessions);
}

async function deleteSession(id) {
    await fetch("/history?session_id=" + id, { method: "DELETE", headers: authHeaders() });
    delete sessionTopics[id];
    pinnedSessions = pinnedSessions.filter(p => p !== id);
    if (id === sessionId) newChat(); else loadSessions();
}

async function shareSession(id) {
    const res = await fetch("/share-chat", { method: "POST", headers: authHeaders(), body: JSON.stringify({ session_id: id }) });
    const data = await res.json();
    if (res.ok) {
        navigator.clipboard.writeText(data.share_url);
        showToast("Share link copied to clipboard!");
    } else { showToast("Failed to share"); }
}

function shareSession(id) {
    fetch("/share-chat", { method: "POST", headers: authHeaders(), body: JSON.stringify({ session_id: id }) })
        .then(r => r.json())
        .then(data => { navigator.clipboard.writeText(data.share_url); showToast("Share link copied!"); });
}

async function renameSession(id) {
    const n = prompt("New name:", sessionTopics[id] || "New Chat");
    if (n) {
        sessionTopics[id] = n;
        await fetch("/save-topic", { method: "POST", headers: authHeaders(), body: JSON.stringify({ session_id: id, topic: n }) });
        renderSessions(allSessions);
    }
}

function togglePin(id) { pinnedSessions = pinnedSessions.includes(id) ? pinnedSessions.filter(p => p !== id) : [...pinnedSessions, id]; renderSessions(allSessions); }
function newChat() { window.speechSynthesis.cancel(); sessionId = "session_" + Date.now(); showWelcome(); renderSessions(allSessions); }

function showWelcome() {
    document.getElementById("chatBox").innerHTML = `
        <div class="welcome">
            <h2>NOVA AI</h2>
            <p>Your intelligent assistant. How can I help you today?</p>
            <div class="suggestions">
                <button class="suggestion-btn" onclick="suggest('Explain a concept simply')">💡 Explain a concept</button>
                <button class="suggestion-btn" onclick="suggest('Write Python code for')">💻 Write Python code</button>
                <button class="suggestion-btn" onclick="suggest('Summarize this topic:')">📝 Summarize a topic</button>
                <button class="suggestion-btn" onclick="suggest('What are the differences between')">🔍 Compare two things</button>
            </div>
        </div>`;
}

function suggest(text) { document.getElementById("userInput").value = text; document.getElementById("userInput").focus(); }
function toggleTheme() { isLight = !isLight; document.body.classList.toggle("light"); document.getElementById("themeBtn").textContent = isLight ? "Dark Mode" : "Light Mode"; }

async function generateTopic(message) {
    const res = await fetch("/generate-topic", { method: "POST", headers: authHeaders(), body: JSON.stringify({ message }) });
    return (await res.json()).topic;
}

async function sendMessage() {
    const input = document.getElementById("userInput");
    const message = input.value.trim();
    if (!message || isGenerating) return;
    const welcome = document.querySelector(".welcome");
    if (welcome) welcome.remove();

    if (!sessionTopics[sessionId]) {
        const topic = await generateTopic(message);
        sessionTopics[sessionId] = topic;
        await fetch("/save-topic", { method: "POST", headers: authHeaders(), body: JSON.stringify({ session_id: sessionId, topic }) });
    }

    addUserMessage(message);
    await loadSessions();
    input.value = "";
    isGenerating = true;
    document.getElementById("stopBtn").style.display = "block";
    showTyping("NOVA AI is typing...");

    try {
        abortController = new AbortController();
        const res = await fetch("/chat", {
            method: "POST",
            headers: authHeaders(),
            body: JSON.stringify({ session_id: sessionId, message, model: currentModel }),
            signal: abortController.signal
        });
        const data = await res.json();
        removeTyping();
        await addBotMessage(data.reply, message, true);
        if (voiceMode) speakText(data.reply);
        voiceMode = false;
    } catch (e) {
        removeTyping();
        if (e.name !== "AbortError") showToast("Error sending message");
    }

    isGenerating = false;
    document.getElementById("stopBtn").style.display = "none";
    loadSessions();
}

async function retryMessage(userMsg) {
    showTyping("NOVA AI is retrying...");
    const res = await fetch("/retry", { method: "POST", headers: authHeaders(), body: JSON.stringify({ session_id: sessionId, message: userMsg, model: currentModel }) });
    const data = await res.json();
    removeTyping();
    await addBotMessage(data.reply, userMsg, true);
}

async function editMessage(wrapper, oldText) {
    const newText = prompt("Edit your message:", oldText);
    if (!newText || newText === oldText) return;
    await fetch("/edit-message", { method: "POST", headers: authHeaders(), body: JSON.stringify({ session_id: sessionId, message: oldText }) });
    let next = wrapper.nextElementSibling;
    while (next) { const toRemove = next; next = next.nextElementSibling; toRemove.remove(); }
    wrapper.remove();
    document.getElementById("userInput").value = newText;
    sendMessage();
}

async function uploadImage(event) {
    const file = event.target.files[0];
    if (!file) return;
    const welcome = document.querySelector(".welcome");
    if (welcome) welcome.remove();
    const reader = new FileReader();
    reader.onload = e => {
        const wrapper = document.createElement("div");
        wrapper.classList.add("message-wrapper", "user-wrapper");
        const img = document.createElement("img");
        img.src = e.target.result;
        img.className = "uploaded-image";
        wrapper.appendChild(img);
        document.getElementById("chatBox").appendChild(wrapper);
    };
    reader.readAsDataURL(file);
    showTyping("NOVA AI is analyzing image...");
    const formData = new FormData();
    formData.append("file", file);
    const res = await fetch("/upload-image", { method: "POST", headers: { "Authorization": "Bearer " + getToken() }, body: formData });
    const data = await res.json();
    removeTyping();
    await addBotMessage(data.reply, "image", true);
    if (!sessionTopics[sessionId]) {
        const topic = "Image: " + file.name;
        sessionTopics[sessionId] = topic;
        await fetch("/save-topic", { method: "POST", headers: authHeaders(), body: JSON.stringify({ session_id: sessionId, topic }) });
        loadSessions();
    }
    event.target.value = "";
}

async function uploadFile(event) {
    const file = event.target.files[0];
    if (!file) return;
    const welcome = document.querySelector(".welcome");
    if (welcome) welcome.remove();
    addUserMessage("📄 " + file.name);
    showTyping("NOVA AI is reading file...");
    const formData = new FormData();
    formData.append("file", file);
    const res = await fetch("/upload-file", { method: "POST", headers: { "Authorization": "Bearer " + getToken() }, body: formData });
    const data = await res.json();
    removeTyping();
    await addBotMessage(data.reply, file.name, true);
    if (!sessionTopics[sessionId]) {
        const topic = "File: " + file.name;
        sessionTopics[sessionId] = topic;
        await fetch("/save-topic", { method: "POST", headers: authHeaders(), body: JSON.stringify({ session_id: sessionId, topic }) });
        loadSessions();
    }
    event.target.value = "";
}

function addUserMessage(text) {
    const chatBox = document.getElementById("chatBox");
    const wrapper = document.createElement("div");
    wrapper.classList.add("message-wrapper", "user-wrapper");
    const div = document.createElement("div");
    div.classList.add("message", "user-message");
    div.textContent = text;
    const actions = document.createElement("div");
    actions.className = "actions";
    actions.style.justifyContent = "flex-end";
    [
        { label: "✏️ Edit", fn: () => editMessage(wrapper, text) },
        { label: "Copy", fn: () => { navigator.clipboard.writeText(text); showToast("Copied!"); } }
    ].forEach(b => {
        const btn = document.createElement("button");
        btn.className = "action-btn";
        btn.textContent = b.label;
        btn.onclick = b.fn;
        actions.appendChild(btn);
    });
    wrapper.appendChild(div);
    wrapper.appendChild(actions);
    chatBox.appendChild(wrapper);
    chatBox.scrollTop = chatBox.scrollHeight;
}

async function addBotMessage(text, userMsg, animate) {
    const chatBox = document.getElementById("chatBox");
    const wrapper = document.createElement("div");
    wrapper.classList.add("message-wrapper", "bot-wrapper");
    const div = document.createElement("div");
    div.classList.add("message", "bot-message");
    if (animate) {
        const words = text.split(" ");
        let current = "";
        for (let i = 0; i < words.length; i++) {
            if (!isGenerating && i > 0) break;
            current += (i === 0 ? "" : " ") + words[i];
            div.innerHTML = marked.parse(current);
            chatBox.scrollTop = chatBox.scrollHeight;
            await new Promise(r => setTimeout(r, 30));
        }
    } else { div.innerHTML = marked.parse(text); }

    div.querySelectorAll('pre').forEach(pre => {
        pre.style.position = "relative";
        const code = pre.querySelector('code');
        if (code) hljs.highlightElement(code);
        const copyBtn = document.createElement("button");
        copyBtn.className = "copy-code-btn";
        copyBtn.textContent = "Copy";
        copyBtn.onclick = () => { navigator.clipboard.writeText(pre.querySelector('code').textContent); copyBtn.textContent = "Copied!"; setTimeout(() => copyBtn.textContent = "Copy", 2000); };
        pre.appendChild(copyBtn);
    });

    const actions = document.createElement("div");
    actions.className = "actions";
    const readBtn = document.createElement("button");
    readBtn.className = "action-btn";
    readBtn.textContent = "Read Aloud";
    readBtn.onclick = () => {
        if (window.speechSynthesis.speaking) { window.speechSynthesis.cancel(); readBtn.textContent = "Read Aloud"; }
        else { speakText(text, readBtn); }
    };
    actions.appendChild(readBtn);
    [
        { label: "Copy", fn: () => { navigator.clipboard.writeText(text); showToast("Copied!"); } },
        { label: "👍", fn: () => showToast("Thanks for the feedback!") },
        { label: "👎", fn: () => showToast("Sorry! We will improve.") },
        { label: "Retry", fn: () => retryMessage(userMsg) }
    ].forEach(b => {
        const btn = document.createElement("button");
        btn.className = "action-btn";
        btn.textContent = b.label;
        btn.onclick = b.fn;
        actions.appendChild(btn);
    });
    wrapper.appendChild(div);
    wrapper.appendChild(actions);
    chatBox.appendChild(wrapper);
    chatBox.scrollTop = chatBox.scrollHeight;
}

function showTyping(msg) { const t = document.createElement("div"); t.className = "typing"; t.id = "typing"; t.textContent = msg; document.getElementById("chatBox").appendChild(t); document.getElementById("chatBox").scrollTop = document.getElementById("chatBox").scrollHeight; }
function removeTyping() { const t = document.getElementById("typing"); if (t) t.remove(); }
function showToast(msg) { const toast = document.getElementById("toast"); toast.textContent = msg; toast.style.display = "block"; setTimeout(() => toast.style.display = "none", 2000); }

function speakText(text, btn) {
    window.speechSynthesis.cancel();
    const lang = document.getElementById("langSelect").value;
    const speech = new SpeechSynthesisUtterance(text);
    speech.lang = lang; speech.rate = 1; speech.pitch = 1;
    if (btn) { btn.textContent = "Stop"; speech.onend = () => { btn.textContent = "Read Aloud"; }; }
    window.speechSynthesis.speak(speech);
}

function startVoice() {
    voiceMode = true;
    const lang = document.getElementById("langSelect").value;
    const recognition = new (window.SpeechRecognition || window.webkitSpeechRecognition)();
    recognition.lang = lang;
    recognition.start();
    const micBtn = document.getElementById("micBtn");
    micBtn.classList.add("listening");
    micBtn.textContent = "Listening...";
    recognition.onresult = e => { document.getElementById("userInput").value = e.results[0][0].transcript; micBtn.classList.remove("listening"); micBtn.textContent = "Mic"; sendMessage(); };
    recognition.onerror = () => { voiceMode = false; micBtn.classList.remove("listening"); micBtn.textContent = "Mic"; };
}

function scrollToBottom() {
    const chatBox = document.getElementById("chatBox");
    chatBox.scrollTo({ top: chatBox.scrollHeight, behavior: "smooth" });
    document.getElementById("scrollBtn").style.display = "none";
}

document.getElementById("chatBox").addEventListener("scroll", () => {
    const chatBox = document.getElementById("chatBox");
    const distanceFromBottom = chatBox.scrollHeight - chatBox.scrollTop - chatBox.clientHeight;
    document.getElementById("scrollBtn").style.display = distanceFromBottom > 150 ? "block" : "none";
});

function exportChat() {
    const messages = document.getElementById("chatBox").querySelectorAll(".message");
    let content = `NOVA AI - Chat Export\n${"=".repeat(40)}\n\n`;
    messages.forEach(m => { content += `${m.classList.contains("user-message") ? "You" : "NOVA AI"}:\n${m.textContent}\n\n`; });
    content += `${"=".repeat(40)}\nExported on: ${new Date().toLocaleString()}`;
    const blob = new Blob([content], { type: "text/plain" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "NOVA_AI_Chat.txt"; a.click();
    showToast("Chat exported!");
}

document.addEventListener("keydown", e => {
    if (e.ctrlKey && e.key === "n") { e.preventDefault(); newChat(); }
    if (e.ctrlKey && e.key === "k") { e.preventDefault(); document.getElementById("searchBox").focus(); }
    if (e.ctrlKey && e.key === "d") { e.preventDefault(); toggleTheme(); }
});

document.getElementById("userInput").addEventListener("keypress", e => { if (e.key === "Enter" && !isGenerating) sendMessage(); });

async function init() {
    checkAuth();
    showUserInfo();
    const u = await fetch("/api/me", { headers: authHeaders() }).then(r => r.json());
    currentModel = u.default_model || "llama-3.3-70b-versatile";
    document.getElementById("modelSelect").value = currentModel;
    await loadTopics();
    await loadSessions();
}
init();