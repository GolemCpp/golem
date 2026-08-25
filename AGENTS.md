# Agent Notes

## Scope

- This folder is the Python implementation of the Golem CLI and its Waf-based build frontend.
- Prefer the implementation and the docs site over assumptions from generated artifacts or published packages.

## Source Of Truth

- [README.md](README.md): the user-facing command flow.
- [docs/Developers.md](docs/Developers.md): local contributor setup and contribution expectations.
- [src/golemcpp/golem/main.py](src/golemcpp/golem/main.py): CLI entry and generated `wscript` handoff.
- [src/golemcpp/golem/settings.py](src/golemcpp/golem/settings.py): every setting Golem understands — configuration key, environment variable, CLI option, default. Read it before answering anything about environment behavior; the docs-site page for environment variables is still incomplete.
- [src/golemcpp/golem/resource_manager.py](src/golemcpp/golem/resource_manager.py): how every resource kind (dependency, cookbook, overlay, tool) is fetched into the cache.
- [src/golemcpp/golem/network.py](src/golemcpp/golem/network.py): fetching is a resolve step, so only `golem resolve` and `golem tools install` may reach a remote. Every other command reads what those put in the cache. The rule is checked in `helpers.validate_git_command`. Three places open the scope: `builder.resolve`, `command_tools.handle_install`, and `Context.run_build_script`. The third is there because a project's own script is not Golem fetching a resource. If a command goes online anywhere else, that is a bug. Do not add an exception for it.
- A resource kind is split the way `dependency.py`/`dependency_manager.py` and [tool.py](src/golemcpp/golem/tool.py)/[tool_manager.py](src/golemcpp/golem/tool_manager.py) are: the object a command asked for, holding its own version and what that resolved to, and the manager that caches it. [tool_registry.py](src/golemcpp/golem/tool_registry.py) is the catalogue of `ToolDefinition`s, not an instance of anything.
- [src/golemcpp/golem/source.py](src/golemcpp/golem/source.py): what a location means. `[<kind>+]<locator>[#<version>]`, the kinds that exist, and the detection that fills in an unprefixed one. Adding a kind (archive, SVN) starts at `SOURCE_KINDS`.
- Keep user-facing behavior aligned with the docs sources in [../golemcpp.github.io/content/docs](../golemcpp.github.io/content/docs).

## Environment And Commands

- Requirements are Python 3.10+ and Git. This repo depends on the Waf submodule, so assume a recursive clone is required.
- Development dependencies (pytest, `node-semver`) install with `pip install --group dev`.
- Tests run with `python -m pytest`. [tests/conftest.py](tests/conftest.py) puts `src/` and `waflib/waf` on `sys.path`, so no install step is needed.
- A module directly under `tests/` is shared by every tier and imported by its bare name, so those names have to be unique across the whole suite: [support.py](tests/support.py) builds a test's inputs, [host.py](tests/host.py) says what this machine can run, [example_project.py](tests/example_project.py) drives golem against a copy of an example. A tier keeps its own helpers in a `conftest.py` fixture instead, which is addressed by directory and never imported.
- The suite is split by tier, and every CI leg selects a directory rather than excluding a file. A new test belongs to the tier that can afford to run it.
  - [tests/unit](tests/unit) mocks everything. Fast loop: `python -m pytest tests/unit -q`.
  - [tests/integration](tests/integration) runs the real command line against the projects under [examples](examples); it needs a C++ compiler and network access and skips itself otherwise. Every pull request runs `-m configure`, which stops at configure; the full `-k "not qt and not package"` subset runs nightly and on the way to `main`. See [.github/workflows/tests.yml](.github/workflows/tests.yml).
- Run the CLI from a checkout with the repo launcher [golem](golem) on `PATH`, or with `PYTHONPATH=src:waflib/waf python -m golemcpp.golem`.
- Packaging automation uses `python -m build` in this repo and in [waflib](waflib). See [.github/workflows/python-publish.yml](.github/workflows/python-publish.yml).

## Writing Code

