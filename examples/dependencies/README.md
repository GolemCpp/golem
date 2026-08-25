# dependencies

Start a [clean session](#start-a-clean-session) to run commands, if needed.

## Controlling dependencies globally

To showcase how `overrides.json` work, we suggest you to build this project without and with it.

And each time, have a look at `dependencies.json` created by Golem at the root of the repository. It contains a flat list of all the dependencies needed by the project once resolved `golem resolve`.

Currently, `overrides.json` is forcing the JSON library to `3.10.0`, while the `golemfile.py` is asking for `^3.0.0`.

### Without overrides.json

``` bash
golem configure
golem resolve
golem dependencies
golem build
```

In `dependencies.json`, the JSON library is resolved to `3.12.0`, latest available version today when resolving `^3.0.0`.

### With overrides.json

``` bash
golem configure --overrides-configuration=overrides.json
golem resolve
golem dependencies
golem build
```

In `dependencies.json`, the JSON library is resolved to `3.10.0`, exacly the version forced by `overrides.json`.

## Start a clean session

To run the commands without the Golem environment variables that you may have set on your system:

``` bash
# On Windows
clean-session

# On UNIX/Linux
./clean-session
```

## Where the recipes come from

This example depends on libraries that do not ship a Golem project file, so Golem
needs a recipe for each. It reads them from [../cookbook](../cookbook) rather than
from the published cookbook, which [.golem/config.json](.golem/config.json) says:

```json
{ "cookbooks.locations": "directory+../cookbook" }
```

If you copy this example somewhere else, Golem will report that it cannot find the
cookbook, so either take [../cookbook](../cookbook) with it or delete the setting
to fall back on the published one.