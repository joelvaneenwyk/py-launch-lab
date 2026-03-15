# Copilot Instructions

## Screenshots in Pull Requests

Always include screenshots in pull request descriptions when making changes
that affect any of the following:

- The interactive HTML report (`src/launch_lab/html_report.py`)
- Documentation pages (`docs/`)
- Report generation (`src/launch_lab/report.py`)
- MkDocs configuration (`mkdocs.yml`)

Screenshots help reviewers preview visual changes without needing to build
locally or wait for CI deployment.

### Generating screenshots locally

```bash
# 1. Build the docs site
uv sync --extra docs
uv run mkdocs build --strict

# 2. Serve the site and take screenshots with playwright
pip install playwright
python -m playwright install chromium
python3 -c "
from playwright.sync_api import sync_playwright
import http.server, threading, os

os.chdir('site')
httpd = http.server.HTTPServer(('127.0.0.1', 8080),
                                http.server.SimpleHTTPRequestHandler)
t = threading.Thread(target=httpd.serve_forever, daemon=True)
t.start()

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={'width': 1400, 'height': 900})
    page.goto('http://127.0.0.1:8080/')
    page.screenshot(path='../screenshot.png', full_page=True)
    browser.close()
httpd.shutdown()
"
```

CI workflows (`docs.yml` and `windows.yml`) automatically take screenshots
of the built site and upload them as workflow artifacts for easy review.
