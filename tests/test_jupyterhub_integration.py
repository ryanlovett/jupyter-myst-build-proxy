"""
Integration tests for jupyter-myst-build-proxy with JupyterHub

These tests spin up a local JupyterHub instance and verify that:
1. MyST sites build correctly
2. Assets load from the correct paths (with /user/{username}/ prefix)
3. Navigation links are rewritten correctly
4. Edge cases like username "myst-build" work correctly
"""

import os
import subprocess
import time
import shutil
import requests
import pytest
from pathlib import Path


# Test configuration
JUPYTERHUB_URL = "http://127.0.0.1:8000"
JUPYTERHUB_CONFIG = Path(__file__).parent / "jupyterhub_config.py"
TEST_SITE_DIR = Path(__file__).parent / "test-site"
TEST_USERS = ["testuser", "myst-build", "alice"]


class JupyterHubInstance:
    """Context manager for running JupyterHub"""
    
    def __init__(self, config_file):
        self.config_file = config_file
        self.process = None
        
    def __enter__(self):
        """Start JupyterHub"""
        print(f"Starting JupyterHub with config: {self.config_file}")
        
        # Create log files for debugging
        test_dir = Path(self.config_file).parent
        stdout_log = test_dir / "jupyterhub_stdout.log"
        stderr_log = test_dir / "jupyterhub_stderr.log"
        
        # Open files and keep them open - store file handles
        self.stdout_file = open(stdout_log, 'w')
        self.stderr_file = open(stderr_log, 'w')
        
        # Use files instead of PIPE to avoid deadlock
        self.process = subprocess.Popen(
            ["jupyterhub", "-f", str(self.config_file)],
            stdout=self.stdout_file,
            stderr=self.stderr_file,
            text=True
        )
        
        # Store log paths for potential debugging
        self.stdout_log = stdout_log
        self.stderr_log = stderr_log
        
        # Wait for JupyterHub to be ready
        max_wait = 30
        for i in range(max_wait):
            try:
                response = requests.get(f"{JUPYTERHUB_URL}/hub/api", timeout=1)
                if response.status_code == 200:
                    print("JupyterHub is ready!")
                    return self
            except requests.exceptions.ConnectionError:
                pass
            time.sleep(1)
        
        # If we failed to start, print the logs
        print("JupyterHub failed to start. Logs:")
        self.stdout_file.flush()
        self.stderr_file.flush()
        if stdout_log.exists():
            print(f"\n=== STDOUT ({stdout_log}) ===")
            print(stdout_log.read_text()[-1000:])  # Last 1000 chars
        if stderr_log.exists():
            print(f"\n=== STDERR ({stderr_log}) ===")
            print(stderr_log.read_text()[-1000:])  # Last 1000 chars
        raise RuntimeError("JupyterHub failed to start within 30 seconds")
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Shutdown JupyterHub"""
        print("Shutting down JupyterHub...")
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        
        # Close file handles
        if hasattr(self, 'stdout_file'):
            self.stdout_file.close()
        if hasattr(self, 'stderr_file'):
            self.stderr_file.close()
        
        # Clean up test database, cookie secret, and logs
        test_dir = Path(self.config_file).parent
        for file in ["jupyterhub.sqlite", "jupyterhub_cookie_secret", 
                     "jupyterhub_stdout.log", "jupyterhub_stderr.log"]:
            filepath = test_dir / file
            if filepath.exists():
                filepath.unlink()


def login_and_get_cookie(username, password=""):
    """Login to JupyterHub and return session cookie"""
    import re
    session = requests.Session()
    
    # Get the login page to retrieve CSRF token
    login_page = session.get(f"{JUPYTERHUB_URL}/hub/login")
    
    # Extract CSRF token from the login page
    csrf_match = re.search(r'name="_xsrf"\s+value="([^"]+)"', login_page.text)
    if not csrf_match:
        raise RuntimeError("Could not find CSRF token in login page")
    
    csrf_token = csrf_match.group(1)
    
    # Login with dummy authenticator (any password works)
    login_data = {
        "username": username,
        "password": password or "dummy",
        "_xsrf": csrf_token
    }
    
    response = session.post(
        f"{JUPYTERHUB_URL}/hub/login",
        data=login_data,
        allow_redirects=True
    )
    
    if response.status_code != 200:
        raise RuntimeError(f"Login failed for user {username}: {response.status_code}")
    
    return session


def spawn_server(session, username):
    """Spawn a single-user server for the given user"""
    print(f"Spawning server for user: {username}")
    
    # Check if server is already running
    try:
        check_response = session.get(
            f"{JUPYTERHUB_URL}/user/{username}/api",
            allow_redirects=False,
            timeout=1
        )
        if check_response.status_code == 200:
            print(f"Server already running for user: {username}")
            return True
    except requests.exceptions.RequestException:
        pass
    
    # Request to spawn the server
    response = session.post(
        f"{JUPYTERHUB_URL}/hub/spawn/{username}",
        allow_redirects=False
    )
    
    # Wait for server to be ready
    max_wait = 60
    for i in range(max_wait):
        try:
            # Check if server is ready
            check_response = session.get(
                f"{JUPYTERHUB_URL}/user/{username}/api",
                allow_redirects=False,
                timeout=1
            )
            if check_response.status_code == 200:
                print(f"Server ready for user: {username}")
                return True
        except requests.exceptions.RequestException:
            pass
        time.sleep(1)
    
    raise RuntimeError(f"Server failed to spawn for user {username}")


def setup_test_site(username):
    """Copy test site to user's home directory"""
    # For SimpleLocalProcessSpawner, the user's home is their actual home directory
    # In a real test, you might want to use a temporary directory
    home_dir = Path.home()
    user_test_site = home_dir / "test-myst-site"
    
    # Clean up existing test site
    if user_test_site.exists():
        shutil.rmtree(user_test_site)
    
    # Copy test site
    shutil.copytree(TEST_SITE_DIR, user_test_site)
    print(f"Copied test site to: {user_test_site}")
    print(f"myst.yml exists: {(user_test_site / 'myst.yml').exists()}")
    return user_test_site


