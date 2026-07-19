# MTG Python Deckbuilder

## [Unreleased]
### Added
- **Public REST API** (`/api/v1`): a full JSON API for third-party tools and the upcoming mobile app
  - Deck building (start a build, poll progress, fetch the finished deck) plus deck management (list, view, export, delete, upgrade suggestions)
  - Card, commander, and theme browsing/search; owned-card list management; live TCGPlayer/Card Kingdom price checks; saved headless configs
  - Account registration/login/logout and API key management, authenticated with per-account API keys instead of the website's login cookie
  - Interactive documentation at `/api/v1/docs` (Swagger) and `/api/v1/redoc`; disable both in production with `API_DOCS_ENABLED=0`

### Changed
_No unreleased changes yet_

### Fixed
_No unreleased changes yet_

### Removed
_No unreleased changes yet_

### Security
_No unreleased changes yet_

