## Codex Execution Workflow

- Codex work for the OAF Website must be launched from the OAF Website repository so the website and GraManna workstreams remain isolated.
- Codex prompts should normally be provided as a one-step PowerShell block that the owner can paste directly into the OAF Website terminal.
- Use `Invoke-OAFCodex` for normal website Codex runs.
- In the current PowerShell helper configuration, `Invoke-OAFCodex` copies Codex's final report to the clipboard automatically after a successful run.
- `Invoke-OAFCodexClipboard` is not required merely to receive output on the clipboard; use it only when the prompt itself is being supplied through the clipboard.
- Do not default to the VS Code F4 shortcut for website work unless the owner specifically requests it.
- Every Codex prompt must clearly state that it is working only in the current OAF Website repository.
- Codex must not commit or push changes unless an explicit approved commit checkpoint has been reached.

### Current Supported Codex Modes

The current `Invoke-OAFCodex` helper accepts these modes:

- `SOL / HIGH`
- `SOL / EXTRA HIGH`
- `SOL / MAX`
- `ASTRA / EXTRA HIGH`
- `ASTRA / MAX`

Do not request unsupported modes such as `SOL / MEDIUM` unless the PowerShell helper is later updated to support them.

### Website Visual-Iteration Rule

- Ordinary visual website work does not require app-style validation overhead.
- For small HTML/CSS visual changes, use `SOL / HIGH` with a narrow, lightweight prompt.
- Examples include spacing, colors, image placement, typography, responsive layout, hover effects, button styling, and section arrangement.
- For these changes, owner Eyes & Clicks review in the browser at relevant window sizes remains the primary validation for subjective visual and usability judgments.
- Do not ask Codex to perform extensive validation for simple visual edits unless there is a specific reason.
- Reserve heavier reasoning and validation for structural, cross-page, accessibility, deployment, security, forms, or higher-risk interactive changes.

#### Automated Browser Validation

- Prefer Playwright for automated website browser validation, with checks proportional to the change.
- Keep the working directory in the OAF Website repository and use the verified sibling Python interpreter: `..\GraManna\.venv\Scripts\python.exe`. GraManna's virtual environment contains Playwright 1.61.0, and the shared Chromium browser cache is available. No additional installation is needed for local testing.
- A live smoke test confirmed successful Playwright import, Chromium launch, localhost HTTP 200, and GraManna page load. Browser and temporary server cleanup also passed.
- Serve website pages through localhost when browser testing requires it, and clean up browsers and temporary servers after testing.
- Check responsive layouts, navigation, keyboard behavior, interactive controls, and browser errors as appropriate for the change.
- If the shared interpreter or browser becomes unavailable, report the specific failure before using an alternative validation method. Do not assume Playwright is unavailable simply because the default Python or Node environment cannot import it.
- Automated browser checks complement owner Eyes & Clicks review for subjective visual and usability judgments.

### After Each Codex Run

- Review the Codex final report returned to the clipboard.
- Visually inspect the affected website area in the browser where applicable.
- Request refinements as needed.
- Do not commit or push during active visual iteration unless an approved checkpoint has been reached.