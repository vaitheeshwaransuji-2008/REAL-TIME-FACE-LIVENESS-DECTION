// ---------------- BIOMETRIC FRONTEND CORE ----------------

let socket;
let video;
let overlayCanvas;
let overlayCtx;
let stream;
let frameInterval;
const FRAME_RATE_MS = 50; // ~20 FPS

let activeScreen = "opening"; // "opening", "menu", "dashboard"
let currentMode = "verify";   // "verify", "store"
let enrollName = "";
let activeBlinks = 0;
let isAudioMuted = false;
let isRealFaceLatched = false;
let latchedRealFaceData = null;
let isFakeFaceLatched = false;

// Offscreen canvas for downsampling video frames
const offscreenCanvas = document.createElement("canvas");
const offscreenCtx = offscreenCanvas.getContext("2d");
offscreenCanvas.width = 480;
offscreenCanvas.height = 360;

// Helper for environment network configurations
function getBackendUrls() {
    let wsUrl, httpUrl;
    if (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1") {
        const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        wsUrl = `${protocol}//${window.location.host}/ws`;
        httpUrl = "";
    } else {
        // Deployed on Vercel/cloud, connect to local running Python server
        wsUrl = "ws://127.0.0.1:8000/ws";
        httpUrl = "http://127.0.0.1:8000";
    }
    return { wsUrl, httpUrl };
}

// Web Audio API Synth Engine
let audioCtx = null;

