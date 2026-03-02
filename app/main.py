from fastapi import FastAPI, UploadFile, File, Form, Header, HTTPException, Depends, BackgroundTasks
from app.ocr import scan_image
from app.face import register_face, recognize_face
from app.video import analyze_video
import os
import shutil
import uuid

app = FastAPI()

# In-memory job store
jobs = {}

API_KEY = os.environ.get("API_KEY", "your-secret-api-key")

async def verify_api_key(x_api_key: str = Header(None)):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API Key")

def process_video_analysis(job_id: str, video_path: str):
    """
    Background task to process video analysis.
    """
    try:
        results = analyze_video(video_path)
        jobs[job_id]["status"] = "completed"
        jobs[job_id]["results"] = results
    except Exception as e:
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["error"] = str(e)
    finally:
        # Cleanup temp file
        if os.path.exists(video_path):
            os.remove(video_path)


@app.get("/")
def read_root():
    return {"Hello": "World"}

@app.post("/v1/ocr/scan", dependencies=[Depends(verify_api_key)])
async def ocr_scan(file: UploadFile = File(...)):
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")
    
    content = await file.read()
    results = scan_image(content)
    return {"results": results}

@app.post("/v1/face/register", dependencies=[Depends(verify_api_key)])
async def face_register(name: str = Form(...), file: UploadFile = File(...)):
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")
    
    content = await file.read()
    # Call face registration
    # Note: We pass content first, then name to match face.py signature
    result = register_face(content, name)
    
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
        
    return result

@app.post("/v1/face/recognize", dependencies=[Depends(verify_api_key)])
async def face_recognize(file: UploadFile = File(...)):
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")
    
    content = await file.read()
    result = recognize_face(content)
    
    if "error" in result:
        # If no faces registered or no face detected, return 400 or 404?
        # Let's stick to 400 for now as it's a client error (bad image or state)
        raise HTTPException(status_code=400, detail=result["error"])
        
    return result

@app.post("/v1/video/analyze", dependencies=[Depends(verify_api_key)])
async def video_analyze(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    if not file.content_type.startswith("video/"):
        raise HTTPException(status_code=400, detail="File must be a video")
    
    job_id = str(uuid.uuid4())
    # Save to temp file
    temp_dir = "/tmp"
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)
    temp_path = os.path.join(temp_dir, f"{job_id}_{file.filename}")
    
    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    jobs[job_id] = {"status": "processing"}
    background_tasks.add_task(process_video_analysis, job_id, temp_path)
    
    return {"job_id": job_id}

@app.get("/v1/video/status/{job_id}", dependencies=[Depends(verify_api_key)])
async def video_status(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
        
    return jobs[job_id]
