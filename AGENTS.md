# Agent Notes

## Scope

- This folder is the Python implementation of the Golem CLI and its Waf-based build frontend.
- Prefer the implementation and the docs site over assumptions from generated artifacts or published packages.

## Source Of Truth

- [README.md](README.md): the user-facing command flow.
- [docs/Developers.md](docs/Developers.md): local contributor setup and contribution expectations.
- [src/golemcpp/golem/main.py](src/golemcpp/golem/main.py): CLI entry and generated `wscript` handoff.
- [src/golemcpp/golem/settings.py](src/golemcpp/golem/settings.py): every setting Golem understands — configuration key, environment variable, CLI option, default. Read it before answering anything about environment behavior; the docs-site page for environment variables is still incomplete.
- Keep user-facing behavior aligned with the docs sources in [../golemcpp.github.io/content/docs](../golemcpp.github.io/content/docs).

## Environment And Commands

- Requirements are Python 3.10+ and Git. This repo depends on the Waf submodule, so assume a recursive clone is required.
- Development dependencies (pytest, `node-semver`) install with `pip install --group dev`.
- Tests run with `python -m pytest`. [tests/conftest.py](tests/conftest.py) puts `src/` and `waflib/waf` on `sys.path`, so no install step is needed.
  - Fast loop: `python -m pytest tests -q --ignore=tests/test_examples_integration.py`.
  - [tests/test_examples_integration.py](tests/test_examples_integration.py) builds the projects under [examples](examples); it needs a C++ compiler and network access and skips itself otherwise. CI runs the `-k "not qt and not package"` subset on Linux and Windows, see [.github/workflows/examples-integration.yml](.github/workflows/examples-integration.yml).
- Run the CLI from a checkout with the repo launcher [golem](golem) on `PATH`, or with `PYTHONPATH=src:waflib/waf python -m golemcpp.golem`.
- Packaging automation uses `python -m build` in this repo and in [waflib](waflib). See [.github/workflows/python-publish.yml](.github/workflows/python-publish.yml).

## Writing Code

- Match the file you are in: single-quoted strings, `snake_case`, keyword arguments at call sites. Type annotations only where the module already uses them (the `command_*.py` handlers).
- **Documentation is concise.** A docstring is one to four lines. It gives the reason the function exists, the contract a caller cannot read off the signature, or the invariant it holds. It never restates the parameters, never narrates the body, and is left out entirely when the name already says it.
- Prefer one `#` line above a subtle block over a paragraph in a docstring. Explain why, not how.
- No section banners, no ASCII art, no changelog or migration notes in comments; git history covers that.
- Keep one source of truth. Before adding a constant, a default or a lookup table, check whether an existing module already owns it.
- Change what the task needs. Unrelated renames and reformatting make a diff unreviewable, and a contributor is expected to own every line they submit (see [docs/Developers.md](docs/Developers.md)).

## Cross-Platform

- Golem is a cross-platform tool: the same code runs on Windows, Linux and macOS, drives their native toolchains, and is expected to behave identically from the user's point of view. Never assume the host you are on. Platform checks go through `Context.is_windows/is_linux/is_darwin` ([context.py](src/golemcpp/golem/context.py)) or `sys.platform` in the modules that have no context, never through a new detection scheme.
- CI covers Linux and Windows only (see [.github/workflows/examples-integration.yml](.github/workflows/examples-integration.yml)); macOS paths (`is_darwin`, [package_dmg.py](src/golemcpp/golem/package_dmg.py)) are real code no job exercises, so changes there need a local run or an explicit note that they are unverified.
- Paths: build them with `os.path.join`/`pathlib`, never by concatenating separators, and keep them absolute once resolved. A path can legitimately contain spaces, `#`, `%`, `&`, accents or any non-ASCII character — it must survive being written into a generated `wscript`/golemfile, passed to a subprocess and read back. Windows adds drive letters, `\` separators, case-insensitive comparison and the `file:///C:/...` URI shape handled in [source.py](src/golemcpp/golem/source.py).
- Long paths are a Windows constraint, not a preference: cache path minimization exists because compilers such as CL.exe break past the limit (see the `cache.minimization.*` settings in [settings.py](src/golemcpp/golem/settings.py)). Keep cached layouts short, and do not add nesting under a resource root without weighing it.
- Encoding: pass `encoding='utf-8'` to every `open()` for files Golem owns (manifests, config stores, generated project files), because the platform default is not UTF-8 everywhere. Decode subprocess output through `helpers.decode_output`, which falls back to the console encoding and then to UTF-8 with replacement instead of raising.
- Subprocesses: build argument lists and run them with `shell=False` through `helpers.run_task`/`run_git`, so quoting is never hand-rolled per platform. Anything shelling out to a Windows built-in (`rmdir /s /q` in `helpers.remove_tree`) has to quote through `subprocess.list2cmdline`.
- Cover platform-specific behavior with a test that fakes the platform rather than one that only passes on the host: patch the module's `sys.platform` as [tests/test_config_store.py](tests/test_config_store.py) does, or stub `is_windows` as [tests/test_qt_discovery.py](tests/test_qt_discovery.py) does.

## Editing Rules

- Avoid editing [waflib](waflib) unless the task is explicitly about the vendored Waf subtree.
- Cover a change with tests in `tests/test_<module>.py`, next to the ones already there.
- For behavior that only appears in a real build, validate from a consuming project such as those in [examples](examples) rather than touching vendored code.
- Run the fast test loop before handing work back, and say which failures pre-date the change instead of silently fixing or hiding them.

## Useful Hotspots

- [src/golemcpp/golem/main.py](src/golemcpp/golem/main.py): CLI entry, native commands, `wscript` handoff.
- [src/golemcpp/golem/project.py](src/golemcpp/golem/project.py): project-definition API used by golemfiles and recipes.
- [src/golemcpp/golem/context.py](src/golemcpp/golem/context.py): build orchestration, waf options, dependency and recipe resolution.
- [src/golemcpp/golem/settings.py](src/golemcpp/golem/settings.py), [setting_descriptor.py](src/golemcpp/golem/setting_descriptor.py), [config_store.py](src/golemcpp/golem/config_store.py): setting descriptors, the `Settings` object resolving them (CLI option > persisted `golem configure` option > project > environment > local store > global store > default) and the JSON store behind `golem config`.
- [src/golemcpp/golem/cache_configuration.py](src/golemcpp/golem/cache_configuration.py), [cache_manager.py](src/golemcpp/golem/cache_manager.py), [resource_manager.py](src/golemcpp/golem/resource_manager.py): cache layout and resource resolution across cache directories.
