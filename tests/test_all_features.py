import requests
import sys
import os
import time
import subprocess
import cv2
import numpy as np

# Configuration
BASE_URL = "http://localhost:8002"
API_KEY = "your-secret-api-key"
SAMPLE_FACE = "sample_face.jpg"
SAMPLE_TEXT_IMG = "sample_text.png"
SAMPLE_VIDEO = "sample_video.mp4"
FACE_NAME = "Test User"
TEXT_CONTENT = "HELLO WORLD"

def create_text_image(filename=SAMPLE_TEXT_IMG, text=TEXT_CONTENT):
    """Creates a simple image with text for OCR testing."""
    if os.path.exists(filename):
        return
    
    # Create a white image
    img = np.zeros((200, 600, 3), dtype=np.uint8)
    img.fill(255)
    
    # Add text
    font = cv2.FONT_HERSHEY_SIMPLEX
    # Center the text roughly
    text_size = cv2.getTextSize(text, font, 2, 3)[0]
    text_x = (img.shape[1] - text_size[0]) // 2
    text_y = (img.shape[0] + text_size[1]) // 2
    
    cv2.putText(img, text, (text_x, text_y), font, 2, (0, 0, 0), 3, cv2.LINE_AA)
    cv2.imwrite(filename, img)
    print(f"Created {filename}")

def create_video_from_image(image_path=SAMPLE_FACE, output_path=SAMPLE_VIDEO, duration=3):
    """Creates a video file from a static image."""
    if os.path.exists(output_path):
        return

    if not os.path.exists(image_path):
        print(f"Error: {image_path} not found. Cannot create video.")
        return

    img = cv2.imread(image_path)
    if img is None:
        print(f"Error: Could not read {image_path}")
        return

    height, width, layers = img.shape
    # 'mp4v' is widely supported for .mp4
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    fps = 1
    out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
    
    for _ in range(duration * fps):
        out.write(img)
    
    out.release()
    print(f"Created {output_path}")

def wait_for_server(url, timeout=30):
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            requests.get(url, timeout=1)
            return True
        except requests.exceptions.ConnectionError:
            time.sleep(1)
    return False

def test_authentication():
    print("\n--- Testing Authentication ---")
    # Test without API Key
    response = requests.get(f"{BASE_URL}/") # Root is public, try protected endpoint
    # Actually root is public based on main.py, let's try a protected one
    try:
        response = requests.post(f"{BASE_URL}/v1/ocr/scan")
        if response.status_code == 401 or response.status_code == 403:
             print("PASS: Request without API Key failed as expected (401/403).")
        else:
             print(f"FAIL: Request without API Key returned {response.status_code}")
    except Exception as e:
        print(f"Error testing auth: {e}")

    # Test with invalid API Key
    headers = {"x-api-key": "wrong-key"}
    response = requests.post(f"{BASE_URL}/v1/ocr/scan", headers=headers)
    if response.status_code == 401:
        print("PASS: Request with invalid API Key failed as expected (401).")
    else:
        print(f"FAIL: Request with invalid API Key returned {response.status_code}")

def test_ocr():
    print("\n--- Testing OCR Endpoint ---")
    headers = {"x-api-key": API_KEY}
    with open(SAMPLE_TEXT_IMG, "rb") as f:
        files = {"file": (SAMPLE_TEXT_IMG, f, "image/png")}
        response = requests.post(f"{BASE_URL}/v1/ocr/scan", headers=headers, files=files)
    
    if response.status_code == 200:
        data = response.json()
        results = data.get("results", [])
        found_text = " ".join([r["text"] for r in results])
        print(f"OCR Results: {found_text}")
        
        if TEXT_CONTENT in found_text or TEXT_CONTENT.replace(" ", "") in found_text.replace(" ", ""):
            print("PASS: OCR correctly identified the text.")
        else:
            print(f"FAIL: OCR did not find expected text '{TEXT_CONTENT}'. Found: '{found_text}'")
    else:
        print(f"FAIL: OCR request failed with {response.status_code}: {response.text}")

def test_face_register():
    print("\n--- Testing Face Register Endpoint ---")
    headers = {"x-api-key": API_KEY}
    with open(SAMPLE_FACE, "rb") as f:
        files = {"file": (SAMPLE_FACE, f, "image/jpeg")}
        data = {"name": FACE_NAME}
        response = requests.post(f"{BASE_URL}/v1/face/register", headers=headers, files=files, data=data)
    
    if response.status_code == 200:
        print(f"Register Response: {response.json()}")
        print("PASS: Face registered successfully.")
        return True
    else:
        print(f"FAIL: Face register failed with {response.status_code}: {response.text}")
        return False

