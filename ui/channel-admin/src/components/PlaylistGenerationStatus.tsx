import { useEffect, useState } from "react";
import { fetchPlaylistGenerationStatus, type PlaylistGenerationStatus } from "../api";

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
}

function formatRuntime(runtime: string | undefined): string {
  if (!runtime || runtime === "unknown") return "Unknown";
  return runtime;
}

function PlaylistGenerationStatus() {
  const [status, setStatus] = useState<PlaylistGenerationStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadStatus = async () => {
    try {
      setError(null);
      const data = await fetchPlaylistGenerationStatus();
      setStatus(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load status");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadStatus();
  }, []);

  useEffect(() => {
    if (!status) return;
    // Poll every 2 seconds if generating, every 10 seconds if not
    const interval = setInterval(() => {
      loadStatus();
    }, status.is_generating ? 2000 : 10000);
    return () => clearInterval(interval);
  }, [status?.is_generating]);

  if (loading && !status) {
    return (
      <div className="card playlist-generation-status">
        <div className="loading-message">
          <div className="loading-spinner"></div>
          <span>Loading generation status…</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="card playlist-generation-status">
        <div className="playlist-error">
          ⚠️ Failed to load generation status: {error}
        </div>
      </div>
    );
  }

  if (!status) {
    return null;
  }

  const isGenerating = status.is_generating;
  const hasPlaylist = status.playlist_exists && status.playlist_entries > 0;

  return (
    <div className="card playlist-generation-status">
      <h3>Playlist Generation Status</h3>
      <div className="generation-status-content">
        {isGenerating ? (
          <div className="generation-status-generating">
            <div className="generation-status-header">
              <div className="generation-status-indicator generating">
                <div className="spinner"></div>
                <span>Generating Playlist</span>
              </div>
            </div>
            {status.process_info && (
              <div className="generation-status-details">
                <div className="generation-detail">
                  <span className="detail-label">Process ID:</span>
                  <span className="detail-value">{status.process_info.pid}</span>
                </div>
                {status.process_info.runtime && (
                  <div className="generation-detail">
                    <span className="detail-label">Runtime:</span>
                    <span className="detail-value">{formatRuntime(status.process_info.runtime)}</span>
                  </div>
                )}
                {status.process_info.cpu_percent !== undefined && (
                  <div className="generation-detail">
                    <span className="detail-label">CPU:</span>
                    <span className="detail-value">{status.process_info.cpu_percent.toFixed(1)}%</span>
                  </div>
                )}
                {status.process_info.memory_mb !== undefined && (
                  <div className="generation-detail">
                    <span className="detail-label">Memory:</span>
                    <span className="detail-value">{status.process_info.memory_mb.toFixed(1)} MB</span>
                  </div>
                )}
              </div>
            )}
            <div className="generation-progress">
              {status.playlist_exists ? (
                <div className="progress-info">
                  <span>Playlist file: {formatBytes(status.playlist_size)}</span>
                  {status.playlist_entries > 0 && (
                    <span> • {status.playlist_entries} entries</span>
                  )}
                </div>
              ) : (
                <div className="progress-info">
                  <span>Initializing playlist generation...</span>
                </div>
              )}
            </div>
          </div>
        ) : hasPlaylist ? (
          <div className="generation-status-complete">
            <div className="generation-status-indicator complete">
              <span>✓</span>
              <span>Playlist Ready</span>
            </div>
            <div className="generation-status-details">
              <div className="generation-detail">
                <span className="detail-label">Entries:</span>
                <span className="detail-value">{status.playlist_entries}</span>
              </div>
              <div className="generation-detail">
                <span className="detail-label">Size:</span>
                <span className="detail-value">{formatBytes(status.playlist_size)}</span>
              </div>
            </div>
          </div>
        ) : (
          <div className="generation-status-idle">
            <div className="generation-status-indicator idle">
              <span>○</span>
              <span>No Playlist</span>
            </div>
            <p className="muted">Playlist has not been generated yet.</p>
          </div>
        )}
      </div>
    </div>
  );
}

export default PlaylistGenerationStatus;