- Match the file you are in: single-quoted strings, `snake_case`, keyword arguments at call sites. Type annotations only where the module already uses them (the `command_*.py` handlers).
- Import the module, not the names inside it: `from golemcpp.golem import source`, then `source.SOURCE_TYPE_GIT`. A qualified name shows the reader which module the constant comes from. It also keeps the import list from growing every time a caller reaches for one more. Classes are the exception and come in directly (`from golemcpp.golem.source import Source`), as do the manager factories (`get_cache_manager` and friends), which stand in for the class they build. Sometimes a local name already takes the module name: `source` is the parameter every `Fetcher` works from, see [fetcher.py](src/golemcpp/golem/fetcher.py). There, import what is needed directly, and leave a line saying why. Otherwise the next reader shadows it back.
- **Start a function or method docstring with a verb, in the imperative**, which is what PEP 257 asks for: `Make the cache key of an item.`, not `Makes the cache key ...` and not `The key identifying an item ...`. Say what calling it does, then what the result means.
  - A property, a class or a module is not an action, so it describes instead: `How much of a source to obtain.`
  - A predicate may be written as the question it answers: `Does the version name a semver range or is it a ref?`. Only one that *only* answers. One that also does work names the work and returns the answer (`Convert what the root holds into what is asked for now, and return whether it can keep being used.`), because a question-shaped name promises no side effects.
  - Most docstrings here predate this rule. Convert one while you are already editing it, rather than sweeping the codebase.
- **Documentation is concise.** A docstring is one to four lines, and is left out entirely when the name already says it. Give the reason the function exists, the contract a caller cannot read off the signature, or the invariant it holds.
  - Never restate the parameters, never narrate the body: explain why, not how.
  - Prefer one `#` line above a subtle block to a paragraph in a docstring.
- **A docstring says only what its module knows.**
  - Never explain by what a caller does with the result: `version_resolver` has no roots and no cache keys, so `require_revision` means the caller needs a commit, not that it names a root after one. When the reason lives a layer up, state the requirement and stop.
  - Never re-teach the tools the reader arrived with. pytest, git and waf behave the way their own documentation says, and a paragraph establishing that background buries the one sentence only this module can give.
  - State the contract, not one consequence of it: `safe to use as a directory name` covers what `never holds a path separator` only illustrates.
  - Name the value, not a word standing in for it: `returns False`, not `reports no`. The signature already says a function returns a bool, so only the docstring can say which bool means what.
  - Never make the documentation its own subject: `This asks about the content.` describes the docstring, where `A resource is installed once the source directory is under its root.` states the fact the reader opened it for. A sentence about the documentation also lets its object stay vague, since nothing in it has to be true of the code.
- **Write plainly.** Name the subject, then say what follows from it.
  - One step per sentence, marked with `therefore`, `so`, `but` or `otherwise`, so the reader does not have to infer the turn: `When a root is pinned to a REVISION, it is pinned on a commit. Therefore there is nothing to fetch when refreshing it.`, not `A REVISION-pinned root is the commit it is named after, so it cannot move and there is nothing for a refresh to fetch.`
  - Use the words the domain already has — git says fetch, ref, branch, tag, reset and clone, Golem says locator, request, pinning, root and resolve — instead of inventing a metaphor such as "re-pointed in place".
  - Prefer the concrete word to the general one, for a noun as much as for a verb: `it writes into the root`, not `it makes modifications`; `the source directory`, not `the content`.
  - Give an example where a term stays abstract: `a reference (e.g. a branch, a tag)`.
- **Show the structure instead of narrating it.**
  - When a function behaves differently in several cases, give each case its own line. A paragraph hides how many cases there are, and a reader looking for theirs has to read all of them.
  - Give parallel things a parallel shape: `requires X because ..., and Y because ...` reads in one pass, where `requires X because ..., and Y to ...` makes the reader parse each half differently.
  - A list is only for items that differ. When two share most of their words the difference is the only thing worth writing, and it belongs in a sentence: `a commit is mandatory` says once what one bullet for the resolution handed in and another for the one that came back said twice.
- **Leave out the flourishes.**
  - Do not pack a relation into a compound adjective: write `a root pinned to a REVISION`, not `a REVISION-pinned root`.
  - Do not give the code intentions it does not have.
  - Do not close a sentence on a punchline such as `..., which is what needs the remote`; state the fact and stop.
  - No section banners, no ASCII art, no changelog or migration notes; git history covers that.
  - Being plain is not being long, so cut a sentence instead of decorating it.
