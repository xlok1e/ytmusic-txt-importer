const LS_KEY = "ytimporter_session";

// ── State
let selectedFile = null;
let tracksText = null;
let isImporting = false;
let foundVideoIds = [];
let processedCount = 0;
let totalTracks = 0;

// ── Modal: Help
const modal = document.getElementById("modal-overlay");
document.getElementById("btn-help").onclick = () => modal.classList.add("open");
document.getElementById("modal-close").onclick = () => modal.classList.remove("open");
modal.onclick = (e) => {
	if (e.target === modal) modal.classList.remove("open");
};

// ── Modal: Confirm Stop
const confirmOverlay = document.getElementById("confirm-overlay");
document.getElementById("confirm-cancel").onclick = () => confirmOverlay.classList.remove("open");
confirmOverlay.onclick = (e) => {
	if (e.target === confirmOverlay) confirmOverlay.classList.remove("open");
};
document.getElementById("confirm-stop").onclick = async () => {
	confirmOverlay.classList.remove("open");
	console.log("[INFO] User requested early stop");
	try {
		const res = await fetch("/stop-import", { method: "POST" });
		const json = await res.json();
		console.log("[DEBUG] /stop-import:", json);
	} catch (e) {
		console.error("[ERROR] /stop-import request failed:", e);
	}
};

// ── File Logic
const dropZone = document.getElementById("drop-zone");
const fileInput = document.getElementById("file-input");

dropZone.onclick = () => fileInput.click();
dropZone.ondragover = (e) => {
	e.preventDefault();
	dropZone.classList.add("over");
};
dropZone.ondragleave = () => dropZone.classList.remove("over");
dropZone.ondrop = (e) => {
	e.preventDefault();
	dropZone.classList.remove("over");
	handleFile(e.dataTransfer.files[0]);
};
fileInput.onchange = () => handleFile(fileInput.files[0]);

function handleFile(file) {
	if (!file) return;
	selectedFile = file;
	const reader = new FileReader();
	reader.onload = (e) => {
		tracksText = e.target.result;
		dropZone.classList.add("loaded");
		dropZone.textContent = `Файл: ${file.name}`;
		checkReady();
	};
	reader.onerror = () => console.error("[ERROR] Failed to read file:", file.name);
	reader.readAsText(file, "utf-8");
}

// ── Validation
const headersInput = document.getElementById("headers");
const btnStart = document.getElementById("btn-start");

function checkReady() {
	btnStart.disabled = !(headersInput.value.trim() && (tracksText || processedCount > 0));
}
headersInput.oninput = checkReady;

// ── localStorage
function saveSession() {
	try {
		localStorage.setItem(
			LS_KEY,
			JSON.stringify({
				headers: headersInput.value,
				playlistName: document.getElementById("playlist-name").value,
				tracksText,
				videoIds: foundVideoIds,
				processedCount,
				totalCount: totalTracks,
				timestamp: Date.now(),
			}),
		);
	} catch (e) {
		console.warn("[WARN] localStorage save failed:", e);
	}
}

function loadSavedSession() {
	try {
		const raw = localStorage.getItem(LS_KEY);
		if (!raw) return null;
		const s = JSON.parse(raw);
		if (Date.now() - s.timestamp > 86_400_000) {
			localStorage.removeItem(LS_KEY);
			return null;
		}
		if (!s.tracksText || s.processedCount >= s.totalCount) {
			localStorage.removeItem(LS_KEY);
			return null;
		}
		return s;
	} catch (e) {
		console.warn("[WARN] localStorage load failed:", e);
		localStorage.removeItem(LS_KEY);
		return null;
	}
}

function clearSession() {
	localStorage.removeItem(LS_KEY);
	foundVideoIds = [];
	processedCount = 0;
	totalTracks = 0;
}

// ── Resume Banner
const savedSession = loadSavedSession();
if (savedSession) {
	const banner = document.getElementById("resume-banner");
	document.getElementById("resume-text").textContent =
		`Незавершённый импорт: ${savedSession.processedCount}/${savedSession.totalCount} треков — «${savedSession.playlistName || "без названия"}»`;
	banner.style.display = "flex";

	document.getElementById("resume-continue").onclick = () => {
		headersInput.value = savedSession.headers || "";
		document.getElementById("playlist-name").value = savedSession.playlistName || "";
		tracksText = savedSession.tracksText;
		foundVideoIds = savedSession.videoIds || [];
		processedCount = savedSession.processedCount;
		totalTracks = savedSession.totalCount;
		dropZone.classList.add("loaded");
		dropZone.textContent = `Продолжение с трека ${savedSession.processedCount + 1}`;
		banner.style.display = "none";
		checkReady();
		console.log("[INFO] Session restored:", {
			processedCount,
			totalTracks,
			restoredIds: foundVideoIds.length,
		});
	};

	document.getElementById("resume-discard").onclick = () => {
		clearSession();
		banner.style.display = "none";
		console.log("[INFO] Saved session discarded");
	};
}

