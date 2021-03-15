## SimpleITK Imaris Extensions

[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black) &nbsp;&nbsp;
![ubuntu / macos / windows (Python 3.7, 3.8)](https://github.com/niaid/imaris_extensions/actions/workflows/main.yml/badge.svg)

This repository contains extensions, plugins, for the [Imaris](https://imaris.oxinst.com/) microscopy image analysis program. They either provide additional image analysis capabilities via the open source [SimpleITK](https://simpleitk.org) image analysis library, or are utilities that allow the user to easily modify meta-data associated with images stored in the Imaris file format (e.g. channel names, colors).

The extensions are designed so that they can be run either as independent programs or via the Imaris extension mechanism. When run as independent programs they can be used on any of the standard operating systems (Windows/OSX/Linux).

**Note**: As the testing data is rather large, we use [git-lfs](https://git-lfs.github.com/). To obtain the data using standard git commands you will have to install git-lfs on your system.

## Setup

1. Install a Python environment.  
The specific Python version you need depends on your version of Imaris (for us this is Python 3.7.0). Running the extensions as independent programs is less restrictive, requiring the use of Python version 3.6 or above.[[Miniconda download](https://docs.conda.io/en/latest/miniconda.html) or [plain Python download](https://www.python.org/downloads/)].
2. Configure and install the required Python packages.

  If using Miniconda/Anaconda:

  * **On Windows**: open the Anaconda Prompt (found under the Anaconda3 start menu).
  * **On Linux/OSX**: on the command line ```source path_to_your_anaconda3/bin/activate base```
```
  cd path_to_your_extensions_directory
  conda env create -f environment.yml
  ```

  If using plain Python:

  Open the command line (a.k.a. command prompt, terminal):
```
cd path_to_your_extensions_directory
python -m pip install --upgrade pip
pip install requirements.txt
```
3. Configure Imaris to point to your Python executable and to the directory containing the extensions (see Imaris manual).  
 **Note**: this is an optional step, if you don't have the Imaris software on the specific machine you can still run the extensions.
4. Edit one of these files, set the path to your Python executable:  
  **Windows**: `run_extensions.bat`  
  **OSX/Linux**: `run_extensions.sh`

5. Run the relevant script:  
 **Windows**: double click the `run_extensions.bat`.  

 **OSX/Linux**: from a terminal, make the script executable `chmod +x run_extensions.sh` and run it `./run_extensions.sh`.  

 **Bonus**: On OSX, you can configure things so that double clicking the script in Finder will run it. In Finder,
 1. Right-click the run_extensions.sh file and select "Open with" and then "Other..."
 2. Change the "Enable" dropdown menu from "Recommended Applications" to "All Applications".
 3. Search for "Terminal" and select it (check the "Always Open With" if you want all shell scripts to be run via terminal, otherwise leave it unchecked).


 ## Extensions Overview

### SimpleITK
 1. XTRegisterSameChannel - Registration of 2D or 3D images that share a common channel (correlation based affine alignment).