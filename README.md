# Continuous-Time Deconvolutional Regression (CDR)
CDR (formerly _deconvolutional time series regression_ or _DTSR_) is a regression technique for modeling temporally diffuse effects (Shain & Schuler, 2018, 2019).

This repository contains source code for the `cdr` Python module as well as support for reproducing published experiments.
Full documentation for the `cdr` module is available at [http://dtsr.readthedocs.io/en/latest/](http://dtsr.readthedocs.io/en/latest/).

CDR models can be trained and evaluated using provided utility executables.
Help strings for all available utilities can be viewed by running `python -m cdr.bin.help`.
Full repository documentation, including an API, is provided at the link above.

Note that some published experiments below also involve fitting LME and GAM models, which require `rpy2` and therefore won't work on Windows systems without some serious hacking.
The `cdr` module is cross-platform and therefore CDR models should train regardless of operating system.

## Installation

### Anaconda (recommended)

Installing into a [conda](https://www.anaconda.com/) environment avoids version clashes between CDR package requirements and your local software environment.
Once you have installed Anaconda, run the following commands from this repository root to install CDR:

    conda env create -f environment.yml
    conda activate cdr
    python setup.py install
    
### Setup.py

If you want to install CDR directly into your system environment, simply run:

    python setup.py install
    
Note that installation or runtime errors can occur if you already have conflicting versions of required Python dependencies, *or* if you have the official build of the Edward library.
In these cases, conda installation is needed.

## Basic usage

Once CDR is installed system-wide as described above (and the `cdr` conda environment is activated, if relevant), the CDR package can be imported into Python as shown

    python import cdr
    
Most users will not need to program with CDR, but will instead in run command-line executables for model fitting and criticism.
These can be run as

    python -m cdr.bin.<EXECUTABLE-NAME> ...
    
For more on usage, see the [docs](http://dtsr.readthedocs.io/en/latest/).


## Reproducing published results

This repository is under active development, and reproducibility of previously published results is not guaranteed from the master branch.
For this reason, repository states associated with previous results are saved in Git branches.
To reproduce those results, checkout the relevant branch and follow the instructions in the `README`.
Current reproduction branches are:

 - `emnlp18`
 - `naacl19`

Thus, to reproduce results from NAACL19, for example, run `git checkout naacl19` from the repository root, and follow instructions in the `README` file.
The reproduction branches are also useful sources of example configuration files to use as templates for setting up your own experiments, although you should consult the docs for full documentation of the structure of CDR experiment configurations.

Published results depend on both (1) datasets and (2) models as defined in experiment-specific configuration files.
In general, we do not distribute data with this repository.
The datasets used can be provided by email upon request.

## Help and support

For questions, concerns, or data requests, contact Cory Shain ([shain.3@osu.edu](shain.3@osu.edu)).
Bug reports can be logged in the issue tracker on [Github](https://github.com/coryshain/dtsr).


## References
Shain, Cory and Schuler, William (2018). Deconvolutional time series regression: A technique for modeling temporally diffuse effects. _EMNLP18_.
Shain, Cory and Schuler, William (2019). Continuous-time deconvolutional regression for psycholinguistic modeling. _PsyArXiv_. [https://doi.org/10.31234/osf.io/whvk5](https://doi.org/10.31234/osf.io/whvk5).