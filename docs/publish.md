# Publishing to PyPI

Releases are published automatically via the `publish.yml` workflow when a semver tag is pushed. No API tokens or secrets are needed — authentication uses [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/) (OIDC).

## One-time setup

### 1. Create the PyPI environment in GitHub

Go to the repository → **Settings** → **Environments** → **New environment** and name it `pypi`.

Optionally add a protection rule (e.g. require a reviewer) to gate releases.

### 2. Register a trusted publisher on PyPI

Go to [pypi.org](https://pypi.org) → account menu → **Publishing** → **Add a new pending publisher** and fill in:

| Field | Value |
|---|---|
| PyPI project name | `ottu` |
| Owner | your GitHub username or org |
| Repository name | `ottu` |
| Workflow name | `publish.yml` |
| Environment name | `pypi` |

This links PyPI to the specific workflow and environment, so only that workflow can publish.

## Triggering a release

Push a semver tag (no `v` prefix):

```bash
git tag 1.0.0
git push origin 1.0.0
```

The workflow will run checks (format, lint, type, tests), build the distribution, and publish to PyPI.

## Local dry run

To inspect the built distribution without publishing:

```bash
uv build
tar tzf dist/*.tar.gz   # source dist contents
unzip -l dist/*.whl     # wheel contents
```

To do a full publish dry run locally, set a PyPI API token (scoped to the project):

```bash
export UV_PUBLISH_TOKEN=pypi-<your-token>
uv publish --dry-run
```
