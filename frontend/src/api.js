export async function validateVideo(videoFile, sceneFile) {
  const form = new FormData();
  form.append("video", videoFile);
  form.append("scene", sceneFile);

  const res = await fetch("/api/validate", {
    method: "POST",
    body: form,
  });

  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* ignore parse errors */
    }
    throw new Error(detail);
  }
  return res.json();
}

export async function getHealth() {
  try {
    const res = await fetch("/api/health");
    if (!res.ok) return null;
    return res.json();
  } catch {
    return null;
  }
}
