import cv2
import dlib
import numpy as np
import face_recognition
from scipy.spatial import distance as dist
from imutils import face_utils
import os
import json
import glob
import tkinter as tk
from tkinter import ttk
import time

# ---------------- THEME COLORS ----------------
# Cyber-Guard Liveness design tokens
def hex_to_bgr(hex_color):
    """Convert hex color (#RRGGBB) to OpenCV BGR tuple."""
    value = hex_color.lstrip("#")
    return (int(value[4:6], 16), int(value[2:4], 16), int(value[0:2], 16))


THEME = {
    "surface": hex_to_bgr("#10131b"),
    "surface_container_low": hex_to_bgr("#181c23"),
    "surface_container": hex_to_bgr("#1c2027"),
    "surface_variant": hex_to_bgr("#31353d"),
    "outline_variant": hex_to_bgr("#414754"),
    "primary": hex_to_bgr("#adc7ff"),
    "primary_container": hex_to_bgr("#4a8eff"),
    "secondary_container": hex_to_bgr("#c8055b"),
    "on_surface": hex_to_bgr("#e0e2ed"),
    "on_surface_variant": hex_to_bgr("#c1c6d7"),
    "success_green": hex_to_bgr("#28c76f"),  # REAL chip
    "error_red": hex_to_bgr("#ea5455"),      # SPOOF chip
    "warning_orange": hex_to_bgr("#ef6719"),
}

TOKENS = {
    "spacing_xs": 4,
    "spacing_sm": 12,
    "spacing_md": 24,
    "spacing_xl": 80,  # safe-zone concept around viewport
    "radius_md": 12,
    "radius_lg": 16,
    "radius_xl": 24,
}

# ---------------- FILES ----------------

FACES_DIR = "stored_faces"
METADATA_FILE = os.path.join(FACES_DIR, "face_metadata.json")

# Create faces directory if not exists
if not os.path.exists(FACES_DIR):
    os.makedirs(FACES_DIR)

stored_faces = {}  # {face_id: {encoding, name, image_path}}
next_face_id = 1

# ---------------- MODE VARIABLES ----------------

MODE_STORE = "store"
MODE_VERIFY = "verify"
current_mode = MODE_VERIFY  # Default to verify mode

# ---------------- MODE FUNCTIONS ----------------

def switch_mode(new_mode):
    """Switch between store and verify modes"""
    global current_mode
    if new_mode in [MODE_STORE, MODE_VERIFY]:
        current_mode = new_mode
        print(f"\033[94mMode switched to: {new_mode.upper()}\033[0m")  # Blue text
        return True
    return False

def draw_glass_panel(canvas, x1, y1, x2, y2):
    """Draw a reusable glass-style panel."""
    panel = canvas.copy()
    roi = panel[y1:y2, x1:x2]
    blurred = cv2.GaussianBlur(roi, (0, 0), sigmaX=12, sigmaY=12)
    cv2.addWeighted(blurred, 0.75, roi, 0.25, 0, roi)
    cv2.rectangle(panel, (x1, y1), (x2, y2), THEME["surface_container"], -1)
    cv2.addWeighted(panel, 0.22, canvas, 0.78, 0, canvas)
    cv2.rectangle(canvas, (x1, y1), (x2, y2), THEME["outline_variant"], 1)

def show_opening_screen():
    """Show first opening screen with app title."""
    w, h = 1080, 640
    screen = np.zeros((h, w, 3), dtype=np.uint8)
    screen[:] = THEME["surface"]

    # Accent lines for a cyber dashboard look.
    cv2.line(screen, (32, 32), (w - 32, 32), THEME["primary_container"], 2)
    cv2.line(screen, (32, h - 32), (w - 32, h - 32), THEME["primary_container"], 2)

    draw_glass_panel(screen, 120, 120, w - 120, h - 120)

    cv2.putText(screen, "FACE LIVENESS DETECTION", (210, 300), cv2.FONT_HERSHEY_SIMPLEX, 1.25, THEME["on_surface"], 3)
    cv2.putText(screen, "Biometric anti-spoof verification console", (290, 350), cv2.FONT_HERSHEY_SIMPLEX, 0.65, THEME["on_surface_variant"], 2)
    cv2.putText(screen, "Press ENTER to continue", (390, 460), cv2.FONT_HERSHEY_SIMPLEX, 0.7, THEME["primary"], 2)

    window_name = "Liveness Detection System"
    while True:
        cv2.imshow(window_name, screen)
        key = cv2.waitKey(25) & 0xFF
        if key in (13, 10, 32):  # Enter / Return / Space
            break
        if key == 27:  # ESC
            return False

    return True

