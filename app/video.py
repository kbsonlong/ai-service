import cv2
import os
from app.face import recognize_face_from_img

def analyze_video(video_path):
    """
    Analyzes a video file to identify people in frames (1 frame per second).
    Returns a list of results with timestamp, person name, and confidence.
    """
    results = []
    
    if not os.path.exists(video_path):
        return {"error": "Video file not found"}

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return {"error": "Could not open video file"}
        
    fps = cap.get(cv2.CAP_PROP_FPS)
    if fps <= 0:
        # Fallback if FPS is not detected correctly
        fps = 30 
        
    frame_interval = int(fps) # process 1 frame every second
    if frame_interval == 0:
        frame_interval = 1
        
    frame_count = 0
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
            
        if frame_count % frame_interval == 0:
            # Timestamp in seconds
            timestamp = frame_count / fps
            
            # Recognize face
            face_result = recognize_face_from_img(frame)
            
            if "name" in face_result:
                results.append({
                    "timestamp": round(timestamp, 2),
                    "person_name": face_result["name"],
                    "confidence": face_result["distance"] 
                })
            # Ignore errors or "Unknown face" or "No face detected"
                
        frame_count += 1
        
    cap.release()
    return results
