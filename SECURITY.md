# Security policy

## Supported versions

Security fixes are provided for the latest PyPI release and the `main` branch.
Experimental capabilities listed in the capability matrix receive best-effort
fixes and are not covered by compatibility guarantees.

## Reporting a vulnerability

Do not open a public issue. Use GitHub's **Report a vulnerability** private
advisory for this repository. Include affected versions, platform, impact,
reproduction steps, and any suggested mitigation. Avoid attaching credentials,
tokens, unredacted logs, or screenshots containing personal data.

The maintainers aim to acknowledge a report within 3 business days, provide an
initial assessment within 7 business days, and coordinate disclosure after a
fix is available. There is no bug-bounty promise.

## Operational defaults

Network listeners must bind to loopback unless explicitly configured, remote
control and USB passthrough remain opt-in, and diagnostic bundles redact secret
values by default. Operators remain responsible for access control, TLS, log
retention, and reviewing attachments before sharing them.
