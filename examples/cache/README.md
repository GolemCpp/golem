# cache

Start a [clean session](#start-a-clean-session) to run commands, if needed.

## Controlling the locations

To showcase how to control where dependencies get cached, we suggest to run the following:

``` bash
golem configure --cache-directory=cache-default --define-cache-directories="cache-recipes=.*GolemCpp\/recipes.*|cache-json=.*nlohmann.*"
golem resolve
golem dependencies
golem build
```

This will create 3 cache directories:
- `cache-recipes` will contain any repository matching `.*GolemCpp\/recipes.*`  
Such as the official recipes repository for Golem
- `cache-json` will contain any repository matching `.*nlohmann.*`  
Such as https://github.com/nlohmann/json.git
- `cache-default` will contain any dependency not matched by other cache rules  
Such as https://github.com/microsoft/GSL.git

By default, the cache resolution policy is set on `strict`, which forces dependencies to be stored or found in the the first cache directory matching explicitly the URL.

If we set the cache resolution policy to `weak`, a dependency is allowed to be found in other caches matching the URL, or the default cache.

To illustrate this behavior, we suggest to run the following:

``` bash
golem configure --cache-directory=cache-default --define-cache-directories="cache-recipes=.*GolemCpp\/recipes.*|cache-json=.*nlohmann.*|cache-gsl=.*microsoft.*" --cache-resolution-policy=weak
golem resolve
golem dependencies
golem build
```

`cache-gsl` is added and can contain any repository matching `.*microsoft.*`, such as https://github.com/microsoft/GSL.git. But since the cache resolution policy is set on `weak`, the GSL can be found in other cache directories, therefore Golem picks it from `cache-default`.

Switching the cache resolution policy to `strict`, or removing the option (since the default value is `strict`) will impose to find the GSL in `cache-gsl`. Therefore, this missing cache directory will be created. The GSL in `cache-default` is ignored.

To illustrate this behavior, we suggest to run the following:

``` bash
golem configure --cache-directory=cache-default --define-cache-directories="cache-recipes=.*GolemCpp\/recipes.*|cache-json=.*nlohmann.*|cache-gsl=.*microsoft.*" --cache-resolution-policy=strict
golem resolve
golem dependencies
golem build
```

## Start a clean session

To run the commands without the Golem environment variables that you may have set on your system:

``` bash
# On Windows
clean-session

# On UNIX/Linux
./clean-session
```