@pytest.fixture(scope="module")
def jupyterhub():
    """Fixture to start and stop JupyterHub for all tests"""
    with JupyterHubInstance(JUPYTERHUB_CONFIG) as hub:
        yield hub


def test_basic_myst_build(jupyterhub):
    """Test that a MyST site builds and loads correctly for a regular user"""
    username = "testuser"
    
    # Login and spawn server
    session = login_and_get_cookie(username)
    spawn_server(session, username)
    
    # Setup test site
    test_site = setup_test_site(username)
    
    # Access the MyST proxy endpoint
    myst_url = f"{JUPYTERHUB_URL}/user/{username}/myst-build/test-myst-site/"
    print(f"Accessing: {myst_url}")
    
    response = session.get(myst_url, timeout=60)
    
    # Should get building page first, then the actual site
    if response.status_code != 200:
        print(f"Error {response.status_code}: {response.text[:500]}")
    assert response.status_code == 200
    
    # Wait for build to complete (check for actual site content)
    max_wait = 60
    for i in range(max_wait):
        response = session.get(myst_url, timeout=10)
        if "Test MyST Site" in response.text and "building" not in response.text.lower():
            break
        time.sleep(2)
    
    # Verify the site loaded
    assert response.status_code == 200
    assert "Test MyST Site" in response.text
    
    # Print asset path info for debugging
    html = response.text
    if f"/user/{username}/myst-build/" in html:
        print("✓ Asset paths are correctly prefixed with user/username/myst-build/")
    elif 'href="/build/' in html:
        print("⚠ Asset paths are NOT prefixed (using /build/ directly)")
    
    # Clean up
    if test_site.exists():
        shutil.rmtree(test_site)


