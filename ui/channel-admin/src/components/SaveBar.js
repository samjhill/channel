import { jsxs as _jsxs, jsx as _jsx } from "react/jsx-runtime";
function SaveBar({ dirty, saving, disabled, status, onSave, onDiscard }) {
    return (_jsxs("div", { className: "save-bar", children: [_jsxs("div", { className: "status-message", "aria-live": "polite", children: [saving && "Restarting media server…", !saving && dirty && "Saving will restart the media server.", !saving && !dirty && (status || "No changes")] }), _jsxs("div", { style: { display: "flex", gap: "0.5rem" }, children: [_jsx("button", { className: "btn btn-secondary", onClick: onDiscard, disabled: !dirty || saving, children: "Discard" }), _jsx("button", { className: "btn btn-primary", onClick: onSave, disabled: disabled || saving, children: saving ? "Restarting…" : "Save" })] })] }));
}
export default SaveBar;
