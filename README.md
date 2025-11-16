# jupyter-myst-build-proxy

A Jupyter server extension that serves and proxies static MyST websites.

## Overview

`jupyter-myst-build-proxy` helps JupyterHub users development MyST-based websites. It can build the static HTML assets and serve them from a minimal python web server, allowing users to view MyST sites directly in a JupyterHub environment.

## Features

- **Path-based routing**: Access MyST projects at `/myst-build/<project-path>/`
- **On-demand building**: Automatically builds MyST sites when first accessed
- **Rebuild support**: Trigger rebuilds with `?rebuild=1` query parameter
- **Multiple projects**: Serve different MyST projects from subdirectories
- **Error handling**: Shows helpful error page when `myst.yml` is missing

## Installation

```bash
pip install jupyter-myst-build-proxy
```

## Usage

### Basic Usage

With a jupyter application running, visit `/myst-build/<project-path>/` where `<project-path>` is a directory containing a MyST project (with `myst.yml`).

Example 1: Jupyter server on localhost
```
http://localhost:8888/myst-build/my-documentation/
```

Example 2: Jupyter server on a JupyterHub
```
https://jupyterhub.example.edu/user/username/myst-build/my-website/
```

### Configuration

Set the default directory using the `JUPYTER_MYST_BUILD_PROXY_DIR` environment variable to specify an alternative root for where the extension finds MyST projects. The default is the user's current working directory.

### Rebuilding Sites

To force a rebuild of a MyST site, add `?rebuild=1` to any page URL:

```
http://localhost:8888/myst-build/my-documentation/?rebuild=1
```

This will delete the `_build/html` directory and regenerate the site.

#### Rebuild button

To have `jupyter-myst-build-proxy` run a post-build script which injects a "Rebuild" button into your site, set the `JUPYTER_MYST_BUILD_PROXY_POSTBUILD` environment variable to any value.

With this functionality enabled, users click this button instead of editing the URL to trigger a rebuild.

## How It Works

1. When you access `/myst-build/<project-path>/`, the extension:
   - Checks if `<project-path>/myst.yml` exists
   - If the site hasn't been built, runs `myst build --html --ci` with the appropriate `BASE_URL`
   - Serves the static HTML from `<project-path>/_build/html/`

2. The extension uses path-based routing to ensure all assets and navigation links work correctly with the `/myst-build/<project-path>/` prefix.

## Requirements

- `jupyter-server-proxy` >= 4.1.0
- `mystmd` (MyST Markdown CLI tool)

## Project Structure

```
jupyter-myst-build-proxy/
├── jupyter_myst_build_proxy/
│   ├── __init__.py           # Main extension setup
│   ├── static_server.py      # HTTP server for serving MyST sites
│   ├── building.html         # Building status template
│   ├── directory_browser.html # Directory browser template
│   └── logo-square.svg       # MyST logo
├── tests/                    # pytest tests
├── setup.py                  # Package configuration
└── README.md                 # This file
```
