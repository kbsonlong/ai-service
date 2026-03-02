import requests
import sys
import os
import time
import subprocess

def download_sample_image(filename="sample_face.jpg"):
    url = "https://raw.githubusercontent.com/deepinsight/insightface/master/python-package/insightface/data/images/t1.jpg"
    if not os.path.exists(filename):
        print(f"Downloading sample image from {url}...")
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                with open(filename, 'wb') as f:
                    f.write(response.content)
                print("Download successful.")
            else:
                print(f"Failed to download image: {response.status_code}")
                return False
        except Exception as e:
            print(f"Error downloading image: {e}")
            return False
    return True

def test_face_endpoints():
    if not download_sample_image():
        print("Skipping tests because sample image could not be downloaded.")
        return

    print("Starting server for testing...")
    # Start uvicorn in background
    # Ensure PYTHONPATH includes the current directory
    env = os.environ.copy()
    env["PYTHONPATH"] = os.getcwd()

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", "8002"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        cwd=os.getcwd() # Run in current directory
    )

    try:
        # Wait for server to start
        print("Waiting for server to start (polling for up to 300s)...")
        base_url = "http://localhost:8002"
        start_time = time.time()
        while True:
            try:
                requests.get(base_url, timeout=1)
                print("Server is up!")
                break
            except requests.exceptions.ConnectionError:
                if time.time() - start_time > 300:
                    print("Timeout waiting for server to start.")
                    raise
                time.sleep(5)
                print(".", end="", flush=True)
        print() # Newline

        api_key = "your-secret-api-key" # Default key in main.py

        # Test 1: Register Face
        print("\nTesting /v1/face/register...")
        with open("sample_face.jpg", "rb") as f:
            files = {"file": ("sample_face.jpg", f, "image/jpeg")}
            data = {"name": "Test Person"}
            headers = {"x-api-key": api_key}

            response = requests.post(
                f"{base_url}/v1/face/register",
                files=files,
                data=data,
                headers=headers
            )

        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")

        if response.status_code == 200:
            print("Register Success!")
        else:
            print("Register Failed!")

        # Test 2: Recognize Face
        print("\nTesting /v1/face/recognize...")
        with open("sample_face.jpg", "rb") as f:
            files = {"file": ("sample_face.jpg", f, "image/jpeg")}
            headers = {"x-api-key": api_key}

            response = requests.post(
                f"{base_url}/v1/face/recognize",
                files=files,
                headers=headers
            )

        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")

        if response.status_code == 200:
            result = response.json()
            if result.get("name") == "Test Person":
                print("Recognize Success! Name matches.")
            else:
                print(f"Recognize Failed! Name mismatch: {result.get('name')}")
        else:
            print("Recognize Failed!")

    finally:
        print("\nStopping server...")
        proc.terminate()
        try:
            outs, errs = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            outs, errs = proc.communicate()

        # print("Server Output:")
        # print(outs.decode())
        # print("Server Error:")
        # print(errs.decode())

if __name__ == "__main__":
    test_face_endpoints()
