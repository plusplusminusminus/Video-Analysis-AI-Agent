"""Generate a small synthetic .mp4 with a few distinct shots for local testing."""

import cv2
import numpy as np

OUT = "test_clip.mp4"
W, H, FPS = 320, 240, 24

fourcc = cv2.VideoWriter_fourcc(*"mp4v")
writer = cv2.VideoWriter(OUT, fourcc, FPS, (W, H))

# Five 1-second shots with strongly different content so ContentDetector splits them.
colors = [(30, 30, 160), (200, 120, 20), (20, 160, 60), (160, 40, 160), (40, 160, 200)]
labels = ["SUV / desert", "man at sun", "trunk open", "blue bottle", "drink / smile"]

for color, label in zip(colors, labels):
    for _ in range(FPS):
        frame = np.full((H, W, 3), color, dtype=np.uint8)
        cv2.putText(frame, label, (18, H // 2), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        writer.write(frame)

writer.release()
print(f"wrote {OUT}")
