# CI Findings

The full **interactive HTML report** (with filters, sorting, and anomaly explanations)
is available at:

[**:material-chart-bar: Interactive Report**](../report.md){ .md-button .md-button--primary }

!!! tip "Multi-version comparison"
    The interactive report shows results from both the **official uv release** and the
    **custom `joelvaneenwyk/uv` build**. Use the **uv Version** column filter to compare
    results side by side and identify which anomalies the custom build addresses.

---

<!-- The following section is replaced automatically by Windows CI. -->

!!! info "No results yet"

    This page is automatically populated with results from the Windows CI
    pipeline. Once the scenario matrix runs on a Windows runner, the findings
    report will appear here.

    To generate results locally on Windows:

    ```powershell
    uv sync --extra dev
    py-launch-lab matrix run
    py-launch-lab report build --findings docs/findings
    ```

    The generated report replaces this placeholder.
