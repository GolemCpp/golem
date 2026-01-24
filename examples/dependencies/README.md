# dependencies

## Controlling dependencies globally

To showcase how `master_dependencies.json` work, we suggest you to build this project without and with it.

And each time, have a look at `dependencies.json` created by Golem at the root of the repository. It contains a flat list of all the dependencies needed by the project once resolved `golem resolve`.

Currently, `master_dependencies.json` is forcing the JSON library to `3.10.0`, while the `golemfile.py` is asking for `^3.0.0`.

### Without master_dependencies.json

``` bash
golem configure
golem resolve
golem dependencies
golem build
```

In `dependencies.json`, the JSON library is resolved to `3.12.0`, latest available version today when resolving `^3.0.0`.

### With master_dependencies.json

``` bash
golem configure --master-dependencies-configuration=master_dependencies.json
golem resolve
golem dependencies
golem build
```

In `dependencies.json`, the JSON library is resolved to `3.10.0`, exacly the version forced by `master_dependencies.json`.

