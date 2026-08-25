# A local cookbook

A cookbook is where Golem looks for a recipe: the project file to use for a
dependency that does not ship one of its own.

Golem's default cookbook is the published [GolemCpp/recipes](https://github.com/GolemCpp/recipes),
and this is a local one holding just the two recipes the examples beside it
need.

The examples that use it say so in their own `.golem/config.json`:

```json
{ "cookbooks.locations": "directory+../cookbook" }
```

A recipe directory is named after the identity Golem composes for the
dependency's repository, which is how a lookup finds it:

| repository | recipe directory |
| --- | --- |
| `https://github.com/nlohmann/json.git` | `json@com.github.nlohmann` |
| `https://github.com/microsoft/GSL.git` | `gsl@com.github.microsoft` |

## Editing a recipe

A cookbook is copied into the cache before it is read, and only `golem resolve`
refreshes that copy. So run `golem resolve` after editing a recipe here, or
`golem build` keeps using the copy it already has.