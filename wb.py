import os
import asyncio
import requests  
from datetime import datetime
from telethon import TelegramClient, events
import whisper  
import uuid
import time

from config import (
    API_ID,
    API_HASH,
    SESSION_NAME,
    HF_TOKEN,
    RUNPOD_API_KEY,
    RUNPOD_POD_ID,
    RUNPOD_ENDPOINT_URL,
    BOT_PASSWORD,
)
FILES_DIR = os.path.abspath("files")
os.makedirs(FILES_DIR, exist_ok=True)

defaultdict = dict 
user_states = {} 
user_tasks = {} 
latest_session_id = {} 
active_jobs_lock = None  
ACTIVE_JOBS_FILE = os.path.join(FILES_DIR, "active_jobs.txt")
USERS_FILE = os.path.join(FILES_DIR, "users.txt")

def log(msg):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}")

def detect_language(audio_path):
    """
    Detect language of an audio file using OpenAI Whisper.
    """
    model = whisper.load_model("tiny")  
    result = model.transcribe(audio_path, task="transcribe", language=None, fp16=False)
    return result.get("language", "unknown")

class RunPodAPI:
    def __init__(self, api_key, pod_id, endpoint_url):
        self.api_key = api_key
        self.pod_id = pod_id
        self.endpoint_url = endpoint_url
        self.base_url = "https://api.runpod.io/graphql"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
    def get_server_url(self):
        return self.endpoint_url.rstrip("/") + "/run_whisperx"
    def get_pod_status(self):
        url = f"https://rest.runpod.io/v1/pods/{self.pod_id}"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        resp = requests.get(url, headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("desiredStatus", None)
        return None
    def start_pod(self):
        url = f"https://rest.runpod.io/v1/pods/{self.pod_id}/start"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        resp = requests.post(url, headers=headers)
        print(f"Starting pod {self.pod_id}, response: {resp.status_code} {resp.text}")
        if resp.status_code == 200:
            data = resp.json()
            return data.get("status", None)
        return None
    def pause_pod(self):
        url = f"https://rest.runpod.io/v1/pods/{self.pod_id}/stop"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        resp = requests.post(url, headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("status", None)
        return None

runpod_api = RunPodAPI(RUNPOD_API_KEY, RUNPOD_POD_ID, RUNPOD_ENDPOINT_URL)

def read_active_jobs() -> int:
    try:
        with open(ACTIVE_JOBS_FILE, "r") as f:
            return int(f.read().strip())
    except Exception:
        return 0

def write_active_jobs(value: int):
    try:
        with open(ACTIVE_JOBS_FILE, "w") as f:
            f.write(str(value))
    except Exception as e:
        log(f"[active_jobs] File write error: {e}")

try:
    with open(ACTIVE_JOBS_FILE, "w") as f:
        f.write("0")
except Exception:
    pass

def is_user_authenticated(user_id: int) -> bool:
    try:
        if not os.path.exists(USERS_FILE):
            return False
        with open(USERS_FILE, "r") as f:
            users = set(line.strip() for line in f if line.strip())
        return str(user_id) in users
    except Exception:
        return False

def add_authenticated_user(user_id: int):
    try:
        with open(USERS_FILE, "a") as f:
            f.write(f"{user_id}\n")
    except Exception as e:
        log(f"[users.txt] File write error: {e}")

async def main():
    global active_jobs_lock
    active_jobs_lock = asyncio.Lock()
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    @client.on(events.NewMessage())
    async def handler(event):
        user_id = event.sender_id
        
        if not is_user_authenticated(user_id):
            if event.text and event.text.strip() == BOT_PASSWORD:
                add_authenticated_user(user_id)
                await event.reply(
                    "✅ Password accepted! You are now authenticated. Please start with: add <min speakers> <max speakers (optional)> <language code (optional)>"
                )
                return
            else:
                await event.reply("🔒 Please enter the password to use this bot.")
                return
        if user_id not in user_tasks:
            user_tasks[user_id] = []
        
        session_id = None
        
        if event.text and event.text.strip().lower().startswith("add"):
            session_id = str(uuid.uuid4())
            latest_session_id[user_id] = session_id
        
        elif event.media and user_id in latest_session_id:
            session_id = latest_session_id[user_id]
            del latest_session_id[user_id]  
        else:
            
            session_id = str(uuid.uuid4())
        async def process_task(event_copy, session_id):
            try:
                log("=" * 60)
                log(f"Current working directory: {os.getcwd()}")
                log(f"Received message from user {user_id}. Message ID: {event.id}, Text: {event.text!r}, Media: {bool(event.media)}")
                log(f"Current state for user {user_id}, session {session_id}: {user_states.get((user_id, session_id), {})}")
                state = user_states.get((user_id, session_id), {})
                
                if not state and not event_copy.media:
                    
                    parts = event_copy.text.strip().split()
                    if len(parts) >= 2 and parts[0].lower() == "add":
                        try:
                            min_speakers = int(parts[1])
                            if len(parts) > 2 and parts[2].isdigit():
                                max_speakers = int(parts[2])
                                language = parts[3].lower() if len(parts) > 3 else None
                            else:
                                max_speakers = min_speakers
                                language = parts[2].lower() if len(parts) > 2 else None
                            user_states[(user_id, session_id)] = {
                                "step": "await_file",
                                "min_speakers": min_speakers,
                                "max_speakers": max_speakers,
                                "language": language,
                            }
                            if language:
                                await event_copy.reply(
                                    f"Now upload your audio file.\nSpeakers: {min_speakers}-{max_speakers}\nLanguage: {language}"
                                )
                                log(f"User {user_id} set min_speakers={min_speakers}, max_speakers={max_speakers}, language={language} (session {session_id})")
                            else:
                                await event_copy.reply(
                                    f"Now upload your audio file.\nSpeakers: {min_speakers}-{max_speakers}\nLanguage will be auto-detected."
                                )
                                log(f"User {user_id} set min_speakers={min_speakers}, max_speakers={max_speakers}, language=auto (session {session_id})")
                            return
                        except Exception as e:
                            await event_copy.reply(
                                "Please use: add <min speakers> <max speakers (optional)> <language code (optional)>, e.g. 'add 2 3 en', 'add 2 en', or 'add 2'."
                            )
                            log(f"Error parsing input for user {user_id}, session {session_id}: {e}")
                            return
                    else:
                        await event_copy.reply(
                            "Please start with: add <min speakers> <max speakers (optional)> <language code (optional)>, e.g. 'add 2 3 en', 'add 2 en', or 'add 2'."
                        )
                        log(f"Asked user {user_id} for 'add <min> <max> <language>' (session {session_id}).")
                        return
                
                if state.get("step") == "await_file":
                    if not event_copy.media:
                        await event_copy.reply("Please upload your audio file.")
                        log(f"User {user_id} sent non-media when awaiting file (session {session_id}).")
                        return
                    await event_copy.reply("📥 Downloading audio file, please wait…")
                    fname = f"{user_id}_{session_id}_{int(datetime.now().timestamp())}.audio"
                    file_path = os.path.join(FILES_DIR, fname)
                    await event_copy.download_media(file_path)
                    log(f"Downloaded file for user {user_id}, session {session_id} to: {file_path}")
                    if not os.path.exists(file_path):
                        log(f"FATAL: Audio file not found at {file_path} before WhisperX runs (session {session_id}).")
                        await event_copy.reply(f"❌ FATAL: Audio file not found at {file_path}")
                        user_states[(user_id, session_id)] = {}
                        return
                    else:
                        user_states[(user_id, session_id)]["file_path"] = file_path
                        log(f"Audio file saved at {file_path}, size={os.path.getsize(file_path)} bytes (session {session_id})")
                    
                    if not state.get("language"):
                        await event_copy.reply("🔎 Detecting language, please wait…")
                        detected_lang = detect_language(file_path)
                        user_states[(user_id, session_id)]["language"] = detected_lang
                        user_states[(user_id, session_id)]["file_path"] = file_path
                        user_states[(user_id, session_id)]["step"] = "confirm_language"
                        await event_copy.reply(
                            f"🌐 Detected language: {detected_lang}\nIf this is correct, reply 'yes'. Otherwise, type the correct language code (e.g. 'en', 'ru')."
                        )
                        log(f"Detected language for user {user_id}, session {session_id}: {detected_lang}")
                        
                        state = user_states.get((user_id, session_id), {})
                        
                    if state.get("step") == "confirm_language":
                        lang = None
                        try:
                            
                            reply_event = await client.wait_event(
                                events.NewMessage(from_users=user_id), timeout=60
                            )
                            lang = reply_event.text.strip().lower()
                        except asyncio.TimeoutError:
                            
                            lang = "yes"
                            await event_copy.reply("⏳ No language reply in 1 minute, continuing with detected language.")
                        if lang == "yes":
                            language = user_states[(user_id, session_id)]["language"]
                        else:
                            language = lang
                            user_states[(user_id, session_id)]["language"] = language
                        user_states[(user_id, session_id)]["step"] = "processing"
                        await event_copy.reply(
                            f"👍 Got it!\nSpeakers: {user_states[(user_id, session_id)]['min_speakers']}-{user_states[(user_id, session_id)]['max_speakers']}\nLanguage: {language}\nStarting transcription now…"
                        )
                        log(f"User {user_id} confirmed/overrode language: {language} (session {session_id}).")
                    status_msg = await event_copy.reply("⏳ Running WhisperX, please wait…")
                    min_speakers = user_states[(user_id, session_id)]["min_speakers"]
                    max_speakers = user_states[(user_id, session_id)]["max_speakers"]
                    language = user_states[(user_id, session_id)]["language"]
                    file_path = user_states[(user_id, session_id)]["file_path"]
                    async def run_whisperx_and_monitor():
                        async with active_jobs_lock:
                            count = read_active_jobs()
                            count += 1
                            write_active_jobs(count)
                            log(f"[active_jobs] Incremented: {count}")
                        try:
                            
                            status = runpod_api.get_pod_status()
                            if status != "RUNNING":
                                log(f"Pod not running (status={status}), resuming...")
                                max_retries = 40
                                for attempt in range(max_retries):
                                    start_response = runpod_api.start_pod()
                                    
                                    if start_response is None:
                                        log("Pod start returned None, retrying...")
                                    elif isinstance(start_response, str) and "not enough free GPUs" in start_response:
                                        log(f"Pod start error: not enough free GPUs (attempt {attempt+1}/{max_retries})")
                                        time.sleep(10)
                                        continue
                                    
                                    for _ in range(60):
                                        time.sleep(5)
                                        status = runpod_api.get_pod_status()
                                        if status == "RUNNING":
                                            break
                                    if status == "RUNNING":
                                        break
                                if status != "RUNNING":
                                    log("Pod did not start in time or not enough GPUs.")
                                    await event_copy.reply("❌ Remote error: Pod did not start in time or not enough GPUs available. Please try again later.")
                                    return ["Remote error: Pod did not start in time or not enough GPUs."]
                            log(f"Pod is running (status={status})")
                            await asyncio.sleep(50)
                            remote_url = runpod_api.get_server_url()
                            log(f"Using remote WhisperX server at: {remote_url}")
                            with open(file_path, "rb") as f:
                                files = {"audio": (os.path.basename(file_path), f, "application/octet-stream")}
                                data = {
                                    "min_speakers": str(min_speakers),
                                    "max_speakers": str(max_speakers),
                                    "language": language,
                                    "HF_TOKEN": HF_TOKEN,
                                }
                                response = requests.post(remote_url, files=files, data=data, timeout=3000)
                            if response.status_code not in (200, 202):
                                log(f"Remote WhisperX error: {response.text}")
                                await event_copy.reply(f"❌ Remote error: {response.text}")
                                return [f"Remote error: {response.text}"]
                            job_id = response.json().get("job_id")
                            if not job_id:
                                log(f"Remote WhisperX error: No job_id in response: {response.text}")
                                await event_copy.reply(f"❌ Remote error: No job_id in response: {response.text}")
                                return [f"Remote error: No job_id in response: {response.text}"]
                            log(f"Job submitted, job_id={job_id}")
                            status_url = remote_url.replace("/run_whisperx", f"/job_status/{job_id}")
                            transcript_url = remote_url.replace("/run_whisperx", f"/get_transcript/{job_id}")
                            for poll_count in range(720):
                                status_resp = requests.get(status_url, timeout=10)
                                if status_resp.status_code != 200:
                                    await asyncio.sleep(10)
                                    continue
                                status_data = status_resp.json()
                                if status_data.get("status") == "done":
                                    log(f"Job {job_id} done, downloading transcript...")
                                    break
                                elif status_data.get("status") == "error":
                                    error_msg = status_data.get("error")
                                    log(f"Job {job_id} error: {error_msg}")
                                    await event_copy.reply(f"❌ WhisperX error: {error_msg}")
                                    return [f"Remote error: {error_msg}"]
                                await asyncio.sleep(10)
                            else:
                                log(f"Job {job_id} timed out after polling.")
                                await event_copy.reply("❌ Remote error: Job timed out.")
                                return ["Remote error: Job timed out."]
                            transcript_resp = requests.get(transcript_url, timeout=600)
                            if transcript_resp.status_code == 200:
                                transcript_path = file_path.rsplit(".audio", 1)[0] + ".txt"
                                with open(transcript_path, "wb") as out:
                                    out.write(transcript_resp.content)
                                log(f"Transcript downloaded from remote pod: {transcript_path}")
                                with open(transcript_path, "r") as f:
                                    lines = f.readlines()
                                return [line.strip() for line in lines]
                            else:
                                log(f"Remote WhisperX error: {transcript_resp.text}")
                                await event_copy.reply(f"❌ WhisperX error: {transcript_resp.text}")
                                return [f"Remote error: {transcript_resp.text}"]
                        finally:
                            async with active_jobs_lock:
                                count = read_active_jobs()
                                count = max(count - 1, 0)
                                write_active_jobs(count)
                                log(f"[active_jobs] Decremented: {count}")
                                if count <= 0:
                                    log(f"All jobs for user {user_id} finished. Pausing pod.")
                                    runpod_api.pause_pod()
                    output_lines = await run_whisperx_and_monitor()
                    log(f"WhisperX process finished for user {user_id}. Checking for transcript file.")
                    
                    transcript = ""
                    folder = FILES_DIR
                    transcript_filename = fname.rsplit(".audio", 1)[0] + ".txt"
                    transcript_path = os.path.join(folder, transcript_filename)
                    
                    if os.path.exists(transcript_path):
                        with open(transcript_path, "r") as f:
                            transcript = f.read()
                        log(f"Transcript loaded from: {transcript_path}")
                    else:
                        transcript = "\n".join(output_lines) or "No transcript found."
                        with open(transcript_path, "w") as f:
                            f.write(transcript)
                        log(f"Transcript written to: {transcript_path}")
                    
                    for i in range(0, len(transcript), 4000):
                        await event_copy.reply(transcript[i:i+4000])
                        log(f"Transcript chunk {i//4000+1} sent to user {user_id}, length: {len(transcript[i:i+4000])}")
                    
                    if transcript_path and os.path.exists(transcript_path):
                        await event_copy.reply(file=transcript_path, message="📝 Transcript file")
                        log(f"Transcript file sent to user {user_id}: {transcript_path}")
                    await event_copy.reply("✅ Transcript sent as text and file. Ready for a new task! Start by entering number of speakers and language (e.g. 'add 2 en').")
                    log(f"All done for user {user_id}. State reset for next session.")
                    
                    user_states.pop((user_id, session_id), None)
            except Exception as exc:
                import traceback
                err_str = ''.join(traceback.format_exception(type(exc), exc, exc.__traceback__))
                await event_copy.reply("❌ Internal error occurred, check logs for details.")
                log(f"Exception for user {user_id}, session {session_id}:\n{err_str}")
            finally:
                user_tasks[user_id] = [t for t in user_tasks[user_id] if not t.done()]
        
        task = asyncio.create_task(process_task(event, session_id))
        user_tasks[user_id].append(task)
    log("Telethon bot running. To start: type 'add <speakers> <language>' or just 'add <speakers>', then upload audio.")
    await client.start()
    await client.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())