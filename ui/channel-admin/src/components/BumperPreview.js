import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { useEffect, useState } from "react";
import { API_BASE, fetchBumperPreview, } from "../api";
export default function BumperPreview() {
    const [preview, setPreview] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const loadPreview = async () => {
        setLoading(true);
        setError(null);
        try {
            const data = await fetchBumperPreview();
            setPreview(data);
        }
        catch (err) {
            const message = err instanceof Error ? err.message : "Failed to load bumper preview";
            setError(message);
            setPreview(null);
        }
        finally {
            setLoading(false);
        }
    };
    useEffect(() => {
        loadPreview();
    }, []);
    const handleRefresh = () => {
        loadPreview();
    };
    const musicLabel = preview?.music_track?.split(/[\\/]/).pop() || "Random track";
    const videoSrc = preview ? `${API_BASE}${preview.video_url}` : undefined;
    return (_jsxs("div", { className: "bumper-preview card", children: [_jsxs("div", { className: "preview-header", children: [_jsx("h2", { children: "Bumper Preview" }), _jsx("button", { className: "btn btn-secondary", onClick: handleRefresh, disabled: loading, children: loading ? "Refreshing…" : "Refresh Preview" })] }), _jsx("p", { className: "help-text", children: "Generates the next bumper block (sassy + optional weather + up-next + network) with its shared music bed so you can review it before it airs." }), error && (_jsx("div", { className: "error-message", style: { marginBottom: "1rem" }, children: error })), loading && (_jsxs("div", { className: "loading-message", style: { marginBottom: "1rem" }, children: [_jsx("div", { className: "loading-spinner" }), _jsx("span", { children: "Loading preview\u2026" })] })), !loading && preview && (_jsxs(_Fragment, { children: [_jsx("video", { controls: true, style: {
                            width: "100%",
                            maxHeight: "420px",
                            borderRadius: "8px",
                            background: "#000",
                            marginBottom: "1rem",
                        }, src: videoSrc }, preview.video_url), _jsxs("div", { className: "preview-meta", children: [_jsxs("p", { children: [_jsx("strong", { children: "Promoted Episode:" }), " ", preview.episode_filename] }), _jsxs("p", { children: [_jsx("strong", { children: "Music Track:" }), " ", musicLabel] }), _jsxs("p", { children: [_jsx("strong", { children: "Block ID:" }), " ", preview.block_id] })] }), _jsxs("div", { className: "form-section", children: [_jsxs("h3", { children: ["Included Bumpers (", preview.bumpers.length, ")"] }), _jsx("ul", { className: "bumper-list", children: preview.bumpers.map((item, idx) => (_jsxs("li", { children: [_jsx("strong", { children: item.type.toUpperCase() }), ": ", item.filename] }, `${item.path}-${idx}`))) })] })] })), !loading && !preview && !error && (_jsx("div", { className: "card", children: "Unable to locate an upcoming bumper block. Try refreshing again in a moment." }))] }));
}
