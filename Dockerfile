# Use a larger base image with full build tools
FROM python:3.9-bullseye

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install ALL required system libraries including full cmake and boost
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    cmake-data \
    pkg-config \
    libopenblas-dev \
    liblapack-dev \
    libatlas-base-dev \
    libboost-all-dev \
    libx11-dev \
    libgtk2.0-dev \
    libgtk-3-dev \
    python3-dev \
    wget \
    bzip2 \
    git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Upgrade pip and install build tools first
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Install numpy first - dlib needs it
RUN pip install --no-cache-dir "numpy==1.24.4"

# Install dlib separately with extra time allowed
# Using --no-build-isolation helps with cmake detection
RUN pip install --no-cache-dir --verbose "dlib==19.24.1"

# Install remaining packages
RUN pip install --no-cache-dir \
    "scipy==1.11.4" \
    "imutils==0.5.4" \
    "face-recognition==1.3.0" \
    "opencv-python-headless==4.8.1.78" \
    "fastapi==0.104.1" \
    "uvicorn[standard]==0.24.0" \
    "websockets==12.0" \
    "python-multipart==0.0.6"

# Download shape predictor model from official dlib source
RUN wget -q "http://dlib.net/files/shape_predictor_68_face_landmarks.dat.bz2" \
    -O /tmp/sp.dat.bz2 \
    && bunzip2 /tmp/sp.dat.bz2 \
    && mv /tmp/sp.dat shape_predictor_68_face_landmarks.dat \
    && echo "Model ready: $(du -sh shape_predictor_68_face_landmarks.dat)"

# Copy project files
COPY . .

# Ensure stored_faces dir exists with empty metadata
RUN mkdir -p stored_faces \
    && [ -f stored_faces/face_metadata.json ] || echo '{}' > stored_faces/face_metadata.json

EXPOSE 8000

# Use a startup script to handle PORT properly
CMD ["sh", "-c", "uvicorn web_app:app --host 0.0.0.0 --port ${PORT:-8000}"]
