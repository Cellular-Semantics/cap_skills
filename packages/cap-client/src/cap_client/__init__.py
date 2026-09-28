"""cap-client: read annotation evidence out of CAP (celltype.info).

No browser, no authentication, no h5ad download -- everything here goes through
CAP's public GraphQL endpoint and the dataset page.

Agents should use the `cap` CLI rather than importing this package; the CLI is
the supported interface and its --json output has stable field names.
"""
from .errors import CapError
from .transport import GraphQLClient

__version__ = "0.1.0"

__all__ = ["CapError", "GraphQLClient", "__version__"]
