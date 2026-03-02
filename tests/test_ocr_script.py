import cv2
import numpy as np
import time
import requests
import subprocess
import sys
import os
from app.ocr import scan_image

def create_test_image(text="Hello World"):
    # Create a white image
    img = np.ones((100, 300, 3), dtype=np.uint8) * 255
    # Add text
    font = cv2.FONT_HERSHEY_SIMPLEX
    cv2.putText(img, text, (10, 50), font, 1, (0, 0, 0), 2, cv2.LINE_AA)
    # Encode to bytes
    _, img_encoded = cv2.imencode('.png', img)
    return img_encoded.tobytes()

def test_scan_image_direct():
    print("Testing scan_image function directly...")
    image_bytes = create_test_image("Hello World")
    results = scan_image(image_bytes)
    print(f"Direct Scan Results: {results}")
    # Check if results is a list
    if isinstance(results, list):
        print("scan_image returned a list as expected.")
    else:
        print("scan_image did NOT return a list.")
        sys.exit(1)

def test_api_endpoint():
    print("Testing API endpoint...")
    # Start uvicorn in background
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", "8001"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    try:
        # Wait for server to start
        time.sleep(5)
        
        base_url = "http://localhost:8001"
        
        # Test 1: No API Key
        image_bytes = create_test_image()
        response = requests.post(
            f"{base_url}/v1/ocr/scan",
            files={"file": ("test.png", image_bytes, "image/png")}
        )
        print(f"No API Key: {response.status_code}")
        if response.status_code != 401:
            print("Failed: Expected 401 for no API Key")
            # Don't exit yet, try other tests
        
        # Test 2: Invalid API Key
        response = requests.post(
            f"{base_url}/v1/ocr/scan",
            headers={"X-API-Key": "wrong-key"},
            files={"file": ("test.png", image_bytes, "image/png")}
        )
        print(f"Invalid API Key: {response.status_code}")
        if response.status_code != 401:
            print("Failed: Expected 401 for invalid API Key")

        # Test 3: Valid API Key
        response = requests.post(
            f"{base_url}/v1/ocr/scan",
            headers={"X-API-Key": "my-secret-key"},
            files={"file": ("test.png", image_bytes, "image/png")}
        )
        print(f"Valid API Key: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"API Scan Results: {data}")
            if "results" in data:
                print("Success: Got results from API")
            else:
                print("Failed: No results in response")
        else:
            print(f"Failed: API returned {response.status_code}")
            print(response.text)

    finally:
        proc.terminate()
        proc.wait()

if __name__ == "__main__":
    test_scan_image_direct()
    test_api_endpoint()
