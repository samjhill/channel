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
      <div className="status-message">
        {saving && "Saving…"}
        {!saving && dirty && "You have unsaved changes"}
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
          {saving ? "Saving…" : "Save"}
        </button>
      </div>
    </div>
  );
}

export default SaveBar;