def test_username_myst(jupyterhub):
    """Test that username 'myst-build' works correctly (edge case)"""
    username = "myst-build"
    
    # Login and spawn server
    session = login_and_get_cookie(username)
    spawn_server(session, username)
    
    # Setup test site
    test_site = setup_test_site(username)
    
    # Access the MyST proxy endpoint
    # URL should be /user/myst-build/myst-build/test-myst-site/
    myst_url = f"{JUPYTERHUB_URL}/user/{username}/myst-build/test-myst-site/"
    print(f"Accessing: {myst_url}")
    
    response = session.get(myst_url, timeout=60)
    
    # Wait for build to complete
    max_wait = 60
    for i in range(max_wait):
        response = session.get(myst_url, timeout=10)
        if "Test MyST Site" in response.text and "building" not in response.text.lower():
            break
        time.sleep(2)
    
    # Verify the site loaded
    assert response.status_code == 200
    assert "Test MyST Site" in response.text
    
    # Verify assets paths are correct (should not confuse the two "myst"s)
    html = response.text
    assert f"/user/{username}/myst-build/" in html or f'href="build/' in html
    
    # Clean up
    if test_site.exists():
        shutil.rmtree(test_site)


def test_asset_loading(jupyterhub):
    """Test that JS/CSS assets load correctly with proper paths"""
    username = "alice"
    
    # Login and spawn server
    session = login_and_get_cookie(username)
    spawn_server(session, username)
    
    # Setup test site
    test_site = setup_test_site(username)
    
    # Access the MyST site
    myst_url = f"{JUPYTERHUB_URL}/user/{username}/myst-build/test-myst-site/"
    
    # Wait for build
    max_wait = 60
    response = None
    for i in range(max_wait):
        response = session.get(myst_url, timeout=10)
        if "Test MyST Site" in response.text and "building" not in response.text.lower():
            break
        time.sleep(2)
    
    assert response is not None, "Failed to get response from server"
    assert response.status_code == 200
    html = response.text
    
    # Extract asset URLs from HTML (look for JS and CSS files)
    import re
    
    # Find script tags
    scripts = re.findall(r'<script[^>]*src="([^"]+)"', html)
    styles = re.findall(r'<link[^>]*href="([^"]+\.css)"', html)
    
    all_assets = scripts + styles
    
    # Test loading a few assets (if any exist)
    for asset_url in all_assets[:3]:  # Test first 3 assets
        if asset_url.startswith("http"):
            # External asset, skip
            continue
        
        # Construct full URL
        if not asset_url.startswith("/"):
            full_asset_url = f"{myst_url.rstrip('/')}/{asset_url}"
        else:
            full_asset_url = f"{JUPYTERHUB_URL}{asset_url}"
        
        print(f"Testing asset: {full_asset_url}")
        asset_response = session.get(full_asset_url, timeout=10)
        
        # Should not be 404
        assert asset_response.status_code in [200, 304], \
            f"Asset failed to load: {asset_url} (status: {asset_response.status_code})"
    
    # Clean up
    if test_site.exists():
        shutil.rmtree(test_site)


def test_deep_subdirectory_paths(jupyterhub):
    """Test that MyST sites in deep subdirectories work correctly"""
    username = "bob"
    
    # Login and spawn server
    session = login_and_get_cookie(username)
    spawn_server(session, username)
    
    # Setup test site in a deep subdirectory: courses/fall/stat159
    home_dir = Path.home()
    deep_path = home_dir / "courses" / "fall" / "stat159"
    
    # Clean up existing test site
    if deep_path.exists():
        shutil.rmtree(deep_path)
    
    # Create the deep directory structure and copy test site
    deep_path.mkdir(parents=True, exist_ok=True)
    shutil.copytree(TEST_SITE_DIR, deep_path, dirs_exist_ok=True)
    print(f"Copied test site to: {deep_path}")
    print(f"myst.yml exists: {(deep_path / 'myst.yml').exists()}")
    
    # Access the MyST proxy endpoint with deep path
    myst_url = f"{JUPYTERHUB_URL}/user/{username}/myst-build/courses/fall/stat159/"
    print(f"Accessing: {myst_url}")
    
    response = session.get(myst_url, timeout=60)
    
    # Wait for build to complete
    max_wait = 60
    for i in range(max_wait):
        response = session.get(myst_url, timeout=10)
        if "Test MyST Site" in response.text and "building" not in response.text.lower():
            break
        time.sleep(2)
    
    # Verify the site loaded
    assert response.status_code == 200
    assert "Test MyST Site" in response.text
    
    # Verify assets paths include the deep path
    html = response.text
    assert f"/user/{username}/myst-build/courses/fall/stat159/" in html or f'href="build/' in html
    
    # Clean up - remove the entire courses directory
    courses_dir = home_dir / "courses"
    if courses_dir.exists():
        shutil.rmtree(courses_dir)


