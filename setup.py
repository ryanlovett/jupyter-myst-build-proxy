import setuptools
from jupyter_myst_proxy import MYST_CONTENT_PATH

setuptools.setup(
    name="jupyter-myst-proxy",
    version="0.0.1.dev",
    url="https://github.com/ryanlovett/jupyter-myst-proxy",
    author="Ryan Lovett",
    description="Jupyter extension to proxy MyST",
    packages=setuptools.find_packages(),
    keywords=["Jupyter"],
    classifiers=["Framework :: Jupyter"],
    install_requires=["jupyter-server-proxy>4.1.0"],
    entry_points={
        "jupyter_serverproxy_servers": [
            "myst = jupyter_myst_proxy:setup_myst",
            f"{MYST_CONTENT_PATH} = jupyter_myst_proxy:setup_myst_content",
        ]
    },
    # package_data={
    #    'jupyter_myst_proxy': ['icons/myst.svg'],
    # },
)
