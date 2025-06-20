# WhisperX Telegram Bot

**Repository:** [https://github.com/jagajaga/whisper-tg](https://github.com/jagajaga/whisper-tg)

## Overview
A Telegram bot for transcribing audio files using WhisperX (with speaker diarization and language detection), running on a remote RunPod server. Supports multiple users, authentication, and parallel sessions.

---

## Features
- Audio transcription via WhisperX (remote RunPod pod)
- Speaker diarization: specify min/max speakers
- Automatic language detection (or specify language code)
- Telegram bot interface (Telethon)
- Parallel user sessions and multi-tasking
- Authentication: password-protected access
- Active job tracking and pod auto-pause
- Transcript delivery as text and file

---

## Prerequisites
- Python 3.8+
- Telegram account (for bot and users)
- RunPod account with a deployed WhisperX pod
- HuggingFace token (for WhisperX)
- All required Python packages (see below)

---

## Installation
1. **Clone the repository:**
   ```bash
   git clone https://github.com/jagajaga/whisper-tg.git
   cd whisper-tg
   ```
2. **Install dependencies:**
   ```bash
   pip install telethon whisper requests
   ```
3. **Set up configuration:**
   - Copy the provided `config.py` template and fill in your private parameters:
     - `API_ID`, `API_HASH`: Telegram API credentials
     - `SESSION_NAME`: Session name for Telethon
     - `WHISPERX_MODEL`: WhisperX model name (e.g., "large-v3")
     - `HF_TOKEN`: HuggingFace token
     - `BOT_TOKEN`: Telegram bot token
     - `RUNPOD_API_KEY`, `RUNPOD_POD_ID`, `RUNPOD_ENDPOINT_URL`: RunPod credentials and endpoint
     - `BOT_PASSWORD`: Password for bot authentication (default: 'thisisthebestbot')
4. **(Optional) Add `config.py` to `.gitignore`** to avoid leaking secrets.

---

## Configuration (`config.py`)
Example:
```python
API_ID = 12345678
API_HASH = 'your_telegram_api_hash'
SESSION_NAME = 'whisperx-client'
WHISPERX_MODEL = 'large-v3'
HF_TOKEN = 'your_hf_token'
BOT_TOKEN = 'your_telegram_bot_token'
RUNPOD_API_KEY = 'your_runpod_api_key'
RUNPOD_POD_ID = 'your_runpod_pod_id'
RUNPOD_ENDPOINT_URL = 'https://<your-pod-id>-8000.proxy.runpod.net/'
BOT_PASSWORD = 'password'
```

---

## Usage

### 1. Start the Bot
```bash
python wb.py
```
The bot will connect to Telegram and wait for messages.

### 2. Authenticate
- The first time you message the bot, you must enter the password set in `config.py` (`BOT_PASSWORD`).
- After authentication, you can use the bot's features.

### 3. Add a Transcription Task
- To start a new task, send a message in one of the following formats:
  - `add <min speakers> <max speakers> <language code>`
  - `add <min speakers> <language code>`
  - `add <min speakers>`
- Examples:
  - `add 2 3 en` (2-3 speakers, English)
  - `add 2 en` (2 speakers, English)
  - `add 2` (2 speakers, language auto-detected)

### 4. Upload Audio File
- After sending the `add ...` command, upload your audio file as a Telegram attachment.
- The bot will:
  - Download the file
  - Detect language (if not specified)
  - Ask for confirmation or correction of the detected language

### 5. Confirm Language
- If language was auto-detected, reply with:
  - `yes` to accept
  - Or type the correct language code (e.g., `en`, `ru`)

### 6. Transcription
- The bot will process your file, send status updates, and deliver the transcript as:
  - Text (in chunks if long)
  - A `.txt` file attachment

### 7. Ready for Next Task
- After completion, you can start a new task by sending another `add ...` command.

---

## File Structure
- `wb.py` — Main bot script
- `config.py` — Private configuration (not tracked in git)
- `files/` — Stores uploaded audio and transcript files
- `active_jobs.txt` — Tracks number of active jobs (auto-managed)
- `users.txt` — Tracks authenticated users (auto-managed)

---

## Troubleshooting
- If the bot does not respond, check your API keys and tokens.
- Ensure your RunPod pod is deployed and reachable.
- Check logs printed to the console for errors.

---

## Server Side (Remote WhisperX Server)

The bot requires a remote WhisperX server with GPU support. You can deploy this using the provided `remote_whisperx_server.py` and `Dockerfile`.

### Using the Prebuilt Docker Image

You can use the prebuilt image from Docker Hub:
```bash
docker pull docker.io/jagajaga/whisperx-bot:latest
docker run --gpus all -p 8000:8000 -e HF_TOKEN=your_hf_token -e WHISPERX_MODEL=large-v3 -v /tmp/files:/tmp/files docker.io/jagajaga/whisperx-bot:latest
```
- Replace `your_hf_token` with your HuggingFace token.
- All other instructions remain the same as below.

---

### Running the WhisperX Server with Docker

1. **Build the Docker image:**
   ```bash
   docker build -t whisperx-server .
   ```
2. **Run the container (with GPU support):**
   ```bash
   docker run --gpus all -p 8000:8000 -e HF_TOKEN=your_hf_token -e WHISPERX_MODEL=large-v3 -v /tmp/files:/tmp/files whisperx-server
   ```
   - Replace `your_hf_token` with your HuggingFace token.
   - You can change the model or files directory as needed.
   - The server will listen on port 8000 by default.

3. **Environment Variables:**
   - `HF_TOKEN`: Your HuggingFace token (required)
   - `WHISPERX_MODEL`: WhisperX model name (default: `large-v3`)
   - `FILES_DIR`: Directory for storing files (default: `/tmp/files`)

4. **Endpoints:**
   - `POST /run_whisperx`: Submit an audio file for transcription
   - `GET /job_status/<job_id>`: Check job status
   - `GET /get_transcript/<job_id>`: Download transcript

### Manual (Non-Docker) Server Start
If you have a GPU machine with Python and dependencies installed:
```bash
pip install flask whisperx pytorch-lightning
python remote_whisperx_server.py
```

---

## License
This project is for personal/research use. Use responsibly and do not share private credentials.