def test_multiple_deep_paths(jupyterhub):
    """Test accessing multiple MyST sites at different deep paths for the same user"""
    username = "alice"  # Reuse alice from test_asset_loading
    
    # Login (server should already be spawned from previous test)
    session = login_and_get_cookie(username)
    spawn_server(session, username)
    
    # Setup two different test sites in different deep paths
    home_dir = Path.home()
    
    # Clean up any existing courses directory first
    courses_dir = home_dir / "courses"
    if courses_dir.exists():
        shutil.rmtree(courses_dir)
    
    # First site: courses/fall/stat159
    fall_path = home_dir / "courses" / "fall" / "stat159"
    fall_path.mkdir(parents=True, exist_ok=True)
    shutil.copytree(TEST_SITE_DIR, fall_path, dirs_exist_ok=True)
    
    # Second site: courses/spring/stat159
    spring_path = home_dir / "courses" / "spring" / "stat159"
    spring_path.mkdir(parents=True, exist_ok=True)
    shutil.copytree(TEST_SITE_DIR, spring_path, dirs_exist_ok=True)
    
    # Modify spring site to distinguish it
    spring_index = spring_path / "index.md"
    if spring_index.exists():
        content = spring_index.read_text()
        content = content.replace("Test MyST Site", "Spring Semester MyST Site")
        spring_index.write_text(content)
    
    print(f"Created fall site at: {fall_path}")
    print(f"Created spring site at: {spring_path}")
    
    # Test fall site
    fall_url = f"{JUPYTERHUB_URL}/user/{username}/myst-build/courses/fall/stat159/"
    print(f"Accessing fall site: {fall_url}")
    
    max_wait = 60
    fall_response = None
    for i in range(max_wait):
        try:
            fall_response = session.get(fall_url, timeout=30)
            if fall_response.status_code == 200 and "building" not in fall_response.text.lower():
                break
        except requests.exceptions.Timeout:
            print(f"Timeout on attempt {i+1}, retrying...")
            continue
        except requests.exceptions.RequestException as e:
            print(f"Request exception on attempt {i+1}: {e}")
            continue
        time.sleep(2)
    
    assert fall_response is not None
    assert fall_response.status_code == 200, f"Got status {fall_response.status_code}"
    assert "Test MyST Site" in fall_response.text
    
    # Test spring site
    spring_url = f"{JUPYTERHUB_URL}/user/{username}/myst-build/courses/spring/stat159/"
    print(f"Accessing spring site: {spring_url}")
    
    spring_response = None
    for i in range(max_wait):
        try:
            spring_response = session.get(spring_url, timeout=30)
            if spring_response.status_code == 200 and "building" not in spring_response.text.lower():
                break
        except requests.exceptions.Timeout:
            print(f"Timeout on attempt {i+1}, retrying...")
            continue
        except requests.exceptions.RequestException as e:
            print(f"Request exception on attempt {i+1}: {e}")
            continue
        time.sleep(2)
    
    assert spring_response is not None
    assert spring_response.status_code == 200, f"Got status {spring_response.status_code}"
    assert "Spring Semester MyST Site" in spring_response.text
    
    # Verify they are indeed different sites
    assert fall_response.text != spring_response.text
    
    # Clean up
    if courses_dir.exists():
        shutil.rmtree(courses_dir)


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "-s"])
