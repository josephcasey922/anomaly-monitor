# Publishing v0.2 as an independent public project

The release contains **only synthetic example data**. Do not commit any employer-specific source files, SQL credentials, or real reports. The source is under `src/anomaly_monitor/`; the demo, tests, documentation and Docker-only example are separate.

If creating a new repository:

```powershell
git init
git add .
git status
git commit -m "Anomaly Monitor v0.2.0 release"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPOSITORY.git
git push -u origin main
git tag v0.2.0
git push origin v0.2.0
```

Create the empty repository first; if adding this code to an existing repository, do not force-push over existing history. Carefully inspect `git status` before pushing to avoid files ignored incorrectly.

To install from the published repository:

```powershell
py -3 -m pip install "git+https://github.com/YOUR_USERNAME/YOUR_REPOSITORY.git#egg=anomaly-monitor[app]"
anomaly-monitor app
```

For reproducible workflows, install a tagged version in your virtual environment. Run `python -m pytest -q` to verify in your environment.

**Security boundary:** Streamlit is intended as a *local* single-user exploratory interface. It has no remote-user authentication or per-user data isolation; it must not be exposed publicly with real credentials or confidential datasets without an approved secure deployment architecture.
