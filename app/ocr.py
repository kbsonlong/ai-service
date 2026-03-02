from rapidocr_onnxruntime import RapidOCR
import cv2
import numpy as np

# Initialize RapidOCR once
ocr = RapidOCR()

def scan_image(image_bytes: bytes):
    """
    Scans an image for text using RapidOCR.

    Args:
        image_bytes (bytes): The image content in bytes.

    Returns:
        list: A list of dictionaries containing text, confidence, and coordinates.
    """
    # Convert bytes to numpy array
    nparr = np.frombuffer(image_bytes, np.uint8)
    # Decode image
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if img is None:
        return []

    # Run OCR
    result, _ = ocr(img)

    if not result:
        return []

    formatted_result = []
    for item in result:
        # item structure: [coordinates, text, confidence]
        coordinates = item[0]
        text = item[1]
        confidence = item[2]
        
        formatted_result.append({
            "text": text,
            "confidence": confidence,
            "coordinates": coordinates
        })

    return formatted_result
