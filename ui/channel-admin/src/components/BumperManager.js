import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { useEffect, useState } from "react";
import { fetchSassyConfig, updateSassyConfig, fetchWeatherConfig, updateWeatherConfig, } from "../api";
export default function BumperManager() {
    const [config, setConfig] = useState(null);
    const [weatherConfig, setWeatherConfig] = useState(null);
    const [loadingSassy, setLoadingSassy] = useState(true);
    const [loadingWeather, setLoadingWeather] = useState(true);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState(null);
    const [status, setStatus] = useState(null);
    const [editingIndex, setEditingIndex] = useState(null);
    const [newMessage, setNewMessage] = useState("");
    const [activeTab, setActiveTab] = useState("sassy");
    useEffect(() => {
        loadConfig();
        loadWeatherConfig();
    }, []);
    const loadConfig = async () => {
        setLoadingSassy(true);
        setError(null);
        try {
            const data = await fetchSassyConfig();
            setConfig(data);
        }
        catch (err) {
            const errorMsg = err instanceof Error ? err.message : "Failed to load sassy config";
            setError(errorMsg);
            console.error("Failed to load sassy config:", err);
        }
        finally {
            setLoadingSassy(false);
        }
    };
    const loadWeatherConfig = async () => {
        setLoadingWeather(true);
        try {
            const data = await fetchWeatherConfig();
            setWeatherConfig(data);
        }
        catch (err) {
            // Weather config might not exist yet, that's okay - we'll show a message
            console.warn("Failed to load weather config:", err);
            // Don't set error here as weather config is optional
        }
        finally {
            setLoadingWeather(false);
        }
    };
    const handleSave = async () => {
        if (activeTab === "sassy") {
            if (!config)
                return;
            setSaving(true);
            setError(null);
            setStatus(null);
            try {
                const updated = await updateSassyConfig(config);
                setConfig(updated);
                setStatus("Sassy card configuration saved successfully");
                setTimeout(() => setStatus(null), 3000);
            }
            catch (err) {
                setError(err instanceof Error ? err.message : "Failed to save");
            }
            finally {
                setSaving(false);
            }
        }
        else if (activeTab === "weather") {
            if (!weatherConfig)
                return;
            setSaving(true);
            setError(null);
            setStatus(null);
            try {
                const updated = await updateWeatherConfig(weatherConfig);
                setWeatherConfig(updated);
                setStatus("Weather bumper configuration saved successfully");
                setTimeout(() => setStatus(null), 3000);
            }
            catch (err) {
                setError(err instanceof Error ? err.message : "Failed to save");
            }
            finally {
                setSaving(false);
            }
        }
    };
    const handleToggleEnabled = () => {
        if (!config)
            return;
        setConfig({ ...config, enabled: !config.enabled });
    };
    const handleUpdateField = (field, value) => {
        if (!config)
            return;
        setConfig({ ...config, [field]: value });
    };
    const handleWeatherUpdateField = (field, value) => {
        if (!weatherConfig)
            return;
        setWeatherConfig({ ...weatherConfig, [field]: value });
    };
    const handleWeatherLocationUpdate = (field, value) => {
        if (!weatherConfig)
            return;
        setWeatherConfig({
            ...weatherConfig,
            location: { ...weatherConfig.location, [field]: value },
        });
    };
    const handleAddMessage = () => {
        if (!config || !newMessage.trim())
            return;
        setConfig({
            ...config,
            messages: [...config.messages, newMessage.trim()]
        });
        setNewMessage("");
    };
    const handleEditMessage = (index, newText) => {
        if (!config)
            return;
        const updated = [...config.messages];
        updated[index] = newText;
        setConfig({ ...config, messages: updated });
        setEditingIndex(null);
    };
    const handleDeleteMessage = (index) => {
        if (!config)
            return;
        if (window.confirm("Delete this message?")) {
            const updated = config.messages.filter((_, i) => i !== index);
            setConfig({ ...config, messages: updated });
        }
    };
    const handleMoveMessage = (index, direction) => {
        if (!config)
            return;
        const newIndex = direction === "up" ? index - 1 : index + 1;
        if (newIndex < 0 || newIndex >= config.messages.length)
            return;
        const updated = [...config.messages];
        [updated[index], updated[newIndex]] = [updated[newIndex], updated[index]];
        setConfig({ ...config, messages: updated });
    };
    const isLoading = activeTab === "sassy" ? loadingSassy : loadingWeather;
    return (_jsxs("div", { className: "bumper-manager", children: [_jsxs("div", { className: "card", children: [_jsx("h2", { children: "Bumper Management" }), _jsxs("div", { className: "bumper-tabs", children: [_jsx("button", { className: `bumper-tab ${activeTab === "sassy" ? "active" : ""}`, onClick: () => setActiveTab("sassy"), children: "Sassy Cards" }), _jsx("button", { className: `bumper-tab ${activeTab === "weather" ? "active" : ""}`, onClick: () => setActiveTab("weather"), children: "Weather Bumpers" })] }), error && activeTab === "sassy" && (_jsxs("div", { className: "error-message", style: { marginBottom: "1rem" }, children: [_jsx("strong", { children: "Error:" }), " ", error] })), status && (_jsx("div", { className: "success-message", style: { marginBottom: "1rem" }, children: status })), isLoading && (_jsxs("div", { className: "loading-message", style: { marginBottom: "1rem" }, children: [_jsx("div", { className: "loading-spinner" }), _jsxs("span", { children: ["Loading ", activeTab === "sassy" ? "sassy card" : "weather bumper", " configuration..."] })] })), activeTab === "sassy" && !loadingSassy && !config && (_jsxs("div", { className: "error-message", style: { marginBottom: "1rem" }, children: [_jsx("strong", { children: "Error:" }), " Failed to load sassy card configuration. Please try reloading.", _jsx("button", { className: "btn btn-secondary", onClick: loadConfig, style: { marginTop: "0.5rem" }, children: "Reload" })] })), activeTab === "sassy" && config && (_jsxs(_Fragment, { children: [_jsx("p", { className: "help-text", children: "Manage sassy card messages that appear between episodes. These messages are randomly selected from your list." }), _jsx("div", { className: "form-section", children: _jsxs("label", { className: "checkbox-label", children: [_jsx("input", { type: "checkbox", checked: config.enabled, onChange: handleToggleEnabled }), _jsx("span", { children: "Enable sassy cards" })] }) }), _jsx("div", { className: "form-section", children: _jsxs("div", { className: "field", children: [_jsx("label", { htmlFor: "sassy-duration", children: "Duration (seconds)" }), _jsx("input", { id: "sassy-duration", type: "number", min: "1", max: "30", step: "0.5", value: config.duration_seconds, onChange: (e) => handleUpdateField("duration_seconds", parseFloat(e.target.value)) })] }) }), _jsx("div", { className: "form-section", children: _jsxs("div", { className: "field", children: [_jsx("label", { htmlFor: "sassy-music-volume", children: "Music Volume (0.0 - 1.0)" }), _jsx("input", { id: "sassy-music-volume", type: "number", min: "0", max: "1", step: "0.1", value: config.music_volume, onChange: (e) => handleUpdateField("music_volume", parseFloat(e.target.value)) })] }) }), _jsx("div", { className: "form-section", children: _jsxs("div", { className: "field", children: [_jsx("label", { htmlFor: "sassy-probability", children: "Probability Between Episodes (0.0 - 1.0)" }), _jsx("input", { id: "sassy-probability", type: "number", min: "0", max: "1", step: "0.1", value: config.probability_between_episodes, onChange: (e) => handleUpdateField("probability_between_episodes", parseFloat(e.target.value)) }), _jsx("small", { children: "1.0 = always show, 0.0 = never show" })] }) }), _jsx("div", { className: "form-section", children: _jsxs("div", { className: "field", children: [_jsx("label", { htmlFor: "sassy-style", children: "Style" }), _jsxs("select", { id: "sassy-style", value: config.style, onChange: (e) => handleUpdateField("style", e.target.value), children: [_jsx("option", { value: "hbn-cozy", children: "HBN Cozy" }), _jsx("option", { value: "adult-swim-minimal", children: "Adult Swim Minimal" })] })] }) }), _jsxs("div", { className: "form-section", children: [_jsxs("h3", { children: ["Messages (", config.messages.length, ")"] }), _jsx("div", { className: "message-list", children: config.messages.map((message, index) => (_jsx("div", { className: "message-item", children: editingIndex === index ? (_jsxs("div", { className: "message-edit", children: [_jsx("textarea", { value: message, onChange: (e) => {
                                                            const updated = [...config.messages];
                                                            updated[index] = e.target.value;
                                                            setConfig({ ...config, messages: updated });
                                                        }, onBlur: () => setEditingIndex(null), onKeyDown: (e) => {
                                                            if (e.key === "Enter" && e.ctrlKey) {
                                                                setEditingIndex(null);
                                                            }
                                                            if (e.key === "Escape") {
                                                                loadConfig(); // Revert changes
                                                                setEditingIndex(null);
                                                            }
                                                        }, rows: 2, autoFocus: true }), _jsx("button", { className: "btn-small", onClick: () => setEditingIndex(null), children: "Done" })] })) : (_jsxs(_Fragment, { children: [_jsx("div", { className: "message-text", onClick: () => setEditingIndex(index), title: "Click to edit", children: message }), _jsxs("div", { className: "message-actions", children: [_jsx("button", { className: "btn-small", onClick: () => handleMoveMessage(index, "up"), disabled: index === 0, title: "Move up", children: "\u2191" }), _jsx("button", { className: "btn-small", onClick: () => handleMoveMessage(index, "down"), disabled: index === config.messages.length - 1, title: "Move down", children: "\u2193" }), _jsx("button", { className: "btn-small", onClick: () => setEditingIndex(index), title: "Edit", children: "\u270F\uFE0F" }), _jsx("button", { className: "btn-small btn-danger", onClick: () => handleDeleteMessage(index), title: "Delete", children: "\uD83D\uDDD1\uFE0F" })] })] })) }, index))) }), _jsxs("div", { className: "add-message", children: [_jsx("textarea", { placeholder: "Enter a new message...", value: newMessage, onChange: (e) => setNewMessage(e.target.value), onKeyDown: (e) => {
                                                    if (e.key === "Enter" && e.ctrlKey) {
                                                        handleAddMessage();
                                                    }
                                                }, rows: 2 }), _jsx("button", { className: "btn-primary", onClick: handleAddMessage, disabled: !newMessage.trim(), children: "Add Message" }), _jsx("small", { children: "Press Ctrl+Enter to add" })] })] }), _jsxs("div", { className: "form-actions", children: [_jsx("button", { className: "btn-primary", onClick: handleSave, disabled: saving, children: saving ? "Saving..." : "Save Configuration" }), _jsx("button", { className: "btn-secondary", onClick: loadConfig, disabled: saving, children: "Reload" })] })] }))] }), activeTab === "weather" && !loadingWeather && !weatherConfig && (_jsxs("div", { className: "card", children: [_jsx("h2", { children: "Weather Bumper Settings" }), _jsxs("div", { className: "error-message", style: { marginBottom: "1rem" }, children: ["Weather configuration not found. The server may need to initialize it first.", _jsx("button", { className: "btn btn-secondary", onClick: loadWeatherConfig, style: { marginTop: "0.5rem" }, children: "Retry" })] })] })), activeTab === "weather" && !loadingWeather && weatherConfig && (_jsxs("div", { className: "card", children: [_jsx("h2", { children: "Weather Bumper Settings" }), _jsx("p", { className: "help-text", children: "Configure dynamic weather bumpers that show current weather information between episodes. Weather data is fetched fresh at playback time." }), _jsx("div", { className: "form-section", children: _jsxs("label", { className: "checkbox-label", children: [_jsx("input", { type: "checkbox", checked: weatherConfig.enabled, onChange: (e) => handleWeatherUpdateField("enabled", e.target.checked) }), _jsx("span", { children: "Enable weather bumpers" })] }) }), _jsxs("div", { className: "form-section", children: [_jsx("h3", { children: "Location" }), _jsxs("div", { className: "form-grid form-grid-2", children: [_jsxs("div", { className: "field", children: [_jsx("label", { htmlFor: "weather-city", children: "City" }), _jsx("input", { id: "weather-city", type: "text", value: weatherConfig.location.city, onChange: (e) => handleWeatherLocationUpdate("city", e.target.value), placeholder: "Newark" })] }), _jsxs("div", { className: "field", children: [_jsx("label", { htmlFor: "weather-region", children: "Region/State" }), _jsx("input", { id: "weather-region", type: "text", value: weatherConfig.location.region, onChange: (e) => handleWeatherLocationUpdate("region", e.target.value), placeholder: "NJ" })] })] }), _jsxs("div", { className: "form-grid form-grid-3", children: [_jsxs("div", { className: "field", children: [_jsx("label", { htmlFor: "weather-country", children: "Country" }), _jsx("input", { id: "weather-country", type: "text", value: weatherConfig.location.country, onChange: (e) => handleWeatherLocationUpdate("country", e.target.value), placeholder: "US" })] }), _jsxs("div", { className: "field", children: [_jsx("label", { htmlFor: "weather-lat", children: "Latitude" }), _jsx("input", { id: "weather-lat", type: "number", step: "0.0001", value: weatherConfig.location.lat, onChange: (e) => handleWeatherLocationUpdate("lat", parseFloat(e.target.value) || 0), placeholder: "40.7357" })] }), _jsxs("div", { className: "field", children: [_jsx("label", { htmlFor: "weather-lon", children: "Longitude" }), _jsx("input", { id: "weather-lon", type: "number", step: "0.0001", value: weatherConfig.location.lon, onChange: (e) => handleWeatherLocationUpdate("lon", parseFloat(e.target.value) || 0), placeholder: "-74.1724" })] })] }), _jsxs("small", { children: ["Find coordinates at ", _jsx("a", { href: "https://www.latlong.net/", target: "_blank", rel: "noreferrer", children: "latlong.net" })] })] }), _jsxs("div", { className: "form-section", children: [_jsx("h3", { children: "API Configuration" }), _jsxs("div", { className: "field", children: [_jsx("label", { htmlFor: "weather-api-key", children: "OpenWeatherMap API Key" }), _jsx("input", { id: "weather-api-key", type: "password", value: weatherConfig.api_key || "", onChange: (e) => handleWeatherUpdateField("api_key", e.target.value), placeholder: weatherConfig.api_key_set ? "API key is set (enter new to change)" : "Enter your API key" }), _jsxs("small", { children: ["Get a free API key at", " ", _jsx("a", { href: "https://openweathermap.org/api", target: "_blank", rel: "noreferrer", children: "openweathermap.org/api" }), ". The key will be set as an environment variable."] })] })] }), _jsxs("div", { className: "form-section", children: [_jsx("h3", { children: "Display Settings" }), _jsxs("div", { className: "form-grid form-grid-2", children: [_jsxs("div", { className: "field", children: [_jsx("label", { htmlFor: "weather-units", children: "Units" }), _jsxs("select", { id: "weather-units", value: weatherConfig.units, onChange: (e) => handleWeatherUpdateField("units", e.target.value), children: [_jsx("option", { value: "imperial", children: "Imperial (\u00B0F)" }), _jsx("option", { value: "metric", children: "Metric (\u00B0C)" })] })] }), _jsxs("div", { className: "field", children: [_jsx("label", { htmlFor: "weather-duration", children: "Duration (seconds)" }), _jsx("input", { id: "weather-duration", type: "number", min: "1", max: "30", step: "0.5", value: weatherConfig.duration_seconds, onChange: (e) => handleWeatherUpdateField("duration_seconds", parseFloat(e.target.value)) })] })] })] }), _jsxs("div", { className: "form-section", children: [_jsx("h3", { children: "Behavior" }), _jsxs("div", { className: "form-grid form-grid-2", children: [_jsxs("div", { className: "field", children: [_jsx("label", { htmlFor: "weather-probability", children: "Probability Between Episodes (0.0 - 1.0)" }), _jsx("input", { id: "weather-probability", type: "number", min: "0", max: "1", step: "0.05", value: weatherConfig.probability_between_episodes, onChange: (e) => handleWeatherUpdateField("probability_between_episodes", parseFloat(e.target.value)) }), _jsx("small", { children: "1.0 = always show, 0.0 = never show" })] }), _jsxs("div", { className: "field", children: [_jsx("label", { htmlFor: "weather-cache-ttl", children: "Cache TTL (minutes)" }), _jsx("input", { id: "weather-cache-ttl", type: "number", min: "1", max: "60", step: "1", value: weatherConfig.cache_ttl_minutes, onChange: (e) => handleWeatherUpdateField("cache_ttl_minutes", parseFloat(e.target.value)) }), _jsx("small", { children: "How long to cache weather data" })] })] }), weatherConfig.music_volume !== undefined && (_jsxs("div", { className: "field", style: { marginTop: "1.5rem" }, children: [_jsx("label", { htmlFor: "weather-music-volume", children: "Music Volume (0.0 - 1.0)" }), _jsx("input", { id: "weather-music-volume", type: "number", min: "0", max: "1", step: "0.1", value: weatherConfig.music_volume, onChange: (e) => handleWeatherUpdateField("music_volume", parseFloat(e.target.value)) })] }))] }), _jsxs("div", { className: "form-actions", children: [_jsx("button", { className: "btn-primary", onClick: handleSave, disabled: saving, children: saving ? "Saving..." : "Save Configuration" }), _jsx("button", { className: "btn-secondary", onClick: loadWeatherConfig, disabled: saving, children: "Reload" })] })] }))] }));
}