function initAudio() {
    if (!audioCtx) {
        audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
    if (audioCtx.state === 'suspended') {
        audioCtx.resume();
    }
}

function playSound(type) {
    if (isAudioMuted) return;
    try {
        initAudio();
        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        osc.connect(gain);
        gain.connect(audioCtx.destination);
        
        const now = audioCtx.currentTime;
        
        if (type === "click") {
            osc.type = "sine";
            osc.frequency.setValueAtTime(800, now);
            osc.frequency.exponentialRampToValueAtTime(1200, now + 0.05);
            gain.gain.setValueAtTime(0.08, now);
            gain.gain.exponentialRampToValueAtTime(0.001, now + 0.05);
            osc.start(now);
            osc.stop(now + 0.06);
        } 
        else if (type === "blink") {
            osc.type = "triangle";
            osc.frequency.setValueAtTime(600, now);
            osc.frequency.exponentialRampToValueAtTime(900, now + 0.08);
            gain.gain.setValueAtTime(0.12, now);
            gain.gain.exponentialRampToValueAtTime(0.001, now + 0.08);
            osc.start(now);
            osc.stop(now + 0.09);
        }
        else if (type === "success") {
            osc.type = "sine";
            osc.frequency.setValueAtTime(523.25, now);
            osc.frequency.setValueAtTime(659.25, now + 0.08);
            osc.frequency.setValueAtTime(783.99, now + 0.16);
            osc.frequency.exponentialRampToValueAtTime(1046.50, now + 0.3);
            gain.gain.setValueAtTime(0.15, now);
            gain.gain.exponentialRampToValueAtTime(0.001, now + 0.4);
            osc.start(now);
            osc.stop(now + 0.45);
        }
        else if (type === "fail") {
            osc.type = "sawtooth";
            osc.frequency.setValueAtTime(150, now);
            osc.frequency.linearRampToValueAtTime(90, now + 0.35);
            gain.gain.setValueAtTime(0.2, now);
            gain.gain.exponentialRampToValueAtTime(0.001, now + 0.35);
            osc.start(now);
            osc.stop(now + 0.4);
        }
    } catch (e) {
        console.warn("Audio synthesis error: ", e);
    }
}

// Logger System
function logMessage(text, type = "info") {
    const logsContainer = document.getElementById("consoleLogs");
    if (!logsContainer) return;
    
    const timeStr = new Date().toTimeString().split(" ")[0];
    const logLine = document.createElement("div");
    logLine.className = `console-line ${type}`;
    logLine.innerHTML = `<span style="color:var(--text-muted)">[${timeStr}]</span> ${text}`;
    
    logsContainer.appendChild(logLine);
    logsContainer.scrollTop = logsContainer.scrollHeight;
    
    while (logsContainer.children.length > 50) {
        logsContainer.removeChild(logsContainer.firstChild);
    }
}

// Dynamic Floating Toast Notifications
function showToast(message, isError = false) {
    const toast = document.getElementById("toastBanner");
    toast.textContent = message.toUpperCase();
    if (isError) {
        toast.className = "toast-banner error show";
    } else {
        toast.className = "toast-banner show";
    }
    
    setTimeout(() => {
        toast.className = "toast-banner";
    }, 3000);
}

// ---------------- SCREEN NAVIGATION ROUTER ----------------

function showScreen(screenId) {
    activeScreen = screenId;
    playSound("click");
    
    // Toggle active screen visibility
    document.querySelectorAll(".screen-view").forEach(s => s.classList.remove("active"));
    const targetScreen = document.getElementById(`screen-${screenId}`);
    if (targetScreen) targetScreen.classList.add("active");
    
    logMessage(`Switched screen routing to: ${screenId.toUpperCase()}`, "system");
    
    // Lifecycle Management based on screen states
    if (screenId === "dashboard") {
        // Start streaming & camera ONLY when reaching Screen 3
        startCamera();
    } else {
        // Stop camera immediately on other screens to save system resources
        stopCamera();
        isRealFaceLatched = false;
        latchedRealFaceData = null;
        isFakeFaceLatched = false;
    }
}

// Clocks Update
function startClocks() {
    setInterval(() => {
        const d = new Date();
        const timeStr = d.toLocaleTimeString();
        document.getElementById("headerClock").textContent = timeStr;
        document.getElementById("menuClock").textContent = timeStr;
        document.getElementById("dashboardClock").textContent = timeStr;
    }, 1000);
}

// ---------------- CAMERA MANAGEMENT (ON DEMAND) ----------------

async function startCamera() {
    video = document.getElementById("videoElement");
    overlayCanvas = document.getElementById("overlayCanvas");
    overlayCtx = overlayCanvas.getContext("2d");
    
    try {
        logMessage("Accessing media devices...", "info");
        stream = await navigator.mediaDevices.getUserMedia({
            video: { width: 640, height: 480, facingMode: "user" },
            audio: false
        });
        
        video.srcObject = stream;
        video.play();
        logMessage("Webcam connection stream established.", "success");
        
        // Start WS uplink frames push
        video.onloadedmetadata = () => {
            startWebSocket();
        };
    } catch (err) {
        logMessage(`Webcam access denied: ${err.message}`, "error");
        showToast("Camera access is required!", true);
        showScreen("menu");
    }
}

function stopCamera() {
    // Clear WS loops
    if (frameInterval) {
        clearInterval(frameInterval);
        frameInterval = null;
    }
    
    // Release hardware stream
    if (stream) {
        stream.getTracks().forEach(track => track.stop());
        stream = null;
        logMessage("Webcam stream release complete.", "system");
    }
    
    if (socket) {
        socket.close();
        socket = null;
    }
}

// ---------------- WEBSOCKET FRAME TRANSFERS ----------------

function startWebSocket() {
    const urls = getBackendUrls();
    const wsUrl = urls.wsUrl;
    
    socket = new WebSocket(wsUrl);
    
    socket.onopen = () => {
        logMessage("Security uplink connected.", "success");
        
        // Handshake current configuration state to server
        socket.send(JSON.stringify({
            type: "config",
            mode: currentMode,
            name: currentMode === "store" ? enrollName : null
        }));
        
        // Trigger webcam capturing loop
        frameInterval = setInterval(sendVideoFrame, FRAME_RATE_MS);
    };
    
    socket.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        handleServerMessage(msg);
    };
    
    socket.onerror = (err) => {
        logMessage("Uplink error detected.", "error");
    };
    
    socket.onclose = () => {
        logMessage("Uplink signal terminated.", "warning");
        if (activeScreen === "dashboard") {
            // Auto reconnect only if on Dashboard screen
            setTimeout(startWebSocket, 3000);
        }
    };
}

