import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
function ChannelSelector({ channels, selectedId, disabled, onSelect }) {
    return (_jsxs("div", { className: "channel-selector", children: [_jsx("label", { htmlFor: "channel-select", children: "Channel" }), _jsxs("select", { id: "channel-select", value: selectedId, disabled: disabled || channels.length === 0, onChange: (evt) => onSelect(evt.target.value), children: [channels.length === 0 && _jsx("option", { value: "", children: "No channels configured" }), channels.map((channel) => (_jsx("option", { value: channel.id, children: channel.name }, channel.id)))] })] }));
}
export default ChannelSelector;
