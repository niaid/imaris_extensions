## Overview

[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black) &nbsp;&nbsp;
![ubuntu / macos / windows (Python 3.7, 3.8)](https://github.com/niaid/imaris_extensions/actions/workflows/main.yml/badge.svg)
&nbsp;&nbsp;[![https://niaid.github.io/imaris_extensions/](https://img.shields.io/website-up-down-brightgreen-red/http/shields.io.svg)](https://niaid.github.io/imaris_extensions/)

This repository contains extensions, plugins, for the [Imaris](https://imaris.oxinst.com/) (Oxford Instruments) microscopy image analysis program. They either provide additional image analysis capabilities via the open source [SimpleITK](https://simpleitk.org) image analysis library, or are utilities that allow the user to easily modify meta-data associated with images stored in the Imaris file format (e.g. channel names, colors).

The extensions are designed so that they can be run either as independent programs or via the Imaris extension mechanism. When run as independent programs they can be used on any of the standard operating systems (Windows/OSX/Linux).

Software development notes:

1. We use the [black code formatter](https://github.com/psf/black) to ensure uniform code style.
2. The code is tested on Linux/OSX/Windows with Python versions 3.7 and 3.8.
3. As the testing data is rather large, we use [git-lfs](https://git-lfs.github.com/). To obtain the data using standard git commands you will have to install git-lfs on your system.

## Download

1. Dowload code as [zip file](https://github.com/niaid/imaris_extensions/archive/refs/heads/main.zip).
2. Download documentation as [zip file](https://github.com/niaid/imaris_extensions/archive/refs/heads/gh-pages.zip).
3. Clone repository using git (with GitHub account):

  ```
  git clone https://github.com/niaid/imaris_extensions.git
  ```

## Extensions Listing

> :warning: **Corrupt files** will cause the extensions to fail with an error message "*...OSError: Can't read data (inflate() failed)*". In some cases imaris is able to read such files while the extensions fail to do so. A solution, that often works, is to read the file into imaris and then "Save as" to a new file which can then be read by the extensions.

### Algorithms
  1. [XTRegisterSameChannel](http://niaid.github.io/imaris_extensions/XTRegisterSameChannel.html) - Registration of 2D or 3D images that share a common channel (correlation based affine alignment). Sample datasets are freely available on zenodo [![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.4632320.svg)](https://doi.org/10.5281/zenodo.4632320). A video illustrating the usage of the extension is available on [YouTube](https://www.youtube.com/watch?v=rrCajI8jroE).
  2. [XTChannelArithmetic](http://niaid.github.io/imaris_extensions/XTChannelArithmetic.html) - Perform channel arithmetic, and more advanced channel manipulations via short SimpleITK expressions (short SimpleITK programs).
  3. More to come.

### Utilities
  1. [XTConfigureChannelSettings](http://niaid.github.io/imaris_extensions/XTConfigureChannelSettings.html) - Configure channel settings, name, description and visualization configuration specified via a csv file or an Imaris file.
  2. [XTExportChannelSettings](http://niaid.github.io/imaris_extensions/XTExportChannelSettings.html) - Export channel settings, name, description and visualization configuration to a csv file. The resulting csv file can be easily edited and then applied to other imaris files using the XTConfigureChannelSettings extension.
  3. More to come.

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
