# Use Python 3.10 slim as base
FROM python:3.10-slim

# Install system dependencies needed for dlib, OpenCV, and face_recognition
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    libopenblas-dev \
    liblapack-dev \
    libx11-dev \
    libgtk-3-dev \
    libboost-python-dev \
    libboost-thread-dev \
    wget \
    curl \
    bzip2 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for layer caching
COPY requirements.txt .

# Install Python dependencies
# Use headless opencv (no display needed on server)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
        numpy \
        scipy \
        imutils \
        cmake \
        dlib \
        face-recognition \
        opencv-python-headless \
        fastapi \
        "uvicorn[standard]" \
        websockets \
        python-multipart

# Download the shape predictor model at build time
RUN wget -q "https://github.com/italojs/facial-landmarks-recognition/raw/master/shape_predictor_68_face_landmarks.dat" \
    -O shape_predictor_68_face_landmarks.dat || \
    wget -q "https://huggingface.co/spaces/asdasdasdasd/Face-forgery-detection/resolve/main/shape_predictor_68_face_landmarks.dat" \
    -O shape_predictor_68_face_landmarks.dat

# Copy the rest of the project
COPY . .

# Create stored_faces directory and ensure metadata file exists
RUN mkdir -p stored_faces && \
    if [ ! -f stored_faces/face_metadata.json ]; then echo '{}' > stored_faces/face_metadata.json; fi

# Expose port
EXPOSE 8000

# Start the FastAPI server
CMD ["uvicorn", "web_app:app", "--host", "0.0.0.0", "--port", "8000"]
