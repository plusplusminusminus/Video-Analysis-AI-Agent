import ScoreMeter from "./ScoreMeter.jsx";

export default function AnalysisSummary({ analysis, meta }) {
  if (!analysis) return null;
  const passRate = Math.round((analysis.pass_rate ?? 0) * 100);
  const overallValid = !!analysis.overall_valid;

  return (
    <section className="card summary">
      <div className="summary-head">
        <ScoreMeter score={analysis.overall_score} size={120} stroke={11} label="Overall" />
        <div className="summary-headtext">
          <span className={`badge ${overallValid ? "badge-ok" : "badge-bad"}`}>
            {overallValid ? "Scene matched" : "Scene mismatch"}
          </span>
          <p className="summary-text">{analysis.summary}</p>
          <div className="summary-stats">
            <div>
              <strong>{passRate}%</strong>
              <span>Pass rate</span>
            </div>
            <div>
              <strong>{meta?.shot_count ?? analysis.shots?.length ?? 0}</strong>
              <span>Shots</span>
            </div>
            <div>
              <strong>{meta?.model ?? "-"}</strong>
              <span>Model</span>
            </div>
          </div>
        </div>
      </div>

      <div className="summary-lists">
        {analysis.key_issues?.length > 0 && (
          <div className="summary-block">
            <h4>Key issues</h4>
            <ul>
              {analysis.key_issues.map((x, i) => (
                <li key={i}>{x}</li>
              ))}
            </ul>
          </div>
        )}
        {analysis.recommendations?.length > 0 && (
          <div className="summary-block">
            <h4>Recommendations</h4>
            <ul>
              {analysis.recommendations.map((x, i) => (
                <li key={i}>{x}</li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {meta?.aggregation_source && (
        <div className="summary-source">Analysis engine: {meta.aggregation_source}</div>
      )}
    </section>
  );
}
