"""The one exception type this package raises for expected failures.

Library code never calls sys.exit -- the CLI catches CapError and turns it into
a message on stderr plus a non-zero exit status.
"""


class CapError(Exception):
    """A CAP request failed, or was asked for something that does not exist."""
