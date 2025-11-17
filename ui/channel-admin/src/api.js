const API_BASE = (import.meta.env.VITE_API_BASE || "").replace(/\/$/, "");
async function handleResponse(res) {
    if (!res.ok) {
        const detail = await res
            .json()
            .catch(() => ({ detail: res.statusText || "Request failed" }));
        throw new Error(detail.detail || res.statusText);
    }
    return res.json();
}
export async function fetchChannels() {
    const res = await fetch(`${API_BASE}/api/channels`);
    return handleResponse(res);
}
export async function fetchChannel(id) {
    const res = await fetch(`${API_BASE}/api/channels/${encodeURIComponent(id)}`);
    return handleResponse(res);
}
export async function saveChannel(cfg) {
    const res = await fetch(`${API_BASE}/api/channels/${encodeURIComponent(cfg.id)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(cfg)
    });
    await handleResponse(res);
}
export async function discoverShows(id, mediaRoot) {
    const params = mediaRoot ? `?media_root=${encodeURIComponent(mediaRoot)}` : "";
    const res = await fetch(`${API_BASE}/api/channels/${encodeURIComponent(id)}/shows/discover${params}`);
    return handleResponse(res);
}
export async function fetchPlaylistSnapshot(channelId, limit = 25) {
    const res = await fetch(`${API_BASE}/api/channels/${encodeURIComponent(channelId)}/playlist/next?limit=${limit}`);
    return handleResponse(res);
}
export async function updateUpcomingPlaylist(channelId, payload, limit = 25) {
    const res = await fetch(`${API_BASE}/api/channels/${encodeURIComponent(channelId)}/playlist/next?limit=${limit}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
    });
    return handleResponse(res);
}
export async function skipCurrentEpisode(channelId) {
    const res = await fetch(`${API_BASE}/api/channels/${encodeURIComponent(channelId)}/playlist/skip-current`, {
        method: "POST"
    });
    return handleResponse(res);
}
