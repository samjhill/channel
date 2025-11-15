export type PlaybackMode = "sequential" | "random" | "inherit";

export interface ShowConfig {
  id: string;
  label: string;
  path: string;
  include: boolean;
  playback_mode: PlaybackMode;
  weight: number;
  [key: string]: unknown;
}

export interface ChannelConfig {
  id: string;
  name: string;
  enabled: boolean;
  media_root: string;
  playback_mode: "sequential" | "random";
  loop_entire_library: boolean;
  shows: ShowConfig[];
  bumpers?: unknown;
  branding?: unknown;
  [key: string]: unknown;
}

export interface PlaylistItem {
  path: string;
  label: string;
  detail: string;
  relative_path: string;
  filename: string;
  type: string;
  controllable: boolean;
  position: number;
}

export interface PlaylistSnapshot {
  channel_id: string;
  version: number;
  fetched_at: number;
  current: PlaylistItem | null;
  upcoming: PlaylistItem[];
  total_entries: number;
  total_segments: number;
  controllable_remaining: number;
  limit: number;
  state?: Record<string, unknown> | null;
}

export interface PlaylistUpdatePayload {
  version: number;
  desired: string[];
  skipped: string[];
}

const API_BASE = (import.meta.env.VITE_API_BASE || "").replace(/\/$/, "");

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const detail = await res
      .json()
      .catch(() => ({ detail: res.statusText || "Request failed" }));
    throw new Error(detail.detail || res.statusText);
  }
  return res.json() as Promise<T>;
}

export async function fetchChannels(): Promise<ChannelConfig[]> {
  const res = await fetch(`${API_BASE}/api/channels`);
  return handleResponse<ChannelConfig[]>(res);
}

export async function fetchChannel(id: string): Promise<ChannelConfig> {
  const res = await fetch(`${API_BASE}/api/channels/${encodeURIComponent(id)}`);
  return handleResponse<ChannelConfig>(res);
}

export async function saveChannel(cfg: ChannelConfig): Promise<void> {
  const res = await fetch(`${API_BASE}/api/channels/${encodeURIComponent(cfg.id)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(cfg)
  });
  await handleResponse(res);
}

export async function discoverShows(
  id: string,
  mediaRoot?: string
): Promise<ShowConfig[]> {
  const params = mediaRoot ? `?media_root=${encodeURIComponent(mediaRoot)}` : "";
  const res = await fetch(
    `${API_BASE}/api/channels/${encodeURIComponent(id)}/shows/discover${params}`
  );
  return handleResponse<ShowConfig[]>(res);
}

export async function fetchPlaylistSnapshot(
  channelId: string,
  limit = 25
): Promise<PlaylistSnapshot> {
  const res = await fetch(
    `${API_BASE}/api/channels/${encodeURIComponent(channelId)}/playlist/next?limit=${limit}`
  );
  return handleResponse<PlaylistSnapshot>(res);
}

export async function updateUpcomingPlaylist(
  channelId: string,
  payload: PlaylistUpdatePayload,
  limit = 25
): Promise<PlaylistSnapshot> {
  const res = await fetch(
    `${API_BASE}/api/channels/${encodeURIComponent(channelId)}/playlist/next?limit=${limit}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }
  );
  return handleResponse<PlaylistSnapshot>(res);
}

export async function skipCurrentEpisode(channelId: string): Promise<PlaylistSnapshot> {
  const res = await fetch(
    `${API_BASE}/api/channels/${encodeURIComponent(channelId)}/playlist/skip-current`,
    {
      method: "POST"
    }
  );
  return handleResponse<PlaylistSnapshot>(res);
}

