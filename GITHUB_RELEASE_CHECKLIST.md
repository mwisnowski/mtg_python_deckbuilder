# GitHub Release Checklist

## Pre-Release Preparation

### 1. Version Management
- [ ] Update version in `pyproject.toml` (currently 1.0.0)
- [ ] Update version in `__init__.py` if applicable
- [ ] Update any hardcoded version references

### 2. Documentation Updates
- [ ] Update README.md with latest features
- [ ] Update DOCKER.md if needed
- [ ] Create/update CHANGELOG.md
- [ ] Verify all documentation is current

### 3. Code Quality
- [ ] Run tests: `python -m pytest`
- [ ] Check type hints: `mypy code/`
- [ ] Lint code if configured
- [ ] Verify Docker builds: `docker build -t mtg-deckbuilder .`

### 4. Final Testing
- [ ] Test Docker container functionality
- [ ] Test from fresh clone
- [ ] Verify all major features work
- [ ] Check file persistence in Docker

## Release Process

### 1. GitHub Release Creation
1. Go to: https://github.com/mwisnowski/mtg_python_deckbuilder/releases
2. Click "Create a new release"
3. Configure release:
   - **Tag version**: `v1.0.0` (create new tag)
   - **Target**: `main` branch
   - **Release title**: `MTG Python Deckbuilder v1.0.0`
   - **Description**: Use content from RELEASE_NOTES.md

### 2. Release Assets (Optional)
Consider including:
- [ ] Source code (automatic)
- [ ] Docker image reference
- [ ] Windows executable (if using PyInstaller)
- [ ] Requirements file

### 3. Docker Image Release (Optional)
```bash
# Build and tag for GitHub Container Registry
docker build -t ghcr.io/mwisnowski/mtg-deckbuilder:1.0.0 .
docker build -t ghcr.io/mwisnowski/mtg-deckbuilder:latest .

# Login to GitHub Container Registry
echo $GITHUB_TOKEN | docker login ghcr.io -u mwisnowski --password-stdin

# Push images
docker push ghcr.io/mwisnowski/mtg-deckbuilder:1.0.0
docker push ghcr.io/mwisnowski/mtg-deckbuilder:latest
```

### 4. PyPI Release (Optional)
```bash
# Build package
python -m build

# Upload to PyPI
python -m twine upload dist/*
```

## Post-Release

### 1. Documentation Updates
- [ ] Update README.md with release badge
- [ ] Add installation instructions
- [ ] Update Docker Hub description if applicable

### 2. Communication
- [ ] Announce on relevant platforms
- [ ] Update project status
- [ ] Create next milestone/version

### 3. Cleanup
- [ ] Merge any release branches
- [ ] Update development branch
- [ ] Plan next version features

## Quick Commands

```bash
# Check current version
grep version pyproject.toml

# Test Docker build
docker build -t mtg-deckbuilder-test .

# Run final tests
python -m pytest
mypy code/

# Create GitHub release (using gh CLI)
gh release create v1.0.0 --title "MTG Python Deckbuilder v1.0.0" --notes-file RELEASE_NOTES.md
```
