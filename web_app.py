import cv2
import dlib
import numpy as np
import face_recognition
from scipy.spatial import distance as dist
from imutils import face_utils
import os
import json
import glob
import base64
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

# ---------------- PATHS & FILES ----------------
# Resolve paths relative to this file so they work both locally and in Docker
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FACES_DIR = os.path.join(BASE_DIR, "stored_faces")
METADATA_FILE = os.path.join(FACES_DIR, "face_metadata.json")
MODEL_PATH = os.path.join(BASE_DIR, "shape_predictor_68_face_landmarks.dat")

if not os.path.exists(FACES_DIR):
    os.makedirs(FACES_DIR)

# Ensure metadata file exists
if not os.path.exists(METADATA_FILE):
    with open(METADATA_FILE, "w") as _f:
        json.dump({}, _f)

stored_faces = {}  # {face_id: {encoding, name, image_path}}
next_face_id = 1

# Load models
print("[System] Loading shape predictor model...")
if not os.path.exists(MODEL_PATH):
    raise FileNotFoundError(
        f"Shape predictor model not found at: {MODEL_PATH}\n"
        "Download it from: https://github.com/italojs/facial-landmarks-recognition/raw/master/shape_predictor_68_face_landmarks.dat"
    )
detector = dlib.get_frontal_face_detector()
predictor = dlib.shape_predictor(MODEL_PATH)
print("[System] Models loaded successfully.")

# ---------------- FUNCTIONS ----------------

def load_stored_faces():
    """Load existing face data from storage"""
    global stored_faces, next_face_id
    if os.path.exists(METADATA_FILE):
        try:
            with open(METADATA_FILE, 'r') as f:
                all_faces = json.load(f)
            
            stored_faces = {}
            for face_id, face_data in all_faces.items():
                if os.path.exists(face_data['image_path']):
                    stored_faces[face_id] = face_data
            
            if stored_faces:
                next_face_id = max(int(face_id) for face_id in stored_faces.keys()) + 1
            else:
                next_face_id = 1
            print(f"[System] Loaded {len(stored_faces)} stored face profiles.")
            return True
        except Exception as e:
            print(f"[Error] Loading faces: {e}")
            stored_faces = {}
            next_face_id = 1
    return False

def store_new_face(face_encoding, face_img, x1, y1, x2, y2, custom_name=None):
    """Store a new face with encoding and image"""
    global next_face_id, stored_faces
    
    # Check if this face is already stored
    for face_id, face_data in stored_faces.items():
        try:
            stored_encoding = np.array(face_data['encoding'])
            distance = face_recognition.face_distance([stored_encoding], face_encoding)[0]
            if distance < 0.45:
                return False, face_data['name']
        except:
            continue
    
    face_id = str(next_face_id)
    face_name = custom_name if custom_name else f"Person_{next_face_id}"
    
    # Ensure coordinates are within image bounds
    h, w = face_img.shape[:2]
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)
    face_crop = face_img[y1:y2, x1:x2]
    
    image_path = f"{FACES_DIR}/face_{face_id}.jpg"
    cv2.imwrite(image_path, face_crop)
    
    stored_faces[face_id] = {
        'encoding': face_encoding.tolist(),
        'name': face_name,
        'image_path': image_path
    }
    
    with open(METADATA_FILE, 'w') as f:
        json.dump(stored_faces, f)
    
    next_face_id += 1
    print(f"[System] Enrolled new user: {face_name}")
    return True, face_name

def eye_aspect_ratio(eye):
    try:
        A = dist.euclidean(eye[1], eye[5])
        B = dist.euclidean(eye[2], eye[4])
        C = dist.euclidean(eye[0], eye[3])
        return (A + B) / (2.0 * C)
    except:
        return 0.23

def decode_base64_image(base64_string):
    """Decode base64 string to OpenCV BGR image"""
    if "," in base64_string:
        base64_string = base64_string.split(",")[1]
    img_data = base64.b64decode(base64_string)
    nparr = np.frombuffer(img_data, np.uint8)
    return cv2.imdecode(nparr, cv2.IMREAD_COLOR)