function sendVideoFrame() {
    if (!socket || socket.readyState !== WebSocket.OPEN) return;
    if (!video || video.paused || video.ended) return;
    
    offscreenCtx.drawImage(video, 0, 0, offscreenCanvas.width, offscreenCanvas.height);
    const dataUrl = offscreenCanvas.toDataURL("image/jpeg", 0.65);
    
    socket.send(JSON.stringify({
        type: "frame",
        image: dataUrl
    }));
}

function handleServerMessage(msg) {
    if (msg.type === "init") {
        updateIdentityVault(msg.enrolled);
    } 
    else if (msg.type === "vault_update") {
        playSound("success");
        showToast("Profile Stored Successfully!");
        updateIdentityVault(msg.enrolled);
        
        // Flash status to FACES STORED on Screen 3
        const statusTextEl = document.getElementById("hudStatusText");
        statusTextEl.textContent = "FACES STORED";
        document.getElementById("hudStatusBadge").className = "hud-status-badge success";
        document.getElementById("hudStatusDot").style.backgroundColor = "var(--success)";
        
        // Keep screen visible for 2.5s, then redirect back to operations selection page
        setTimeout(() => {
            showScreen("menu");
        }, 2500);
    }
    else if (msg.type === "vault_purged") {
        playSound("fail");
        showToast("Vault Purged Completely!");
        updateIdentityVault([]);
    }
    else if (msg.type === "config_ack") {
        logMessage(`Backend Mode synchronised: ${msg.mode.toUpperCase()}`, "info");
        
        // Update Screen 3 UI banner details
        const modePill = document.getElementById("dashboardActiveModePill");
        if (msg.mode === "store") {
            modePill.textContent = `ENROLLING TARGET: ${msg.enroll_name.toUpperCase()}`;
            modePill.className = "active-profile-pill store";
        } else {
            modePill.textContent = "VERIFICATION STREAM ACTIVE";
            modePill.className = "active-profile-pill";
        }
    }
    else if (msg.type === "telemetry") {
        drawHUDOverlay(msg);
        updateTelemetryDashboard(msg);
    }
}

// Update Vault layouts on Screen 2 and Screen 3
function updateIdentityVault(enrolled) {
    const vaultCountVal = enrolled.length;
    
    // Vault count on Screen 2
    document.getElementById("menuVaultCount").textContent = vaultCountVal;
    
    // Vault elements on Screen 3
    const listContainer = document.getElementById("vaultList");
    const emptyContainer = document.getElementById("vaultEmpty");
    
    if (vaultCountVal === 0) {
        listContainer.style.display = "none";
        emptyContainer.style.display = "flex";
        return;
    }
    
    listContainer.style.display = "flex";
    emptyContainer.style.display = "none";
    listContainer.innerHTML = "";
    
    enrolled.forEach(person => {
        const card = document.createElement("div");
        card.className = "vault-card";
        const urls = getBackendUrls();
        const imgSrc = `${urls.httpUrl}/${person.image}?t=${Date.now()}`;
        
        card.innerHTML = `
            <div class="vault-avatar">
                <img src="${imgSrc}" alt="${person.name}" onerror="this.src='data:image/svg+xml;utf8,<svg xmlns=%22http://www.w3.org/2000/svg%22 width=%2240%22 height=%2240%22><rect width=%22100%%22 height=%22100%%22 fill=%22%23222%22/><text x=%2250%%22 y=%2260%%22 font-size=%2216%22 fill=%22%23555%22 font-family=%22sans-serif%22 text-anchor=%22middle%22>?</text></svg>'">
            </div>
            <div class="vault-info">
                <div class="vault-name">${person.name}</div>
                <div class="vault-meta">ID: ${person.id.padStart(4, '0')}</div>
            </div>
        `;
        listContainer.appendChild(card);
    });
}

