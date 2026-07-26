import { forwardRef } from "react";

const VideoPlayer = forwardRef(function VideoPlayer({ src }, ref) {
  if (!src) {
    return (
      <div className="video-empty">
        <span>🎥</span>
        <p>Your uploaded video will preview here</p>
      </div>
    );
  }
  return (
    <video ref={ref} className="video-player" src={src} controls preload="metadata" />
  );
});

export default VideoPlayer;
