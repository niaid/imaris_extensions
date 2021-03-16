#!/bin/bash

cd "$(dirname "$BASH_SOURCE")"
# provide the full path to the Anaconda/Miniconda
# installation.
PATH_TO_ANACONDA=/toolkits/anaconda3
"$PATH_TO_ANACONDA"/envs/imaris/bin/python ExtensionDriver.py
