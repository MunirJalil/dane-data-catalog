"""dane-catalog: catalog and query all data published by Colombia's DANE.

Sources:
* datos.gov.co — DANE's open datasets on the national Socrata portal
* microdatos.dane.gov.co — DANE's central microdata archive (NADA)

Example
-------
>>> from dane_catalog.client import HttpClient
>>> from dane_catalog.catalog import load
>>> from dane_catalog.search import search
>>> cat = load()
>>> search(cat, "gran encuesta integrada de hogares", limit=3)["results"][0]["title"]
...
"""

from .catalog import build, load, save
from .client import HttpClient
from .microdata import MicrodataCatalog
from .search import get, search, stats
from .socrata import SocrataCatalog

__version__ = "1.0.0"

__all__ = [
    "HttpClient",
    "SocrataCatalog",
    "MicrodataCatalog",
    "build",
    "load",
    "save",
    "search",
    "get",
    "stats",
    "__version__",
]
