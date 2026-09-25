"""XML helpers.

Calling ``defusedxml.defuse_stdlib()`` at import time monkey-patches the
stdlib XML parsers (xml.etree.ElementTree, xml.dom.minidom, xml.sax, ...)
so any subsequent parsing in this package — including accidental imports
by third-party code — is XXE/billion-laughs safe. We still prefer the
explicit ``defusedxml`` API in our own modules for clarity.
"""
import warnings

import defusedxml

# defusedxml 0.7.1's defuse_stdlib() imports its own deprecated cElementTree
# module, so importing this package raised a DeprecationWarning -- an error,
# and a failed ``import je_auto_control``, in any test suite that turns
# warnings into errors. defusedxml 0.8.0rc2 silences it the same way.
with warnings.catch_warnings():
    warnings.filterwarnings("ignore", message="defusedxml.cElementTree is deprecated",
                            category=DeprecationWarning)
    defusedxml.defuse_stdlib()
