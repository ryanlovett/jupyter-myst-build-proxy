import os
import tempfile

_MYST_SERVER_PORT_FILE = os.path.join(
    tempfile.gettempdir(), f"myst_server_port_{os.getpid()}"
)
MYST_CONTENT_PATH = "myst-content"


def rewrite_myst_response(response, request):
    """Rewrite MyST responses - minimal rewriting for static HTML"""
    # Static HTML already has correct /myst/ paths from BASE_URL
    # No rewriting needed
    return response


def setup_myst():
    import os as _os
    import sys
    import subprocess
    
    def _get_cmd(port, base_url="/"):
        myst_dir = _os.environ.get("MYST_DIR", "test-myst-site")
        if not _os.path.isabs(myst_dir):
            myst_dir = _os.path.abspath(myst_dir)
        
        html_dir = _os.path.join(myst_dir, "_build", "html")
        
        print(f"[jupyter_myst_proxy] _get_cmd called with port={port}, base_url={base_url}", file=sys.stderr)
        print(f"[jupyter_myst_proxy] myst_dir: {myst_dir}", file=sys.stderr)
        print(f"[jupyter_myst_proxy] html_dir: {html_dir}", file=sys.stderr)
        
        if not _os.path.exists(_os.path.join(html_dir, "index.html")):
            print(f"[jupyter_myst_proxy] Building static HTML with BASE_URL=/myst", file=sys.stderr)
            env = _os.environ.copy()
            env["BASE_URL"] = "/myst"
            result = subprocess.run(
                ["myst", "build", "--html", "--ci"],
                cwd=myst_dir,
                env=env,
                capture_output=True,
                text=True
            )
            print(f"[jupyter_myst_proxy] Build output: {result.stdout}", file=sys.stderr)
            if result.returncode != 0:
                print(f"[jupyter_myst_proxy] Build error: {result.stderr}", file=sys.stderr)
        
        print(f"[jupyter_myst_proxy] Serving static files from {html_dir} on port {port}", file=sys.stderr)
        
        static_server = _os.path.join(_os.path.dirname(__file__), "static_server.py")
        return ["python3", static_server, str(port), html_dir]

    return {
        "command": _get_cmd,
        "timeout": 60,
        "absolute_url": False,
        "rewrite_response": rewrite_myst_response,
        "launcher_entry": {
            "title": "MyST",
        },
    }


def setup_myst_content():
    def _get_port(port):
        # Read the server port from the file written by setup_myst
        try:
            with open(_MYST_SERVER_PORT_FILE, "r") as f:
                return int(f.read().strip())
        except:
            return None  # No port available yet

    return {
        "port": _get_port,
        "timeout": 30,
        "absolute_url": False,
    }
