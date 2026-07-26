import ScoreMeter from "./ScoreMeter.jsx";

function fmtTime(t) {
  if (t == null || Number.isNaN(t)) return "--:--";
  const s = Math.floor(t % 60);
  const m = Math.floor(t / 60);
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

export default function ShotCard({ shot, onJump }) {
  const valid = !!shot.Valid;
  const issues = shot.Issues || [];
  return (
    <div className={`shot-card ${valid ? "ok" : "bad"}`}>
      <div className="shot-card-head">
        <div>
          <div className="shot-index">Shot {Number(shot.shot_index) + 1}</div>
          <button className="timestamp-chip" onClick={() => onJump?.(shot.timestamp)}>
            ⏱ {fmtTime(shot.start_time)} &rarr; jump
          </button>
        </div>
        <span className={`badge ${valid ? "badge-ok" : "badge-bad"}`}>
          {valid ? "Valid" : "Invalid"}
        </span>
      </div>

      <div className="shot-card-body">
        <ScoreMeter score={shot.Score} />
        <div className="shot-issues">
          <h4>{issues.length ? "Issues" : "No issues detected"}</h4>
          {issues.length > 0 && (
            <ul>
              {issues.map((issue, i) => (
                <li key={i}>{issue}</li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {shot.expectation && (
        <details className="shot-expectation">
          <summary>Expected</summary>
          <pre>{shot.expectation}</pre>
        </details>
      )}
    </div>
  );
}
