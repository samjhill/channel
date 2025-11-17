import { useCallback, useEffect, useMemo, useState } from "react";
import {
  PlaylistItem,
  PlaylistSnapshot,
  fetchPlaylistSnapshot,
  skipCurrentEpisode,
  updateUpcomingPlaylist
} from "../api";

interface PlaylistManagerProps {
  channelId: string;
  active: boolean;
}

const WINDOW_SIZE = 25;

function formatEpisodeTitle(title: string): string {
  // Remove file extensions
  const withoutExt = title.replace(/\.(mkv|mp4|avi|mov|m4v|webm|flv|wmv)$/i, "");
  // Replace common separators with spaces
  return withoutExt
    .replace(/[-_\.]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function PlaylistManager({ channelId, active }: PlaylistManagerProps) {
  const [snapshot, setSnapshot] = useState<PlaylistSnapshot | null>(null);
  const [draft, setDraft] = useState<PlaylistItem[]>([]);
  const [skipped, setSkipped] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [skipping, setSkipping] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);

  const loadSnapshot = useCallback(
    async (silent = false) => {
      if (!channelId || !active) {
        return;
      }
      if (!silent) {
        setLoading(true);
      }
      setError(null);
      try {
        const data = await fetchPlaylistSnapshot(channelId, WINDOW_SIZE);
        setSnapshot(data);
        if (!dirty) {
          setDraft(data.upcoming);
          setSkipped(new Set());
          setDirty(false);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load playlist");
      } finally {
        if (!silent) {
          setLoading(false);
        }
      }
    },
    [channelId, active, dirty]
  );

  useEffect(() => {
    if (!channelId || !active) {
      return;
    }
    loadSnapshot();
  }, [channelId, active, loadSnapshot]);

  useEffect(() => {
    if (!channelId || !active || dirty) {
      return;
    }
    const id = window.setInterval(() => {
      loadSnapshot(true);
    }, 15000);
    return () => window.clearInterval(id);
  }, [channelId, active, dirty, loadSnapshot]);

  const moveItem = (index: number, delta: number) => {
    setDraft((prev) => {
      const next = [...prev];
      const target = index + delta;
      if (target < 0 || target >= next.length) {
        return prev;
      }
      const [item] = next.splice(index, 1);
      next.splice(target, 0, item);
      return next;
    });
    setDirty(true);
  };

  const handleSkip = (path: string) => {
    setDraft((prev) => prev.filter((item) => item.path !== path));
    setSkipped((prev) => new Set(prev).add(path));
    setDirty(true);
  };

  const handleReset = () => {
    if (!snapshot) {
      return;
    }
    setDraft(snapshot.upcoming);
    setSkipped(new Set());
    setDirty(false);
    setStatus(null);
  };

  const handleApply = async () => {
    if (!snapshot || !channelId) {
      return;
    }
    setSaving(true);
    setStatus(null);
    setError(null);
    try {
      const nextSnapshot = await updateUpcomingPlaylist(
        channelId,
        {
          version: snapshot.version,
          desired: draft.map((item) => item.path),
          skipped: Array.from(skipped)
        },
        WINDOW_SIZE
      );
      setSnapshot(nextSnapshot);
      setDraft(nextSnapshot.upcoming);
      setSkipped(new Set());
      setDirty(false);
      setStatus("Playlist updated");
      setTimeout(() => setStatus(null), 3000);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to update playlist";
      setError(message);
    } finally {
      setSaving(false);
    }
  };

  const handleSkipCurrent = async () => {
    if (!channelId) {
      return;
    }
    setSkipping(true);
    setStatus("Sending skip command...");
    setError(null);
    
    // Show progress updates during skip
    const progressInterval = setInterval(() => {
      setStatus((prev) => {
        if (prev === "Sending skip command...") {
          return "Waiting for streamer to skip...";
        } else if (prev === "Waiting for streamer to skip...") {
          return "Confirming skip...";
        } else if (prev === "Confirming skip...") {
          return "Sending skip command..."; // Cycle back
        }
        return prev;
      });
    }, 800); // Update every 800ms to show progress
    
    try {
      const startTime = Date.now();
      const nextSnapshot = await skipCurrentEpisode(channelId);
      const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
      clearInterval(progressInterval);
      setSnapshot(nextSnapshot);
      setDraft(nextSnapshot.upcoming);
      setSkipped(new Set());
      setDirty(false);
      setStatus(`Skipped to next episode (${elapsed}s)`);
      setTimeout(() => setStatus(null), 3000);
    } catch (err) {
      clearInterval(progressInterval);
      const message =
        err instanceof Error ? err.message : "Failed to skip episode";
      setError(message);
      setStatus(null);
      console.error("Skip episode error:", err);
      // Keep error visible for longer so user can see it
      setTimeout(() => setError(null), 10000);
    } finally {
      setSkipping(false);
    }
  };

  const hasDraft = draft.length > 0;

  const summary = useMemo(() => {
    if (!snapshot) {
      return "";
    }
    if (!snapshot.controllable_remaining) {
      return "No controllable items remain in this playlist.";
    }
    return `${Math.min(
      snapshot.controllable_remaining,
      WINDOW_SIZE
    )} controllable items shown (${snapshot.controllable_remaining} total upcoming).`;
  }, [snapshot]);

  return (
    <section className="card playlist-manager">
      <header className="playlist-header">
        <div>
          <h2>Playlist Management</h2>
          <p className="muted">
            Review and resequence the next {WINDOW_SIZE} controllable items. Skipping
            removes them from this loop; reordering takes effect without restarting
            the stream.
          </p>
        </div>
        <div className="playlist-actions">
          <button
            className="btn btn-secondary"
            onClick={handleReset}
            disabled={!dirty || loading || saving}
          >
            Reset
          </button>
          <button
            className="btn btn-primary"
            onClick={handleApply}
            disabled={!dirty || saving || !snapshot}
          >
            {saving ? "Applying…" : "Apply changes"}
          </button>
        </div>
      </header>
      {error && <div className="playlist-error">⚠️ {error}</div>}
      {status && <div className="playlist-status">{status}</div>}
      {!channelId && <div>Please select a channel to manage its playlist.</div>}
      {channelId && (
        <>
          <div className="playlist-now card">
            <div className="playlist-now-header">
              <h3>Now Playing</h3>
              <button
                className="btn btn-primary"
                onClick={handleSkipCurrent}
                disabled={skipping || loading || saving || !snapshot || !snapshot.current}
              >
                {skipping ? "Skipping…" : "Skip Current Episode"}
              </button>
            </div>
            {skipping && status && (
              <div className="playlist-status" style={{ marginTop: "0.5rem", marginBottom: "0.5rem" }}>
                ⏳ {status}
              </div>
            )}
            {!snapshot && loading && <p>Loading current item…</p>}
            {snapshot && snapshot.current ? (
              <div>
                <div className="playlist-row-title">{formatEpisodeTitle(snapshot.current.detail)}</div>
                <div className="playlist-row-detail">{snapshot.current.label}</div>
              </div>
            ) : (
              <p>No active segment detected.</p>
            )}
          </div>
          <div className="card playlist-upcoming">
            <div className="playlist-upcoming-header">
              <h3>Upcoming ({draft.length})</h3>
              {summary && <small>{summary}</small>}
            </div>
            {loading && !snapshot && <p>Loading playlist…</p>}
            {!loading && !hasDraft && (
              <p>No controllable items were found in the upcoming window.</p>
            )}
            {hasDraft && (
              <ul className="playlist-list">
                {draft.map((item, index) => (
                  <li key={item.path} className="playlist-row">
                    <div className="playlist-row-info">
                      <span className="playlist-row-index">{index + 1}</span>
                      <div>
                        <div className="playlist-row-title">{formatEpisodeTitle(item.detail)}</div>
                        <div className="playlist-row-detail">{item.label}</div>
                      </div>
                    </div>
                    <div className="playlist-row-controls">
                      <button
                        className="btn btn-light"
                        onClick={() => moveItem(index, -1)}
                        disabled={index === 0}
                      >
                        ↑
                      </button>
                      <button
                        className="btn btn-light"
                        onClick={() => moveItem(index, 1)}
                        disabled={index === draft.length - 1}
                      >
                        ↓
                      </button>
                      <button
                        className="btn btn-danger"
                        onClick={() => handleSkip(item.path)}
                      >
                        Skip
                      </button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      )}
    </section>
  );
}

export default PlaylistManager;

