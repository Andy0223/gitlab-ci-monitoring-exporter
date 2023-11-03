# gitlab-ci-monitoring-exporter

## Getting started

This repository is the exporter for retrieving the CI data from Gitlab CI, which contains various dimensions, such as pipeline and job level. Then, transform these data toward Prometheus metrics.

## Clone the repo

```
cd existing_folder
git clone https://github.com/Andy0223/gitlab-ci-monitoring-exporter.git
git checkout dev
git commit -S -m "commit message"
git push -u origin dev
```

## Directory structure and definition

- **gitlabApi**
  - **gitlab.py** - _gitlab class and related methods for projects-pipelines retrieval and runner-jobs retrieval_
- **prometheus**
  - **exporter.py** - _Define prometheus class and related methods for creating metrics and metrics update_
- **main.py** - _execution of fetching metrics and metrics collection, waiting for the pull from prometheus server_
- **Dockefile**
- **poetry.lock**
- **pyproject.toml** - _Poetry configuration files for managing dependencies_
- **requirements.txt** - _A Python requirements file for dependencies and used in docker._
- **run_scripts.sh** - _Dynamically given the argument from helm chart to run different container based on the same docker image_

## Installation

1. Forked this repository and clone it to your local computer
2. Download poetry within global installation to your root(home) directroy
   `curl -sSL https://install.python-poetry.org | python3 -`
3. Configure the PATH and it would be applied after you restart the shell
   `export PATH=$PATH:$HOME/.local/bin`
4. Configure the virtualenv
   `poetry config virtualenvs.in-project true`
5. Use Python3 as the virtual environment for developing
   `poetry env use python3`
6. Start the virtualenv
   `poetry shell`
7. Make sure you have replace the actual token while you're developing

   ```python=
   def get_gitlab_client(self):
       # if you wanna test at local pc, you can replace it with the actual token.
       private_token = os.getenv("PRIVATE_ACCESS_TOKEN")
       if private_token is None:
           raise ValueError("PRIVATE_ACCESS_TOKEN is not set in the environment")

       gl = gitlab.Gitlab(private_token=private_token)
       gl.auth()
       return gl
   ```

