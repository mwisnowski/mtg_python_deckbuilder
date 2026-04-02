# MTG Python Deckbuilder

## [Unreleased]
### Added
- **SBOM & supply chain provenance**: Every tagged release now attaches source SBOMs (SPDX + CycloneDX JSON) for Python dependencies and a CycloneDX container image SBOM to the GitHub Release assets. Build provenance attestations (SLSA-style) are published for the multi-arch Docker image via the GitHub Attestations API. `provenance: mode=max` is enabled on all arch builds.

