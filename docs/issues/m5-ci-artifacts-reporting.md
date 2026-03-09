# Milestone M5 — CI Artifacts and Reporting

> Issue: #8 (<https://github.com/joelvaneenwyk/py-launch-lab/issues/8>)

## Description

Wire up GitHub Actions to run the full scenario matrix on Windows runners, upload evidence artifacts, generate a Markdown summary report from the collected JSON results, and deploy documentation to GitHub Pages.

## How it Works

1. `windows.yml` runs the complete test matrix on Windows CI runners
2. All per-scenario JSON artifacts are uploaded as workflow artifacts
3. `report.py` reads the JSON results and generates a Markdown summary
4. Findings are written to `docs/findings/`
5. `docs.yml` deploys the documentation site (including findings) to GitHub Pages

## Tasks

- [ ] GitHub Actions `windows.yml` runs full matrix on Windows runners
- [ ] Artifacts uploaded to workflow run
- [ ] `report.py` generates Markdown summary from JSON results
- [ ] `docs/findings/` populated with per-run findings
- [ ] `docs.yml` deploys docs to GitHub Pages

## Related Issues

- Depends on [m2-python-vs-pythonw-launch.md](m2-python-vs-pythonw-launch.md) - needs Python launch results
- Depends on [m3-uv-uvw-scenario-coverage.md](m3-uv-uvw-scenario-coverage.md) - needs uv/uvw scenario results
- Depends on [m4-rust-shim-integration.md](m4-rust-shim-integration.md) - needs shim test results

## Next Steps

- [ ] Verify CI workflow triggers on push and pull request
- [ ] Confirm artifact upload captures all JSON results
- [ ] Review generated Markdown report for accuracy and completeness
