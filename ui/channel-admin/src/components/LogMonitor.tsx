import { useEffect, useState, useRef, useCallback } from "react";
import { fetchLogs, LogResponse } from "../api";

export default function LogMonitor() {
  const [logs, setLogs] = useState<LogResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [refreshInterval, setRefreshInterval] = useState(3); // seconds
  const [lines, setLines] = useState(500);
  const [container, setContainer] = useState("tvchannel");
  const [filter, setFilter] = useState("");
  const logContainerRef = useRef<HTMLDivElement>(null);
  const autoScrollRef = useRef(true);

  const loadLogs = useCallback(async () => {
    try {
      setError(null);
      const data = await fetchLogs(container, lines);
      setLogs(data);
      setLoading(false);
      
      // Auto-scroll to bottom if enabled
      if (autoScrollRef.current && logContainerRef.current) {
        setTimeout(() => {
          if (logContainerRef.current) {
            logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
          }
        }, 100);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load logs");
      setLoading(false);
    }
  }, [container, lines]);

  useEffect(() => {
    loadLogs();
  }, [loadLogs]);

  useEffect(() => {
    if (!autoRefresh) {
      return;
    }

    const interval = setInterval(() => {
      loadLogs();
    }, refreshInterval * 1000);

    return () => clearInterval(interval);
  }, [autoRefresh, refreshInterval, loadLogs]);

  const handleScroll = () => {
    if (!logContainerRef.current) return;
    
    const { scrollTop, scrollHeight, clientHeight } = logContainerRef.current;
    // Auto-scroll if user is near bottom (within 100px)
    autoScrollRef.current = scrollHeight - scrollTop - clientHeight < 100;
  };

  const filteredLogs = logs?.logs.filter((line) =>
    filter ? line.toLowerCase().includes(filter.toLowerCase()) : true
  ) || [];

  const getLogLevel = (line: string): "info" | "warning" | "error" | "debug" => {
    const lower = line.toLowerCase();
    if (lower.includes("[error]") || lower.includes("error:") || lower.includes("exception")) {
      return "error";
    }
    if (lower.includes("[warning]") || lower.includes("warning:")) {
      return "warning";
    }
    if (lower.includes("[debug]") || lower.includes("debug:")) {
      return "debug";
    }
    return "info";
  };

  return (
    <div className="log-monitor">
      <div className="card">
        <h2>Log Monitor</h2>
        
        {/* Controls */}
        <div className="log-controls" style={{ 
          display: "flex", 
          gap: "1rem", 
          marginBottom: "1rem",
          flexWrap: "wrap",
          alignItems: "center"
        }}>
          <div className="field" style={{ marginBottom: 0, minWidth: "150px" }}>
            <label>Container</label>
            <input
              type="text"
              value={container}
              onChange={(e) => setContainer(e.target.value)}
              placeholder="tvchannel"
            />
          </div>
          
          <div className="field" style={{ marginBottom: 0, minWidth: "120px" }}>
            <label>Lines</label>
            <input
              type="number"
              value={lines}
              onChange={(e) => setLines(Math.max(1, Math.min(10000, parseInt(e.target.value) || 500)))}
              min={1}
              max={10000}
            />
          </div>

          <div className="field" style={{ marginBottom: 0, flex: 1, minWidth: "200px" }}>
            <label>Filter</label>
            <input
              type="text"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Filter logs..."
            />
          </div>

          <div style={{ display: "flex", gap: "0.5rem", alignItems: "flex-end" }}>
            <label className="checkbox-label" style={{ marginBottom: 0 }}>
              <input
                type="checkbox"
                checked={autoRefresh}
                onChange={(e) => setAutoRefresh(e.target.checked)}
              />
              <span>Auto-refresh</span>
            </label>
            
            {autoRefresh && (
              <div className="field" style={{ marginBottom: 0, minWidth: "100px" }}>
                <input
                  type="number"
                  value={refreshInterval}
                  onChange={(e) => setRefreshInterval(Math.max(1, parseInt(e.target.value) || 3))}
                  min={1}
                  max={60}
                  style={{ width: "60px" }}
                />
                <small style={{ display: "block", marginTop: "0.25rem" }}>sec</small>
              </div>
            )}
            
            <button
              className="btn btn-secondary"
              onClick={loadLogs}
              disabled={loading}
            >
              {loading ? "Loading..." : "Refresh"}
            </button>
          </div>
        </div>

        {/* Status */}
        {logs && (
          <div style={{ 
            marginBottom: "1rem", 
            padding: "0.75rem", 
            background: "var(--color-bg-secondary)",
            borderRadius: "var(--radius-sm)",
            fontSize: "0.875rem",
            color: "var(--color-text-muted)"
          }}>
            <strong>Source:</strong> {logs.source}
            {logs.source === "docker" && logs.container && ` (${logs.container})`}
            {logs.source === "file" && logs.path && ` (${logs.path})`}
            {logs.message && ` - ${logs.message}`}
            {" | "}
            <strong>Lines:</strong> {filteredLogs.length} / {logs.lines}
            {filter && ` (filtered from ${logs.lines})`}
          </div>
        )}

        {error && (
          <div className="error-message" style={{ marginBottom: "1rem" }}>
            <strong>Error:</strong> {error}
          </div>
        )}

        {/* Log Display */}
        <div
          ref={logContainerRef}
          onScroll={handleScroll}
          style={{
            background: "#0a0e1a",
            border: "1px solid var(--color-border)",
            borderRadius: "var(--radius-sm)",
            padding: "1rem",
            fontFamily: "monospace",
            fontSize: "0.8125rem",
            lineHeight: "1.5",
            maxHeight: "600px",
            overflowY: "auto",
            color: "#e2e8f0",
          }}
        >
          {loading && !logs && (
            <div className="loading-message">
              <div className="loading-spinner"></div>
              <span>Loading logs...</span>
            </div>
          )}

          {!loading && filteredLogs.length === 0 && (
            <div style={{ color: "var(--color-text-muted)", textAlign: "center", padding: "2rem" }}>
              {filter ? "No logs match the filter" : "No logs available"}
            </div>
          )}

          {filteredLogs.map((line, idx) => {
            const level = getLogLevel(line);
            const levelColors = {
              error: "#f87171",
              warning: "#fbbf24",
              debug: "#94a3b8",
              info: "#e2e8f0",
            };
            
            return (
              <div
                key={idx}
                style={{
                  color: levelColors[level],
                  marginBottom: "0.25rem",
                  wordBreak: "break-word",
                  whiteSpace: "pre-wrap",
                }}
              >
                {line}
              </div>
            );
          })}
        </div>

        {autoRefresh && (
          <div style={{ 
            marginTop: "0.5rem", 
            fontSize: "0.75rem", 
            color: "var(--color-text-muted)",
            textAlign: "right"
          }}>
            Auto-refreshing every {refreshInterval} second{refreshInterval !== 1 ? "s" : ""}
          </div>
        )}
      </div>
    </div>
  );
}

