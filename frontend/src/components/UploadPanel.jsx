import { useRef, useState } from "react";

function FileDrop({ label, hint, accept, file, onSelect, icon }) {
  const inputRef = useRef(null);
  const [dragging, setDragging] = useState(false);

  const handleDrop = (e) => {
    e.preventDefault();
    setDragging(false);
    const dropped = e.dataTransfer.files?.[0];
    if (dropped) onSelect(dropped);
  };

  return (
    <div
      className={`filedrop ${dragging ? "dragging" : ""} ${file ? "has-file" : ""}`}
      onClick={() => inputRef.current?.click()}
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
    >
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        hidden
        onChange={(e) => e.target.files?.[0] && onSelect(e.target.files[0])}
      />
      <div className="filedrop-icon">{icon}</div>
      <div className="filedrop-text">
        <strong>{file ? file.name : label}</strong>
        <span>{file ? `${(file.size / 1024 / 1024).toFixed(2)} MB` : hint}</span>
      </div>
    </div>
  );
}

export default function UploadPanel({
  videoFile,
  sceneFile,
  onVideo,
  onScene,
  onValidate,
  loading,
}) {
  const canValidate = videoFile && sceneFile && !loading;

  return (
    <section className="card upload-panel">
      <h2 className="card-title">1 &middot; Upload</h2>
      <div className="upload-grid">
        <FileDrop
          label="Drop a video"
          hint="MP4, MOV, WebM"
          accept="video/*"
          file={videoFile}
          onSelect={onVideo}
          icon="🎬"
        />
        <FileDrop
          label="Drop a scene definition"
          hint=".scene or .json"
          accept=".scene,.json,application/json"
          file={sceneFile}
          onSelect={onScene}
          icon="📄"
        />
      </div>
      <button className="btn-primary" onClick={onValidate} disabled={!canValidate}>
        {loading ? (
          <>
            <span className="spinner" /> Validating&hellip;
          </>
        ) : (
          "Validate video against scene"
        )}
      </button>
    </section>
  );
}
