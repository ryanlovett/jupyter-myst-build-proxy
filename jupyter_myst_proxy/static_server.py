#!/usr/bin/env python3
import os
import sys
import subprocess
import tempfile
import logging
from http.server import SimpleHTTPRequestHandler, HTTPServer
from urllib.parse import unquote, urlparse, parse_qs

log = logging.getLogger(__name__)


class MystHTTPRequestHandler(SimpleHTTPRequestHandler):
    default_directory = "."

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
        - / -> myst_dir=., file_path=/
        """
        clean_path = unquote(self.path.split("?")[0])
        parts = [p for p in clean_path.split("/") if p]

        if not parts:
            # Root path: /
            return self.default_directory, "/"

        # First part is the myst project directory
        myst_dir = parts[0]
        if not os.path.isabs(myst_dir):
            myst_dir = os.path.abspath(myst_dir)

        # Remaining parts are the file path
        file_path = "/" + "/".join(parts[1:])
        if self.path.split("?")[0].endswith("/") and file_path != "/":
            file_path += "/"

        return myst_dir, file_path

    def _render_no_myst_page(self, myst_dir):
        """Return an HTML page indicating no myst.yml found"""
        template_path = os.path.join(os.path.dirname(__file__), "no_myst_error.html")
        with open(template_path, "r") as f:
            html = f.read()
        return html.format(myst_dir=myst_dir).encode("utf-8")

    def _build_myst_site(self, myst_dir, base_url):
        """Build the MyST site if needed"""
        html_dir = os.path.join(myst_dir, "_build", "html")

        if not os.path.exists(os.path.join(html_dir, "index.html")):
            log.info(f"Building static HTML for {myst_dir} with BASE_URL={base_url}")
            env = os.environ.copy()
            env["BASE_URL"] = base_url
            result = subprocess.run(
                ["myst", "build", "--html", "--ci"],
                cwd=myst_dir,
                env=env,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                log.error(f"Build error: {result.stderr}")
                return None

        return html_dir

    def do_GET(self):
        myst_dir, file_path = self._parse_path()

        log.debug(f"Request: {self.path}")
        log.debug(f"Parsed: myst_dir={myst_dir}, file_path={file_path}")

        # Determine BASE_URL for this project
        # If myst_dir is same as default_directory, BASE_URL is /myst
        # Otherwise, BASE_URL is /myst/<project_path>
        # Note: No trailing slash - MyST adds it automatically
        if os.path.abspath(myst_dir) == os.path.abspath(self.default_directory):
            base_url = "/myst"
            url_prefix = ""
        else:
            # Extract the project name from the path
            rel_path = os.path.relpath(myst_dir, self.default_directory)
            base_url = f"/myst/{rel_path}"
            url_prefix = f"/{rel_path}"

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

                # Redirect without ?rebuild=1, preserving the full path with /myst/ prefix
                self.send_response(302)
                redirect_url = base_url + file_path
                self.send_header("Location", redirect_url)
                self.end_headers()
                return

        # Check if myst.yml exists
        if not os.path.exists(os.path.join(myst_dir, "myst.yml")):
            self.send_response(404)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            body = self._render_no_myst_page(myst_dir)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        # Build the site if needed
        html_dir = self._build_myst_site(myst_dir, base_url)
        if not html_dir:
            self.send_response(500)
            self.send_header("Content-Type", "text/plain")
            body = b"Build failed"
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        # Serve from html_dir
        self.directory = html_dir

        # Map file_path to actual file in html_dir
        full_path = os.path.join(self.directory, file_path.lstrip("/"))

        # Handle directory redirects
        if os.path.isdir(full_path) and not file_path.endswith("/"):
            self.send_response(301)
            # Use relative redirect
            path_parts = file_path.rstrip("/").split("/")
            relative_redirect = path_parts[-1] + "/" if path_parts[-1] else "./"
            if "?" in self.path:
                relative_redirect += "?" + self.path.split("?", 1)[1]
            self.send_header("Location", relative_redirect)
            self.end_headers()
            return

        # Update self.path to be relative to html_dir
        self.path = file_path
        if "?" in self.path:
            self.path = file_path + "?" + self.path.split("?", 1)[1]

        super().do_GET()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    default_dir = sys.argv[2] if len(sys.argv) > 2 else os.getcwd()

    MystHTTPRequestHandler.default_directory = default_dir

    with HTTPServer(("", port), MystHTTPRequestHandler) as httpd:
        log.info(f"Starting on port {port}, default directory: {default_dir}")
        httpd.serve_forever()
