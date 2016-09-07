# Golem Documentation

## Conventions

Build and commit output to a release repo.
Each target has a branch, builds are commited tagged pushed.
Build output contains folders for each sys/conf targeted.

    # Example
    libname-master-win-vc140-x86-st-sh-d-hash/v3.1.0/

## Writing a Library

1. Write some code (including building, testing, debuging, etc.)
2. Getting satisfied of it, commit the changes. :)
3. May repeat from step 1
4. Getting satisfied of previous commits, want to release the work with a version and a tag. :)

### About Releasing

1. Bump version (major, minor or patch)
2. Create a tag with the bumped version and a default message (or the user-specified one)
   git tag -a v0.0.0 -m "message"

## Using a Library

1. Write some code (obviously)
2. Need to link the code with an external lib. :o
3. Specify dependencies (external libs) in the project file.
4. Build and be happy continuing to step 1. :)

### About Specifying a Dependency


    # Reposiroty
    <repo> = <gitserver> + <reponame>

    # Dependency
    <dep> = <repo> + <branch> + <version>

    # Configuration
    <conf> = <os> + <arch> + <compiler> + <runtime> + <type> + <id>


### About Building with Dependencies

For a specific targeted configuration build...

1. Find corresponding dependencies
2. Check existing dependency build in the cache repository.
3. Build needed dependency if no build found in cache.
4. Clone the dependency build cached to a dependency dir.
5. Build the lib against the dependencies.

## Scripts for Memo

```
#!/bin/bash

repo="url"

out=`git ls-remote --heads --exit-code "$repo" $1`
if test $? = 0; then
    echo 'Yes :D'
else
    echo 'No :('
fi

out=`git ls-remote --tags --exit-code "$repo" master | grep $1` 
if test $? = 0; then
    echo 'Yes :D'
else
    echo 'No :('
fi

number_of_commits=$(git rev-list HEAD --count)
git_release_version=$(git describe --tags --always --abbrev=0)
```
