# Contributing Code

This project follows the standard GitHub [fork and pull request, triangular, workflow](https://guides.github.com/activities/forking/) and a [trunk based development approach](https://trunkbaseddevelopment.com/):

1. Code modifications are done using short lived branches which are merged into the main trunk.
2. Releases are done from the main trunk, except for **critical** bug fixes. These lead to retroactive creation of a release branch. The bug fix is contributed like all code changes, developed on a branch which is merged into the main trunk. Once merged, the commit is [cherry-picked](https://git-scm.com/docs/git-cherry-pick) into the release branch.
3. Binary and large files are added into the repository using [git-lfs](https://git-lfs.github.com/).

## Adding/Modifying Code

To contribute code, please follow these steps:

### One time setup

1. Fork the repository on GitHub.
2. Clone the fork to a local directory (below, change `your_github_username` to the appropriate value):
```
git clone git@github.com:your_github_username/imaris_extensions.git
git remote add upstream git@github.com:niaid/imaris_extensions.git
```
3. Set up the development environment using the
[environment_dev.yml](environment_dev.yml) or [requirements_dev.txt](requirements_dev.txt) files. This will install all dependencies including those only used during
development (e.g. [pytest](https://docs.pytest.org), [black](https://black.readthedocs.io/en/stable/) etc.):
```
#setup a virtual environment named imaris_dev using your favorite tool (venv, virtualenv etc.)
python -m pip install --upgrade pip
pip install -r requirements_dev.txt
```
or
```
conda env create -f environment_dev.yml
```
4. Activate the virtual environment and configure the git [pre-commit](https://pre-commit.com/) framework:
```
pre-commit install
```
The [.pre-commit-config.yaml](.pre-commit-config.yaml) file contains the specification of the git pre-commit hooks and their settings.
Our minimal settings preclude commits of files that do not conform to the requirements of the black style and flake8 and large files (maximal file size is specified in the pre-commit yaml config file).

5. Install [git-lfs](https://git-lfs.github.com/), instructions from GitHub for all three operating systems are [available here](https://docs.github.com/en/repositories/working-with-files/managing-large-files/installing-git-large-file-storage). In our case, we specified that files with the *.ims* extension will be tracked by git-lfs, see the [.gitattributes](.gitattributes) file (`git lfs ls-files --all` will list all git-lfs tracked files in the repository).

### Development

1. Activate the virtual environment.
2. Checkout a new development branch:
```
git checkout -b new_feature
```
3. Develop, and when done run the black formatter, flake8 and pytest.
```
black path_to_my_new_file.py
python -m flake8 . --show-source --statistics
python -m pytest
```

If you did not configure the development environment correctly or for some reason did not install the pre-commit hooks or disabled them for a commit (i.e. `git commit --no-verify`), don't worry. **All changes are evaluated when the pull request is issued**. So, while we trust code is tested on the local system the continuous integration testing will verify it before we merge it into the main repository.

## Adding data

Use git-lfs to add binary data files. Before adding a file, check which file types or specific files are already tracked by git-lfs (see .gitattributes file). If a file type, as identified by file extension, is not tracked you will need to configure git-lfs to track it before adding it into the repository (e.g. *.onnx*, the Open Neural Network Exchange):
```
git lfs track "*.onnx"
git add segmentation_model.onnx
git commit -m "Adding basic segmentation model weights."
```

## Credit where credit is due

If you haven't already done so, add your details to the contributer's list in the [.zenodo.json](.zenodo.json) file.
