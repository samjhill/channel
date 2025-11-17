interface Props {
  dirty: boolean;
  saving: boolean;
  disabled?: boolean;
  status: string | null;
  onSave: () => void;
  onDiscard: () => void;
}

function SaveBar({ dirty, saving, disabled, status, onSave, onDiscard }: Props) {
  return (
    <div className="save-bar">
      <div className="status-message" aria-live="polite">
        {saving && (
          <>
            <div className="loading-spinner" style={{ display: "inline-block", marginRight: "0.5rem" }}></div>
            <span>Restarting media server…</span>
          </>
        )}
        {!saving && dirty && (
          <>
            <span>Saving will restart the media server.</span>
            <small style={{ display: "block", marginTop: "0.25rem", opacity: 0.8 }}>
              Press Ctrl+S to save, Esc to discard
            </small>
          </>
        )}
        {!saving && !dirty && (status || "No changes")}
      </div>
      <div className="save-bar-actions">
        <button className="btn btn-secondary" onClick={onDiscard} disabled={!dirty || saving}>
          Discard
        </button>
        <button
          className="btn btn-primary"
          onClick={onSave}
          disabled={disabled || saving}
        >
          {saving ? "Restarting…" : "Save"}
        </button>
      </div>
    </div>
  );
}

export default SaveBar;