function drawHUDOverlay(data) {
    if (!overlayCanvas) return;
    const width = overlayCanvas.width;
    const height = overlayCanvas.height;
    
    overlayCtx.clearRect(0, 0, width, height);
    
    const center = { x: width / 2, y: height / 2 };
    const radius = 195;
    
    overlayCtx.save();
    overlayCtx.beginPath();
    overlayCtx.arc(center.x, center.y, radius, 0, Math.PI * 2);
    overlayCtx.clip();
    
    // Mirror webcam projection
    overlayCtx.translate(width, 0);
    overlayCtx.scale(-1, 1);
    overlayCtx.drawImage(video, 0, 0, width, height);
    overlayCtx.restore();
    
    if (data.face_detected && data.box) {
        const [x1, y1, x2, y2] = data.box;
        const scaleX = width / video.videoWidth;
        const scaleY = height / video.videoHeight;
        
        const bx = width - (x2 * scaleX);
        const by = y1 * scaleY;
        const bw = (x2 - x1) * scaleX;
        const bh = (y2 - y1) * scaleY;
        
        let hudColor = "hsl(192, 95%, 50%)"; // Cyan (Scanning)
        let hudGlow = "rgba(192, 95, 50, 0.4)";
        
        if (data.status === "REAL FACE") {
            hudColor = "hsl(142, 76%, 45%)"; // Success Green
            hudGlow = "rgba(142, 76, 45, 0.4)";
        } else if (data.status === "FAKE FACE" || data.status === "UNKNOWN IDENTITY") {
            hudColor = "hsl(354, 76%, 48%)"; // Alert Red
            hudGlow = "rgba(254, 76, 48, 0.4)";
        }
        
        overlayCtx.strokeStyle = hudColor;
        overlayCtx.lineWidth = 1.5;
        
        const length = Math.min(bw, bh) * 0.2;
        
        // Top-Left
        overlayCtx.beginPath();
        overlayCtx.moveTo(bx + length, by);
        overlayCtx.lineTo(bx, by);
        overlayCtx.lineTo(bx, by + length);
        overlayCtx.stroke();
        
        // Top-Right
        overlayCtx.beginPath();
        overlayCtx.moveTo(bx + bw - length, by);
        overlayCtx.lineTo(bx + bw, by);
        overlayCtx.lineTo(bx + bw, by + length);
        overlayCtx.stroke();
        
        // Bottom-Left
        overlayCtx.beginPath();
        overlayCtx.moveTo(bx + length, by + bh);
        overlayCtx.lineTo(bx, by + bh);
        overlayCtx.lineTo(bx, by + bh - length);
        overlayCtx.stroke();
        
        // Bottom-Right
        overlayCtx.beginPath();
        overlayCtx.moveTo(bx + bw - length, by + bh);
        overlayCtx.lineTo(bx + bw, by + bh);
        overlayCtx.lineTo(bx + bw, by + bh - length);
        overlayCtx.stroke();
        
        overlayCtx.fillStyle = hudGlow.replace("0.4", "0.03");
        overlayCtx.fillRect(bx, by, bw, bh);
        
        // Face landmarks rendering
        if (data.landmarks && data.landmarks.length > 0) {
            overlayCtx.fillStyle = hudColor;
            overlayCtx.strokeStyle = hudColor.replace(")", ", 0.15)");
            overlayCtx.lineWidth = 0.5;
            
            const drawFacialPath = (startIndex, endIndex, close = false) => {
                overlayCtx.beginPath();
                for (let i = startIndex; i <= endIndex; i++) {
                    const pt = data.landmarks[i];
                    const px = width - (pt[0] * scaleX);
                    const py = pt[1] * scaleY;
                    if (i === startIndex) overlayCtx.moveTo(px, py);
                    else overlayCtx.lineTo(px, py);
                }
                if (close) overlayCtx.closePath();
                overlayCtx.stroke();
            };
            
            drawFacialPath(36, 41, true);
            drawFacialPath(42, 47, true);
            drawFacialPath(17, 21);
            drawFacialPath(22, 26);
            drawFacialPath(27, 30);
            drawFacialPath(31, 35);
            drawFacialPath(48, 59, true);
            
            data.landmarks.forEach(pt => {
                const px = width - (pt[0] * scaleX);
                const py = pt[1] * scaleY;
                overlayCtx.beginPath();
                overlayCtx.arc(px, py, 1.5, 0, Math.PI * 2);
                overlayCtx.fill();
            });
        }
    }
}

