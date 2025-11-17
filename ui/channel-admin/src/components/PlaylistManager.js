import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { useCallback, useEffect, useMemo, useState } from "react";
import { fetchPlaylistSnapshot, skipCurrentEpisode, updateUpcomingPlaylist } from "../api";
const WINDOW_SIZE = 25;
function formatEpisodeTitle(title) {
    // Remove file extensions
    const withoutExt = title.replace(/\.(mkv|mp4|avi|mov|m4v|webm|flv|wmv)$/i, "");
    // Replace common separators with spaces
    return withoutExt
        .replace(/[-_\.]/g, " ")
        .replace(/\s+/g, " ")
        .trim();
}
function PlaylistManager({ channelId, active }) {
    const [snapshot, setSnapshot] = useState(null);
    const [draft, setDraft] = useState([]);
    const [skipped, setSkipped] = useState(new Set());
    const [loading, setLoading] = useState(false);
    const [saving, setSaving] = useState(false);
    const [skipping, setSkipping] = useState(false);
    const [error, setError] = useState(null);
    const [status, setStatus] = useState(null);
    const [dirty, setDirty] = useState(false);
    const loadSnapshot = useCallback(async (silent = false) => {
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
        }
        catch (err) {
            setError(err instanceof Error ? err.message : "Failed to load playlist");
        }
        finally {
            if (!silent) {
                setLoading(false);
            }
        }
    }, [channelId, active, dirty]);
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
    const moveItem = (index, delta) => {
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
    const handleSkip = (path) => {
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
            const nextSnapshot = await updateUpcomingPlaylist(channelId, {
                version: snapshot.version,
                desired: draft.map((item) => item.path),
                skipped: Array.from(skipped)
            }, WINDOW_SIZE);
            setSnapshot(nextSnapshot);
            setDraft(nextSnapshot.upcoming);
            setSkipped(new Set());
            setDirty(false);
            setStatus("Playlist updated");
            setTimeout(() => setStatus(null), 3000);
        }
        catch (err) {
            const message = err instanceof Error ? err.message : "Failed to update playlist";
            setError(message);
        }
        finally {
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
                }
                else if (prev === "Waiting for streamer to skip...") {
                    return "Confirming skip...";
                }
                else if (prev === "Confirming skip...") {
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
        }
        catch (err) {
            clearInterval(progressInterval);
            const message = err instanceof Error ? err.message : "Failed to skip episode";
            setError(message);
            setStatus(null);
            console.error("Skip episode error:", err);
            // Keep error visible for longer so user can see it
            setTimeout(() => setError(null), 10000);
        }
        finally {
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
        return `${Math.min(snapshot.controllable_remaining, WINDOW_SIZE)} controllable items shown (${snapshot.controllable_remaining} total upcoming).`;
    }, [snapshot]);
    return (_jsxs("section", { className: "card playlist-manager", children: [_jsxs("header", { className: "playlist-header", children: [_jsxs("div", { children: [_jsx("h2", { children: "Playlist Management" }), _jsxs("p", { className: "muted", children: ["Review and resequence the next ", WINDOW_SIZE, " controllable items. Skipping removes them from this loop; reordering takes effect without restarting the stream."] })] }), _jsxs("div", { className: "playlist-actions", children: [_jsx("button", { className: "btn btn-secondary", onClick: handleReset, disabled: !dirty || loading || saving, children: "Reset" }), _jsx("button", { className: "btn btn-primary", onClick: handleApply, disabled: !dirty || saving || !snapshot, children: saving ? "Applying…" : "Apply changes" })] })] }), error && (_jsxs("div", { className: "playlist-error", style: { display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "1rem" }, children: [_jsxs("span", { children: ["\u26A0\uFE0F ", error] }), _jsx("button", { className: "btn btn-secondary", onClick: () => setError(null), style: { padding: "0.25rem 0.5rem", fontSize: "0.875rem", flexShrink: 0 }, "aria-label": "Dismiss error", children: "\u2715" })] })), status && _jsx("div", { className: "playlist-status", children: status }), !channelId && _jsx("div", { children: "Please select a channel to manage its playlist." }), channelId && (_jsxs(_Fragment, { children: [_jsxs("div", { className: "playlist-now card", children: [_jsxs("div", { className: "playlist-now-header", children: [_jsx("h3", { children: "Now Playing" }), _jsx("button", { className: "btn btn-primary", onClick: handleSkipCurrent, disabled: skipping || loading || saving || !snapshot || !snapshot.current, children: skipping ? "Skipping…" : "Skip Current Episode" })] }), skipping && status && (_jsxs("div", { className: "playlist-status", style: { marginTop: "0.5rem", marginBottom: "0.5rem" }, children: ["\u23F3 ", status] })), !snapshot && loading && (_jsxs("div", { className: "loading-message", children: [_jsx("div", { className: "loading-spinner" }), _jsx("span", { children: "Loading current item\u2026" })] })), snapshot && snapshot.current ? (_jsxs("div", { children: [_jsx("div", { className: "playlist-row-title", children: formatEpisodeTitle(snapshot.current.detail) }), _jsx("div", { className: "playlist-row-detail", children: snapshot.current.label })] })) : (_jsx("p", { children: "No active segment detected." }))] }), _jsxs("div", { className: "card playlist-upcoming", children: [_jsxs("div", { className: "playlist-upcoming-header", children: [_jsxs("h3", { children: ["Upcoming (", draft.length, ")"] }), summary && _jsx("small", { children: summary })] }), loading && !snapshot && (_jsxs("div", { className: "loading-message", children: [_jsx("div", { className: "loading-spinner" }), _jsx("span", { children: "Loading playlist\u2026" })] })), !loading && !hasDraft && (_jsx("p", { children: "No controllable items were found in the upcoming window." })), hasDraft && (_jsx("ul", { className: "playlist-list", children: draft.map((item, index) => (_jsxs("li", { className: "playlist-row", children: [_jsxs("div", { className: "playlist-row-info", children: [_jsx("span", { className: "playlist-row-index", children: index + 1 }), _jsxs("div", { children: [_jsx("div", { className: "playlist-row-title", children: formatEpisodeTitle(item.detail) }), _jsx("div", { className: "playlist-row-detail", children: item.label })] })] }), _jsxs("div", { className: "playlist-row-controls", children: [_jsx("button", { className: "btn btn-light", onClick: () => moveItem(index, -1), disabled: index === 0, children: "\u2191" }), _jsx("button", { className: "btn btn-light", onClick: () => moveItem(index, 1), disabled: index === draft.length - 1, children: "\u2193" }), _jsx("button", { className: "btn btn-danger", onClick: () => handleSkip(item.path), children: "Skip" })] })] }, item.path))) }))] })] }))] }));
}
export default PlaylistManager;
