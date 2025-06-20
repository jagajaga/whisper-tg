
FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04
WORKDIR /app

RUN apt-get update && \
    apt-get install -y python3 python3-pip ffmpeg git && \
    rm -rf /var/lib/apt/lists/*

RUN python3 -m pip install --upgrade pip
RUN pip3 install flask whisperx

RUN python3 -m pip install pytorch-lightning && \
    python3 -m pytorch_lightning.utilities.upgrade_checkpoint || true

COPY remote_whisperx_server.py .

RUN mkdir -p /tmp/files
ENV FILES_DIR=/tmp/files
EXPOSE 8000
CMD ["python3", "remote_whisperx_server.py"]