let lastStatus = "";
function updateTelemetryDashboard(data) {
    const earVal = data.ear;
    const maxEAR = 0.35;
    const percentage = Math.min(100, Math.max(0, (earVal / maxEAR) * 100));
    
    const circleCircumference = 170;
    const offset = circleCircumference - (percentage / 100) * circleCircumference;
    
    const fillRing = document.getElementById("earFillRing");
    const earTextVal = document.getElementById("earValueText");
    
    fillRing.style.strokeDashoffset = offset;
    earTextVal.textContent = earVal.toFixed(2);
    
    if (earVal < 0.23) {
        fillRing.style.stroke = "var(--error)";
    } else {
        fillRing.style.stroke = "var(--primary)";
    }
    
    // Blinks Counter
    const blinkCountEl = document.getElementById("blinkCounter");
    if (data.blinks !== activeBlinks) {
        activeBlinks = data.blinks;
        blinkCountEl.textContent = activeBlinks.toString().padStart(2, '0');
        playSound("blink");
        logMessage(`Blink action confirmed. Total: ${activeBlinks}`, "success");
    }
    
    // Checklist
    updateCheckItem("checkBlink", activeBlinks >= 1, activeBlinks >= 1 ? "1 / 1" : "0 / 1");
    updateCheckItem("checkLeft", data.head_left, data.head_left ? "DETECTED" : "PENDING");
    updateCheckItem("checkRight", data.head_right, data.head_right ? "DETECTED" : "PENDING");
    
    // Center Status Badge below Viewport
    const statusTextEl = document.getElementById("hudStatusText");
    const hudBadgeEl = document.getElementById("hudStatusBadge");
    const hudStatusDotEl = document.getElementById("hudStatusDot");
    const cameraHudEl = document.getElementById("cameraHud");
    
    // Enrollment Status vs Verification Status
    if (currentMode === "store") {
        if (data.status.startsWith("ENROLLED") || data.status.startsWith("EXISTS")) {
            statusTextEl.textContent = "FACES STORED";
            hudBadgeEl.className = "hud-status-badge success";
            hudStatusDotEl.style.backgroundColor = "var(--success)";
            cameraHudEl.className = "camera-hud real";
        } else {
            statusTextEl.textContent = "SCANNING";
            hudBadgeEl.className = "hud-status-badge";
            hudStatusDotEl.style.backgroundColor = "var(--warning)";
            cameraHudEl.className = "camera-hud scanning";
        }
    } 
    // Verification state status checks
    else {
        // Clear latched status if a new challenge begins
        if (data.blinks > 0 || data.head_left || data.head_right) {
            if (isRealFaceLatched || isFakeFaceLatched) {
                isRealFaceLatched = false;
                latchedRealFaceData = null;
                isFakeFaceLatched = false;
                logMessage("New liveness challenge started. Resetting status.", "info");
            }
        }

        if (data.status === "REAL FACE") {
            isRealFaceLatched = true;
            latchedRealFaceData = {
                match_name: data.match_name,
                confidence: data.confidence
            };
            isFakeFaceLatched = false;
        } else if (data.status === "FAKE FACE" || data.status === "UNKNOWN IDENTITY") {
            isRealFaceLatched = false;
            latchedRealFaceData = null;
            isFakeFaceLatched = true;
        }

        if (isRealFaceLatched && latchedRealFaceData) {
            statusTextEl.textContent = `REAL FACE: ${latchedRealFaceData.match_name.toUpperCase()}`;
            hudBadgeEl.className = "hud-status-badge success";
            hudStatusDotEl.style.backgroundColor = "var(--success)";
            cameraHudEl.className = "camera-hud real";
            
            if (lastStatus !== "REAL FACE") {
                playSound("success");
                logMessage(`VERIFIED REAL FACE: ${latchedRealFaceData.match_name} (${latchedRealFaceData.confidence}% confidence)`, "success");
            }
        } 
        else if (isFakeFaceLatched) {
            statusTextEl.textContent = "SPOOF ALERT / FAKE FACE";
            hudBadgeEl.className = "hud-status-badge error";
            hudStatusDotEl.style.backgroundColor = "var(--error)";
            cameraHudEl.className = "camera-hud spoof";
            
            if (lastStatus !== "FAKE FACE") {
                playSound("fail");
                logMessage("VERIFICATION ALERT: FAKE FACE DETECTED", "error");
            }
        } 
        else {
            statusTextEl.textContent = data.status === "VAULT EMPTY - ENROLL FIRST" ? data.status : "SCANNING";
            hudBadgeEl.className = "hud-status-badge";
            hudStatusDotEl.style.backgroundColor = "var(--primary)";
            cameraHudEl.className = "camera-hud scanning";
        }
    }
    
    lastStatus = data.status;
}

