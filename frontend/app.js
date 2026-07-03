const state = {
  logs: ["trend.log", "script.log", "voice.log", "video.log", "publish.log", "publisher_decision.log", "cleanup.log"],
  activeLog: "script.log",
  last: JSON.parse(localStorage.getItem("socialMediaAiLast") || "{}"),
  pipelinePoll: null,
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

async function loadAuth() {
  try {
    const status = await requestJson("/auth/status");
    const panel = $("authPanel");
    const authenticated = status.authenticated === true;
    panel.classList.toggle("signed-in", authenticated);
    panel.classList.toggle("signed-out", !authenticated);
    $("authStatus").textContent = authenticated ? "signed in" : "signed out";
    if (authenticated && status.user) {
      $("authName").textContent = status.user.name || "Google user";
      $("authEmail").textContent = status.user.email || "";
      $("authAvatar").src = status.user.picture || "";
    } else {
      $("authName").textContent = "Signed out";
      $("authEmail").textContent = "Google authentication inactive";
      $("authAvatar").removeAttribute("src");
    }
  } catch {
    $("authStatus").textContent = "unavailable";
  }
}

async function logoutGoogle() {
  try {
    await requestJson("/auth/logout", { method: "POST" });
  } finally {
    await loadAuth();
  }
}

async function loadYoutubeConnection() {
  try {
    const status = await requestJson("/youtube/status");
    const connected = status.connected === true && status.channel;
    const channel = status.channel || {};
    const channelPanel = document.querySelector(".youtube-channel");
    channelPanel.classList.toggle("connected", connected);
    channelPanel.classList.toggle("disconnected", !connected);
    $("youtubeConnectionStatus").textContent = connected ? "connected" : "disconnected";
    $("youtubeConnectionBadge").textContent = connected ? "connected" : status.error || "disconnected";
    $("youtubeChannelName").textContent = connected ? channel.channel_name || "YouTube Channel" : "Disconnected";
    $("youtubeChannelId").textContent = connected ? channel.channel_id || "-" : "No channel connected";
    $("youtubeSubscribers").textContent = connected ? channel.subscriber_count ?? 0 : "-";
    $("youtubeVideos").textContent = connected ? channel.video_count ?? 0 : "-";
    $("youtubeCountry").textContent = connected ? channel.country || "-" : "-";
    $("youtubeLanguage").textContent = connected ? channel.default_language || "-" : "-";
    if (connected && channel.channel_thumbnail) {
      $("youtubeChannelThumb").src = channel.channel_thumbnail;
    } else {
      $("youtubeChannelThumb").removeAttribute("src");
    }
  } catch {
    $("youtubeConnectionStatus").textContent = "unavailable";
    $("youtubeConnectionBadge").textContent = "unavailable";
  }
}

async function disconnectYoutube() {
  try {
    await requestJson("/youtube/disconnect", { method: "POST" });
  } finally {
    await loadYoutubeConnection();
  }
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
  if (action === "full") startPipelinePolling();
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
  } finally {
    if (action === "full") {
      stopPipelinePolling();
      await loadPipelineReport();
      await loadPipelineHistory();
    }
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
  renderQualityMetrics();
  if (state.last.thumbnailPath) $("latestThumb").src = `${state.last.thumbnailPath}?t=${Date.now()}`;
  if (state.last.videoPath) $("latestVideo").src = `${state.last.videoPath}?t=${Date.now()}`;
}

function renderQualityMetrics() {
  const metadata = state.last.metadata || {};
  $("researchScore").textContent = metadata.research_score?.overall ?? metadata.research_score ?? "-";
  $("scriptScore").textContent = metadata.script_score?.overall ?? "-";
  $("scriptAccepted").textContent = formatBoolean(metadata.script_accepted);
  $("scriptRegenerated").textContent = formatBoolean(metadata.script_regenerated);
  $("scriptAttempts").textContent = metadata.script_attempt_count ?? "-";
  $("originalityScore").textContent = metadata.originality_score ?? "-";
  $("chosenVideoAngle").value = metadata.chosen_video_angle || "";
  $("missingAngles").value = Array.isArray(metadata.missing_angles) ? metadata.missing_angles.join("\n") : "";
  const competitorCount = metadata.competitors_analyzed ?? metadata.competitor_titles?.length ?? 0;
  $("competitorCount").textContent = `${competitorCount} competitors`;
  $("overallConfidence").textContent = metadata.overall_confidence ?? "-";
  $("claimsVerified").textContent = Array.isArray(metadata.verified_claims) ? metadata.verified_claims.length : "-";
  $("claimsRejected").textContent = Array.isArray(metadata.rejected_claims) ? metadata.rejected_claims.length : "-";
  $("sourcesChecked").textContent = Array.isArray(metadata.verification_sources) ? metadata.verification_sources.length : "-";
  $("verificationFallback").textContent = metadata.verification_fallback_used === undefined
    ? "-"
    : `fallback ${formatBoolean(metadata.verification_fallback_used)}`;
  $("selectedHook").value = metadata.selected_hook || "";
  $("hookType").textContent = metadata.hook_type || "-";
  $("hookOverallScore").textContent = metadata.hook_scores?.[0]?.overall_score ?? "-";
  $("topHooks").value = Array.isArray(metadata.top_hooks) ? metadata.top_hooks.join("\n") : "";
  const intelligence = metadata.content_intelligence || {};
  $("retentionScore").textContent = intelligence.overall_retention_score ?? "-";
  $("openingStrength").textContent = intelligence.opening_strength ?? "-";
  $("storyFlow").textContent = intelligence.story_flow ?? "-";
  $("curiosityGap").textContent = intelligence.curiosity_gap ?? "-";
  $("paceScore").textContent = intelligence.pace ?? "-";
  $("endingStrength").textContent = intelligence.ending_strength ?? "-";
  $("dropRisk").textContent = intelligence.drop_risk || "-";
  $("contentImprovements").value = Array.isArray(intelligence.improvements)
    ? intelligence.improvements.slice(0, 3).join("\n")
    : "";
  const thumbnail = metadata.thumbnail_intelligence || {};
  $("thumbnailOverall").textContent = thumbnail.overall_score ?? "-";
  $("thumbnailCtr").textContent = thumbnail.ctr_prediction ?? "-";
  $("thumbnailCuriosity").textContent = thumbnail.curiosity_score ?? "-";
  $("thumbnailEmotion").textContent = thumbnail.emotion_score ?? "-";
  $("thumbnailContrast").textContent = thumbnail.contrast_score ?? "-";
  $("thumbnailReadability").textContent = thumbnail.text_readability ?? "-";
  $("thumbnailMobile").textContent = thumbnail.mobile_visibility ?? "-";
  $("thumbnailAttempts").textContent = thumbnail.regeneration_attempt !== undefined
    ? thumbnail.regeneration_attempt + 1
    : "-";
  $("thumbnailAccepted").textContent = thumbnail.accepted === undefined
    ? "-"
    : `accepted ${formatBoolean(thumbnail.accepted)}`;
  $("thumbnailImprovements").value = Array.isArray(thumbnail.recommended_changes)
    ? thumbnail.recommended_changes.slice(0, 3).join("\n")
    : "";
  const seo = metadata.seo_intelligence || {};
  $("seoOverall").textContent = seo.overall_score ?? "-";
  $("seoTitleScore").textContent = seo.title_score ?? "-";
  $("seoCtr").textContent = seo.ctr_prediction ?? "-";
  $("seoSearchIntent").textContent = seo.search_intent_score ?? "-";
  $("seoKeywords").textContent = seo.keyword_score ?? "-";
  $("seoCompetition").textContent = seo.competition_level || "-";
  $("seoDescriptionScore").textContent = seo.description_score ?? "-";
  $("seoTagsScore").textContent = seo.tag_score ?? "-";
  $("seoAttempts").textContent = seo.attempt !== undefined ? seo.attempt + 1 : "-";
  $("seoAccepted").textContent = seo.accepted === undefined
    ? "-"
    : `accepted ${formatBoolean(seo.accepted)}`;
  $("seoRecommendations").value = Array.isArray(seo.recommended_changes)
    ? seo.recommended_changes.slice(0, 3).join("\n")
    : "";
  const viral = metadata.viral_prediction || {};
  $("viralScore").textContent = viral.viral_score ?? "-";
  $("viralCtr").textContent = viral.predicted_ctr ?? "-";
  $("viralRetention").textContent = viral.predicted_retention ?? "-";
  $("viralConfidence").textContent = viral.confidence ?? "-";
  $("viralRecommendation").textContent = viral.publish_recommendation === undefined
    ? "-"
    : `publish ${formatBoolean(viral.publish_recommendation)}`;
  $("viralReasons").value = Array.isArray(viral.reasons) ? viral.reasons.slice(0, 3).join("\n") : "";
  $("viralImprovements").value = Array.isArray(viral.improvements) ? viral.improvements.slice(0, 3).join("\n") : "";
  const publisher = metadata.publisher_decision || {};
  $("publisherOverall").textContent = publisher.overall_score ?? "-";
  $("publisherConfidence").textContent = publisher.confidence ?? "-";
  $("publisherRisk").textContent = publisher.risk_level || "-";
  $("publisherViews").textContent = publisher.expected_views ?? "-";
  $("publisherCtr").textContent = publisher.expected_ctr ?? "-";
  $("publisherRetention").textContent = publisher.expected_retention ?? "-";
  $("publisherTime").textContent = publisher.recommended_publish_time && publisher.recommended_day
    ? `${publisher.recommended_day} ${publisher.recommended_publish_time}`
    : publisher.recommended_publish_time || "-";
  $("publisherRecommendation").textContent = publisher.publish === undefined
    ? "-"
    : `publish ${formatBoolean(publisher.publish)}`;
  $("publisherStrengths").value = Array.isArray(publisher.strengths) ? publisher.strengths.slice(0, 3).join("\n") : "";
  $("publisherWeaknesses").value = Array.isArray(publisher.weaknesses) ? publisher.weaknesses.slice(0, 3).join("\n") : "";
  $("publisherImprovements").value = Array.isArray(publisher.improvements) ? publisher.improvements.slice(0, 3).join("\n") : "";
  const upload = metadata.youtube_upload || {};
  const videoUrl = upload.video_url || metadata.youtube_url || "";
  $("uploadStatus").textContent = upload.upload_status || "-";
  $("uploadProgress").textContent = upload.progress !== undefined ? `${upload.progress}%` : "-";
  $("uploadTime").textContent = upload.upload_time !== undefined && upload.upload_time !== null
    ? `${upload.upload_time}s`
    : "-";
  $("processingStatus").textContent = upload.processing_status || metadata.youtube_processing_status || "-";
  $("youtubeVideoUrl").value = videoUrl;
  $("openYoutube").href = videoUrl || "#";
  const versions = metadata.script_variants || {};
  $("versionWinner").textContent = versions.winner || "-";
  $("versionCount").textContent = versions.version_count !== undefined
    ? `${versions.version_count} versions`
    : "-";
  $("versionBestHook").textContent = versions.best_hook || "-";
  $("versionScores").value = versions.version_scores
    ? Object.entries(versions.version_scores).map(([label, score]) => `${label}: ${score}`).join("\n")
    : "";
  $("versionReason").value = versions.selection_reason || "";
}

function formatBoolean(value) {
  if (value === true) return "yes";
  if (value === false) return "no";
  return "-";
}

async function refreshArtifacts() {
  await Promise.all([
    loadLatestMetadata(),
    loadPipelineReport(),
    loadPipelineHistory(),
    findLatestMedia("videos", "video_", ".mp4"),
    findLatestMedia("thumbnails", "thumb_", ".jpg"),
  ]);
  renderOutput();
}

function startPipelinePolling() {
  stopPipelinePolling();
  loadPipelineReport();
  state.pipelinePoll = setInterval(loadPipelineReport, 1200);
}

function stopPipelinePolling() {
  if (state.pipelinePoll) {
    clearInterval(state.pipelinePoll);
    state.pipelinePoll = null;
  }
}

async function loadPipelineReport() {
  try {
    const response = await fetch(`/storage/generated/pipeline_reports/latest.json?t=${Date.now()}`);
    if (!response.ok) return;
    const report = await response.json();
    $("pipelineStatus").textContent = report.status || "-";
    $("pipelineStage").textContent = report.current_stage || "-";
    $("pipelineProgress").textContent = report.progress !== undefined ? `${report.progress}%` : "-";
    $("pipelineRuntime").textContent = report.runtime !== undefined ? `${report.runtime}s` : "-";
    $("pipelineErrors").textContent = Array.isArray(report.errors) ? report.errors.length : "-";
    $("pipelineReportOutput").value = JSON.stringify(report, null, 2);
  } catch {
    return;
  }
}

async function loadPipelineHistory() {
  try {
    const response = await fetch(`/storage/generated/pipeline_reports/index.json?t=${Date.now()}`);
    if (!response.ok) return;
    const history = await response.json();
    $("pipelineHistoryOutput").textContent = Array.isArray(history)
      ? history.map((item) => `${item.timestamp}  ${item.status}  ${item.runtime}s  errors:${item.errors}`).join("\n")
      : "No runs yet.";
  } catch {
    return;
  }
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
  await Promise.allSettled([loadHealth(), loadAuth(), loadYoutubeConnection(), loadLogs(), refreshArtifacts()]);
}

document.addEventListener("DOMContentLoaded", () => {
  renderLogTabs();
  renderOutput();
  document.querySelectorAll("[data-action]").forEach((button) => {
    button.addEventListener("click", () => runAction(button.dataset.action));
  });
  $("refreshAll").addEventListener("click", refreshAll);
  $("logoutGoogle").addEventListener("click", logoutGoogle);
  $("disconnectYoutube").addEventListener("click", disconnectYoutube);
  refreshAll();
  setInterval(loadLogs, 10000);
  setInterval(loadHealth, 30000);
  setInterval(loadAuth, 30000);
  setInterval(loadYoutubeConnection, 30000);
});
