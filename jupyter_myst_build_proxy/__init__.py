def rewrite_myst_response(response, request):
    """Rewrite MyST responses to fix navigation URLs in page data"""
    import re
    from urllib.parse import urlparse

    content_type = response.headers.get("Content-Type", "")

    # Only rewrite HTML responses
    if "text/html" not in content_type:
        return response

    body = response.body.decode("utf-8")

    # Extract the project path from the request URL
    # URL format: /myst/<project_path>/<file>
    path_parts = [p for p in urlparse(request.uri).path.split("/") if p]

    if len(path_parts) > 1:
        # Has a project path like /myst/my-myst-site/
        project_path = path_parts[1]
        base_url = f"/myst/{project_path}"

        # Fix navigation URLs in footer/next/prev that are missing the project prefix
        # Pattern: "url":"/foo" -> "url":"/myst/my-myst-site/foo"
        body = re.sub(r'"url":"(/(?!myst/)[^"]+)"', rf'"url":"{base_url}\1"', body)
    else:
        # Root /myst/ path - uses /myst/ as base
        # Fix navigation URLs: "url":"/foo" -> "url":"/myst/foo"
        body = re.sub(r'"url":"(/(?!myst/)[^"]+)"', r'"url":"/myst\1"', body)

    response.body = body.encode("utf-8")
    response.headers["Content-Length"] = str(len(response.body))

    return response


def setup_myst():
    import os as _os
    import logging

    log = logging.getLogger(__name__)

    def _get_cmd(port, base_url="/"):
        # Default to cwd, but can be overridden with JUPYTER_MYST_BUILD_PROXY_DIR env var
        default_dir = _os.environ.get("JUPYTER_MYST_BUILD_PROXY_DIR", _os.getcwd())
        if not _os.path.isabs(default_dir):
            default_dir = _os.path.abspath(default_dir)

        log.info(f"Starting static server on port {port} in directory: {default_dir}")

        static_server = _os.path.join(_os.path.dirname(__file__), "static_server.py")
        return [static_server, str(port), default_dir]

    return {
        "command": _get_cmd,
        "timeout": 60,
        "absolute_url": False,
        "rewrite_response": rewrite_myst_response,
        "path_info": "myst/",
        "launcher_entry": {
            "title": "MyST Build",
            "icon_path": _os.path.join(_os.path.dirname(__file__), "logo-square.svg"),
        },
    }
