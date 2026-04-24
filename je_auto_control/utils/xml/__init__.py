"""XML helpers.

Calling ``defusedxml.defuse_stdlib()`` at import time monkey-patches the
stdlib XML parsers (xml.etree.ElementTree, xml.dom.minidom, xml.sax, ...)
so any subsequent parsing in this package — including accidental imports
by third-party code — is XXE/billion-laughs safe. We still prefer the
explicit ``defusedxml`` API in our own modules for clarity.
"""
import defusedxml

defusedxml.defuse_stdlib()
