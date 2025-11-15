import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { useEffect, useState } from "react";
import { fetchChannel, fetchChannels, saveChannel } from "./api";
import ChannelSelector from "./components/ChannelSelector";
import ChannelSettingsForm from "./components/ChannelSettingsForm";
import ShowDiscovery from "./components/ShowDiscovery";
import ShowTable from "./components/ShowTable";
import PlaylistManager from "./components/PlaylistManager";
import SaveBar from "./components/SaveBar";
function cloneChannel(channel) {
    return channel ? JSON.parse(JSON.stringify(channel)) : null;
}
function App() {
    const [channels, setChannels] = useState([]);
    const [selectedId, setSelectedId] = useState("");
    const [currentChannel, setCurrentChannel] = useState(null);
    const [initialChannel, setInitialChannel] = useState(null);
    const [loading, setLoading] = useState(false);
    const [saving, setSaving] = useState(false);
    const [status, setStatus] = useState(null);
    const [error, setError] = useState(null);
    const [dirty, setDirty] = useState(false);
    const [activeView, setActiveView] = useState("settings");
    useEffect(() => {
        fetchChannels()
            .then((list) => {
            setChannels(list);
            if (list.length > 0) {
                setSelectedId(list[0].id);
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
    return (_jsxs("div", { className: "app-shell", children: [_jsxs("header", { className: "app-header", children: [_jsxs("div", { className: "header-content", children: [_jsx("h1", { children: "Channel Admin" }), _jsx(ChannelSelector, { channels: channels, selectedId: selectedId, onSelect: setSelectedId, disabled: loading })] }), _jsxs("div", { className: "view-switch", children: [_jsx("button", { className: `tab-button ${activeView === "settings" ? "active" : ""}`, onClick: () => setActiveView("settings"), children: "Channel Settings" }), _jsx("button", { className: `tab-button ${activeView === "playlist" ? "active" : ""}`, onClick: () => setActiveView("playlist"), children: "Playlist Management" })] })] }), _jsxs("main", { className: "app-content", children: [error && (_jsxs("div", { className: "card error-message", children: [_jsx("strong", { children: "Error:" }), " ", error] })), !error && loading && (_jsx("div", { className: "card loading-message", children: "Loading channel\u2026" })), !loading && currentChannel && activeView === "settings" && (_jsxs(_Fragment, { children: [_jsx(ChannelSettingsForm, { channel: currentChannel, onChange: handleChannelChange }), _jsx(ShowDiscovery, { channelId: currentChannel.id, mediaRoot: currentChannel.media_root, disabled: !currentChannel.media_root, onAddShows: handleDiscoveredShows }), _jsx(ShowTable, { shows: currentChannel.shows, channelMode: currentChannel.playback_mode, onChange: handleShowChange, onBulkAction: handleBulkAction })] })), !loading && currentChannel && activeView === "playlist" && (_jsx(PlaylistManager, { channelId: currentChannel.id, active: activeView === "playlist" })), !loading && !currentChannel && (_jsx("div", { className: "card", children: "Select a channel to manage its settings." }))] }), _jsx(SaveBar, { dirty: dirty, saving: saving, disabled: !currentChannel || !dirty, status: status, onSave: handleSave, onDiscard: handleDiscard })] }));
}
export default App;
