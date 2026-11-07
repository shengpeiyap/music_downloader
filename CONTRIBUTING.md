# Contributing to MusicDesk

Thanks for considering a contribution. MusicDesk is an early-stage project; small, reviewable changes are easiest to validate.

## Before you start

- For bugs, search existing issues and use the bug report template.
- For larger changes, open an issue first to discuss scope and compatibility.
- Do not include copyrighted media, credentials, private user data, signing keys, or downloaded audio in issues or pull requests.

## Development checks

Desktop and Android Python tests use the root `requirements.txt`. Node regression checks require Node.js 20. Run the relevant checks from the repository root before submitting:

```powershell
python -m unittest test_app -v
python -m unittest discover -s android/app/src/test/python -v
node tests/test_android_search_fallback.js
node tests/test_android_processing_route.js
node tests/test_android_ui_gates.js
node tests/test_library_sort.js
node tests/test_friendly_message.js
node tests/test_i18n_connection_copy.js
node tests/test_download_settings_gating.js
```

For Android UI or Java changes, also build the app:

```powershell
cd android
.\gradlew.bat assembleDebug
```

Include the commands you ran and their results in the pull request. If a check cannot run locally, state why. Keep changes focused and add regression coverage for behavior changes.

## Pull requests

- Explain the user-visible problem and proposed change.
- Note affected platforms (desktop, browser, Android) and any migration or compatibility impact.
- Include screenshots for UI changes where useful, without private data.
- Update user-facing documentation when behavior or setup changes.
- Never commit build outputs, generated APKs, local settings, personal credentials, or signing material.

By participating, you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).
