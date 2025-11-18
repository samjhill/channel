export const API_BASE = (import.meta.env.VITE_API_BASE || "").replace(/\/$/, "");
async function handleResponse(res) {
    if (!res.ok) {
        const detail = await res
            .json()
            .catch(() => ({ detail: res.statusText || "Request failed" }));
        throw new Error(detail.detail || res.statusText);
    }
    return res.json();
}
// Create a fetch wrapper with timeout
function fetchWithTimeout(url, options = {}, timeout = 10000) {
    return Promise.race([
        fetch(url, options),
        new Promise((_, reject) => setTimeout(() => reject(new Error(`Request timeout: ${url}`)), timeout))
    ]);
}
export async function fetchChannels() {
    const res = await fetchWithTimeout(`${API_BASE}/api/channels`);
    return handleResponse(res);
}
export async function fetchChannel(id) {
    const res = await fetchWithTimeout(`${API_BASE}/api/channels/${encodeURIComponent(id)}`);
    return handleResponse(res);
}
export async function saveChannel(cfg) {
    const res = await fetchWithTimeout(`${API_BASE}/api/channels/${encodeURIComponent(cfg.id)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(cfg)
    });
    await handleResponse(res);
}
export async function discoverShows(id, mediaRoot) {
    const params = mediaRoot ? `?media_root=${encodeURIComponent(mediaRoot)}` : "";
    const res = await fetchWithTimeout(`${API_BASE}/api/channels/${encodeURIComponent(id)}/shows/discover${params}`);
    return handleResponse(res);
}
export async function fetchPlaylistSnapshot(channelId, limit = 25) {
    const res = await fetchWithTimeout(`${API_BASE}/api/channels/${encodeURIComponent(channelId)}/playlist/next?limit=${limit}`);
    return handleResponse(res);
}
export async function updateUpcomingPlaylist(channelId, payload, limit = 25) {
    const res = await fetchWithTimeout(`${API_BASE}/api/channels/${encodeURIComponent(channelId)}/playlist/next?limit=${limit}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
    });
    return handleResponse(res);
}
export async function skipCurrentEpisode(channelId) {
    const res = await fetchWithTimeout(`${API_BASE}/api/channels/${encodeURIComponent(channelId)}/playlist/skip-current`, {
        method: "POST"
    });
    return handleResponse(res);
}
export async function fetchSassyConfig() {
    const res = await fetchWithTimeout(`${API_BASE}/api/bumpers/sassy`);
    return handleResponse(res);
}
export async function updateSassyConfig(config) {
    const res = await fetchWithTimeout(`${API_BASE}/api/bumpers/sassy`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(config)
    });
    return handleResponse(res);
}
export async function fetchWeatherConfig() {
    const res = await fetchWithTimeout(`${API_BASE}/api/bumpers/weather`);
    return handleResponse(res);
}
export async function updateWeatherConfig(config) {
    const res = await fetchWithTimeout(`${API_BASE}/api/bumpers/weather`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(config)
    });
    return handleResponse(res);
}
export async function fetchBumperPreview() {
    const cacheBust = Date.now();
    const res = await fetchWithTimeout(`${API_BASE}/api/bumper-preview/next?ts=${cacheBust}`);
    return handleResponse(res);
}
export async function fetchLogs(container = "tvchannel", lines = 500) {
    const params = new URLSearchParams({
        container,
        lines: lines.toString(),
    });
    const res = await fetchWithTimeout(`${API_BASE}/api/logs?${params}`);
    return handleResponse(res);
}
