#!/usr/bin/env python3
"""A simple CLI video player using mpv."""

import argparse
import os
import subprocess
import sys
from typing import List


def main() -> None:
    """Main execution function for the CLI video player."""
    parser = argparse.ArgumentParser(description="A simple CLI video player.")
    parser.add_argument("video_path", help="Path to the video file to play")
    parser.add_argument(
        "--fullscreen", "-f", action="store_true", help="Play in fullscreen"
    )

    args = parser.parse_args()

    if not os.path.exists(args.video_path):
        print(f"Error: File '{args.video_path}' not found.")
        sys.exit(1)

    # Build the command
    command: List[str] = ["mpv", args.video_path]
    if args.fullscreen:
        command.append("--fs")

    # Run the player
    try:
        print(f"Playing {args.video_path}...")
        subprocess.run(command, check=True)
    except KeyboardInterrupt:
        print("\\nPlayback stopped by user.")
    except FileNotFoundError:
        print("Error: 'mpv' is not installed or not in PATH.")
    except subprocess.CalledProcessError as e:
        print(f"Error: Playback failed with exit code {e.returncode}.")


if __name__ == "__main__":
    main()