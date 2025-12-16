import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useEffect, useState } from "react";
import { fetchPlaylistGenerationStatus } from "../api";
function formatBytes(bytes) {
    if (bytes === 0)
        return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
}
function formatRuntime(runtime) {
    if (!runtime || runtime === "unknown")
        return "Unknown";
    return runtime;
}
function PlaylistGenerationStatus() {
    const [status, setStatus] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const loadStatus = async () => {
        try {
            setError(null);
            const data = await fetchPlaylistGenerationStatus();
            setStatus(data);
        }
        catch (err) {
            setError(err instanceof Error ? err.message : "Failed to load status");
        }
        finally {
            setLoading(false);
        }
    };
    useEffect(() => {
        loadStatus();
    }, []);
    useEffect(() => {
        if (!status)
            return;
        // Poll every 2 seconds if generating, every 10 seconds if not
        const interval = setInterval(() => {
            loadStatus();
        }, status.is_generating ? 2000 : 10000);
        return () => clearInterval(interval);
    }, [status?.is_generating]);
    if (loading && !status) {
        return (_jsx("div", { className: "card playlist-generation-status", children: _jsxs("div", { className: "loading-message", children: [_jsx("div", { className: "loading-spinner" }), _jsx("span", { children: "Loading generation status\u2026" })] }) }));
    }
    if (error) {
        return (_jsx("div", { className: "card playlist-generation-status", children: _jsxs("div", { className: "playlist-error", children: ["\u26A0\uFE0F Failed to load generation status: ", error] }) }));
    }
    if (!status) {
        return null;
    }
    const isGenerating = status.is_generating;
    const hasPlaylist = status.playlist_exists && status.playlist_entries > 0;
    return (_jsxs("div", { className: "card playlist-generation-status", children: [_jsx("h3", { children: "Playlist Generation Status" }), _jsx("div", { className: "generation-status-content", children: isGenerating ? (_jsxs("div", { className: "generation-status-generating", children: [_jsx("div", { className: "generation-status-header", children: _jsxs("div", { className: "generation-status-indicator generating", children: [_jsx("div", { className: "spinner" }), _jsx("span", { children: "Generating Playlist" })] }) }), status.process_info && (_jsxs("div", { className: "generation-status-details", children: [_jsxs("div", { className: "generation-detail", children: [_jsx("span", { className: "detail-label", children: "Process ID:" }), _jsx("span", { className: "detail-value", children: status.process_info.pid })] }), status.process_info.runtime && (_jsxs("div", { className: "generation-detail", children: [_jsx("span", { className: "detail-label", children: "Runtime:" }), _jsx("span", { className: "detail-value", children: formatRuntime(status.process_info.runtime) })] })), status.process_info.cpu_percent !== undefined && (_jsxs("div", { className: "generation-detail", children: [_jsx("span", { className: "detail-label", children: "CPU:" }), _jsxs("span", { className: "detail-value", children: [status.process_info.cpu_percent.toFixed(1), "%"] })] })), status.process_info.memory_mb !== undefined && (_jsxs("div", { className: "generation-detail", children: [_jsx("span", { className: "detail-label", children: "Memory:" }), _jsxs("span", { className: "detail-value", children: [status.process_info.memory_mb.toFixed(1), " MB"] })] }))] })), _jsx("div", { className: "generation-progress", children: status.playlist_exists ? (_jsxs("div", { className: "progress-info", children: [_jsxs("span", { children: ["Playlist file: ", formatBytes(status.playlist_size)] }), status.playlist_entries > 0 && (_jsxs("span", { children: [" \u2022 ", status.playlist_entries, " entries"] }))] })) : (_jsx("div", { className: "progress-info", children: _jsx("span", { children: "Initializing playlist generation..." }) })) })] })) : hasPlaylist ? (_jsxs("div", { className: "generation-status-complete", children: [_jsxs("div", { className: "generation-status-indicator complete", children: [_jsx("span", { children: "\u2713" }), _jsx("span", { children: "Playlist Ready" })] }), _jsxs("div", { className: "generation-status-details", children: [_jsxs("div", { className: "generation-detail", children: [_jsx("span", { className: "detail-label", children: "Entries:" }), _jsx("span", { className: "detail-value", children: status.playlist_entries })] }), _jsxs("div", { className: "generation-detail", children: [_jsx("span", { className: "detail-label", children: "Size:" }), _jsx("span", { className: "detail-value", children: formatBytes(status.playlist_size) })] })] })] })) : (_jsxs("div", { className: "generation-status-idle", children: [_jsxs("div", { className: "generation-status-indicator idle", children: [_jsx("span", { children: "\u25CB" }), _jsx("span", { children: "No Playlist" })] }), _jsx("p", { className: "muted", children: "Playlist has not been generated yet." })] })) })] }));
}
export default PlaylistGenerationStatus;
