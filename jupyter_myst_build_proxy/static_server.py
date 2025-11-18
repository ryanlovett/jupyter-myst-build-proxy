#!/usr/bin/env python3
import os
import sys
import subprocess
import threading
import logging
import re
import time
from glob import glob
from http.server import SimpleHTTPRequestHandler, HTTPServer
from urllib.parse import unquote, urlparse, parse_qs

log = logging.getLogger(__name__)

# Track builds in progress: {myst_dir: {'status': 'building'|'success'|'failed', 'error': str, 'last_output': str}}
build_status = {}
build_lock = threading.Lock()


class MystHTTPRequestHandler(SimpleHTTPRequestHandler):
    default_directory = "."
    jupyter_base_url = "/"  # Will be set to /user/{username}/ on JupyterHub

    def __init__(self, *args, **kwargs):
        super().__init__(
            *args, directory=MystHTTPRequestHandler.default_directory, **kwargs
        )

    def _set_nocache_headers(self):
        """Set headers to prevent caching of dynamic content"""
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")

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
        log.debug(
            f"_parse_path: self.path={self.path}, clean_path={clean_path}, parts={parts}, default_directory={self.default_directory}"
        )

        if not parts:
            # Root path: /
            log.debug(
                f"_parse_path: Root path, returning default_directory={self.default_directory}"
            )
            return self.default_directory, "/"

        # Try to find myst.yml by traversing path segments from longest to shortest
        # This allows for deeper paths like /proj/project1/website
        for i in range(len(parts), 0, -1):
            potential_myst_dir = os.path.join(self.default_directory, *parts[:i])
            potential_myst_dir = os.path.abspath(potential_myst_dir)
            log.debug(f"_parse_path: Checking {potential_myst_dir}/myst.yml")

            # Check if this path contains a myst.yml
            if os.path.exists(os.path.join(potential_myst_dir, "myst.yml")):
                myst_dir = potential_myst_dir
                file_path = "/" + "/".join(parts[i:])
                if self.path.split("?")[0].endswith("/") and file_path != "/":
                    file_path += "/"
                log.debug(
                    f"_parse_path: Found myst.yml! myst_dir={myst_dir}, file_path={file_path}"
                )
                return myst_dir, file_path

        # No myst.yml found in any parent path, use the full path as myst_dir
        myst_dir = os.path.join(self.default_directory, *parts)
        myst_dir = os.path.abspath(myst_dir)

        log.debug(
            f"_parse_path: No myst.yml found, using full path as myst_dir={myst_dir}"
        )
        return myst_dir, "/"

    def _render_template(self, template_name, **kwargs):
        """Render an HTML template"""
        import html

        template_path = os.path.join(os.path.dirname(__file__), template_name)
        with open(template_path, "r") as f:
            template_html = f.read()

        # Handle last_output formatting for building.html
        if "last_output" in kwargs:
            last_output = kwargs.pop("last_output")
            if last_output:
                # Escape HTML special characters
                escaped_output = html.escape(last_output)
                kwargs["last_output_html"] = (
                    f'<div class="build-output">{escaped_output}</div>'
                )
            else:
                kwargs["last_output_html"] = ""

        return template_html.format(**kwargs).encode("utf-8")

    def _render_directory_browser(self, myst_dir, base_url):
        """Render directory browser showing available directories"""
        import html

        # Get current path relative to default directory
        if os.path.abspath(myst_dir) == os.path.abspath(self.default_directory):
            current_path = "~"
            rel_path = ""
        else:
            rel_path = os.path.relpath(myst_dir, self.default_directory)
            current_path = f"~/{rel_path}"

        # List directories in the current directory
        directories = []
        try:
            if os.path.isdir(myst_dir):
                entries = os.listdir(myst_dir)
                for entry in sorted(entries):
                    entry_path = os.path.join(myst_dir, entry)
                    if os.path.isdir(entry_path) and not entry.startswith("."):
                        # Check if this directory contains myst.yml
                        has_myst = os.path.exists(os.path.join(entry_path, "myst.yml"))

                        # Build the URL for this directory
                        if rel_path:
                            dir_url = f"{base_url}/{entry}/"
                        else:
                            dir_url = f"{base_url.rstrip('/')}/{entry}/"

                        # Create directory entry
                        myst_badge = (
                            '<span class="myst-badge">MyST</span>' if has_myst else ""
                        )
                        # Rebuild button (only for MyST projects)
                        rebuild_button = ""
                        if has_myst:
                            rebuild_url = f"{html.escape(dir_url)}?rebuild=1"
                            rebuild_button = (
                                f'<a href="{rebuild_url}" class="rebuild-button" '
                                'title="Rebuild site" target="_blank" rel="noopener noreferrer">🔄</a>'
                            )

                        # MyST projects open in new tab
                        target_attr = (
                            ' target="_blank" rel="noopener noreferrer"'
                            if has_myst
                            else ""
                        )

                        directories.append(
                            f'<li class="directory-item">'
                            f'<div class="directory-row">'
                            f'<a href="{html.escape(dir_url)}" class="directory-link"{target_attr}>'
                            f'<span class="folder-icon">📁</span>'
                            f'<span class="directory-name">{html.escape(entry)}</span>'
                            f"</a>"
                            f'<div class="directory-controls">'
                            f"{myst_badge}"
                            f"{rebuild_button}"
                            f"</div>"
                            f"</div>"
                            f"</li>"
                        )
        except PermissionError:
            pass

        # Add parent directory link if not at root
        parent_directory = ""
        if rel_path:
            parent_url = base_url.rsplit("/", 1)[0]
            if not parent_url or parent_url.endswith("/myst-build"):
                parent_url = parent_url.rstrip("/") if parent_url else ""
            parent_directory = (
                '<li class="directory-item">'
                f'<a href="{html.escape(parent_url + "/") if parent_url else "/"}" class="directory-link">'
                '<span class="folder-icon">📁</span>'
                '<span class="directory-name">..</span>'
                "</a>"
                "</li>"
            )

        # Build the HTML
        if directories:
            directories_html = "\n".join(directories)
            empty_state = ""
        else:
            directories_html = ""
            empty_state = (
                '<div class="empty-state">'
                '<div class="empty-state-icon">📁</div>'
                '<div class="empty-state-text">No directories found</div>'
                "</div>"
            )

        return self._render_template(
            "directory_browser.html",
            current_path=html.escape(current_path),
            parent_directory=parent_directory,
            directories=directories_html,
            empty_state=empty_state,
        )

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

                # Use Popen to capture output line by line
                process = subprocess.Popen(
                    ["myst", "build", "--html", "--ci"],
                    cwd=myst_dir,
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )

                output_lines = []
                if process.stdout:
                    for line in process.stdout:
                        line = line.rstrip()
                        if line:  # Only track non-empty lines
                            output_lines.append(line)
                            with build_lock:
                                if myst_dir in build_status:
                                    build_status[myst_dir]["last_output"] = line
                            log.debug(f"Build output: {line}")

                process.wait()

                with build_lock:
                    if process.returncode != 0:
                        error_output = "\n".join(output_lines[-20:])  # Last 20 lines
                        log.error(f"Build error: {error_output}")
                        build_status[myst_dir] = {
                            "status": "failed",
                            "error": error_output,
                        }
                    else:
                        log.info(f"Build completed for {myst_dir}")
                        self._postbuild(myst_dir)
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

    def _postbuild(self, myst_dir):

        if not os.getenv("JUPYTER_MYST_BUILD_PROXY_POSTBUILD"):
            log.debug(
                "JUPYTER_MYST_BUILD_PROXY_POSTBUILD not set."
                f" Skipping post-build HTML injection for {myst_dir}"
            )
            return

        html_dir = os.path.join(myst_dir, "_build", "html")
        injectable_html_file = os.path.join(
            os.path.dirname(__file__),
            "remixContextMod.html",
        )

        with open(injectable_html_file, "r", encoding="utf-8") as f:
            injectable_html = f.read().strip()

        try:
            log.debug(f"Injecting HTML in {html_dir}")
            html_files = glob(
                os.path.join(html_dir, "**", "*.html"),
                recursive=True,
            )

            for html_file in html_files:
                log.debug(f"Modifying {html_file}")
                with open(html_file, "r", encoding="utf-8") as f:
                    html = f.read()

                # Should never happen, but let's handle anyway
                if '</body>' not in html:
                    msg = f"No <body> tag found in {html_file}"
                    log.error(f"Error: {msg}")
                    raise RuntimeError(msg)

                modified_html = html.replace(
                    "</body>",
                    f"{injectable_html}\n</body>"
                )

                with open(html_file, "w", encoding="utf-8") as f:
                    f.write(modified_html)

        except Exception as e:
            log.error(f"Error injecting HTML into {html_file}: {e}")
            return

        log.info(f"Post-build HTML injection completed for {myst_dir}")

    def do_GET(self):
        myst_dir, file_path = self._parse_path()

        log.debug(f"Request: {self.path}")
        log.debug(f"Parsed: myst_dir={myst_dir}, file_path={file_path}")

        # Construct base_url with jupyter_base_url prefix (for JupyterHub support)
        # Remove trailing slash from jupyter_base_url if present
        jupyter_prefix = self.jupyter_base_url.rstrip("/")

        if os.path.abspath(myst_dir) == os.path.abspath(self.default_directory):
            base_url = f"{jupyter_prefix}/myst-build"
        else:
            rel_path = os.path.relpath(myst_dir, self.default_directory)
            base_url = f"{jupyter_prefix}/myst-build/{rel_path}"

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

                # Redirect with timestamp parameter to force cache bust
                self.send_response(302)
                redirect_url = f"{base_url}{file_path}?_t={int(time.time() * 1000)}"
                self.send_header("Location", redirect_url)
                self._set_nocache_headers()
                self.end_headers()
                return

        # Check if myst.yml exists
        if not os.path.exists(os.path.join(myst_dir, "myst.yml")):
            # Show directory browser instead of error page
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            body = self._render_directory_browser(myst_dir, base_url)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        # Check build status
        with build_lock:
            status_info = build_status.get(myst_dir, {})
            status = status_info.get("status")
            last_output = status_info.get("last_output", "")

        if status == "building":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self._set_nocache_headers()
            body = self._render_template(
                "building.html", myst_dir=myst_dir, last_output=last_output
            )
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
                build_status[myst_dir] = {"status": "building", "last_output": ""}
            self._start_build(myst_dir, base_url)

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self._set_nocache_headers()
            body = self._render_template(
                "building.html", myst_dir=myst_dir, last_output=""
            )
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
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

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