- Keep one source of truth. Before adding a constant, a default or a lookup table, check whether an existing module already owns it.
- Change what the task needs. Unrelated renames and reformatting make a diff unreviewable, and a contributor is expected to own every line they submit (see [docs/Developers.md](docs/Developers.md)).

## Cross-Platform

- Golem is a cross-platform tool. The same code runs on Windows, Linux and macOS, and drives the native toolchain of each. A user must see the same behaviour on all three. Never assume the host you are on. Platform checks go through `Context.is_windows/is_linux/is_darwin` ([context.py](src/golemcpp/golem/context.py)) or `sys.platform` in the modules that have no context, never through a new detection scheme.
- CI covers Linux and Windows only (see [.github/workflows/examples-integration.yml](.github/workflows/examples-integration.yml)); macOS paths (`is_darwin`, [package_dmg.py](src/golemcpp/golem/package_dmg.py)) are real code, but no job exercises them. Therefore a change there needs a local run, or an explicit note that it is unverified.
- Paths: build them with `os.path.join`/`pathlib`, never by concatenating separators, and keep them absolute once resolved. A path can legitimately contain spaces, `#`, `%`, `&`, accents or any non-ASCII character. Therefore it must survive being written into a generated `wscript` or golemfile, passed to a subprocess, and read back. Windows adds drive letters, `\` separators, case-insensitive comparison and the `file:///C:/...` URI shape handled in [source.py](src/golemcpp/golem/source.py).
- Long paths break real builds on Windows. Cache path minimization exists because compilers such as CL.exe fail past the limit (see the `cache.minimization.*` settings in [settings.py](src/golemcpp/golem/settings.py)). Keep cached layouts short, and do not add nesting under a resource root without weighing it.
- Encoding: pass `encoding='utf-8'` to every `open()` for files Golem owns (manifests, config stores, generated project files), because the platform default is not UTF-8 everywhere. Decode subprocess output through `helpers.decode_output`, which falls back to the console encoding and then to UTF-8 with replacement instead of raising.
- Subprocesses: build argument lists and run them with `shell=False` through `helpers.run_task`/`run_git`, so quoting is never hand-rolled per platform. Anything shelling out to a Windows built-in (`rmdir /s /q` in `helpers.remove_tree`) has to quote through `subprocess.list2cmdline`.
- Cover platform-specific behavior with a test that fakes the platform rather than one that only passes on the host: patch the module's `sys.platform` as [tests/unit/test_config_store.py](tests/unit/test_config_store.py) does, or stub `is_windows` as [tests/unit/test_qt_discovery.py](tests/unit/test_qt_discovery.py) does.

## Editing Rules

- Avoid editing [waflib](waflib) unless the task is explicitly about the vendored Waf subtree.
- Cover a change with tests in `tests/unit/test_<module>.py`, next to the ones already there.
- For behavior that only appears in a real build, validate from a consuming project such as those in [examples](examples) rather than touching vendored code.
- Run the fast test loop before handing work back, and say which failures pre-date the change instead of silently fixing or hiding them.

## Useful Hotspots

- [src/golemcpp/golem/main.py](src/golemcpp/golem/main.py): CLI entry, native commands, `wscript` handoff.
- [src/golemcpp/golem/project.py](src/golemcpp/golem/project.py): project-definition API used by golemfiles and recipes.
- [src/golemcpp/golem/context.py](src/golemcpp/golem/context.py): build orchestration, waf options, dependency and recipe resolution.
- [src/golemcpp/golem/settings.py](src/golemcpp/golem/settings.py), [setting_descriptor.py](src/golemcpp/golem/setting_descriptor.py), [config_store.py](src/golemcpp/golem/config_store.py): setting descriptors, the `Settings` object resolving them (CLI option > persisted `golem configure` option > project > environment > local store > global store > default) and the JSON store behind `golem config`.
- [src/golemcpp/golem/cache_configuration.py](src/golemcpp/golem/cache_configuration.py), [cache_manager.py](src/golemcpp/golem/cache_manager.py), [resource_manager.py](src/golemcpp/golem/resource_manager.py): cache layout and resource resolution across cache directories.
