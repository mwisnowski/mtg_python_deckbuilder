# MTG Python Deckbuilder

## [Unreleased]
### Added
- **User accounts**: Self-service registration, login, logout, and per-user file isolation
- **Admin panel** (`/admin/`): Create, deactivate, and delete accounts; grant/revoke admin role; change passwords when SMTP is not configured (hides Change Password when users can self-serve via forgot-password)
- **Env-based admin account**: Synthetic admin configured via `secrets.env`; disable with `ADMIN_ENABLED=0` after promoting a real DB user to admin
- **Profile page** (`/auth/profile`): Authenticated users can change their own password
- **Audit log** (`/admin/audit`): All auth and admin actions recorded, capped at 10,000 rows
- **Welcome & account-created emails**: New registrants and admin-created accounts receive emails when SMTP is configured
- **Password reset**: Forgot-password flow with time-limited tokens; URL logged when SMTP is not configured; form replaced with a "contact your administrator" message when SMTP is disabled
- **Login rate limiting**: Per-IP and per-username lockout
- **`secrets.env` / `secrets.env.example`**: Gitignored credential file for `SESSION_SECRET`, admin credentials, and SMTP settings

### Changed
- Setup, Diagnostics, and Logs pages restricted to admin accounts

### Fixed
_No unreleased changes yet_
