# Real-Time Face Liveness Detection & Biometric Console

A high-performance, real-time face liveness detection system designed to prevent spoofing attacks (such as photos, videos, or masks) during biometric enrollment and verification. The system features a modern cyber-themed UI dashboard built with dynamic telemetry visualizations.

It supports two modes of operation:
1. **Web Console** (`web_app.py`): A browser-based dashboard running on FastAPI and WebSockets for low-latency frame analysis.
2. **Desktop Console** (`liveness_detection_themed.py`): An OpenCV-based desktop application with Tkinter bindings and a custom HUD.

---

## 🛡️ Liveness Detection Checklist
To verify that a face is "real" and active, the system enforces a dynamic security checklist:
- [ ] **Blink Action**: Verifies at least one eye blink by tracking the Eye Aspect Ratio (EAR).
- [ ] **Left Head Turn**: Confirms leftward yaw movement by calculating the nose-to-jaw relative distance.
- [ ] **Right Head Turn**: Confirms rightward yaw movement.

The user must successfully perform these actions before they can enroll a new identity or verify their profile against the database.

---

## 🚀 How to Run Locally

### Prerequisites
1. **Python**: Ensure you have Python 3.8 to 3.11 installed.
2. **Pre-trained Landmark Predictor**: 
   - Download the 68 face landmark predictor file: [shape_predictor_68_face_landmarks.dat](https://github.com/italojs/facial-landmarks-recognition/raw/master/shape_predictor_68_face_landmarks.dat)
   - Place `shape_predictor_68_face_landmarks.dat` directly in the project root directory.

### Installation
Open your terminal in the project directory and run:
```bash
pip install -r requirements.txt
```

> **Note for Windows users**: Installing `dlib` requires Visual Studio with C++ CMake build tools installed. If you encounter issues installing `dlib`, you can download a pre-built wheel (.whl) matching your Python version.

### 🌐 Running the Web App (FastAPI)
The web app is optimized for clean styling, responsive layouts, and interactive audio feedback.
1. Run the FastAPI server:
   ```bash
   python web_app.py
   ```
2. Open your web browser and navigate to:
   ```
   http://127.0.0.1:8000
   ```
3. Allow camera access, select your action (Enroll or Verify), and follow the HUD challenge prompts.

### 🖥️ Running the Desktop App (OpenCV)
For the standalone desktop version:
1. Run the script:
   ```bash
   python liveness_detection_themed.py
   ```
2. Press **Enter** on the splash screen.
3. Select your mode (1/S for Store, 2/V for Verify, 3/C for Clear) and follow the instructions in the window.

---

## ☁️ Deployment & Vercel Compatibility Details

### Why Vercel shows `404: NOT_FOUND` or fails to build
When you push to GitHub, Vercel may attempt to auto-deploy your repository. However, Vercel is **not compatible** with this project because:
1. **No Root `index.html`**: The static files are contained inside the `static/` directory, so Vercel cannot find an entry page at the root route `/`.
2. **WebSocket Limitations**: The web app relies on persistent WebSocket connections (`ws://`) for streaming video frames to the backend. Vercel Serverless Functions are stateless, run with quick timeouts, and **do not support WebSockets**.
3. **Heavy Python Libraries**: Libraries like `dlib` and `face_recognition` compile large C++ codebases during installation. Vercel's build environment lacks the necessary compilers (like CMake) and has strict size/time constraints that block these packages.

### How to host this application on the cloud
To deploy this project to a live URL, use containerized hosting platforms that support Docker, long-running Python processes, and WebSockets:
* **Railway**
* **Render**
* **Fly.io**
* **AWS App Runner / ECS**

A standard `Dockerfile` containing `cmake`, `g++`, and python dependencies is required to build `dlib` successfully in those environments.
