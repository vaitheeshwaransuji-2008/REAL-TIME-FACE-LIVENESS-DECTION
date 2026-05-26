# Use a full Python image (not slim) - has gcc/cmake pre-available
FROM python:3.10-bullseye

# Prevent interactive prompts during apt installs
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install ALL system dependencies in one layer
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    git \
    wget \
    curl \
    libopenblas-dev \
    liblapack-dev \
    libx11-dev \
    libatlas-base-dev \
    libboost-all-dev \
    python3-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Step 1: Install numpy first (dlib needs it at build time)
RUN pip install --no-cache-dir --upgrade pip setuptools wheel
RUN pip install --no-cache-dir numpy==1.24.4

# Step 2: Install dlib from source (no pre-built wheel available for 3.10)
RUN pip install --no-cache-dir dlib==19.24.2

# Step 3: Install face_recognition and the rest
RUN pip install --no-cache-dir \
    scipy==1.11.4 \
    imutils==0.5.4 \
    face-recognition==1.3.0 \
    opencv-python-headless==4.8.1.78 \
    fastapi==0.104.1 \
    "uvicorn[standard]==0.24.0" \
    websockets==12.0 \
    python-multipart==0.0.6

# Step 4: Download the shape predictor model (bz2 compressed, ~100MB)
RUN wget -q \
    "http://dlib.net/files/shape_predictor_68_face_landmarks.dat.bz2" \
    -O /tmp/shape_predictor.dat.bz2 \
    && bunzip2 /tmp/shape_predictor.dat.bz2 \
    && mv /tmp/shape_predictor.dat shape_predictor_68_face_landmarks.dat \
    && echo "Model downloaded successfully"

# Step 5: Copy project files
COPY . .

# Ensure stored_faces dir and metadata exist
RUN mkdir -p stored_faces \
    && [ -f stored_faces/face_metadata.json ] || echo '{}' > stored_faces/face_metadata.json

EXPOSE 8000

# Railway injects $PORT dynamically — use shell form so the variable is expanded
CMD uvicorn web_app:app --host 0.0.0.0 --port ${PORT:-8000}
