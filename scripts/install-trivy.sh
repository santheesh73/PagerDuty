#!/usr/bin/env bash
# Installs the Trivy scanner at a pinned version, checked against a pinned SHA-256.
#
# Not aquasecurity/trivy-action or setup-trivy: in March 2026 their tags were force-pushed to
# malicious commits, and the v0.69.4 binary was trojaned (CVE-2026-33634, GHSA-69fq-xp46-6x23).
# v0.69.3 predates the attack and is an immutable release. Its signing certificate names
# aquasecurity/trivy's release workflow at refs/tags/v0.69.3, and it was signed on 2026-03-03.
# Bump the version and checksum together, and only to a release whose signature you have checked:
#   cosign verify-blob --bundle trivy_<v>_checksums.txt.sigstore.json \
#     --certificate-identity-regexp 'https://github\.com/aquasecurity/' \
#     --certificate-oidc-issuer https://token.actions.githubusercontent.com trivy_<v>_checksums.txt
#
# Usage: scripts/install-trivy.sh [install-dir]   (default: ./.bin)
set -euo pipefail

VERSION=0.69.3
SHA256=1816b632dfe529869c740c0913e36bd1629cb7688bd5634f4a858c1d57c88b75  # Linux-64bit.tar.gz
DEST=${1:-./.bin}

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
curl -sSfL -o "$tmp/trivy.tgz" \
  "https://github.com/aquasecurity/trivy/releases/download/v${VERSION}/trivy_${VERSION}_Linux-64bit.tar.gz"
echo "${SHA256}  $tmp/trivy.tgz" | sha256sum --check --quiet
mkdir -p "$DEST"
tar -xzf "$tmp/trivy.tgz" -C "$DEST" trivy
"$DEST/trivy" --version | head -1
