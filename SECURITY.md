# Security Policy

## Supported versions

Security fixes are applied to the current development branch. Older release versions may not receive fixes; update to the latest release when possible.

## Reporting a vulnerability

Please do not report security vulnerabilities in public Issues or Discussions. Use GitHub's **Report a vulnerability** action in the repository's Security tab to create a private report. Include the affected version, reproduction steps, impact, and any safe proof of concept. Do not attach real personal data, credentials, or copyrighted media.

If private vulnerability reporting is unavailable, contact the repository owner through the contact method listed on their GitHub profile and ask for a private channel. Please allow maintainers reasonable time to investigate and prepare a fix before public disclosure.

## Deployment guidance

The desktop HTTP service is intended for local use. LAN mode is for a trusted private network with token authentication; it is not an internet-facing server. Do not forward its port publicly. Treat a paired desktop as able to process requests sent by the connected Android app.
