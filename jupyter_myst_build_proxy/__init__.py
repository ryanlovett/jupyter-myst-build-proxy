# Global variable to store the proxy base URL
# This will be set when the server starts
_PROXY_BASE_URL = None


def rewrite_myst_response(response, request):
    """Rewrite MyST responses to fix navigation URLs in page data"""
    import re
    from urllib.parse import urlparse

    content_type = response.headers.get("Content-Type", "")

    # Only rewrite HTML responses
    if "text/html" not in content_type:
        return response

    body = response.body.decode("utf-8")

    # Use the stored proxy base URL to determine where our proxy is mounted
    # Local: _PROXY_BASE_URL = "/myst-build/"
    # JupyterHub: _PROXY_BASE_URL = "/user/{username}/myst-build/"
    if _PROXY_BASE_URL is None:
        # Fallback: can't rewrite without knowing the base
        return response

    proxy_base = _PROXY_BASE_URL.rstrip("/")
    path = urlparse(request.uri).path

    # Verify this request is actually for our proxy
    if not path.startswith(proxy_base + "/") and path != proxy_base:
        return response

    # Extract the Jupyter server base (everything before "/myst-build")
    # proxy_base is like "/user/{username}/myst-build" or "/myst-build"
    # We need to remove the final "/myst-build" part
    if proxy_base.endswith("/myst-build"):
        jupyter_base = proxy_base[:-11]
    else:
        jupyter_base = ""

    # Everything after proxy_base is the project path + file
    if path == proxy_base:
        project_and_file = "/"
    else:
        project_and_file = path[len(proxy_base) :]

    # Parse project path from the remaining path
    parts = [p for p in project_and_file.split("/") if p]

    # Check if last part looks like a file
    if parts and ("." in parts[-1] or parts[-1] in ["index"]):
        parts = parts[:-1]

    # Construct the base URL
    if parts:
        base_url = f"{jupyter_base}/myst-build/" + "/".join(parts)
    else:
        base_url = f"{jupyter_base}/myst-build"

    # Fix navigation URLs in footer/next/prev that are missing the project prefix
    # Pattern: "url":"/foo" -> "url":"<base_url>/foo"
    body = re.sub(r'"url":"(/(?!myst-build/|user/)[^"]+)"', rf'"url":"{base_url}\1"', body)

    response.body = body.encode("utf-8")
    response.headers["Content-Length"] = str(len(response.body))

    return response


def setup_myst():
    import os
    import sys
    import logging

    log = logging.getLogger(__name__)

    # This is the path suffix that jupyter-server-proxy adds
    PATH_INFO = "myst-build/"

    def _get_cmd(port, base_url="/"):
        global _PROXY_BASE_URL

        # Store the proxy base URL for use in rewrite_response
        _PROXY_BASE_URL = base_url

        # Default to cwd, but can be overridden with JUPYTER_MYST_BUILD_PROXY_DIR env var
        default_dir = os.environ.get("JUPYTER_MYST_BUILD_PROXY_DIR", os.getcwd())
        if not os.path.isabs(default_dir):
            default_dir = os.path.abspath(default_dir)

        # base_url from jupyter-server-proxy includes the full path:
        # - Local: "/myst-build/"
        # - JupyterHub: "/user/{username}/myst-build/"
        # We need to strip our path_info to get the jupyter server base
        jupyter_base_url = base_url.rstrip("/")
        if jupyter_base_url.endswith("/" + PATH_INFO.rstrip("/")):
            # Remove "/myst-build" from the end
            jupyter_base_url = jupyter_base_url[: -(len(PATH_INFO.rstrip("/")) + 1)]
        if not jupyter_base_url:
            jupyter_base_url = "/"

        log.info(f"Starting static server on port {port} in directory: {default_dir}")
        log.info(
            f"base_url from proxy: {base_url}, jupyter_base_url: {jupyter_base_url}"
        )

        static_server = os.path.join(os.path.dirname(__file__), "static_server.py")
        return [sys.executable, static_server, str(port), default_dir, jupyter_base_url]

    return {
        "command": _get_cmd,
        "timeout": 60,
        "absolute_url": False,
        "rewrite_response": rewrite_myst_response,
        "path_info": PATH_INFO,
        "launcher_entry": {
            "title": "MyST Build",
            "icon_path": os.path.join(os.path.dirname(__file__), "logo-square.svg"),
        },
    }