function updateCheckItem(id, passed, badgeText) {
    const item = document.getElementById(id);
    const badge = item.querySelector(".check-badge");
    const icon = item.querySelector(".check-icon");
    
    if (passed) {
        item.className = "check-item passed";
        badge.textContent = badgeText;
        icon.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>`;
    } else {
        item.className = "check-item";
        badge.textContent = badgeText;
        icon.innerHTML = "";
    }
}

// ---------------- MENU AND TRIGGER CONFIGS ----------------

function handleMenuStore() {
    const wrapper = document.getElementById("enrollInputWrapper");
    const nameInput = document.getElementById("menuEnrollName");
    
    if (!wrapper.classList.contains("active")) {
        playSound("click");
        wrapper.classList.add("active");
        nameInput.focus();
    } else {
        const name = nameInput.value.trim();
        if (!name) {
            alert("Please specify a target profile name to enroll the biometric signature.");
            return;
        }
        
        // Go to Screen 3 in Store Mode
        enrollName = name;
        currentMode = "store";
        nameInput.value = "";
        wrapper.classList.remove("active");
        showScreen("dashboard");
    }
}

function handleMenuVerify() {
    currentMode = "verify";
    showScreen("dashboard");
}

function handleMenuClear() {
    playSound("fail");
    if (!confirm("Are you absolutely sure you want to purge the entire identity vault database? This operation is irreversible!")) {
        return;
    }
    
    // Connect to WS backend briefly to run clear command
    const urls = getBackendUrls();
    const tempSocket = new WebSocket(urls.wsUrl);
    
    tempSocket.onopen = () => {
        tempSocket.send(JSON.stringify({
            type: "clear"
        }));
        setTimeout(() => {
            tempSocket.close();
            // Trigger temporary visual update on Screen 2 directly
            document.getElementById("menuVaultCount").textContent = "0";
            showToast("Database Cleared Successfully!");
        }, 300);
    };
}

// Global toggle for system audio status
function toggleAudio() {
    isAudioMuted = !isAudioMuted;
    const btn = document.getElementById("audioToggle");
    if (isAudioMuted) {
        btn.textContent = "AUDIO OFF";
        btn.style.color = "var(--text-muted)";
    } else {
        btn.textContent = "AUDIO ON";
        btn.style.color = "var(--primary)";
        playSound("click");
    }
}

function clearLogs() {
    playSound("click");
    document.getElementById("consoleLogs").innerHTML = "";
    logMessage("Console event logs history cleared.", "system");
}

// ---------------- INITIAL KEYBOARD TRIGGER CONTROLLER ----------------

function handleGlobalKeyEvents(e) {
    const key = e.key;
    
    // Screen 1 Transitions
    if (activeScreen === "opening") {
        if (key === "Enter" || key === " ") {
            e.preventDefault();
            showScreen("menu");
        }
    } 
    
    // Screen 2 transitions
    else if (activeScreen === "menu") {
        // Prevent typing intercept on enrollment text input
        if (document.activeElement.id === "menuEnrollName") {
            if (key === "Enter") {
                handleMenuStore();
            }
            return;
        }
        
        if (key === "1" || key === "s" || key === "S") {
            handleMenuStore();
        } 
        else if (key === "2" || key === "v" || key === "V") {
            handleMenuVerify();
        }
        else if (key === "3" || key === "c" || key === "C") {
            handleMenuClear();
        }
        else if (key === "Enter") {
            // Default to Verify on enter
            handleMenuVerify();
        }
    } 
    
    // Screen 3 active dashboard state
    else if (activeScreen === "dashboard") {
        if (key === "Backspace") {
            e.preventDefault();
            showScreen("menu");
        } 
        else if (key === "Escape") {
            e.preventDefault();
            showScreen("menu");
        }
        else if (key === "s" || key === "S") {
            // Switch mode to Store on-the-fly
            const name = prompt("Enter Target Enrollment Profile Name:");
            if (name && name.trim()) {
                isRealFaceLatched = false;
                latchedRealFaceData = null;
                isFakeFaceLatched = false;
                enrollName = name.trim();
                currentMode = "store";
                logMessage(`Operational Mode switched to: STORE [${enrollName}]`, "warning");
                if (socket && socket.readyState === WebSocket.OPEN) {
                    socket.send(JSON.stringify({
                        type: "config",
                        mode: "store",
                        name: enrollName
                    }));
                }
            }
        }
        else if (key === "v" || key === "V") {
            isRealFaceLatched = false;
            latchedRealFaceData = null;
            isFakeFaceLatched = false;
            currentMode = "verify";
            logMessage("Operational Mode switched to: VERIFY", "info");
            if (socket && socket.readyState === WebSocket.OPEN) {
                socket.send(JSON.stringify({
                    type: "config",
                    mode: "verify"
                }));
            }
        }
        else if (key === "c" || key === "C") {
            if (confirm("Purge Identity Vault?")) {
                if (socket && socket.readyState === WebSocket.OPEN) {
                    socket.send(JSON.stringify({
                        type: "clear"
                    }));
                }
            }
        }
    }
}

// Bootstrap
window.addEventListener("DOMContentLoaded", () => {
    startClocks();
    
    // Screen 1 bindings
    document.getElementById("btnStartConsole").addEventListener("click", () => showScreen("menu"));
    
    // Screen 2 bindings
    document.getElementById("btnSelectStore").addEventListener("click", handleMenuStore);
    document.getElementById("btnSelectVerify").addEventListener("click", handleMenuVerify);
    document.getElementById("btnSelectClear").addEventListener("click", handleMenuClear);
    
    // Screen 3 bindings
    document.getElementById("btnBackToMenu").addEventListener("click", () => showScreen("menu"));
    document.getElementById("audioToggle").addEventListener("click", toggleAudio);
    document.getElementById("consoleClearBtn").addEventListener("click", clearLogs);
    
    // Add global key triggers
    window.addEventListener("keydown", handleGlobalKeyEvents);
    
    // Boot loading of enrolled vaults
    // Fetch initial list via temporary sockets
    const urls = getBackendUrls();
    const tempSocket = new WebSocket(urls.wsUrl);
    tempSocket.onmessage = (e) => {
        const msg = JSON.parse(e.data);
        if (msg.type === "init") {
            updateIdentityVault(msg.enrolled);
            tempSocket.close();
        }
    };
});
