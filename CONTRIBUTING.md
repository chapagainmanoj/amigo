# Contributing to Amigo

Thank you for improving Amigo. The project welcomes focused fixes, tests, documentation, and
well-scoped features that fit the current product direction.

## Before You Start

- Read [`AGENTS.md`](AGENTS.md) for repository boundaries and required synchronization between
  store and protocol implementations.
- For a substantial change, open an issue before investing significant work so its scope and
  product fit can be agreed first.
- Do not include secrets, production data, private conversations, or personally identifying test
  fixtures in an issue, commit, or pull request.
- Security vulnerabilities follow [`SECURITY.md`](SECURITY.md), not the public issue tracker.

## Local Setup

Amigo requires Python 3.12 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Run the required checks before submitting a pull request:

```bash
python -m pytest tests/ -v
ruff check src tests scripts
python scripts/smoke_check.py --scheduler
cd web && npm ci && npm run lint && npm run build
```

Explain the behavior changed, the reason for the change, and the verification performed in the
pull-request description. Keep unrelated changes out of the same pull request.

## Developer Certificate of Origin

Amigo uses the [Developer Certificate of Origin 1.1](https://developercertificate.org/) instead of
a Contributor License Agreement. By signing off a commit, you certify that you have the right to
submit the contribution under the repository's license.

Sign each commit with Git's `--signoff` option:

```bash
git commit --signoff
```

This adds a trailer in this form:

```text
Signed-off-by: Your Name <you@example.com>
```

Use a real name and an email address associated with the contribution. To add sign-off to the
latest local commit, run `git commit --amend --signoff`; do not rewrite commits that other people
may already depend on.

## License

Unless explicitly identified otherwise, submitted contributions are licensed under the
[GNU Affero General Public License version 3](LICENSE). Third-party materials retain their own
applicable licenses. Submission does not guarantee acceptance, and maintainers may request
changes or decline work that does not fit the project's direction.
