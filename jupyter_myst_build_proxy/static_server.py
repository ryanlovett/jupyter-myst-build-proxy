#!/usr/bin/env python3
import os
import sys
import subprocess
import threading
import logging
from http.server import SimpleHTTPRequestHandler, HTTPServer
from urllib.parse import unquote, urlparse, parse_qs

log = logging.getLogger(__name__)

# Track builds in progress: {myst_dir: {'status': 'building'|'success'|'failed', 'error': str}}
build_status = {}
build_lock = threading.Lock()


class MystHTTPRequestHandler(SimpleHTTPRequestHandler):
    default_directory = "."
    jupyter_base_url = "/"  # Will be set to /user/{username}/ on JupyterHub

    def __init__(self, *args, **kwargs):
        super().__init__(
            *args, directory=MystHTTPRequestHandler.default_directory, **kwargs
        )

    def _parse_path(self):
        """
        Parse the request path to extract myst_dir and file_path.

        URL format: /<myst_project_path>/<file_path>

        Examples:
        - /test-myst-site/ -> myst_dir=test-myst-site, file_path=/
        - /test-myst-site/foo/ -> myst_dir=test-myst-site, file_path=/foo/
        - /proj/project1/website/ -> myst_dir=proj/project1/website, file_path=/
        - / -> myst_dir=., file_path=/
        """
        clean_path = unquote(self.path.split("?")[0])
        parts = [p for p in clean_path.split("/") if p]

        if not parts:
            # Root path: /
            return self.default_directory, "/"

        # Try to find myst.yml by traversing path segments from longest to shortest
        # This allows for deeper paths like /proj/project1/website
        for i in range(len(parts), 0, -1):
            potential_myst_dir = os.path.join(*parts[:i])
            if not os.path.isabs(potential_myst_dir):
                potential_myst_dir = os.path.abspath(potential_myst_dir)

            # Check if this path contains a myst.yml
            if os.path.exists(os.path.join(potential_myst_dir, "myst.yml")):
                myst_dir = potential_myst_dir
                file_path = "/" + "/".join(parts[i:])
                if self.path.split("?")[0].endswith("/") and file_path != "/":
                    file_path += "/"
                return myst_dir, file_path

        # No myst.yml found in any parent path, use the full path as myst_dir
        myst_dir = os.path.join(*parts)
        if not os.path.isabs(myst_dir):
            myst_dir = os.path.abspath(myst_dir)

        return myst_dir, "/"

    def _render_template(self, template_name, **kwargs):
        """Render an HTML template"""
        template_path = os.path.join(os.path.dirname(__file__), template_name)
        with open(template_path, "r") as f:
            html = f.read()
        return html.format(**kwargs).encode("utf-8")

    def _start_build(self, myst_dir, base_url):
        """Start building the MyST site in a background thread"""

        def build():
            html_dir = os.path.join(myst_dir, "_build", "html")

            try:
                log.info(
                    f"Building static HTML for {myst_dir} with BASE_URL={base_url}"
                )
                env = os.environ.copy()
                env["BASE_URL"] = base_url
                result = subprocess.run(
                    ["myst", "build", "--html", "--ci"],
                    cwd=myst_dir,
                    env=env,
                    capture_output=True,
                    text=True,
                )

                with build_lock:
                    if result.returncode != 0:
                        log.error(f"Build error: {result.stderr}")
                        build_status[myst_dir] = {
                            "status": "failed",
                            "error": result.stderr,
                        }
                    else:
                        log.info(f"Build completed for {myst_dir}")
                        build_status[myst_dir] = {"status": "success"}
            except Exception as e:
                log.error(f"Build exception: {e}")
                with build_lock:
                    build_status[myst_dir] = {"status": "failed", "error": str(e)}

        thread = threading.Thread(target=build, daemon=True)
        thread.start()

    def _needs_build(self, myst_dir):
        """Check if the MyST site needs to be built"""
        html_dir = os.path.join(myst_dir, "_build", "html")
        return not os.path.exists(os.path.join(html_dir, "index.html"))

    def do_GET(self):
        myst_dir, file_path = self._parse_path()

        log.debug(f"Request: {self.path}")
        log.debug(f"Parsed: myst_dir={myst_dir}, file_path={file_path}")

        # Construct base_url with jupyter_base_url prefix (for JupyterHub support)
        # Remove trailing slash from jupyter_base_url if present
        jupyter_prefix = self.jupyter_base_url.rstrip("/")

        if os.path.abspath(myst_dir) == os.path.abspath(self.default_directory):
            base_url = f"{jupyter_prefix}/myst"
        else:
            rel_path = os.path.relpath(myst_dir, self.default_directory)
            base_url = f"{jupyter_prefix}/myst/{rel_path}"

        log.debug(f"base_url={base_url}")

        # Check for rebuild trigger
        query = parse_qs(urlparse(self.path).query)
        if query.get("rebuild") == ["1"]:
            if os.path.exists(os.path.join(myst_dir, "myst.yml")):
                import shutil

                html_dir = os.path.join(myst_dir, "_build", "html")
                log.info(f"Rebuild requested, removing {html_dir}")
                if os.path.exists(html_dir):
                    shutil.rmtree(html_dir)

                with build_lock:
                    if myst_dir in build_status:
                        del build_status[myst_dir]

                self.send_response(302)
                redirect_url = base_url + file_path
                self.send_header("Location", redirect_url)
                self.end_headers()
                return

        # Check if myst.yml exists
        if not os.path.exists(os.path.join(myst_dir, "myst.yml")):
            self.send_response(404)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            body = self._render_template("no_myst_error.html", myst_dir=myst_dir)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        # Check build status
        with build_lock:
            status = build_status.get(myst_dir, {}).get("status")

        if status == "building":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            body = self._render_template("building.html", myst_dir=myst_dir)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if status == "failed":
            with build_lock:
                error = build_status.get(myst_dir, {}).get("error", "Unknown error")
            self.send_response(500)
            self.send_header("Content-Type", "text/plain")
            body = f"Build failed:\n{error}".encode("utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        # Check if build is needed
        if self._needs_build(myst_dir):
            with build_lock:
                build_status[myst_dir] = {"status": "building"}
            self._start_build(myst_dir, base_url)

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            body = self._render_template("building.html", myst_dir=myst_dir)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        # Site is built, serve it
        html_dir = os.path.join(myst_dir, "_build", "html")
        self.directory = html_dir

        full_path = os.path.join(self.directory, file_path.lstrip("/"))

        # Handle directory redirects
        if os.path.isdir(full_path) and not file_path.endswith("/"):
            self.send_response(301)
            path_parts = file_path.rstrip("/").split("/")
            relative_redirect = path_parts[-1] + "/" if path_parts[-1] else "./"
            if "?" in self.path:
                relative_redirect += "?" + self.path.split("?", 1)[1]
            self.send_header("Location", relative_redirect)
            self.end_headers()
            return

        self.path = file_path
        if "?" in self.path:
            self.path = file_path + "?" + self.path.split("?", 1)[1]

        super().do_GET()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    default_dir = sys.argv[2] if len(sys.argv) > 2 else os.getcwd()
    jupyter_base_url = sys.argv[3] if len(sys.argv) > 3 else "/"

    MystHTTPRequestHandler.default_directory = default_dir
    MystHTTPRequestHandler.jupyter_base_url = jupyter_base_url

    with HTTPServer(("", port), MystHTTPRequestHandler) as httpd:
        log.info(
            f"Starting on port {port}, default directory: {default_dir}, jupyter_base_url: {jupyter_base_url}"
        )
        httpd.serve_forever()