def select_mode_manually():
    """Show themed mode selection screen and return True to continue."""
    global current_mode, next_face_id, stored_faces
    w, h = 1080, 640
    window_name = "Liveness Detection System"

    current_mode = MODE_VERIFY

    def draw_action_card(canvas, x, y, card_w, card_h, title, subtitle, hotkey, border_color, active=False, button_text="SELECT"):
        """Draw dashboard-like action card."""
        card = canvas.copy()
        roi = card[y:y + card_h, x:x + card_w]
        blur = cv2.GaussianBlur(roi, (0, 0), sigmaX=10, sigmaY=10)
        cv2.addWeighted(blur, 0.72, roi, 0.28, 0, roi)
        cv2.rectangle(card, (x, y), (x + card_w, y + card_h), THEME["surface_container_low"], -1)
        cv2.addWeighted(card, 0.26, canvas, 0.74, 0, canvas)

        edge_thickness = 2 if active else 1
        edge_color = border_color if active else THEME["outline_variant"]
        cv2.rectangle(canvas, (x, y), (x + card_w, y + card_h), edge_color, edge_thickness)
        cv2.line(canvas, (x + 1, y + 1), (x + card_w - 1, y + 1), border_color, 2)
        cv2.rectangle(canvas, (x + card_w - 42, y + 12), (x + card_w - 12, y + 34), THEME["surface_variant"], -1)
        cv2.putText(canvas, hotkey, (x + card_w - 36, y + 29), cv2.FONT_HERSHEY_SIMPLEX, 0.5, THEME["on_surface_variant"], 1)
        cv2.circle(canvas, (x + 52, y + 58), 16, border_color, -1)

        cv2.putText(canvas, title, (x + 24, y + 114), cv2.FONT_HERSHEY_SIMPLEX, 0.9, THEME["on_surface"], 2)
        cv2.putText(canvas, subtitle, (x + 24, y + 146), cv2.FONT_HERSHEY_SIMPLEX, 0.55, THEME["on_surface_variant"], 1)

        button_color = border_color if active else THEME["surface_variant"]
        cv2.rectangle(canvas, (x + 24, y + card_h - 62), (x + card_w - 24, y + card_h - 18), button_color, -1)
        label = "SELECTED" if active else button_text
        cv2.putText(canvas, label, (x + 54, y + card_h - 33), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

    while True:
        screen = np.zeros((h, w, 3), dtype=np.uint8)
        screen[:] = THEME["surface"]

        # page title
        cv2.putText(screen, "SECURITY PROTOCOL v2.4", (420, 72), cv2.FONT_HERSHEY_SIMPLEX, 0.48, THEME["primary"], 1)
        cv2.putText(screen, "Biometric Console", (352, 112), cv2.FONT_HERSHEY_SIMPLEX, 1.25, THEME["on_surface"], 3)
        cv2.putText(
            screen,
            "Select high-security facial operation to proceed",
            (330, 144),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.58,
            THEME["on_surface_variant"],
            1,
        )

        # action cards (center-aligned after removing side/top/bottom sections)
        card_y = 170
        card_w = 288
        card_h = 350
        gap = 24
        start_x = (w - (card_w * 3 + gap * 2)) // 2
        draw_action_card(
            screen,
            start_x,
            card_y,
            card_w,
            card_h,
            "STORE FACE",
            "Enroll new biometric profile",
            "01",
            THEME["secondary_container"],
            current_mode == MODE_STORE,
            "INITIALIZE ENROLLMENT",
        )
        draw_action_card(
            screen,
            start_x + card_w + gap,
            card_y,
            card_w,
            card_h,
            "VERIFY FACE",
            "Authenticate against vault",
            "02",
            THEME["primary_container"],
            current_mode == MODE_VERIFY,
            "AUTHENTICATE NOW",
        )
        draw_action_card(
            screen,
            start_x + (card_w + gap) * 2,
            card_y,
            card_w,
            card_h,
            "CLEAR FACES",
            "Purge local biometric dataset",
            "03",
            THEME["error_red"],
            False,
            "PURGE DATASET",
        )

        # minimal footer instructions
        cv2.putText(
            screen,
            f"Enrolled users: {len(stored_faces)}   |   1/S Store   2/V Verify   3/C Clear   Enter Continue   Esc Exit",
            (120, h - 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.52,
            THEME["on_surface_variant"],
            1,
        )

        cv2.imshow(window_name, screen)
        key = cv2.waitKey(25) & 0xFF

        if key in (ord("1"), ord("s"), ord("S")):
            switch_mode(MODE_STORE)
            current_mode = MODE_STORE
        elif key in (ord("2"), ord("v"), ord("V")):
            switch_mode(MODE_VERIFY)
            current_mode = MODE_VERIFY
        elif key in (ord("3"), ord("c"), ord("C")):
            if stored_faces:
                stored_faces.clear()
                next_face_id = 1
                for file in glob.glob(os.path.join(FACES_DIR, "*.jpg")):
                    os.remove(file)
                with open(METADATA_FILE, "w") as f:
                    json.dump({}, f)
                print("\033[92mAll stored faces cleared from mode screen\033[0m")
            else:
                print("\033[93mNo faces to clear\033[0m")
        elif key in (13, 10):
            print(f"\033[94mStartup mode selected: {current_mode.upper()}\033[0m")
            return True
        elif key == 27:
            return False

# ---------------- BLINK DETECTION ----------------

def eye_aspect_ratio(eye):
    try:
        # Calculate vertical distances
        A = dist.euclidean(eye[1], eye[5])
        B = dist.euclidean(eye[2], eye[4])
        
        # Calculate horizontal distance
        C = dist.euclidean(eye[0], eye[3])
        
        # Eye aspect ratio
        ear = (A + B) / (2.0 * C)
        return ear
    except:
        return 0.23

# ---------------- LOAD STORED FACES ----------------

def load_stored_faces():
    """Load existing face data from storage"""
    global stored_faces, next_face_id
    
    if os.path.exists(METADATA_FILE):
        try:
            with open(METADATA_FILE, 'r') as f:
                all_faces = json.load(f)
            
            # Filter out faces whose image files don't exist
            stored_faces = {}
            for face_id, face_data in all_faces.items():
                if os.path.exists(face_data['image_path']):
                    stored_faces[face_id] = face_data
            
            # Find the next available face ID
            if stored_faces:
                next_face_id = max(int(face_id) for face_id in stored_faces.keys()) + 1
            else:
                next_face_id = 1
            
            print(f"\033[92mLoaded {len(stored_faces)} valid stored faces\033[0m")  # Green text
            return True
        except Exception as e:
            print(f"\033[91mError loading faces: {e}\033[0m")  # Red text
            stored_faces = {}
            next_face_id = 1
    return False

# ---------------- STORE NEW FACE ----------------

def store_new_face(face_encoding, face_img, x1, y1, x2, y2):
    """Store a new face with encoding and image"""
    global next_face_id, stored_faces
    
    # Check if this face is already stored
    for face_id, face_data in stored_faces.items():
        try:
            stored_encoding = np.array(face_data['encoding'])
            distance = face_recognition.face_distance([stored_encoding], face_encoding)[0]
            if distance < 0.45:
                print(f"\033[93mFace already exists: {face_data['name']}\033[0m")  # Yellow text
                return False, face_data['name']
        except:
            continue
    
    # Store new face
    face_id = str(next_face_id)
    face_name = f"Person_{next_face_id}"
    
    # Save face image
    face_img = face_img[y1:y2, x1:x2]
    image_path = f"{FACES_DIR}/face_{face_id}.jpg"
    cv2.imwrite(image_path, face_img)
    
    # Store face data
    stored_faces[face_id] = {
        'encoding': face_encoding.tolist(),
        'name': face_name,
        'image_path': image_path
    }
    
    # Save metadata
    with open(METADATA_FILE, 'w') as f:
        json.dump(stored_faces, f)
    
    next_face_id += 1
    print(f"\033[92mNew face stored: {face_name}\033[0m")  # Green text
    return True, face_name

# ---------------- THEMED CONSOLE STATUS DISPLAY ----------------

def print_status(mode, blinks, head_left, head_right, face_status, stored_faces):
    """Print themed status to console"""
    print("\n" + "\033[96m" + "="*60 + "\033[0m")  # Cyan header
    print(f"\033[94mMODE:\033[0m \033[96m{mode.upper()}\033[0m")
    print(f"\033[94mBLINKS:\033[0m \033[92m{blinks}\033[0m")
    
    head_text = "None"
    head_color = "\033[93m"  # Yellow for None
    if head_left and head_right:
        head_text = "Both"
        head_color = "\033[92m"  # Green for Both
    elif head_left:
        head_text = "Left"
        head_color = "\033[92m"  # Green for Left
    elif head_right:
        head_text = "Right"
        head_color = "\033[92m"  # Green for Right
    
    print(f"\033[94mHEAD MOVEMENT:\033[0m {head_color}{head_text}\033[0m")
    
    # Color code face status
    if "REAL FACE" in face_status:
        status_color = "\033[92m"  # Green for REAL FACE
    elif "FAKE FACE" in face_status:
        status_color = "\033[91m"  # Red for FAKE FACE
    else:
        status_color = "\033[93m"  # Yellow for other status
    
    print(f"\033[94mFACE STATUS:\033[0m {status_color}{face_status}\033[0m")
    
    # Color code liveness
    blink_status = "PASS" if blinks >= 1 else "FAIL"
    head_status = "PASS" if (head_left or head_right) else "FAIL"
    blink_color = "\033[92m" if blinks >= 1 else "\033[91m"
    head_color_liveness = "\033[92m" if (head_left or head_right) else "\033[91m"
    
    print(f"\033[94mLIVENESS:\033[0m {blink_color}Blink: {blink_status}\033[0m {head_color_liveness}Head: {head_status}\033[0m")
    print(f"\033[94mSTORED FACES:\033[0m \033[96m{stored_faces}\033[0m")
    print("\033[96m" + "="*60 + "\033[0m")

# ---------------- THEMED CAMERA OVERLAY ----------------

def draw_themed_overlay(frame, mode, blinks, head_left, head_right, face_status):
    """Draw full cyber dashboard overlay inspired by reference."""
    out_w, out_h = 1280, 720
    dashboard = np.zeros((out_h, out_w, 3), dtype=np.uint8)
    dashboard[:] = THEME["surface"]

    # Top navigation
    cv2.rectangle(dashboard, (0, 0), (out_w, 52), THEME["surface_container_low"], -1)
    cv2.putText(dashboard, "Live Stream", (430, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.47, THEME["on_surface"], 1)
    cv2.putText(dashboard, "Analytics", (535, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.47, THEME["on_surface_variant"], 1)
    cv2.putText(dashboard, "Identity Vault", (640, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.47, THEME["on_surface_variant"], 1)
    cv2.putText(dashboard, "System Logs", (780, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.47, THEME["on_surface_variant"], 1)

    # Status pill
    pill_x1, pill_y1, pill_x2, pill_y2 = 525, 70, 980, 106
    cv2.rectangle(dashboard, (pill_x1, pill_y1), (pill_x2, pill_y2), THEME["surface_container"], -1)
    cv2.rectangle(dashboard, (pill_x1, pill_y1), (pill_x2, pill_y2), THEME["outline_variant"], 1)
    if mode == MODE_STORE:
        label_text = "FACES STORED" if "stored" in face_status.lower() else "STORE MODE ACTIVE"
        label_color = THEME["success_green"] if "stored" in face_status.lower() else THEME["warning_orange"]
    else:
        label_text = "VERIFY MODE ACTIVE"
        label_color = THEME["primary_container"]
    cv2.circle(dashboard, (575, 88), 7, label_color, -1)
    cv2.putText(dashboard, label_text, (595, 94), cv2.FONT_HERSHEY_SIMPLEX, 0.62, label_color, 2)
    cv2.putText(dashboard, f"LIVENESS CONFIRMED: {99.8 if blinks > 0 else 0:.1f}%", (760, 94), cv2.FONT_HERSHEY_SIMPLEX, 0.5, THEME["on_surface_variant"], 1)

    # Circular viewport
    center = (640, 340)
    radius = 220
    cam_square = cv2.resize(frame, (radius * 2, radius * 2))
    cam_mask = np.zeros((radius * 2, radius * 2), dtype=np.uint8)
    cv2.circle(cam_mask, (radius, radius), radius - 4, 255, -1)
    roi = dashboard[center[1] - radius:center[1] + radius, center[0] - radius:center[0] + radius]
    bg = cv2.bitwise_and(roi, roi, mask=cv2.bitwise_not(cam_mask))
    fg = cv2.bitwise_and(cam_square, cam_square, mask=cam_mask)
    dashboard[center[1] - radius:center[1] + radius, center[0] - radius:center[0] + radius] = cv2.add(bg, fg)
    cv2.circle(dashboard, center, radius, THEME["primary_container"], 2)
    cv2.circle(dashboard, center, radius - 32, THEME["outline_variant"], 1)
    cv2.circle(dashboard, center, radius - 52, THEME["outline_variant"], 1)

    # Scan brackets
    br = THEME["primary"]
    cv2.line(dashboard, (315, 120), (365, 120), br, 2); cv2.line(dashboard, (315, 120), (315, 170), br, 2)
    cv2.line(dashboard, (965, 120), (915, 120), br, 2); cv2.line(dashboard, (965, 120), (965, 170), br, 2)
    cv2.line(dashboard, (315, 560), (365, 560), br, 2); cv2.line(dashboard, (315, 560), (315, 510), br, 2)
    cv2.line(dashboard, (965, 560), (915, 560), br, 2); cv2.line(dashboard, (965, 560), (965, 510), br, 2)

    # Bottom metric cards
    card_y = 580
    for i, x in enumerate([170, 510, 850]):
        cv2.rectangle(dashboard, (x, card_y), (x + 260, card_y + 120), THEME["surface_container"], -1)
        cv2.rectangle(dashboard, (x, card_y), (x + 260, card_y + 120), THEME["outline_variant"], 1)
        if i == 0:
            cv2.putText(dashboard, "BLINK COUNT", (x + 24, card_y + 34), cv2.FONT_HERSHEY_SIMPLEX, 0.5, THEME["on_surface_variant"], 1)
            cv2.putText(dashboard, str(blinks), (x + 24, card_y + 78), cv2.FONT_HERSHEY_SIMPLEX, 1.3, THEME["primary"], 3)
        elif i == 1:
            cv2.putText(dashboard, "MOVEMENT TRACKING", (x + 16, card_y + 34), cv2.FONT_HERSHEY_SIMPLEX, 0.45, THEME["on_surface_variant"], 1)
            cv2.putText(dashboard, "Head Movement Right", (x + 16, card_y + 68), cv2.FONT_HERSHEY_SIMPLEX, 0.67, THEME["on_surface"], 2)
            val_color = THEME["success_green"] if head_right else THEME["error_red"]
            cv2.rectangle(dashboard, (x + 170, card_y + 48), (x + 232, card_y + 80), val_color, -1)
            cv2.putText(dashboard, "TRUE" if head_right else "FALSE", (x + 176, card_y + 70), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
        else:
            cv2.putText(dashboard, "MOVEMENT TRACKING", (x + 16, card_y + 34), cv2.FONT_HERSHEY_SIMPLEX, 0.45, THEME["on_surface_variant"], 1)
            cv2.putText(dashboard, "Head Movement Left", (x + 16, card_y + 68), cv2.FONT_HERSHEY_SIMPLEX, 0.67, THEME["on_surface"], 2)
            val_color = THEME["success_green"] if head_left else THEME["error_red"]
            cv2.rectangle(dashboard, (x + 170, card_y + 48), (x + 232, card_y + 80), val_color, -1)
            cv2.putText(dashboard, "TRUE" if head_left else "FALSE", (x + 176, card_y + 70), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)

    # Footer
    cv2.rectangle(dashboard, (0, out_h - 22), (out_w, out_h), THEME["surface_container_low"], -1)
    cv2.putText(dashboard, "PRIVACY POLICY    TERMINAL ACCESS    HEALTH STATUS", (24, out_h - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.41, THEME["on_surface_variant"], 1)
    cv2.putText(dashboard, "CYBER-GUARD", (440, out_h - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.62, THEME["on_surface"], 2)
    cv2.putText(dashboard, "ENCRYPTED UPLINK ACTIVE", (1030, out_h - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, THEME["success_green"], 1)

    return dashboard

# ---------------- MAIN ----------------

def main():
    global next_face_id

    # Load stored faces
    load_stored_faces()
    
    # Opening splash and mode selection screens
    if not show_opening_screen():
        cv2.destroyAllWindows()
        return
    if not select_mode_manually():
        cv2.destroyAllWindows()
        return

    while True:
        print("\n" + "\033[96m" + "="*60 + "\033[0m")
        print("\033[96m    FACE LIVENESS DETECTION STATUS CONSOLE\033[0m")
        print("\033[96m" + "="*60 + "\033[0m")

        # ---------------- CAMERA ----------------
        cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_FPS, 30)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        if not cap.isOpened():
            print("\033[91mCamera not working\033[0m")
            return

        print("\033[92mCamera started\033[0m")
        print("\033[94mLoading models...\033[0m")
        detector = dlib.get_frontal_face_detector()
        predictor = dlib.shape_predictor("shape_predictor_68_face_landmarks.dat")

        total_blinks = 0
        blink_counter = 0
        head_left = False
        head_right = False
        initial_nose_x = None
        frame_count = 0
        status_update_counter = 0
        current_face_status = "SCANNING"
        go_home = False
        latched_real_face = False
        latched_fake_face = False

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = detector(gray)
            frame_count += 1

            if frame_count % 3 != 0:
                frame = draw_themed_overlay(frame, current_mode, total_blinks, head_left, head_right, current_face_status)
                cv2.imshow("Liveness Detection System", frame)
                key = cv2.waitKey(1) & 0xFF

                if key == 27:
                    break
                elif key in (8, 127):  # Backspace
                    go_home = True
                    break
                elif key in (ord("s"), ord("S")):
                    switch_mode(MODE_STORE)
                    latched_real_face = False
                    latched_fake_face = False
                elif key in (ord("v"), ord("V")):
                    switch_mode(MODE_VERIFY)
                    latched_real_face = False
                    latched_fake_face = False
                elif key in (ord("c"), ord("C")):
                    if stored_faces:
                        stored_faces.clear()
                        next_face_id = 1
                        for file in glob.glob(os.path.join(FACES_DIR, "*.jpg")):
                            os.remove(file)
                        with open(METADATA_FILE, "w") as f:
                            json.dump({}, f)
                        print("\033[92mAll stored faces cleared\033[0m")
                    else:
                        print("\033[93mNo faces to clear\033[0m")
                continue

            for face in faces:
                x1 = face.left()
                y1 = face.top()
                x2 = face.right()
                y2 = face.bottom()

                cv2.rectangle(frame, (x1, y1), (x2, y2), THEME["primary_container"], 2)
                cv2.rectangle(frame, (x1 - 2, y1 - 2), (x2 + 2, y2 + 2), THEME["primary"], 1)

                try:
                    shape = predictor(gray, face)
                    shape = face_utils.shape_to_np(shape)
                    left_eye = shape[42:48]
                    right_eye = shape[36:42]
                    leftEAR = eye_aspect_ratio(left_eye)
                    rightEAR = eye_aspect_ratio(right_eye)
                    ear = (leftEAR + rightEAR) / 2.0

                    if ear < 0.23:
                        blink_counter += 1
                    else:
                        if blink_counter > 0:
                            total_blinks += 1
                            blink_counter = 0
                            print(f"\033[96mBlink detected! Total blinks: {total_blinks}\033[0m")

                    x_nose = shape[30][0]
                    x_left = shape[0][0]
                    x_right = shape[16][0]
                    face_width = x_right - x_left
                    if face_width > 0:
                        ratio = (x_nose - x_left) / face_width
                        if ratio < 0.38:
                            head_left = True
                            print("\033[96mHead movement: LEFT detected\033[0m")
                        elif ratio > 0.62:
                            head_right = True
                            print("\033[96mHead movement: RIGHT detected\033[0m")

                    # Clear latches if a new liveness challenge begins
                    if total_blinks > 0 or head_left or head_right:
                        latched_real_face = False
                        latched_fake_face = False

                    liveness_verified = (total_blinks >= 1 and head_left and head_right)

                    if liveness_verified:
                        face_locations = face_recognition.face_locations(rgb)
                        if len(face_locations) > 0:
                            encodings = face_recognition.face_encodings(rgb, face_locations)
                            current_encoding = encodings[0]

                            if current_mode == MODE_STORE:
                                try:
                                    success, name = store_new_face(current_encoding, frame, x1, y1, x2, y2)
                                    if success:
                                        print(f"\033[92mFace stored successfully: {name}\033[0m")
                                    display_status = "FACES STORED"
                                except Exception as e:
                                    print(f"\033[91mFace storage error: {e}\033[0m")
                                    display_status = "PROCESSING ERROR"
                            else:
                                if len(stored_faces) > 0:
                                    min_distance = float("inf")
                                    for face_id, face_data in stored_faces.items():
                                        try:
                                            stored_encoding = np.array(face_data["encoding"])
                                            distance = face_recognition.face_distance([stored_encoding], current_encoding)[0]
                                            if distance < min_distance:
                                                min_distance = distance
                                        except:
                                            continue

                                    if min_distance < 0.45:
                                        display_status = "REAL FACE"
                                        latched_real_face = True
                                        latched_fake_face = False
                                    else:
                                        display_status = "FAKE FACE"
                                        latched_real_face = False
                                        latched_fake_face = True
                                else:
                                    display_status = "NO FACES STORED"
                                    latched_real_face = False
                                    latched_fake_face = False

                                # Reset liveness check on verification result to prevent server lag and allow re-trying
                                total_blinks = 0
                                blink_counter = 0
                                head_left = False
                                head_right = False
                        else:
                            display_status = "SCANNING"
                    else:
                        if current_mode == MODE_STORE:
                            display_status = "SCANNING"
                        else:
                            if latched_real_face:
                                display_status = "REAL FACE"
                            elif latched_fake_face:
                                display_status = "FAKE FACE"
                            else:
                                display_status = "SCANNING"

                    if display_status == "REAL FACE":
                        cv2.putText(frame, "REAL FACE", (150, 100), cv2.FONT_HERSHEY_SIMPLEX, 1, THEME["success_green"], 3)
                    elif display_status == "FAKE FACE":
                        cv2.putText(frame, "FAKE FACE", (200, 100), cv2.FONT_HERSHEY_SIMPLEX, 1, THEME["error_red"], 3)
                    elif display_status == "SCANNING":
                        cv2.putText(frame, "SCANNING", (200, 100), cv2.FONT_HERSHEY_SIMPLEX, 1, THEME["warning_orange"], 3)
                    elif display_status == "NO FACES STORED":
                        cv2.putText(frame, "NO FACES STORED", (100, 100), cv2.FONT_HERSHEY_SIMPLEX, 1, THEME["warning_orange"], 3)

                    current_face_status = display_status
                    status_update_counter += 1
                    if status_update_counter % 30 == 0:
                        print_status(current_mode, total_blinks, head_left, head_right, display_status, len(stored_faces))
                except Exception as e:
                    print(f"\033[91mProcessing error: {e}\033[0m")

            frame = draw_themed_overlay(frame, current_mode, total_blinks, head_left, head_right, current_face_status)
            h, w = frame.shape[:2]
            cv2.rectangle(frame, (0, h - 42), (w, h), THEME["surface_container_low"], -1)
            cv2.putText(frame, "S=Store | V=Verify | C=Clear | BACKSPACE=Home | ESC=Exit", (10, h - 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, THEME["on_surface_variant"], 1)
            cv2.imshow("Liveness Detection System", frame)

            key = cv2.waitKey(1) & 0xFF
            if key == 27:
                break
            elif key in (8, 127):  # Backspace
                go_home = True
                break
            elif key in (ord("s"), ord("S")):
                switch_mode(MODE_STORE)
                latched_real_face = False
                latched_fake_face = False
            elif key in (ord("v"), ord("V")):
                switch_mode(MODE_VERIFY)
                latched_real_face = False
                latched_fake_face = False
            elif key in (ord("c"), ord("C")):
                if stored_faces:
                    stored_faces.clear()
                    next_face_id = 1
                    for file in glob.glob(os.path.join(FACES_DIR, "*.jpg")):
                        os.remove(file)
                    with open(METADATA_FILE, "w") as f:
                        json.dump({}, f)
                    print("\033[92mAll stored faces cleared\033[0m")
                else:
                    print("\033[93mNo faces to clear\033[0m")

        cap.release()
        cv2.destroyAllWindows()

        if go_home:
            if not select_mode_manually():
                cv2.destroyAllWindows()
                return
            continue

        break

if __name__ == "__main__":
    main()
