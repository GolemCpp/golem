# Agent Notes

## Scope

- This folder is the Python implementation of the Golem CLI and its Waf-based build frontend.
- Prefer the implementation and the docs site over assumptions from generated artifacts or published packages.

## Source Of Truth

- Start with [README.md](README.md) for the user-facing command flow.
- Use [docs/Developers.md](docs/Developers.md) for local contributor setup.
- For implementation details, prefer [src/golemcpp/golem/main.py](src/golemcpp/golem/main.py), [src/golemcpp/golem/project.py](src/golemcpp/golem/project.py), and [src/golemcpp/golem/context.py](src/golemcpp/golem/context.py).
- The docs-site page for environment variables is still incomplete, so environment behavior should be verified in [src/golemcpp/golem/context.py](src/golemcpp/golem/context.py).

## Environment And Commands

- Requirements are Python 3.10+ and Git.
- This repo depends on the Waf submodule. Assume a recursive clone is required.
- Local developer setup in [docs/Developers.md](docs/Developers.md) installs `node-semver==0.8.0` and expects the repo launcher [golem](golem) to be on `PATH`.
- Packaging automation uses `python -m build` in this repo and in [waflib](waflib). See [.github/workflows/python-publish.yml](.github/workflows/python-publish.yml).

## Editing Rules

- Do not invent a repo-wide test command. There is no obvious first-party automated test suite exposed here.
- When validating behavior, prefer end-to-end checks from a consuming project such as those found in [examples](examples) over touching vendored code.
- Avoid editing [waflib](waflib) unless the task is explicitly about the vendored Waf subtree.
- Keep user-facing command behavior aligned with the docs sources in [../golemcpp.github.io/content/docs](../golemcpp.github.io/content/docs).

## Useful Hotspots

- [src/golemcpp/golem/main.py](src/golemcpp/golem/main.py): CLI entry, generated `wscript` handoff.
- [src/golemcpp/golem/project.py](src/golemcpp/golem/project.py): project-definition API used by sample projects and recipes.
- [src/golemcpp/golem/context.py](src/golemcpp/golem/context.py): cache directories, recipes repositories, and environment-driven behavior.