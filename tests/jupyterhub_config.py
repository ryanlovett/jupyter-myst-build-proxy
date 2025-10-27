"""
Minimal JupyterHub configuration for testing jupyter-myst-build-proxy

Note: The 'c' object is provided by JupyterHub at runtime.
"""

import os
import sys

# Use DummyAuthenticator - allows any username/password
c.JupyterHub.authenticator_class = 'dummy'

# Allow any user to login (for testing)
c.Authenticator.allowed_users = {'testuser', 'myst-build', 'alice', 'bob'}
c.Authenticator.admin_users = {'testuser'}

# Use SimpleLocalProcessSpawner - spawns servers as local processes
c.JupyterHub.spawner_class = 'simple'

# Don't redirect to /hub/home after login
c.Authenticator.auto_login = False

# Bind to localhost only for security
c.JupyterHub.ip = '127.0.0.1'
c.JupyterHub.port = 8000

# Set the base URL
c.JupyterHub.base_url = '/'

# Configure single-user servers
c.Spawner.default_url = '/lab'
c.Spawner.cmd = [sys.executable, '-m', 'jupyter', 'labhub']
c.Spawner.notebook_dir = '~'  # Start in home directory

# Set environment variables for spawned servers
import os as _os
from pathlib import Path as _Path
c.Spawner.environment = {
    'JUPYTER_ENABLE_LAB': '1',
    'JUPYTER_MYST_BUILD_PROXY_DIR': str(_Path.home()),  # Use actual home directory
}

# Disable HTTPS for testing
c.JupyterHub.ssl_key = ''
c.JupyterHub.ssl_cert = ''

# Increase timeout for slower builds
c.Spawner.http_timeout = 120
c.Spawner.start_timeout = 120

# Log level
c.JupyterHub.log_level = 'INFO'
c.Spawner.log_level = 'INFO'

# Set the data directory for the test
test_dir = os.path.dirname(os.path.abspath(__file__))
c.JupyterHub.cookie_secret_file = os.path.join(test_dir, 'jupyterhub_cookie_secret')
c.JupyterHub.db_url = os.path.join(test_dir, 'jupyterhub.sqlite')

# Shutdown the hub after tests (optional, can be set via API)
c.JupyterHub.shutdown_on_logout = False
