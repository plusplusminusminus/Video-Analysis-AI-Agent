import { useEffect, useMemo, useRef, useState } from "react";
import { validateVideo, getHealth } from "./api.js";
import UploadPanel from "./components/UploadPanel.jsx";
import VideoPlayer from "./components/VideoPlayer.jsx";
import AnalysisSummary from "./components/AnalysisSummary.jsx";
import ShotCard from "./components/ShotCard.jsx";

export default function App() {
  const [videoFile, setVideoFile] = useState(null);
  const [sceneFile, setSceneFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);
  const [health, setHealth] = useState(null);
  const videoRef = useRef(null);

  const videoUrl = useMemo(
    () => (videoFile ? URL.createObjectURL(videoFile) : null),
    [videoFile]
  );

  useEffect(() => {
    return () => videoUrl && URL.revokeObjectURL(videoUrl);
  }, [videoUrl]);

  useEffect(() => {
    getHealth().then(setHealth);
  }, []);

  const handleValidate = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const data = await validateVideo(videoFile, sceneFile);
      setResult(data);
    } catch (e) {
      setError(e.message || "Validation failed");
    } finally {
      setLoading(false);
    }
  };

  const jumpTo = (t) => {
    if (videoRef.current && t != null) {
      videoRef.current.currentTime = Number(t) || 0;
      videoRef.current.play?.();
    }
  };

  const shots = result?.analysis?.shots ?? result?.shots ?? [];

  return (
    <div className="app">
      <header className="hero">
        <div className="hero-inner">
          <div className="hero-badge">RocketRide &middot; webhook pipeline</div>
          <h1>Video Scene Validator</h1>
          <p>
            Upload a video and a scene definition. We detect shots, validate each frame
            against the expected scene, and synthesize an analysis report.
          </p>
          {health && (
            <div className="hero-status">
              <span className={`dot ${health.vision_provider_configured ? "on" : "off"}`} />
              Vision: {health.vision_provider_configured ? "configured" : "mock mode"}
              <span className="sep">|</span>
              Model: {health.model}
              <span className="sep">|</span>
              Aggregation: {health.rocketride_aggregation_enabled ? "RocketRide" : "local"}
              <span className="sep">|</span>
              <span className={`dot ${health.rocketride_pipeline_running ? "on" : "off"}`} />
              Pipeline: {health.rocketride_pipeline_running ? "running (ttl=0)" : "idle"}
            </div>
          )}
        </div>
      </header>

      <main className="content">
        <div className="top-grid">
          <UploadPanel
            videoFile={videoFile}
            sceneFile={sceneFile}
            onVideo={setVideoFile}
            onScene={setSceneFile}
            onValidate={handleValidate}
            loading={loading}
          />
          <section className="card">
            <h2 className="card-title">2 &middot; Preview</h2>
            <VideoPlayer ref={videoRef} src={videoUrl} />
          </section>
        </div>

        {error && <div className="alert error">⚠ {error}</div>}

        {loading && (
          <div className="loading-block">
            <span className="spinner big" />
            <p>Detecting shots and running vision analysis&hellip;</p>
          </div>
        )}

        {result && !loading && (
          <section className="results">
            <h2 className="section-title">3 &middot; Results</h2>
            <AnalysisSummary analysis={result.analysis} meta={result.meta} />
            <div className="shots-grid">
              {shots.map((shot) => (
                <ShotCard key={shot.shot_index} shot={shot} onJump={jumpTo} />
              ))}
            </div>
            <details className="raw-json">
              <summary>Raw JSON</summary>
              <pre>{JSON.stringify(result, null, 2)}</pre>
            </details>
          </section>
        )}

        {!result && !loading && !error && (
          <div className="empty-state">
            <span>📊</span>
            <p>Results will appear here after validation.</p>
          </div>
        )}
      </main>

      <footer className="footer">
        Built with RocketRide (webhook) + Token Router · Video Scene Validator
      </footer>
    </div>
  );
}
