import os
import numpy as np
import cv2
import faiss
from insightface.app import FaceAnalysis

# Initialize InsightFace
# buffalo_l includes detection and recognition models
# detection: det_10g.onnx
# recognition: w600k_r50.onnx (512-d)
models_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")
face_app = FaceAnalysis(name='buffalo_l', root=models_dir)
# prepare with ctx_id=0 (GPU) or -1 (CPU). Since environment is macos, likely CPU or MPS (if supported, but onnxruntime often defaults to CPU on mac unless configured).
# We use 0 as a safe default for now, assuming onnxruntime handles fallback or user has compatible setup.
face_app.prepare(ctx_id=0, det_size=(640, 640))

# Initialize FAISS index
dimension = 512
index = faiss.IndexFlatL2(dimension)
names = []  # List to store names corresponding to index IDs

def register_face(image_bytes, name):
    """
    Detects a face in the image, extracts embedding, and stores it in FAISS.
    """
    # Convert bytes to numpy array
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if img is None:
        return {"error": "Invalid image data"}

    faces = face_app.get(img)
    if len(faces) == 0:
        return {"error": "No face detected"}

    # Use the largest face (InsightFace sorts by size/score usually, taking the first one)
    # Actually FaceAnalysis.get() returns a list, usually sorted by detection score/size.
    # We take the first one.
    face = faces[0]
    embedding = face.embedding

    # FAISS expects float32 array of shape (n, d)
    embedding_np = np.array([embedding], dtype=np.float32)
    faiss.normalize_L2(embedding_np)

    index.add(embedding_np)
    names.append(name)

    return {"message": f"Face registered for {name}", "face_count": len(faces)}

def recognize_face_from_img(img):
    """
    Helper function to recognize face from a numpy image.
    """
    if img is None:
        return {"error": "Invalid image data"}

    faces = face_app.get(img)
    if len(faces) == 0:
        return {"error": "No face detected"}

    face = faces[0]
    embedding = face.embedding

    embedding_np = np.array([embedding], dtype=np.float32)
    faiss.normalize_L2(embedding_np)

    if index.ntotal == 0:
        return {"error": "No faces registered"}

    k = 1 # Find top 1 match
    D, I = index.search(embedding_np, k)

    idx = I[0][0]
    distance = D[0][0]

    if idx == -1:
         return {"message": "Unknown face"}

    name = names[idx]

    return {"name": name, "distance": float(distance)}

def recognize_face(image_bytes):
    """
    Detects a face, extracts embedding, and searches FAISS for closest match.
    """
    # Convert bytes to numpy array
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    return recognize_face_from_img(img)
