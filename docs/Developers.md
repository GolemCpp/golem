# Developers

## 🌱 Getting started

### How to install?

**Requirements:** Python 3.10 or later, Git

``` bash
git clone --recursive -b main https://github.com/GolemCpp/golem.git
```

To later update your cloned version of Golem:

``` bash
git pull origin/main
git submodule update --init
```

Golem's repository needs to be added to your **PATH** environment variable. And in a Python environment, install the only needed dependency:

``` bash
pip install node-semver==0.8.0
```

## Contribution expectations

Using AI tools to help develop Golem is allowed.

Vibe coding is not. Any AI-assisted change must be thoroughly reviewed before it is committed.

**Owning the code is paramount:** if you submit a change, you are expected to understand it, validate it, and stand behind it.

Therefore, committing with an AI as the co-author is forbidden. Only humans are responsible for the code committed to Golem.