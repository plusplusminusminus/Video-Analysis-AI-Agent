# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "opencv-python",
#     "scenedetect",
#     "openai",
# ]
# ///
import sqlite3
import sys
import cv2
import json
import base64
import os
from typing import Optional, List, Tuple, Any, Dict
from scenedetect import detect, ContentDetector

# Import OpenAI (used for the actual Video-to-Text comparison)
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


class VideoSceneAnalyzer:
    def __init__(self, db_path: str, video_path: str, openai_api_key: Optional[str] = None) -> None:
        """
        Initializes the analyzer.
        
        Args:
            db_path: Path to the SQLite .db file.
            video_path: Path to the .mp4 video file.
            openai_api_key: OpenAI API key for Vision-Language comparison.
                            If None, a mock comparison will be used for testing.
        """
        self.db_path: str = db_path
        self.video_path: str = video_path
        self.api_key: Optional[str] = openai_api_key
        
        self.client: Optional[Any] = None
        if self.api_key and OPENAI_AVAILABLE:
            self.client = OpenAI(api_key=self.api_key)

    def _get_description_from_db(self) -> str:
        """
        Reads the video scene description from the SQLite database.
        Modify the SQL query to match your actual database schema.
        
        Returns:
            The scene description or a fallback string.
        """
        if not os.path.exists(self.db_path):
            raise FileNotFoundError(f"Database not found: {self.db_path}")

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            # ASSUMPTION: You have a table named 'scenes' with a column 'description'
            # Adjust this query based on your actual DB schema.
            cursor.execute("SELECT description FROM scenes LIMIT 1")
            result = cursor.fetchone()
            if result:
                return str(result[0])
            else:
                return "No description found in database."
        except sqlite3.OperationalError as e:
            print(f"Database error: {e}. Please ensure table and column names are correct.")
            return "Fallback generic description."
        finally:
            conn.close()

    def _detect_shots(self) -> List[Tuple[int, int]]:
        """
        Decodes the video and detects scene/shot boundaries.
        
        Returns:
            A list of tuples: (start_frame, end_frame)
        """
        if not os.path.exists(self.video_path):
            raise FileNotFoundError(f"Video not found: {self.video_path}")

        print("Detecting shots in video...")
        scene_list = detect(self.video_path, ContentDetector())
        
        shots: List[Tuple[int, int]] = []
        for i, scene in enumerate(scene_list):
            start_frame = scene[0].get_frames()
            end_frame = scene[1].get_frames()
            shots.append((start_frame, end_frame))
            
        # If no cuts are found, treat the whole video as 1 shot
        if not shots:
            cap = cv2.VideoCapture(self.video_path)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            shots.append((0, total_frames))
            cap.release()
            
        print(f"Detected {len(shots)} shots.")
        return shots

    def _extract_middle_frame(self, start_frame: int, end_frame: int) -> Optional[str]:
        """
        Extracts the middle frame of a shot to represent the whole shot.
        
        Args:
            start_frame: The starting frame index of the shot.
            end_frame: The ending frame index of the shot.
            
        Returns:
            A base64 encoded jpeg image, or None if extraction failed.
        """
        cap = cv2.VideoCapture(self.video_path)
        mid_frame = (start_frame + end_frame) // 2
        
        cap.set(cv2.CAP_PROP_POS_FRAMES, mid_frame)
        ret, frame = cap.read()
        cap.release()
        
        if not ret:
            return None
            
        # Convert frame to jpeg, then base64 for API transmission
        _, buffer = cv2.imencode('.jpg', frame)
        base64_image = base64.b64encode(buffer).decode('utf-8')
        return base64_image

    def _compare_with_ai(self, base64_image: str, description: str) -> Dict[str, Any]:
        """
        Sends the image and description to a Vision-Language Model to evaluate.
        
        Args:
            base64_image: Base64 string of the frame.
            description: Text description to compare against.
            
        Returns:
            A dictionary containing the AI analysis results.
        """
        if not self.client:
            # MOCK RESPONSE for testing without API keys
            return {
                "Valid": True,
                "Issues": ["Lighting is slightly darker than described.", "Actor's position is slightly off center."],
                "Score": 85
            }

        # Actual API Call to OpenAI GPT-4o
        system_prompt = (
            "You are a strict video QA inspector. You will be given an image representing a shot from a video, "
            "and a text description of what that scene is SUPPOSED to contain.\n"
            "Compare the image to the description and output your findings strictly in JSON format matching this schema:\n"
            "{\n"
            '  "Valid": boolean (True if it largely matches, False if completely wrong),\n'
            '  "Issues": [list of strings detailing discrepancies, missing elements, or lighting/composition issues],\n'
            '  "Score": integer between 0 and 100 (100 is perfect match)\n'
            "}"
        )

        response = self.client.chat.completions.create(
            model="gpt-4o",
            response_format={ "type": "json_object" },
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"Expected Description: {description}"},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ]
                }
            ],
            max_tokens=300
        )

        try:
            return dict(json.loads(response.choices[0].message.content))
        except (json.JSONDecodeError, TypeError, AttributeError, KeyError):
            return {"Valid": False, "Issues": ["Failed to parse AI response"], "Score": 0}

    def analyze(self) -> str:
        """
        Main pipeline: Reads DB, detects shots, extracts frames, compares, and outputs JSON.
        
        Returns:
            JSON string format of the results.
        """
        description = self._get_description_from_db()
        print(f"Target Scene Description: '{description}'")
        
        shots = self._detect_shots()
        
        results: Dict[str, Dict[str, Any]] = {}
        
        for idx, (start, end) in enumerate(shots):
            print(f"Processing Shot {idx + 1}/{len(shots)}...")
            
            base64_image = self._extract_middle_frame(start, end)
            if not base64_image:
                analysis = {"Valid": False, "Issues": ["Failed to extract frame from video"], "Score": 0}
            else:
                analysis = self._compare_with_ai(base64_image, description)
            
            results[f"Shot_{idx + 1}"] = analysis
            
        return json.dumps(results, indent=4)


# ==========================================
# Example Usage
# ==========================================
if __name__ == "__main__":
    # Setup your paths (video path and optional db path can be passed as CLI args)
    VIDEO_PATH = sys.argv[1] if len(sys.argv) > 1 else "input_video.mp4"
    DATABASE_PATH = sys.argv[2] if len(sys.argv) > 2 else "scenes.db"
    
    # Optional: Put your OpenAI API key here for real AI analysis. 
    # If left as None, the script will run a mock test.
    OPENAI_KEY = os.environ.get("OPENAI_API_KEY", None) 
    
    # 1. Create dummy files for testing if they don't exist
    if not os.path.exists(DATABASE_PATH):
        conn = sqlite3.connect(DATABASE_PATH)
        conn.execute("CREATE TABLE scenes (description TEXT)")
        conn.execute("INSERT INTO scenes VALUES ('A man walking a dog in a sunny park.')")
        conn.commit()
        conn.close()
        print(f"Created dummy database: {DATABASE_PATH}")
        
    # Initialize and run
    analyzer = VideoSceneAnalyzer(
        db_path=DATABASE_PATH, 
        video_path=VIDEO_PATH, 
        openai_api_key=OPENAI_KEY
    )
    
    try:
        final_json_report = analyzer.analyze()
        print("\n=== FINAL JSON OUTPUT ===")
        print(final_json_report)
        
        # Save to file
        with open("analysis_report.json", "w") as f:
            f.write(final_json_report)
            
    except Exception as e:
        print(f"Error during analysis: {e}")