# Load faces on startup
load_stored_faces()

# ---------------- FASTAPI APPLICATION ----------------
app = FastAPI(title="Biometric Face Liveness System")

# Create static directory if it doesn't exist
if not os.path.exists("static"):
    os.makedirs("static")

# Serve static folder
app.mount("/static", StaticFiles(directory="static"), name="static")

# Serve stored_faces folder
app.mount("/stored_faces", StaticFiles(directory="stored_faces"), name="stored_faces")

# Serve the main page
@app.get("/")
async def get_index():
    with open("static/index.html", "r") as f:
        return HTMLResponse(content=f.read(), status_code=200)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("[WS] Client connected.")
    global next_face_id
    
    # State tracking per WebSocket session
    session_state = {
        "mode": "verify",  # "verify" or "store"
        "enroll_name": None,
        "total_blinks": 0,
        "blink_counter": 0,
        "head_left": False,
        "head_right": False,
        "initial_nose_x": None
    }
    
    try:
        # Send initial vault state
        vault_faces = [{"id": fid, "name": fdata["name"], "image": fdata["image_path"]} 
                       for fid, fdata in stored_faces.items()]
        await websocket.send_json({
            "type": "init",
            "enrolled": vault_faces
        })
        
        while True:
            # Receive message
            data = await websocket.receive_json()
            msg_type = data.get("type")
            
            if msg_type == "config":
                session_state["mode"] = data.get("mode", "verify")
                session_state["enroll_name"] = data.get("name")
                
                # Reset counters on mode switch
                session_state["total_blinks"] = 0
                session_state["blink_counter"] = 0
                session_state["head_left"] = False
                session_state["head_right"] = False
                session_state["initial_nose_x"] = None
                
                print(f"[WS] Config updated. Mode: {session_state['mode'].upper()}")
                await websocket.send_json({
                    "type": "config_ack",
                    "mode": session_state["mode"],
                    "enroll_name": session_state["enroll_name"]
                })
                
            elif msg_type == "clear":
                # Clear all stored faces
                stored_faces.clear()
                next_face_id = 1
                for file in glob.glob(os.path.join(FACES_DIR, "*.jpg")):
                    try:
                        os.remove(file)
                    except Exception as e:
                        print(f"[Error] Failed to remove {file}: {e}")
                with open(METADATA_FILE, "w") as f:
                    json.dump({}, f)
                
                print("[WS] Identity Vault purged.")
                await websocket.send_json({
                    "type": "vault_purged",
                    "enrolled": []
                })
                
            elif msg_type == "frame":
                img_b64 = data.get("image")
                if not img_b64:
                    continue
                
                # Decode image
                try:
                    frame = decode_base64_image(img_b64)
                except Exception as e:
                    print(f"[WS] Decode error: {e}")
                    continue
                
                if frame is None:
                    continue
                
                # Process image
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                faces = detector(gray)
                
                response_data = {
                    "type": "telemetry",
                    "face_detected": False,
                    "box": None,
                    "landmarks": [],
                    "ear": 0.0,
                    "blinks": session_state["total_blinks"],
                    "head_left": session_state["head_left"],
                    "head_right": session_state["head_right"],
                    "status": "SCANNING",
                    "match_name": None,
                    "confidence": 0.0
                }
                
                if len(faces) > 0:
                    face = faces[0]
                    x1, y1, x2, y2 = face.left(), face.top(), face.right(), face.bottom()
                    response_data["face_detected"] = True
                    response_data["box"] = [x1, y1, x2, y2]
                    
                    try:
                        shape = predictor(gray, face)
                        shape_np = face_utils.shape_to_np(shape)
                        
                        # Pack 68 landmarks to send to UI
                        response_data["landmarks"] = shape_np.tolist()
                        
                        # Calculate EAR for blink detection
                        left_eye = shape_np[42:48]
                        right_eye = shape_np[36:42]
                        leftEAR = eye_aspect_ratio(left_eye)
                        rightEAR = eye_aspect_ratio(right_eye)
                        ear = (leftEAR + rightEAR) / 2.0
                        response_data["ear"] = round(ear, 3)
                        
                        # Blink counting
                        if ear < 0.23:
                            session_state["blink_counter"] += 1
                        else:
                            if session_state["blink_counter"] > 0:
                                session_state["total_blinks"] += 1
                                session_state["blink_counter"] = 0
                        response_data["blinks"] = session_state["total_blinks"]
                        
                        # Head turn detection using scale-invariant nose-to-jaw ratio
                        x_nose = shape_np[30][0]
                        x_left = shape_np[0][0]
                        x_right = shape_np[16][0]
                        face_width = x_right - x_left
                        if face_width > 0:
                            ratio = (x_nose - x_left) / face_width
                            if ratio < 0.38:
                                session_state["head_left"] = True
                            elif ratio > 0.62:
                                session_state["head_right"] = True
                            
                        response_data["head_left"] = session_state["head_left"]
                        response_data["head_right"] = session_state["head_right"]
                        
                        # Check if complete liveness checklist is satisfied
                        liveness_verified = (session_state["total_blinks"] >= 1 and 
                                             session_state["head_left"] and 
                                             session_state["head_right"])
                        
                        if liveness_verified:
                            # Only run expensive face recognition/encoding when liveness is verified
                            face_locations = face_recognition.face_locations(rgb)
                            if len(face_locations) > 0:
                                encodings = face_recognition.face_encodings(rgb, face_locations)
                                current_encoding = encodings[0]
                                
                                # Enroll mode
                                if session_state["mode"] == "store":
                                    success, enrolled_name = store_new_face(
                                        current_encoding, frame, x1, y1, x2, y2, session_state["enroll_name"]
                                    )
                                    if success:
                                        response_data["status"] = f"ENROLLED: {enrolled_name}"
                                        # Send updated vault state to user
                                        vault_faces = [{"id": fid, "name": fdata["name"], "image": fdata["image_path"]} 
                                                       for fid, fdata in stored_faces.items()]
                                        await websocket.send_json({
                                            "type": "vault_update",
                                            "enrolled": vault_faces
                                        })
                                        # Reset back to verify mode automatically after successful store
                                        session_state["mode"] = "verify"
                                    else:
                                        response_data["status"] = f"EXISTS: {enrolled_name}"
                                        # Reset back to verify mode automatically after exists
                                        session_state["mode"] = "verify"
                                
                                # Verify mode
                                else:
                                    if len(stored_faces) > 0:
                                        min_distance = 1.0
                                        match_name = None
                                        
                                        for face_id, face_data in stored_faces.items():
                                            try:
                                                stored_encoding = np.array(face_data["encoding"])
                                                distance = face_recognition.face_distance([stored_encoding], current_encoding)[0]
                                                if distance < min_distance:
                                                    min_distance = distance
                                                    match_name = face_data["name"]
                                            except:
                                                continue
                                                
                                        if min_distance < 0.45:
                                            response_data["status"] = "REAL FACE"
                                            response_data["match_name"] = match_name
                                            response_data["confidence"] = round((1.0 - min_distance) * 100, 1)
                                        else:
                                            response_data["status"] = "FAKE FACE"
                                            response_data["match_name"] = "UNKNOWN"
                                        
                                        # Reset checklist counters to free CPU and allow new challenges
                                        session_state["total_blinks"] = 0
                                        session_state["blink_counter"] = 0
                                        session_state["head_left"] = False
                                        session_state["head_right"] = False
                                        session_state["initial_nose_x"] = None
                                    else:
                                        response_data["status"] = "VAULT EMPTY - ENROLL FIRST"
                            else:
                                response_data["status"] = "SCANNING"
                        else:
                            response_data["status"] = "SCANNING"
                                    
                    except Exception as e:
                        print(f"[WS] Shape prediction/matching error: {e}")
                        response_data["status"] = "PROCESSING ERROR"
                
                await websocket.send_json(response_data)
                
    except WebSocketDisconnect:
        print("[WS] Client disconnected.")
    except Exception as e:
        print(f"[WS] Connection error: {e}")

# ---------------- SERVER ENTRY ----------------
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("web_app:app", host="0.0.0.0", port=port, reload=False)
