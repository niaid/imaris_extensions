# Imaris Extensions Changelog

All notable changes to this repository are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Each release should describe the changes using the following subsection types:
  * *Added* - new features.
  * *Changed* - changes in existing functionality.
  * *Deprecated* - soon to be removed features.
  * *Removed* - removed features.
  * *Fixed* - bug fixes.

When working on the package, add information under the "Unreleased" heading. In this manner the release notes are
created incrementally, and do not require a concerted effort prior to a release.

Using a manual approach to create the release notes instead of automatically deriving them from the
commits allows us to provide a high level description of the features and issues, yet provide details when those are
needed. This is equivalent to summarizing all activity on a feature branch versus reporting all commits on that branch.

## Unreleased

## v0.1.0

### Added

* XTRegisterSameChannel: Registration of 2D or 3D images that share a common channel (correlation based affine alignment). Sample datasets are freely available on zenodo [![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.4632320.svg)](https://doi.org/10.5281/zenodo.4632320). A video illustrating the usage of the extension is available on [YouTube](https://www.youtube.com/watch?v=rrCajI8jroE).
* XTChannelArithmetic: Perform channel arithmetic, and more advanced channel manipulations via short SimpleITK expressions (short SimpleITK programs).
* XTVirtualHEStain: Create a virtual H&E stain from a fluoresence image and add the RGB image as three new channels to the original image.
* XTConfigureChannelSettings: Configure channel settings, name, description and visualization configuration specified via a csv file or an Imaris file.
* XTExportChannelSettings: Export channel settings, name, description and visualization configuration to a csv file. The resulting csv file can be easily edited and then applied to other imaris files using the XTConfigureChannelSettings extension.