// ── Import Logic
btnStart.onclick = async () => {
	if (isImporting) {
		confirmOverlay.classList.add("open");
		return;
	}

	const log = document.getElementById("log");
	const progress = document.getElementById("progress");
	const bar = document.getElementById("bar");

	isImporting = true;
	btnStart.textContent = "ЗАВЕРШИТЬ ИМПОРТ";
	btnStart.disabled = false;
	log.innerHTML = "";
	log.classList.add("visible");
	progress.classList.add("visible");

	if (processedCount === 0) foundVideoIds = [];

	const formData = new FormData();
	formData.append("headers_raw", headersInput.value);
	formData.append(
		"playlist_name",
		document.getElementById("playlist-name").value || "Imported Playlist",
	);
	formData.append("tracks_text", tracksText || "");
	formData.append("start_from", String(processedCount));
	formData.append("existing_video_ids", JSON.stringify(foundVideoIds));
	if (selectedFile) formData.append("file", selectedFile);

	console.log("[INFO] Starting import", {
		startFrom: processedCount,
		existingIds: foundVideoIds.length,
	});

	try {
		const res = await fetch("/import", { method: "POST", body: formData });
		console.log("[DEBUG] Response:", res.status, res.statusText);
		if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);

		const reader = res.body.getReader();
		const decoder = new TextDecoder();
		let buffer = "";

		while (true) {
			const { done, value } = await reader.read();
			if (done) {
				console.log("[DEBUG] SSE stream closed. Buffer remainder:", JSON.stringify(buffer));
				break;
			}

			buffer += decoder.decode(value, { stream: true });
			const parts = buffer.split("\n\n");
			buffer = parts.pop();

			for (const part of parts) {
				if (!part.startsWith("data: ")) {
					if (part.trim()) console.warn("[WARN] Unexpected SSE part:", JSON.stringify(part));
					continue;
				}
				let data;
				try {
					data = JSON.parse(part.slice(6));
				} catch (parseErr) {
					console.error("[ERROR] SSE JSON parse failed:", parseErr, "Raw:", JSON.stringify(part));
					continue;
				}
				console.log("[DEBUG] Event:", data.type, data);

				if (data.type === "status") {
					document.getElementById("progress-label").textContent = data.message;
				} else if (data.type === "error") {
					console.error("[ERROR] Backend:", data.message);
					const el = document.createElement("div");
					el.className = "err";
					el.textContent = "⚠ " + data.message;
					log.appendChild(el);
					log.scrollTop = log.scrollHeight;
				} else if (data.type === "track") {
					const isOk = data.status === "ok";
					const el = document.createElement("div");
					el.className = isOk ? "ok" : "err";
					el.textContent = `${isOk ? "✓" : "✕"} ${data.query}`;
					log.appendChild(el);
					log.scrollTop = log.scrollHeight;

					if (isOk && data.videoId) {
						foundVideoIds.push(data.videoId);
					} else if (!isOk) {
						console.warn("[WARN] Not found:", data.query);
					}

					processedCount = data.index;
					totalTracks = data.total;
					document.getElementById("progress-text").textContent = `${data.index} / ${data.total}`;
					bar.style.width = `${(data.index / data.total) * 100}%`;
					saveSession();
				} else if (data.type === "batch") {
					document.getElementById("progress-label").textContent =
						`Добавляем батч ${data.current}/${data.total}...`;
				} else if (data.type === "done") {
					console.log("[INFO] Done:", {
						found: data.found,
						notFound: data.not_found,
						playlistId: data.playlist_id,
					});
					document.getElementById("progress-label").textContent = "Завершено";
					const el = document.createElement("div");
					el.style.marginTop = "10px";
					el.innerHTML = `<a href="https://music.youtube.com/playlist?list=${data.playlist_id}" target="_blank" style="color:var(--red); text-decoration:none; font-weight:600;">→ Открыть плейлист (${data.found} треков)</a>`;
					log.appendChild(el);
					log.scrollTop = log.scrollHeight;
					clearSession();
					isImporting = false;
					btnStart.textContent = "НАЧАТЬ ИМПОРТ";
					btnStart.disabled = false;
				} else {
					console.warn("[WARN] Unknown event type:", data.type, data);
				}
			}
		}
	} catch (e) {
		console.error("[ERROR] Fetch/stream error:", e);
		const el = document.createElement("div");
		el.className = "err";
		el.textContent = "⚠ Ошибка соединения: " + e.message;
		log.appendChild(el);
		log.scrollTop = log.scrollHeight;
	} finally {
		if (isImporting) {
			isImporting = false;
			btnStart.textContent = "НАЧАТЬ ИМПОРТ";
			btnStart.disabled = false;
		}
	}
};
