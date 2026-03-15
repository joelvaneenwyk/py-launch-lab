# Interactive Report

The **full interactive HTML report** with filters, sorting, and anomaly
explanations is the **default landing page** of the deployed site.

The main purpose of this report is to demonstrate that on Windows,
**`pythonw.exe` and GUI-subsystem scripts do not open a Console or Terminal
window**. The report compares multiple `uv` builds side by side and highlights
any cases where the observed behaviour deviates from expectations.

!!! info "Looking for the interactive report?"

    If you're seeing this placeholder page, the interactive report was not
    deployed for this build.  The report is produced by the `generate-report`
    job in the **Windows CI** workflow and replaces this page automatically
    on the [deployed site](/report/).

    To generate the report locally on Windows:

    ```powershell
    uv sync --extra dev
    py-launch-lab matrix run
    py-launch-lab report build
    ```

You can also view the **[CI Findings (Markdown)](findings/report.md)** for a
text-based summary of the latest results.
