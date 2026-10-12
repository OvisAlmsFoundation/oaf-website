# OAF Website

Start the local DEVELOPMENT website from this repository in Windows PowerShell 5.1:

```powershell
.\ops\Start-DevelopmentWebsite.ps1
```

Chrome opens **http://127.0.0.1:5055/gramanna.html** after the runtime checks pass.
Keep the terminal open. Press **Ctrl+C in that terminal** to stop the server;
closing Chrome does not stop it. Startup details are copied to the clipboard,
and the existing OAF visual alert shows readiness or a blocker. For an automated
check without opening Chrome or an alert, use `-NoBrowser -NoAlert`.

The launcher uses the website `.venv` and only `oaf_website_dev` as
`oaf_website_app`, with the existing Windows Credential Manager reference
`OAF Website/development/PostgreSQL`. It rejects a conflicting `OAF_ENV` and
retains the existing fail-closed database configuration and SCRAM identity checks.
Startup checks schema USAGE and State Request SELECT/INSERT permissions using
read-only queries; it performs no migrations or request submissions.
Missing credentials or permissions require separate owner provisioning/approval;
the launcher supplies no replacement identity and changes no grants.

Browser recognition reuses the existing current-user DPAPI-protected key at
`config/local/state-request-recognition.dpapi` (ignored by Git). Keep this file
across restarts; do not delete or replace it. Its shared helper creates a protected
random key once if absent and never uses the database password as the key.
Recognition uses the existing one-year HttpOnly, SameSite=Lax cookie and CSRF/origin
checks. HTTP is explicitly allowed only for this loopback DEVELOPMENT address.
Use the same Chrome profile and address for repeat visits. Clearing cookies,
changing browsers/profiles, or replacing the key permits a new browser identity.
Other processes running as the same Windows user can access its protected secrets.
