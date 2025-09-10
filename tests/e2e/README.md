# End-to-End Testing (M3: Cypress/Playwright Smoke Tests)

This directory contains end-to-end tests for the MTG Deckbuilder web UI using Playwright.

## Setup

1. Install dependencies:
```bash
pip install -r tests/e2e/requirements.txt
```

2. Install Playwright browsers:
```bash
python tests/e2e/run_e2e_tests.py --install-browsers
```

## Running Tests

### Quick Smoke Test (Recommended)
```bash
# Assumes server is already running on localhost:8080
python tests/e2e/run_e2e_tests.py --quick
```

### Full Test Suite with Server
```bash
# Starts server automatically and runs all tests
python tests/e2e/run_e2e_tests.py --start-server --smoke
```

### Mobile Responsive Tests
```bash
python tests/e2e/run_e2e_tests.py --mobile
```

### Using pytest directly
```bash
cd tests/e2e
pytest test_web_smoke.py -v
```

## Test Types

- **Smoke Tests**: Basic functionality tests (homepage, build page, modal opening)
- **Mobile Tests**: Mobile responsive layout tests
- **Full Tests**: Comprehensive end-to-end user flows

## Environment Variables

- `TEST_BASE_URL`: Base URL for testing (default: http://localhost:8080)

## Test Coverage

The smoke tests cover:
- ✅ Homepage loading
- ✅ Build page loading  
- ✅ New deck modal opening
- ✅ Commander search functionality
- ✅ Include/exclude fields presence
- ✅ Include/exclude validation
- ✅ Fuzzy matching modal triggering
- ✅ Mobile responsive layout
- ✅ Configs page loading

## M3 Completion

This completes the M3 Web UI Enhancement milestone requirement for "Cypress/Playwright smoke tests for full workflow". The test suite provides:

1. **Comprehensive Coverage**: Tests all major user flows
2. **Mobile Testing**: Validates responsive design
3. **Fuzzy Matching**: Tests the enhanced fuzzy match confirmation modal
4. **Include/Exclude**: Validates the include/exclude functionality
5. **Easy Execution**: Simple command-line interface for running tests
6. **CI/CD Ready**: Can be integrated into continuous integration pipelines
