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

export const API_BASE = (import.meta.env.VITE_API_BASE || "").replace(/\/$/, "");

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const detail = await res
      .json()
      .catch(() => ({ detail: res.statusText || "Request failed" }));
    throw new Error(detail.detail || res.statusText);
  }
  return res.json() as Promise<T>;
}

// Create a fetch wrapper with timeout
function fetchWithTimeout(url: string, options: RequestInit = {}, timeout = 60000): Promise<Response> {
  return Promise.race([
    fetch(url, options),
    new Promise<Response>((_, reject) =>
      setTimeout(() => reject(new Error(`Request timeout: ${url}`)), timeout)
    )
  ]);
}

export async function fetchChannels(): Promise<ChannelConfig[]> {
  const res = await fetchWithTimeout(`${API_BASE}/api/channels`);
  return handleResponse<ChannelConfig[]>(res);
}

export async function fetchChannel(id: string): Promise<ChannelConfig> {
  const res = await fetchWithTimeout(`${API_BASE}/api/channels/${encodeURIComponent(id)}`);
  return handleResponse<ChannelConfig>(res);
}

export async function saveChannel(cfg: ChannelConfig): Promise<void> {
  const res = await fetchWithTimeout(`${API_BASE}/api/channels/${encodeURIComponent(cfg.id)}`, {
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
  const res = await fetchWithTimeout(
    `${API_BASE}/api/channels/${encodeURIComponent(id)}/shows/discover${params}`
  );
  return handleResponse<ShowConfig[]>(res);
}

export async function fetchPlaylistSnapshot(
  channelId: string,
  limit = 25
): Promise<PlaylistSnapshot> {
  const res = await fetchWithTimeout(
    `${API_BASE}/api/channels/${encodeURIComponent(channelId)}/playlist/next?limit=${limit}`
  );
  return handleResponse<PlaylistSnapshot>(res);
}

export async function updateUpcomingPlaylist(
  channelId: string,
  payload: PlaylistUpdatePayload,
  limit = 25
): Promise<PlaylistSnapshot> {
  const res = await fetchWithTimeout(
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
  const res = await fetchWithTimeout(
    `${API_BASE}/api/channels/${encodeURIComponent(channelId)}/playlist/skip-current`,
    {
      method: "POST"
    }
  );
  return handleResponse<PlaylistSnapshot>(res);
}

export interface SassyConfig {
  enabled: boolean;
  duration_seconds: number;
  music_volume: number;
  probability_between_episodes: number;
  style: string;
  messages: string[];
}

export async function fetchSassyConfig(): Promise<SassyConfig> {
  const res = await fetchWithTimeout(`${API_BASE}/api/bumpers/sassy`);
  return handleResponse<SassyConfig>(res);
}

export async function updateSassyConfig(
  config: Partial<SassyConfig>
): Promise<SassyConfig> {
  const res = await fetchWithTimeout(`${API_BASE}/api/bumpers/sassy`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config)
  });
  return handleResponse<SassyConfig>(res);
}

export interface WeatherLocation {
  city: string;
  region: string;
  country: string;
  lat: number;
  lon: number;
}

export interface WeatherConfig {
  enabled: boolean;
  provider: string;
  api_key_env_var: string;
  location: WeatherLocation;
  units: "imperial" | "metric";
  duration_seconds: number;
  cache_ttl_minutes: number;
  probability_between_episodes: number;
  music_volume?: number;
  api_key?: string | null;  // Will be null if set via env var, or masked if in config
  api_key_set?: boolean;  // Indicates if API key is configured (via env var)
}

export async function fetchWeatherConfig(): Promise<WeatherConfig> {
  const res = await fetchWithTimeout(`${API_BASE}/api/bumpers/weather`);
  return handleResponse<WeatherConfig>(res);
}

export async function updateWeatherConfig(
  config: Partial<WeatherConfig>
): Promise<WeatherConfig> {
  const res = await fetchWithTimeout(`${API_BASE}/api/bumpers/weather`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(config)
  });
  return handleResponse<WeatherConfig>(res);
}

export interface BumperPreviewBumper {
  path: string;
  filename: string;
  type: string;
}

export interface BumperPreviewResponse {
  video_url: string;
  block_id: string;
  music_track?: string | null;
  episode_path: string;
  episode_filename: string;
  bumpers: BumperPreviewBumper[];
  generated_at: number;
}

export async function fetchBumperPreview(): Promise<BumperPreviewResponse> {
  const cacheBust = Date.now();
  const res = await fetchWithTimeout(`${API_BASE}/api/bumper-preview/next?ts=${cacheBust}`);
  return handleResponse<BumperPreviewResponse>(res);
}

export interface LogResponse {
  source: "docker" | "file" | "none";
  container?: string;
  path?: string;
  message?: string;
  lines: number;
  logs: string[];
  timestamp: number;
}

export async function fetchLogs(
  container: string = "tvchannel",
  lines: number = 500
): Promise<LogResponse> {
  const params = new URLSearchParams({
    container,
    lines: lines.toString(),
  });
  const res = await fetchWithTimeout(`${API_BASE}/api/logs?${params}`);
  return handleResponse<LogResponse>(res);
}

export interface PlaylistGenerationStatus {
  is_generating: boolean;
  playlist_exists: boolean;
  playlist_entries: number;
  playlist_size: number;
  process_info: {
    pid?: number;
    cpu_percent?: number;
    memory_mb?: number;
    runtime?: string;
  } | null;
  timestamp: number;
}

export async function fetchPlaylistGenerationStatus(): Promise<PlaylistGenerationStatus> {
  const res = await fetchWithTimeout(`${API_BASE}/api/playlist/generation-status`);
  return handleResponse<PlaylistGenerationStatus>(res);
}

