# JupyterHub Integration Tests

This directory contains integration tests for `jupyter-myst-build-proxy` that verify it works correctly with JupyterHub.

## What the Tests Do

The tests spin up a local JupyterHub instance and verify:

1. **Basic MyST build**: MyST sites build correctly and serve content
2. **Asset loading**: JS/CSS assets load from the correct paths (with `/user/{username}/` prefix)
3. **Edge case - username "myst"**: Correctly handles the case where a username is "myst-build" (path becomes `/user/myst-build/myst-build/...`)
4. **Deep project paths**: Projects in subdirectories like `proj/courses/stat134/fall-2025/` work correctly

## Setup

1. **Create a test virtual environment:**

```bash
python -m venv venv-test
source venv-test/bin/activate  # On Windows: venv-test\Scripts\activate
```

2. **Install the extension in editable mode:**

```bash
# From the root directory of the project
pip install -e .
```

3. **Install test dependencies:**

```bash
pip install -r tests/requirements-test.txt
```

4. **Install MyST CLI (if not already installed):**

```bash
npm install -g mystmd
# or
pip install mystmd
```

## Running the Tests

From the root directory of the project:

```bash
cd tests
pytest test_jupyterhub_integration.py -v -s
```

Options:
- `-v`: Verbose output
- `-s`: Show print statements (useful for debugging)
- `--timeout=300`: Set a timeout for tests (in seconds)

To run a specific test:

```bash
pytest test_jupyterhub_integration.py::test_basic_myst_build -v -s
```

## How It Works

1. **JupyterHub Configuration**: The `jupyterhub_config.py` file sets up:
   - `DummyAuthenticator`: Allows login with any username/password (for testing)
   - `SimpleLocalProcessSpawner`: Spawns servers as local processes (no Docker needed)
   - Localhost binding on port 8000
   - Allowed test users: `testuser`, `myst-build`, `alice`, `bob`

2. **Test Flow**:
   - Start JupyterHub in the background
   - Login as a test user
   - Spawn their single-user server
   - Copy the test MyST site to their home directory
   - Access `/user/{username}/myst-build/test-myst-site/`
   - Wait for the site to build
   - Verify the HTML content and asset paths
   - Clean up

3. **Test Site**: A minimal MyST site in `test-site/` with:
   - `index.md`: Home page with links
   - `about.md`, `contact.md`: Additional pages for navigation testing
   - `myst.yml`: Project configuration

## Troubleshooting

### JupyterHub fails to start

- Check if port 8000 is already in use: `lsof -i :8000`
- Check JupyterHub logs for errors
- Ensure you have the correct dependencies installed

### Tests timeout

- MyST builds can take time on first run
- Increase timeout: `pytest test_jupyterhub_integration.py --timeout=600`
- Check that `myst` CLI is installed and working: `myst --version`

### Permission errors

- The tests use your actual home directory for SimpleLocalProcessSpawner
- Ensure you have write permissions to `~/test-myst-site`

### Assets fail to load (404 errors)

- This is what we're testing for! If assets fail to load, it indicates an issue with the base URL handling
- Check the browser dev console or test output for the exact URLs being requested
- Verify the `_PROXY_BASE_URL` is being set correctly in the logs

## Cleanup

After running tests, clean up:

```bash
# Remove test MyST site from home directory
rm -rf ~/test-myst-site

# Remove JupyterHub database (if created outside test dir)
rm -f tests/jupyterhub.sqlite tests/jupyterhub_cookie_secret
```

## CI/CD Integration

To run these tests in CI (GitHub Actions, etc.):

```yaml
- name: Run JupyterHub integration tests
  run: |
    pip install -e .
    pip install -r tests/requirements-test.txt
    cd tests
    pytest test_jupyterhub_integration.py -v --timeout=300
```

Note: CI environments may need additional setup for Node.js/npm to install MyST CLI.
