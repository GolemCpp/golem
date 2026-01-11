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