def test_face_recognize():
    print("\n--- Testing Face Recognize Endpoint ---")
    headers = {"x-api-key": API_KEY}
    with open(SAMPLE_FACE, "rb") as f:
        files = {"file": (SAMPLE_FACE, f, "image/jpeg")}
        response = requests.post(f"{BASE_URL}/v1/face/recognize", headers=headers, files=files)
    
    if response.status_code == 200:
        data = response.json()
        print(f"Recognize Response: {data}")
        if data.get("name") == FACE_NAME:
            print(f"PASS: Face recognized as {FACE_NAME}.")
        else:
            print(f"FAIL: Face recognized as {data.get('name')}, expected {FACE_NAME}.")
    else:
        print(f"FAIL: Face recognize failed with {response.status_code}: {response.text}")

def test_video_analyze():
    print("\n--- Testing Video Analyze Endpoint ---")
    headers = {"x-api-key": API_KEY}
    
    # 1. Submit Job
    with open(SAMPLE_VIDEO, "rb") as f:
        files = {"file": (SAMPLE_VIDEO, f, "video/mp4")}
        response = requests.post(f"{BASE_URL}/v1/video/analyze", headers=headers, files=files)
    
    if response.status_code != 200:
        print(f"FAIL: Video analyze submission failed with {response.status_code}: {response.text}")
        return

    job_id = response.json().get("job_id")
    print(f"Job submitted. Job ID: {job_id}")
    
    # 2. Poll Status
    status = "processing"
    results = None
    start_time = time.time()
    timeout = 60 # 60 seconds timeout
    
    while status == "processing":
        if time.time() - start_time > timeout:
            print("FAIL: Video analysis timed out.")
            return
        
        time.sleep(2)
        response = requests.get(f"{BASE_URL}/v1/video/status/{job_id}", headers=headers)
        if response.status_code == 200:
            data = response.json()
            status = data.get("status")
            if status == "completed":
                results = data.get("results")
            elif status == "failed":
                print(f"FAIL: Video analysis job failed: {data.get('error')}")
                return
        else:
            print(f"Warning: Status check failed with {response.status_code}")
    
    # 3. Verify Results
    print(f"Video Analysis Results: {results}")
    if results:
        # Check if name appears
        names_found = [r.get("person_name") for r in results]
        if FACE_NAME in names_found:
            print(f"PASS: Video analysis found {FACE_NAME}.")
        else:
            print(f"FAIL: Video analysis did not find {FACE_NAME}. Found: {names_found}")
    else:
        print("FAIL: No results returned from video analysis.")

def main():
    # 1. Prepare Assets
    if not os.path.exists(SAMPLE_FACE):
        print(f"Error: {SAMPLE_FACE} not found. Please ensure it exists in the current directory.")
        # Try to download if missing? No, user provided env usually has it. 
        # But if running in ai-service, it should be there.
        # Let's try to look for it in parent or current dir.
        if os.path.exists(os.path.join("ai-service", SAMPLE_FACE)):
             # We are in root, script assumes we are in ai-service or files are here.
             # The instruction says "Create a test script 'ai-service/tests/test_all_features.py'"
             # So we will likely run it from project root or ai-service root.
             pass
    
    create_text_image()
    create_video_from_image()

    # 2. Start Server
    print("Starting uvicorn server...")
    env = os.environ.copy()
    env["PYTHONPATH"] = os.getcwd() # Ensure imports work
    
    # Assuming running from ai-service directory
    server_process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", "8002", "--host", "0.0.0.0"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env
    )
    
    try:
        if wait_for_server(BASE_URL):
            print("Server is up and running.")
            
            # 3. Run Tests
            test_authentication()
            test_ocr()
            if test_face_register(): # Only proceed if registration works
                test_face_recognize()
                test_video_analyze()
            else:
                print("Skipping recognize and video tests due to registration failure.")
                
        else:
            print("Error: Server failed to start within timeout.")
            out, err = server_process.communicate(timeout=5)
            print("Server Output:\n", out.decode())
            print("Server Error:\n", err.decode())

    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        # 4. Cleanup
        print("\nStopping server...")
        server_process.terminate()
        server_process.wait()
        
        # Clean up generated assets if desired? Maybe keep them for debugging.
        # os.remove(SAMPLE_TEXT_IMG)
        # os.remove(SAMPLE_VIDEO)

if __name__ == "__main__":
    main()
