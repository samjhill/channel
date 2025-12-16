import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { fetchChannel, fetchChannels, saveChannel } from "./api";
import ChannelSelector from "./components/ChannelSelector";
import ChannelSettingsForm from "./components/ChannelSettingsForm";
import ShowDiscovery from "./components/ShowDiscovery";
import ShowTable from "./components/ShowTable";
import PlaylistManager from "./components/PlaylistManager";
import BumperManager from "./components/BumperManager";
import BumperPreview from "./components/BumperPreview";
import LogMonitor from "./components/LogMonitor";
import SaveBar from "./components/SaveBar";
function cloneChannel(channel) {
    return channel ? JSON.parse(JSON.stringify(channel)) : null;
}
function App() {
    const [searchParams, setSearchParams] = useSearchParams();
    // Get view and channel from URL, with defaults
    const viewFromUrl = searchParams.get("view");
    const channelFromUrl = searchParams.get("channel") || "";
    const [channels, setChannels] = useState([]);
    const [selectedId, setSelectedId] = useState(channelFromUrl);
    const [currentChannel, setCurrentChannel] = useState(null);
    const [initialChannel, setInitialChannel] = useState(null);
    const [loading, setLoading] = useState(false);
    const [saving, setSaving] = useState(false);
    const [status, setStatus] = useState(null);
    const [error, setError] = useState(null);
    const [dirty, setDirty] = useState(false);
    const [activeView, setActiveView] = useState(viewFromUrl || "playlist");
    // Sync activeView with URL when URL changes (e.g., browser back/forward)
    useEffect(() => {
        if (viewFromUrl && viewFromUrl !== activeView) {
            setActiveView(viewFromUrl);
        }
    }, [viewFromUrl, activeView]);
    // Update URL when view changes
    const handleViewChange = (view) => {
        setActiveView(view);
        const newParams = new URLSearchParams(searchParams);
        newParams.set("view", view);
        setSearchParams(newParams, { replace: true });
    };
    // Update URL when channel changes
    const handleChannelSelect = (channelId) => {
        setSelectedId(channelId);
        const newParams = new URLSearchParams(searchParams);
        if (channelId) {
            newParams.set("channel", channelId);
        }
        else {
            newParams.delete("channel");
        }
        setSearchParams(newParams, { replace: true });
    };
    useEffect(() => {
        fetchChannels()
            .then((list) => {
            setChannels(list);
            // If URL has a channel ID, use it; otherwise use first channel
            if (channelFromUrl && list.some(ch => ch.id === channelFromUrl)) {
                setSelectedId(channelFromUrl);
            }
            else if (list.length > 0) {
                const firstId = list[0].id;
                setSelectedId(firstId);
                // Update URL with first channel if none was specified
                if (!channelFromUrl) {
                    const newParams = new URLSearchParams(searchParams);
                    newParams.set("channel", firstId);
                    setSearchParams(newParams, { replace: true });
                }
            }
        })
            .catch((err) => setError(err.message));
    }, []);
    useEffect(() => {
        if (!selectedId) {
            return;
        }
        setLoading(true);
        fetchChannel(selectedId)
            .then((channel) => {
            setCurrentChannel(channel);
            setInitialChannel(cloneChannel(channel));
            setDirty(false);
            setError(null);
        })
            .catch((err) => {
            setError(err.message);
            setCurrentChannel(null);
            setInitialChannel(null);
        })
            .finally(() => setLoading(false));
    }, [selectedId]);
    const handleChannelChange = (field, value) => {
        if (!currentChannel) {
            return;
        }
        const next = { ...currentChannel, [field]: value };
        setCurrentChannel(next);
        setDirty(true);
    };
    const handleShowChange = (index, updated) => {
        if (!currentChannel) {
            return;
        }
        const shows = currentChannel.shows.map((show, idx) => idx === index ? { ...show, ...updated } : show);
        setCurrentChannel({ ...currentChannel, shows });
        setDirty(true);
    };
    const handleBulkAction = (action) => {
        if (!currentChannel) {
            return;
        }
        let shows = currentChannel.shows;
        if (action === "selectAll") {
            shows = shows.map((show) => ({ ...show, include: true }));
        }
        else if (action === "deselectAll") {
            shows = shows.map((show) => ({ ...show, include: false }));
        }
        else if (action === "normalizeWeights") {
            shows = shows.map((show) => ({ ...show, weight: 1 }));
        }
        setCurrentChannel({ ...currentChannel, shows });
        setDirty(true);
    };
    const handleDiscoveredShows = (discovered) => {
        if (!currentChannel) {
            return { added: 0, total: discovered.length };
        }
        const existingIndex = new Map(currentChannel.shows.map((show, idx) => [show.id, idx]));
        const merged = [...currentChannel.shows];
        let added = 0;
        let changed = false;
        discovered.forEach((show) => {
            const idx = existingIndex.get(show.id);
            if (idx === undefined) {
                merged.push(show);
                existingIndex.set(show.id, merged.length - 1);
                added += 1;
                changed = true;
            }
            else {
                const prev = merged[idx];
                const next = { ...prev, ...show };
                if (JSON.stringify(prev) !== JSON.stringify(next)) {
                    merged[idx] = next;
                    changed = true;
                }
            }
        });
        if (changed) {
            setCurrentChannel({ ...currentChannel, shows: merged });
            setDirty(true);
        }
        return { added, total: discovered.length };
    };
    const handleSave = async () => {
        if (!currentChannel) {
            return;
        }
        const confirmRestart = window.confirm("Saving will restart the media server so changes take effect. Continue?");
        if (!confirmRestart) {
            return;
        }
        setSaving(true);
        setStatus(null);
        try {
            await saveChannel(currentChannel);
            setInitialChannel(cloneChannel(currentChannel));
            setStatus("Changes saved");
            setDirty(false);
            setError(null);
            setChannels((prev) => prev.map((ch) => (ch.id === currentChannel.id ? currentChannel : ch)));
        }
        catch (err) {
            setError(err instanceof Error ? err.message : "Failed to save");
        }
        finally {
            setSaving(false);
            setTimeout(() => setStatus(null), 3000);
        }
    };
    const handleDiscard = () => {
        if (!initialChannel) {
            return;
        }
        setCurrentChannel(cloneChannel(initialChannel));
        setDirty(false);
    };
    useEffect(() => {
        const handleKeyDown = (e) => {
            // Don't trigger shortcuts when typing in inputs, textareas, or contenteditable elements
            const target = e.target;
            if (target.tagName === "INPUT" ||
                target.tagName === "TEXTAREA" ||
                target.isContentEditable) {
                return;
            }
            // Ctrl+S or Cmd+S to save
            if ((e.ctrlKey || e.metaKey) && e.key === "s") {
                e.preventDefault();
                if (dirty && currentChannel && !saving) {
                    handleSave();
                }
            }
            // Escape to discard
            if (e.key === "Escape" && dirty && !saving) {
                handleDiscard();
            }
        };
        window.addEventListener("keydown", handleKeyDown);
        return () => window.removeEventListener("keydown", handleKeyDown);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [dirty, currentChannel, saving]);
    return (_jsxs("div", { className: "app-shell", children: [_jsxs("header", { className: "app-header", children: [_jsxs("div", { className: "header-content", children: [_jsx("h1", { children: "Channel Admin" }), _jsx(ChannelSelector, { channels: channels, selectedId: selectedId, onSelect: handleChannelSelect, disabled: loading })] }), _jsxs("div", { className: "view-switch", children: [_jsx("button", { className: `tab-button ${activeView === "settings" ? "active" : ""}`, onClick: () => handleViewChange("settings"), children: "Channel Settings" }), _jsx("button", { className: `tab-button ${activeView === "playlist" ? "active" : ""}`, onClick: () => handleViewChange("playlist"), children: "Playlist Management" }), _jsx("button", { className: `tab-button ${activeView === "bumpers" ? "active" : ""}`, onClick: () => handleViewChange("bumpers"), children: "Bumper Management" }), _jsx("button", { className: `tab-button ${activeView === "preview" ? "active" : ""}`, onClick: () => handleViewChange("preview"), children: "Bumper Preview" }), _jsx("button", { className: `tab-button ${activeView === "logs" ? "active" : ""}`, onClick: () => handleViewChange("logs"), children: "Log Monitor" })] })] }), _jsxs("main", { className: "app-content", children: [error && (_jsxs("div", { className: "card error-message", style: { display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "1rem" }, children: [_jsxs("div", { style: { flex: 1 }, children: [_jsx("strong", { children: "Error:" }), " ", error] }), _jsx("button", { className: "btn btn-secondary", onClick: () => setError(null), style: { padding: "0.25rem 0.5rem", fontSize: "0.875rem" }, "aria-label": "Dismiss error", children: "\u2715" })] })), !error && loading && (_jsxs("div", { className: "card loading-message", children: [_jsx("div", { className: "loading-spinner" }), _jsx("span", { children: "Loading channel\u2026" })] })), !loading && currentChannel && activeView === "settings" && (_jsxs(_Fragment, { children: [_jsx(ChannelSettingsForm, { channel: currentChannel, onChange: handleChannelChange }), _jsx(ShowDiscovery, { channelId: currentChannel.id, mediaRoot: currentChannel.media_root, disabled: !currentChannel.media_root, onAddShows: handleDiscoveredShows }), _jsx(ShowTable, { shows: currentChannel.shows, channelMode: currentChannel.playback_mode, onChange: handleShowChange, onBulkAction: handleBulkAction })] })), !loading && currentChannel && activeView === "playlist" && (_jsx(PlaylistManager, { channelId: currentChannel.id, active: activeView === "playlist" })), !loading && activeView === "bumpers" && (_jsx(BumperManager, {})), !loading && activeView === "preview" && (_jsx(BumperPreview, {})), !loading && activeView === "logs" && (_jsx(LogMonitor, {})), !loading && !currentChannel && activeView !== "bumpers" && activeView !== "logs" && (_jsx("div", { className: "card", children: "Select a channel to manage its settings." }))] }), _jsx(SaveBar, { dirty: dirty, saving: saving, disabled: !currentChannel || !dirty, status: status, onSave: handleSave, onDiscard: handleDiscard })] }));
}
export default App;
