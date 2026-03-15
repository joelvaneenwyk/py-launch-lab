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
# Generate the HTML report with sample data
python -c "
from launch_lab.html_report import build_html_report
build_html_report(force=True)
"

# Or use playwright to screenshot the built site
pip install playwright
python -m playwright install chromium
python3 -c "
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={'width': 1400, 'height': 900})
    page.goto('file:///path/to/artifacts/html/report.html')
    page.screenshot(path='screenshot.png', full_page=True)
    browser.close()
"
```

CI workflows (`docs.yml` and `windows.yml`) automatically take screenshots
of the built site and upload them as workflow artifacts for easy review.
