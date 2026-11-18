"""App version and the GitHub repository that publishes its releases.

The release workflow (.github/workflows/release.yml) writes the pushed tag (v1.2.3 -> 1.2.3) into VERSION
before building, so a tag is the only place a version number has to be typed."""
VERSION = "1.0.0"
GITHUB_REPO = "ItsRegnalt/NotAFK"  # "owner/name"; empty = update checks are off
