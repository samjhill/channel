import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState } from "react";
import { discoverShows } from "../api";
function ShowDiscovery({ channelId, mediaRoot, disabled, onAddShows }) {
    const [loading, setLoading] = useState(false);
    const [message, setMessage] = useState(null);
    const [error, setError] = useState(null);
    const handleDiscover = async () => {
        if (!channelId || !mediaRoot) {
            setError("Set a media folder before scanning.");
            return;
        }
        setLoading(true);
        setMessage(null);
        setError(null);
        try {
            const discovered = await discoverShows(channelId, mediaRoot);
            if (!discovered.length) {
                setMessage("No show folders found in that directory.");
                return;
            }
            const { added, total } = onAddShows(discovered);
            if (added > 0) {
                setMessage(`Added ${added} new ${added === 1 ? "show" : "shows"} from ${total} found.`);
            }
            else {
                setMessage("All discovered shows are already in the channel.");
            }
        }
        catch (err) {
            setError(err instanceof Error ? err.message : "Failed to discover shows.");
        }
        finally {
            setLoading(false);
            setTimeout(() => setMessage(null), 4000);
        }
    };
    return (_jsxs("section", { className: "card", children: [_jsxs("div", { className: "discovery-header", children: [_jsxs("div", { children: [_jsx("h2", { children: "Show Discovery" }), _jsx("p", { className: "muted", children: "Scan the media folder for show directories and add them to this channel." })] }), _jsx("button", { className: "btn btn-primary", onClick: handleDiscover, disabled: disabled || loading, children: loading ? "Scanning…" : "Discover shows" })] }), error && (_jsx("div", { className: "discovery-message error", children: error })), message && !error && (_jsx("div", { className: "discovery-message success", children: message }))] }));
}
export default ShowDiscovery;
