import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
const playbackOptions = [
    { label: "Inherit channel setting", value: "inherit" },
    { label: "Sequential", value: "sequential" },
    { label: "Random", value: "random" }
];
function ShowTable({ shows, channelMode, onChange, onBulkAction }) {
    if (!shows.length) {
        return (_jsxs("section", { className: "card", children: [_jsx("h2", { children: "Shows" }), _jsx("p", { children: "No shows found for this channel." })] }));
    }
    return (_jsxs("section", { className: "card", children: [_jsxs("div", { className: "shows-header", children: [_jsxs("h2", { children: ["Shows (", shows.length, ")"] }), _jsxs("div", { className: "shows-actions", children: [_jsx("button", { className: "btn btn-light", onClick: () => onBulkAction("selectAll"), children: "Select all" }), _jsx("button", { className: "btn btn-light", onClick: () => onBulkAction("deselectAll"), children: "Deselect all" }), _jsx("button", { className: "btn btn-light", onClick: () => onBulkAction("normalizeWeights"), children: "Normalize weights" })] })] }), _jsxs("table", { className: "shows-table", children: [_jsx("thead", { children: _jsxs("tr", { children: [_jsx("th", { children: "Include" }), _jsx("th", { children: "Show Name" }), _jsx("th", { children: "Path" }), _jsx("th", { children: "Playback Mode" }), _jsx("th", { children: "Weight" })] }) }), _jsx("tbody", { children: shows.map((show, idx) => (_jsxs("tr", { children: [_jsx("td", { children: _jsx("input", { type: "checkbox", checked: show.include, onChange: (evt) => onChange(idx, { include: evt.target.checked }) }) }), _jsx("td", { children: _jsx("input", { type: "text", value: show.label, onChange: (evt) => onChange(idx, { label: evt.target.value }) }) }), _jsx("td", { children: show.path }), _jsx("td", { children: _jsx("select", { value: show.playback_mode, onChange: (evt) => onChange(idx, { playback_mode: evt.target.value }), children: playbackOptions.map((option) => (_jsxs("option", { value: option.value, children: [option.label, option.value === "inherit" ? ` (${channelMode})` : ""] }, option.value))) }) }), _jsx("td", { children: _jsx("input", { type: "number", min: 0.1, max: 5, step: 0.1, value: show.weight, onChange: (evt) => {
                                            const next = Math.max(0.1, Math.min(5, Number(evt.target.value)));
                                            onChange(idx, { weight: next });
                                        } }) })] }, show.id))) })] })] }));
}
export default ShowTable;
