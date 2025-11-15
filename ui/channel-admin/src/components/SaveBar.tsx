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
        {saving && "Restarting media server…"}
        {!saving && dirty && "Saving will restart the media server."}
        {!saving && !dirty && (status || "No changes")}
      </div>
      <div style={{ display: "flex", gap: "0.5rem" }}>
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

