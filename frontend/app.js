const state = {
  logs: ["trend.log", "script.log", "voice.log", "video.log", "publish.log", "cleanup.log"],
  activeLog: "script.log",
  last: JSON.parse(localStorage.getItem("socialMediaAiLast") || "{}"),
};

const $ = (id) => document.getElementById(id);

function saveState() {
  localStorage.setItem("socialMediaAiLast", JSON.stringify(state.last));
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const text = await response.text();
  let payload;
  try {
    payload = text ? JSON.parse(text) : {};
  } catch {
    payload = { raw: text };
  }
  if (!response.ok) {
    throw new Error(JSON.stringify(payload, null, 2));
  }
  return payload;
}

async function loadHealth() {
  const health = await requestJson("/system-health");
  $("healthBadge").textContent = health.status;
  $("healthBadge").classList.toggle("bad", health.status !== "ok");
  $("ollamaStatus").textContent = health.ollama;
  $("schedulerStatus").textContent = health.scheduler;
  $("youtubeStatus").textContent = health.youtube;
  $("diskUsage").textContent = health.disk_usage;
  $("freeSpace").textContent = `${health.free_space_gb} GB`;
  $("modelName").textContent = health.model;

  const scheduler = await requestJson("/scheduler-status");
  $("schedulerStatus").textContent = `${health.scheduler} (${scheduler.jobs.length} jobs)`;
}

async function loadLogs() {
  const output = $("logOutput");
  try {
    const response = await fetch(`/storage/logs/${state.activeLog}?t=${Date.now()}`);
    if (!response.ok) throw new Error("Log not found");
    const text = await response.text();
    output.textContent = tail(text, 12000) || "Log is empty.";
  } catch (error) {
    output.textContent = `${state.activeLog} unavailable.`;
  }
}

function tail(text, max) {
  return text.length > max ? text.slice(text.length - max) : text;
}

function renderLogTabs() {
  const tabs = $("logTabs");
  tabs.innerHTML = "";
  state.logs.forEach((name) => {
    const button = document.createElement("button");
    button.textContent = name;
    button.className = name === state.activeLog ? "active" : "";
    button.addEventListener("click", () => {
      state.activeLog = name;
      renderLogTabs();
      loadLogs();
    });
    tabs.appendChild(button);
  });
}

async function runAction(action) {
  $("actionStatus").textContent = "running";
  try {
    const payload = await actionRequest(action);
    state.last.response = payload;
    applyPayload(action, payload);
    saveState();
    renderOutput();
    $("lastResponse").textContent = JSON.stringify(payload, null, 2);
    $("actionStatus").textContent = "done";
    await refreshArtifacts();
  } catch (error) {
    $("lastResponse").textContent = error.message;
    $("actionStatus").textContent = "failed";
  }
}

function numericValue(id) {
  const value = $(id).value.trim();
  return value ? Number(value) : null;
}

async function actionRequest(action) {
  switch (action) {
    case "topic":
      return requestJson("/generate-topic", { method: "POST" });
    case "script":
      return requestJson("/generate-script", { method: "POST" });
    case "audio":
      return requestJson("/generate-audio", {
        method: "POST",
        body: JSON.stringify({ script_id: numericValue("scriptId"), voice: "en-US-JennyNeural" }),
      });
    case "video":
      return requestJson("/generate-video", {
        method: "POST",
        body: JSON.stringify({ audio_id: numericValue("audioId") }),
      });
    case "subtitle":
      return requestJson("/generate-subtitles", {
        method: "POST",
        body: JSON.stringify({ video_id: numericValue("videoId") }),
      });
    case "seo":
      return requestJson("/generate-seo", {
        method: "POST",
        body: JSON.stringify({ video_id: numericValue("videoId") }),
      });
    case "thumbnail":
      return requestJson("/generate-thumbnail", {
        method: "POST",
        body: JSON.stringify({ video_id: numericValue("videoId") }),
      });
    case "publish":
      return requestJson("/publish-youtube", {
        method: "POST",
        body: JSON.stringify({ video_id: numericValue("videoId") }),
      });
    case "full":
      return requestJson("/run-full-pipeline", { method: "POST" });
    case "daily":
      return requestJson("/run-daily-jobs", { method: "POST" });
    default:
      throw new Error(`Unknown action ${action}`);
  }
}

function applyPayload(action, payload) {
  if (payload.topic) state.last.topic = payload.topic;
  if (payload.script) state.last.script = payload.script;
  if (payload.title) state.last.seoTitle = payload.title;
  if (payload.thumbnail_path) state.last.thumbnailPath = storageUrl(payload.thumbnail_path);
  if (payload.video_path) state.last.videoPath = storageUrl(payload.video_path);
  if (payload.video_id) $("videoId").value = payload.video_id;
  if (payload.audio_id) $("audioId").value = payload.audio_id;
  if (payload.script_id) $("scriptId").value = payload.script_id;
}

function storageUrl(path) {
  return `/${path.replaceAll("\\", "/")}`;
}

function renderOutput() {
  $("topicOutput").value = state.last.topic || "";
  $("scriptOutput").value = state.last.script || "";
  $("seoTitleOutput").value = state.last.seoTitle || "";
  $("metadataOutput").value = state.last.metadata ? JSON.stringify(state.last.metadata, null, 2) : "";
  if (state.last.thumbnailPath) $("latestThumb").src = `${state.last.thumbnailPath}?t=${Date.now()}`;
  if (state.last.videoPath) $("latestVideo").src = `${state.last.videoPath}?t=${Date.now()}`;
}

async function refreshArtifacts() {
  await Promise.all([loadLatestMetadata(), findLatestMedia("videos", "video_", ".mp4"), findLatestMedia("thumbnails", "thumb_", ".jpg")]);
  renderOutput();
}

async function loadLatestMetadata() {
  try {
    const response = await fetch(`/storage/generated/latest.json?t=${Date.now()}`);
    if (!response.ok) return;
    const metadata = await response.json();
    state.last.metadata = metadata;
    state.last.topic = metadata.topic || state.last.topic;
    state.last.script = metadata.script || state.last.script;
    state.last.seoTitle = metadata.title || state.last.seoTitle;
    if (metadata.thumbnail_path) state.last.thumbnailPath = storageUrl(metadata.thumbnail_path);
    if (metadata.video_path) state.last.videoPath = storageUrl(metadata.video_path);
    saveState();
  } catch {
    return;
  }
}

async function findLatestMedia(folder, prefix, extension) {
  const checks = [];
  for (let id = 1; id <= 300; id += 1) {
    const url = `/storage/${folder}/${prefix}${id}${extension}`;
    checks.push(
      fetch(url, { method: "HEAD" })
        .then((response) => (response.ok ? id : null))
        .catch(() => null)
    );
  }
  const ids = (await Promise.all(checks)).filter(Boolean);
  if (!ids.length) return;
  const latestId = Math.max(...ids);
  const latest = `/storage/${folder}/${prefix}${latestId}${extension}`;
  if (folder === "videos") state.last.videoPath = latest;
  if (folder === "thumbnails") state.last.thumbnailPath = latest;
  saveState();
}

async function refreshAll() {
  await Promise.allSettled([loadHealth(), loadLogs(), refreshArtifacts()]);
}

document.addEventListener("DOMContentLoaded", () => {
  renderLogTabs();
  renderOutput();
  document.querySelectorAll("[data-action]").forEach((button) => {
    button.addEventListener("click", () => runAction(button.dataset.action));
  });
  $("refreshAll").addEventListener("click", refreshAll);
  refreshAll();
  setInterval(loadLogs, 10000);
  setInterval(loadHealth, 30000);
});
