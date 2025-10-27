"""Simple test to diagnose JupyterHub startup issue"""
import subprocess
import time
import requests
from pathlib import Path

JUPYTERHUB_URL = "http://127.0.0.1:8000"
JUPYTERHUB_CONFIG = Path(__file__).parent / "jupyterhub_config.py"

print(f"Config file exists: {JUPYTERHUB_CONFIG.exists()}")
print(f"Starting JupyterHub...")

# Start JupyterHub
proc = subprocess.Popen(
    ["jupyterhub", "-f", str(JUPYTERHUB_CONFIG)],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True
)

# Wait for startup
print("Waiting for JupyterHub to start...")
for i in range(30):
    try:
        response = requests.get(f"{JUPYTERHUB_URL}/hub/api", timeout=1)
        if response.status_code == 200:
            print(f"JupyterHub started successfully after {i+1} seconds!")
            break
    except requests.exceptions.ConnectionError:
        print(f"  Attempt {i+1}: Connection refused, waiting...")
    except Exception as e:
        print(f"  Attempt {i+1}: {type(e).__name__}: {e}")
    time.sleep(1)
else:
    print("JupyterHub failed to start within 30 seconds")
    print("\n=== STDOUT ===")
    stdout, stderr = proc.communicate(timeout=1)
    print(stdout)
    print("\n=== STDERR ===")
    print(stderr)
    proc.kill()
    exit(1)

print("Success! Shutting down...")
proc.terminate()
proc.wait(timeout=10)
print("Done")
