import os
import subprocess
from flask import Flask, request, jsonify, send_file
from datetime import datetime
import threading
import uuid
app = Flask(__name__)

app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024 * 1024  

WHISPERX_MODEL = os.environ.get("WHISPERX_MODEL", "large-v3")
HF_TOKEN = os.environ.get("HF_TOKEN", "")
FILES_DIR = os.environ.get("FILES_DIR", "/tmp/files")
os.makedirs(FILES_DIR, exist_ok=True)

jobs = {}
def log(msg):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] {msg}", flush=True)
def run_whisperx_job(job_id, file_path, transcript_path, min_speakers, max_speakers, language, hf_token):
    log(f"[Job {job_id}] Thread started.")
    
    try:
        import torch
        log(f"[Job {job_id}] torch.cuda.is_available(): {torch.cuda.is_available()}")
        log(f"[Job {job_id}] CUDA_VISIBLE_DEVICES: {os.environ.get('CUDA_VISIBLE_DEVICES')}")
        if torch.cuda.is_available():
            log(f"[Job {job_id}] torch.cuda.device_count(): {torch.cuda.device_count()}")
            log(f"[Job {job_id}] torch.cuda.current_device(): {torch.cuda.current_device()}")
            log(f"[Job {job_id}] torch.cuda.get_device_name(): {torch.cuda.get_device_name(torch.cuda.current_device())}")
    except Exception as e:
        log(f"[Job {job_id}] Could not import torch or get CUDA info: {e}")
    jobs[job_id]["status"] = "running"
    try:
        os.environ["TORCH_DYNAMO_DISABLE"] = "1"
        os.environ["NVIDIA_TF32_OVERRIDE"] = "1"
        cmd = [
            "whisperx",
            file_path,
            "--hf_token", hf_token,
            "--model", WHISPERX_MODEL,
            "--diarize",
            "--min_speakers", str(min_speakers),
            "--max_speakers", str(max_speakers),
            "--compute_type", "float32",
            "--batch_size", "64",
            "--language", language
        ]
        log(f"[Job {job_id}] Running command: {' '.join(cmd)}")
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=FILES_DIR, bufsize=1)
        def stream_output(stream, label):
            for line in iter(stream.readline, ''):
                log(f"[Job {job_id}][{label}]: {line.rstrip()}")
            stream.close()
        t_stdout = threading.Thread(target=stream_output, args=(process.stdout, 'stdout'))
        t_stderr = threading.Thread(target=stream_output, args=(process.stderr, 'stderr'))
        t_stdout.start()
        t_stderr.start()
        t_stdout.join()
        t_stderr.join()
        process.wait()
        log(f"[Job {job_id}] WhisperX process exited with code {process.returncode}")
        if os.path.exists(transcript_path):
            log(f"[Job {job_id}] Transcript found: {transcript_path}")
            jobs[job_id]["status"] = "done"
            jobs[job_id]["transcript_path"] = transcript_path
        else:
            log(f"[Job {job_id}] Transcript not found.")
            jobs[job_id]["status"] = "error"
            jobs[job_id]["error"] = "Transcript not found"
    except Exception as e:
        import traceback
        err_str = ''.join(traceback.format_exception(type(e), e, e.__traceback__))
        log(f"[Job {job_id}] Exception: {err_str}")
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = str(e)
    finally:
        log(f"[Job {job_id}] Thread finished.")
log("WhisperX remote server starting up...")
@app.route("/run_whisperx", methods=["POST"])
def run_whisperx():
    log("/run_whisperx endpoint called.")
    
    audio = request.files.get("audio")
    speakers = request.form.get("speakers", "1")
    min_speakers = request.form.get("min_speakers", "1")
    max_speakers = request.form.get("max_speakers", min_speakers)
    language = request.form.get("language", "en")
    hf_token = request.form.get("HF_TOKEN", HF_TOKEN)
    log(f"Received request: min_speakers={min_speakers}, max_speakers={max_speakers}, language={language}, file={audio.filename if audio else None}")
    if not audio:
        log("No audio file uploaded.")
        return jsonify({"error": "No audio file uploaded"}), 400
    fname = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{audio.filename}"
    file_path = os.path.join(FILES_DIR, fname)
    audio.save(file_path)
    log(f"Audio saved to {file_path}")
    transcript_path = file_path.rsplit(".audio", 1)[0] + ".txt"
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "pending", "transcript_path": None, "error": None}
    t = threading.Thread(target=run_whisperx_job, args=(job_id, file_path, transcript_path, min_speakers, max_speakers, language, hf_token))
    t.start()
    log(f"Job {job_id} started in background.")
    return jsonify({"job_id": job_id}), 202
@app.route("/job_status/<job_id>", methods=["GET"])
def job_status(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify({"status": job["status"], "error": job["error"]})
@app.route("/get_transcript/<job_id>", methods=["GET"])
def get_transcript(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    if job["status"] != "done" or not job["transcript_path"] or not os.path.exists(job["transcript_path"]):
        return jsonify({"error": "Transcript not ready"}), 400
    
    return send_file(job["transcript_path"], as_attachment=True, conditional=True)
if __name__ == "__main__":
    log("Flask app running on 0.0.0.0:8000")
    app.run(host="0.0.0.0", port=8000)
