# =========================================================================
#
#  Copyright Ziv Yaniv
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0.txt
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#
# =========================================================================


"""
SimpleITK Imaris IO module.

This module enables reading and writing of SimpleITK images from and to the
Imaris file format. It does not support IO for additional data elements stored
in Imaris files (e.g. meshes, spots).

The Imaris file format utilizes hdf5 and is described online:
https://imaris.oxinst.com/support/imaris-file-format

A SimpleITK image read from an Imaris file will contain both the raw pixel
information and a metadata dictionary.

The metadata dictionary contains the following keys-values:
    unit_metadata_key - string denoting the physical units of the image origin,
                        and spacing.
    time_metadata_key - string denoting the time associated with the image in
                        ('%Y-%m-%d %H:%M:%S.%f' -
                        Year-month-day hour:minute:second.microsecond) format.
    channels_metadata_key - XML string denoting channel information.
                            XML structure:

<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:element name="imaris_channels_information">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="channel">
          <xs:complexType>
              <xs:element type="xs:string" name="name"/>
              <xs:element type="xs:string" name="description"/>
              <xs:element type="xs:string" name="color"/>
              <xs:element type="xs:string" name="range"/>
              <xs:element type="xs:string" name="gamma" minOccurs="0" maxOccurs="1"/>
          </xs:complexType>
        </xs:element>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
"""

import h5py
import SimpleITK as sitk
import numpy as np
import copy
import datetime
import xml.etree.ElementTree as et

unit2mm_conversion = {"m": 1000.0, "mm": 1.0, "um": 1.0 / 1000.0, "nm": 1.0 / 1000000.0}
"""Conversion factors between the various units supported by Imaris and mm, which
is the common unit in SimpleITK."""

unit_metadata_key = "unit"
time_metadata_key = "times"
# This is the time format used by most files, includes minutes, seconds and
# microseconds (zero-padded on the left) in some rare cases the time does not
# include the microseconds, so we have a "fallback"
time_str_format = "%Y-%m-%d %H:%M:%S.%f"
fallback_time_str_format = "%Y-%m-%d %H:%M:%S"
channels_metadata_key = "imaris_channels_information"


file_format_versions = ["5.5.0"]
default_dataset_info_dirname = "DataSetInfo"
default_dataset_dirname = "DataSet"

supported_pixel_types = {
    sitk.sitkUInt8: "8-bit unsigned integer",
    sitk.sitkVectorUInt8: "vector of 8-bit unsigned integer",
    sitk.sitkUInt16: "16-bit unsigned integer",
    sitk.sitkVectorUInt16: "vector of 16-bit unsigned integer",
    sitk.sitkUInt32: "32-bit unsigned integer",
    sitk.sitkVectorUInt32: "vector of 32-bit unsigned integer",
    sitk.sitkFloat32: "32-bit float",
    sitk.sitkVectorFloat32: "vector of 32-bit float",
}

# Map SimpleITK pixel types to the corresponding Imaris pixel types.
pixel_type_to_scalar_type = {
    sitk.sitkUInt8: sitk.sitkUInt8,
    sitk.sitkVectorUInt8: sitk.sitkUInt8,
    sitk.sitkUInt16: sitk.sitkUInt16,
    sitk.sitkVectorUInt16: sitk.sitkUInt16,
    sitk.sitkUInt32: sitk.sitkUInt32,
    sitk.sitkVectorUInt32: sitk.sitkUInt32,
    sitk.sitkFloat32: sitk.sitkFloat32,
    sitk.sitkVectorFloat32: sitk.sitkFloat32,
}


def read_metadata(file_name):
    """
    Read the meta-data contained in the Imaris file.

    Parameters
    ----------
    file_name (str): Path to Imaris file from which we read.

    Returns
    -------
    meta_data_dict (dictionary): Dictionary containing the following information:
                                 times (list(datetime)): datetime objects corresponding to the temporal image times.
                                 unit (str): unit of physical size (m, mm, um, nm).
                                 sizes (list(list[int])): number of pixels in volume [x,y,z] for each of the existing resolution levels.
                                 spacings (list(list[float])): spacing in 'units' per resolution level.
                                 origin(list[float]): SimpleITK origin in units. SimpleITK origin
                                                      is at the center of the first voxel.
                                channels_information (list[(i,dict)]): Channel information tuples with first entry the channel index
                                                                      and second entry dictionary that includes 'name',
                                                                      'description','color' or 'color_table', 'alpha', 'range', 'gamma', with
                                                                      'gamma' being optional.
                                storage_settings(list(list[tuple,string,int])): Storage settings per resolution level, tuple with hdf5 chunk
                                                                                size, string denoting compression type (imaris only supports gzip),
                                                                                int representing compression options for gzip this is an int in [0,9].
                                sitk_pixel_type: Image's SimpleITK pixel type.

    """  # noqa
    meta_data_dict = {}
    with h5py.File(file_name, "r") as f:
        if f.attrs["ImarisVersion"].tobytes().decode("UTF-8") in file_format_versions:
            dataset_info_dirname = (
                f.attrs["DataSetInfoDirectoryName"].tobytes().decode("UTF-8")
            )
            dataset_dirname = f.attrs["DataSetDirectoryName"].tobytes().decode("UTF-8")
            time_point_number = int(
                (
                    f[dataset_info_dirname]["TimeInfo"]
                    .attrs["DatasetTimePoints"]
                    .tobytes()
                )
            )
            meta_data_dict["times"] = []
            for i in range(1, time_point_number + 1):
                try:
                    meta_data_dict["times"].append(
                        datetime.datetime.strptime(
                            f[dataset_info_dirname]["TimeInfo"]
                            .attrs[f"TimePoint{i}"]
                            .tobytes()
                            .decode("UTF-8"),
                            time_str_format,
                        )
                    )
                except ValueError:
                    meta_data_dict["times"].append(
                        datetime.datetime.strptime(
                            f[dataset_info_dirname]["TimeInfo"]
                            .attrs[f"TimePoint{i}"]
                            .tobytes()
                            .decode("UTF-8"),
                            fallback_time_str_format,
                        )
                    )
            meta_data_dict["unit"] = (
                f[dataset_info_dirname]["Image"].attrs["Unit"].tobytes().decode("UTF-8")
            )
            resolution_sizes = []
            storage_info = []
            for i in range(len(f[dataset_dirname])):
                resolution_name = f"ResolutionLevel {i}"
                resolution_sizes.append(
                    [
                        int(
                            f[dataset_dirname][resolution_name]["TimePoint 0"][
                                "Channel 0"
                            ]
                            .attrs["ImageSizeX"]
                            .tobytes()
                        ),
                        int(
                            f[dataset_dirname][resolution_name]["TimePoint 0"][
                                "Channel 0"
                            ]
                            .attrs["ImageSizeY"]
                            .tobytes()
                        ),
                        int(
                            f[dataset_dirname][resolution_name]["TimePoint 0"][
                                "Channel 0"
                            ]
                            .attrs["ImageSizeZ"]
                            .tobytes()
                        ),
                    ]
                )
                storage_info.append(
                    [
                        f[dataset_dirname][resolution_name]["TimePoint 0"]["Channel 0"][
                            "Data"
                        ].chunks,
                        f[dataset_dirname][resolution_name]["TimePoint 0"]["Channel 0"][
                            "Data"
                        ].compression,
                        f[dataset_dirname][resolution_name]["TimePoint 0"]["Channel 0"][
                            "Data"
                        ].compression_opts,
                    ]
                )

            meta_data_dict["sizes"] = resolution_sizes
            meta_data_dict["storage_settings"] = storage_info

            # Coordinates of the corners of the imaris volume's bounding box
            min_x = float(f[dataset_info_dirname]["Image"].attrs["ExtMin0"].tobytes())
            max_x = float(f[dataset_info_dirname]["Image"].attrs["ExtMax0"].tobytes())
            min_y = float(f[dataset_info_dirname]["Image"].attrs["ExtMin1"].tobytes())
            max_y = float(f[dataset_info_dirname]["Image"].attrs["ExtMax1"].tobytes())
            min_z = float(f[dataset_info_dirname]["Image"].attrs["ExtMin2"].tobytes())
            max_z = float(f[dataset_info_dirname]["Image"].attrs["ExtMax2"].tobytes())
            x_size = max_x - min_x
            y_size = max_y - min_y
            z_size = max_z - min_z
            meta_data_dict["spacings"] = [
                [x_size / sz[0], y_size / sz[1], z_size / sz[2]]
                for sz in meta_data_dict["sizes"]
            ]

            # SimpleITK image origin is 0.5*(pixel spacing) from the corner of the volume.
            meta_data_dict["origin"] = [
                m_val + 0.5 * spc
                for m_val, spc in zip(
                    [min_x, min_y, min_z], meta_data_dict["spacings"][0]
                )
            ]

            # Get the number of channels from a group that is guarenteed to exist
            num_channels = len(f[dataset_dirname]["ResolutionLevel 0"]["TimePoint 0"])

            # Get the pixel type
            meta_data_dict["sitk_pixel_type"] = sitk.GetImageFromArray(
                f[dataset_dirname]["ResolutionLevel 0"]["TimePoint 0"]["Channel 0"][
                    "Data"
                ][0:1, 0:1, 0:1]
            ).GetPixelID()

            # Get the per-channel metadata.
            channels_information = []
            for i in range(num_channels):
                channel_information = {}
                channel_str = f"Channel {i}"
                channel_information["name"] = (
                    f[dataset_info_dirname][channel_str]
                    .attrs["Name"]
                    .tobytes()
                    .decode("UTF-8")
                )
                if channel_information["name"] == "\x00":  # null byte
                    channel_information["name"] = ""
                channel_information["description"] = (
                    f[dataset_info_dirname][channel_str]
                    .attrs["Description"]
                    .tobytes()
                    .decode("UTF-8")
                )
                if channel_information["description"] == "\x00":  # null byte
                    channel_information["description"] = ""
                color_mode = (
                    f[dataset_info_dirname][channel_str]
                    .attrs["ColorMode"]
                    .tobytes()
                    .decode("UTF-8")
                )
                # color is a list of float values in [0.0, 1.0] in r,g,b order.
                # color table is just a longer list of colors in r,g,b order.
                if color_mode == "BaseColor":
                    color_info = f[dataset_info_dirname][channel_str].attrs["Color"]
                    color_key = "color"
                elif color_mode == "TableColor":
                    # The actual color table is stored either as a dataset or as an attribute
                    if "ColorTable" in f[dataset_info_dirname][channel_str].attrs:
                        color_info = f[dataset_info_dirname][channel_str].attrs[
                            "ColorTable"
                        ]
                    else:
                        color_info = f[dataset_info_dirname][channel_str]["ColorTable"][
                            0:-1
                        ]
                    color_key = "color_table"
                channel_information[color_key] = [
                    float(val) for val in color_info.tobytes().split()
                ]
                channel_information["range"] = [
                    float(val)
                    for val in f[dataset_info_dirname][channel_str]
                    .attrs["ColorRange"]
                    .tobytes()
                    .split()
                ]
                channel_information["alpha"] = float(
                    f[dataset_info_dirname][channel_str].attrs["ColorOpacity"].tobytes()
                )
                try:  # Some images have a gamma value, some don't
                    channel_information["gamma"] = float(
                        f[dataset_info_dirname][channel_str]
                        .attrs["GammaCorrection"]
                        .tobytes()
                    )
                except Exception:
                    pass
                channels_information.append((i, channel_information))
            meta_data_dict["channels_information"] = channels_information
    return meta_data_dict


def _ims_set_nullterm_str_attribute(hdf_object, attribute_name, attribute_value):
    """
    Set the value of an attribute attached to the given object. If the attribute
    does not exist it is created. Attribute is encoded as
    an array of fixed length (length of 1) null terminated strings. This encoding
    is specific to imaris and is problematic. The individual string length should
    be two, 'a\x00', but this is not how imaris encodes it.

    This function uses the low level h5py API because the high level API will
    always write the fixed length strings as H5T_STR_NULLPAD and not H5T_STR_NULLTERM
    which is what Imaris is expecting.

    For additional details see the HDF discourse:
        https://forum.hdfgroup.org/t/nullpad-nullterm-strings/9107

    Parameters
    ----------
    hdf_object (File/Group/Dataset): Attribute will be attached to this object.
    attribute_name (str): Attribute name.
    attribute_value (str): Byte string representation of the attribute value (i.e.
                           b'255' or b'255.000').
    """
    # Because we are dealing with fixed length strings we delete the attribute
    # and create it again with the current size. If the attribute doesn't exist
    # we just catch the exception and ignore.
    try:
        del hdf_object.attrs[attribute_name]
    except KeyError:
        pass
    type_id = h5py.h5t.TypeID.copy(h5py.h5t.C_S1)
    type_id.set_size(1)
    type_id.set_strpad(h5py.h5t.STR_NULLTERM)
    attribute_arr = np.frombuffer(attribute_value, dtype="|S1")
    space = h5py.h5s.create_simple((len(attribute_arr),))
    attribute_id = h5py.h5a.create(
        hdf_object.id, attribute_name.encode("UTF-8"), type_id, space
    )
    attribute_id.write(attribute_arr, mtype=attribute_id.get_type())


def write_channels_metadata(meta_data_dict, file_name, access_mode="a"):
    """
    Write the channel metadata into the given file. If file doesn't exist create it.
    If the file exists, the channel indexes given in the meta_data_dict must be in
    the existing range.

    Parameters
    ----------
    meta_data_dict(dictionary): see dictionary description in the read_metadata function.
    file_name: write to this file.
    access_mode: file access mode, default is append.
    """
    # Open the file for reading and writing. If it doesn't exist, create.
    with h5py.File(file_name, access_mode) as f:
        try:  # If file already exists check the imaris file format version and get number of channels.
            imaris_format_version = f.attrs["ImarisVersion"].tobytes().decode("UTF-8")
            if imaris_format_version not in file_format_versions:
                raise ValueError(
                    f"Unsupported imaris file format version {imaris_format_version}."
                )
            dataset_dirname = f.attrs["DataSetDirectoryName"].tobytes().decode("UTF-8")
            dataset_info_dirname = (
                f.attrs["DataSetInfoDirectoryName"].tobytes().decode("UTF-8")
            )
            num_channels = len(f[dataset_dirname]["ResolutionLevel 0"]["TimePoint 0"])
        except KeyError:  # We are dealing with a new file.
            num_channels = len(meta_data_dict["channels_information"])
            dataset_info_dirname = default_dataset_info_dirname
            dataset_dirname = default_dataset_dirname
            _ims_set_nullterm_str_attribute(f, "ImarisDataSet", b"ImarisDataSet")
            _ims_set_nullterm_str_attribute(f, "ImarisVersion", b"5.5.0")
            _ims_set_nullterm_str_attribute(
                f, "DataSetInfoDirectoryName", dataset_info_dirname.encode("UTF-8")
            )
            _ims_set_nullterm_str_attribute(
                f, "DataSetDirectoryName", dataset_dirname.encode("UTF-8")
            )
            f.attrs["NumberOfDataSets"] = np.array([1], dtype=np.uint32)

            f.create_group(dataset_info_dirname + "/ImarisDataSet")
            _ims_set_nullterm_str_attribute(
                f[dataset_info_dirname]["ImarisDataSet"], "Creator", b"SimpleITK"
            )
            _ims_set_nullterm_str_attribute(
                f[dataset_info_dirname]["ImarisDataSet"], "NumberOfImages", b"1"
            )
            _ims_set_nullterm_str_attribute(
                f[dataset_info_dirname]["ImarisDataSet"],
                "Version",
                str(sitk.Version()).encode("UTF-8"),
            )

            f.create_group(dataset_info_dirname + "/Imaris")
            _ims_set_nullterm_str_attribute(
                f[dataset_info_dirname]["Imaris"], "ThumbnailMode", b"thumbnailNone"
            )
            _ims_set_nullterm_str_attribute(
                f[dataset_info_dirname]["Imaris"],
                "Version",
                str(sitk.Version()).encode("UTF-8"),
            )
            for i in range(num_channels):
                f.create_group(dataset_info_dirname + f"/Channel {i}")
        indexes, _ = zip(*meta_data_dict["channels_information"])
        if not all([i in range(num_channels) for i in indexes]):
            raise ValueError(
                f"The index of one or more channels in meta data dictionary is outside the expected range [0, {num_channels-1}]."  # noqa: E501
            )
        # Write the channel information, if it exists in the dictionary.
        # When modifying an existing file some of the information
        # may not exist, i.e. we are only changing the channel colors.
        # Imaris supports two color modes ['BaseColor', 'TableColor'].
        for i, channel_information in meta_data_dict["channels_information"]:
            channel_str = f"Channel {i}"
            if "name" in channel_information:
                _ims_set_nullterm_str_attribute(
                    f[dataset_info_dirname][channel_str],
                    "Name",
                    channel_information["name"].encode("UTF-8"),
                )
            if "description" in channel_information:
                _ims_set_nullterm_str_attribute(
                    f[dataset_info_dirname][channel_str],
                    "Description",
                    channel_information["description"].encode("UTF-8"),
                )
            prev_color_mode = (
                f[dataset_info_dirname][channel_str]
                .attrs["ColorMode"]
                .tobytes()
                .decode("UTF-8")
                if "ColorMode" in f[dataset_info_dirname][channel_str].attrs
                else ""
            )
            if (
                "color" in channel_information or "color_table" in channel_information
            ) and prev_color_mode == "TableColor":
                del f[dataset_info_dirname][channel_str].attrs["ColorTableLength"]
                if "ColorTable" not in f[dataset_info_dirname][channel_str].attrs:
                    del f[dataset_info_dirname][channel_str]["ColorTable"]
            if "color" in channel_information:
                _ims_set_nullterm_str_attribute(
                    f[dataset_info_dirname][channel_str], "ColorMode", b"BaseColor"
                )
                _ims_set_nullterm_str_attribute(
                    f[dataset_info_dirname][channel_str],
                    "Color",
                    " ".join([f"{v:.3f}" for v in channel_information["color"]]).encode(
                        "UTF-8"
                    ),
                )
            elif "color_table" in channel_information:
                if prev_color_mode == "BaseColor":
                    del f[dataset_info_dirname][channel_str].attrs["Color"]
                # Imaris expects the color table infromation to be either in an attribute
                # or in a dataset.
                # For some reason, I can't get h5py to write the dataset in the format expected by Imaris.
                # String, Fixed length=1, padding=H5T_STR_NULLTERM, cset = H5T_CSET_ASCII
                # The padding is always H5T_STR_NULLPAD.
                # Tried a workaround similar to that described on SO, creating a custom type but that didn't work:
                # https://stackoverflow.com/questions/38267076/how-to-write-a-dataset-of-null-terminated-fixed-length-strings-with-h5py
                # tid = h5py.h5t.C_S1.copy()
                # tid.set_strpad(h5py.h5t.STR_NULLTERM)
                # H5T_C_S1_1 = h5py.Datatype(tid)
                #
                # The current "solution" is to write the color table information as an
                # attribute and if that fails write as dataset so the information isn't lost.
                # If the color table is large (>64K bytes) then writting
                # to attribute will fail as it is larger than the HDF5 limit. We then save it as
                # dataset even if imaris will not read it. We can export the file settings which will
                # export the color table as a text file. We can then import the color table back directly
                # from imaris and save the file.
                # Possibly revisit, using low level h5py API as done for the
                # attribute writing.
                try:
                    f[dataset_info_dirname][channel_str].attrs["ColorTable"] = (
                        np.frombuffer(
                            (
                                " ".join(
                                    [
                                        f"{v:.3f}"
                                        for v in channel_information["color_table"]
                                    ]
                                )
                                + " "
                            ).encode("UTF-8"),
                            dtype="S1",
                        )
                    )
                except RuntimeError:
                    f[dataset_info_dirname][channel_str].create_dataset(
                        "ColorTable",
                        data=np.frombuffer(
                            (
                                " ".join(
                                    [
                                        f"{v:.3f}"
                                        for v in channel_information["color_table"]
                                    ]
                                )
                                + " "
                            ).encode("UTF-8"),
                            dtype="S1",
                        ),
                    )
                _ims_set_nullterm_str_attribute(
                    f[dataset_info_dirname][channel_str],
                    "ColorTableLength",
                    str(int(len(channel_information["color_table"]) / 3)).encode(
                        "UTF-8"
                    ),
                )
                _ims_set_nullterm_str_attribute(
                    f[dataset_info_dirname][channel_str], "ColorMode", b"TableColor"
                )
            if "range" in channel_information:
                _ims_set_nullterm_str_attribute(
                    f[dataset_info_dirname][channel_str],
                    "ColorRange",
                    " ".join([f"{v:.3f}" for v in channel_information["range"]]).encode(
                        "UTF-8"
                    ),
                )
            if "gamma" in channel_information:
                _ims_set_nullterm_str_attribute(
                    f[dataset_info_dirname][channel_str],
                    "GammaCorrection",
                    f'{channel_information["gamma"]:.3f}'.encode("UTF-8"),
                )
            if "alpha" in channel_information:
                _ims_set_nullterm_str_attribute(
                    f[dataset_info_dirname][channel_str],
                    "ColorOpacity",
                    f'{channel_information["alpha"]:.3f}'.encode("UTF-8"),
                )


def write_named_channels_metadata(
    meta_data_dict, file_name, channel_prefix_separator=""
):
    """
    Overwrite meta-data in the Imaris file, where channels are specified using their names. A
    channel name consists of three parts prefix+separtor_character+postfix. The given channel
    name is compared to existing channel names as follows:
    if separtor_character==''
      prefix1+separtor_character+postfix1 == prefix2+separtor_character+postfix2
    else
      postfix1==postfix2
    If the separtor_character appears more than once in the name the postfix is the substring
    that appears after the last instance: abc:def:ghi with separtor_character==':' means
    the prefix is "abc:def" and the postfix is "ghi".

    Parameters
    ----------
    meta_data_dict(dictionary): see dictionary description in the read_metadata function.
    file_name: write to this file.
    channel_prefix_separator: character separator described above.

    Returns
    -------
    bool:  False, if none of the given channels from the meta_data_dict are
           found in the file, otherwise True.

    """
    channelname2index = {}
    # Open the file for reading.
    with h5py.File(file_name, "r") as f:
        dataset_info_dirname = (
            f.attrs["DataSetInfoDirectoryName"].tobytes().decode("UTF-8")
        )
        dataset_dirname = f.attrs["DataSetDirectoryName"].tobytes().decode("UTF-8")

        num_channels = len(f[dataset_dirname]["ResolutionLevel 0"]["TimePoint 0"])
        for i in range(num_channels):
            cname = (
                f[dataset_info_dirname][f"Channel {i}"]
                .attrs["Name"]
                .tobytes()
                .decode("UTF-8")
            )
            if channel_prefix_separator:
                cname = (cname.split(channel_prefix_separator)[-1]).strip()
            channelname2index[cname] = i
    indexed_channel_information = []
    for cname, channel_information in meta_data_dict["channels_information"]:
        if channel_prefix_separator:
            cname = (cname.split(channel_prefix_separator)[-1]).strip()
        if cname in channelname2index:
            indexed_channel_information.append(
                (channelname2index[cname], channel_information)
            )
    if not indexed_channel_information:
        return False
    # Make a copy of the meta-data dictionary and modify the channel information to be index based and not name
    # based.
    new_meta_data_dict = copy.deepcopy(meta_data_dict)
    new_meta_data_dict["channels_information"] = indexed_channel_information
    write_channels_metadata(meta_data_dict, file_name)
    return True


def read(
    file_name,
    time_index=0,
    resolution_index=0,
    channel_index=None,
    sub_ranges=None,
    vector_pixels=False,
    convert_to_mm=False,
):
    """
    Read all or part of an image into a SimpleITK image. All indexing is zero
    based.

    Parameters
    ----------
    file_name: Read from this imaris image.
    time_index: Read data for the specified time index.
    resolution_index: Read data from the specified resolution index.
    channel_index (list of ints or a single int): Read data from specified channel(s),
                                                  if set to None read all channels.
    sub_ranges (list[range, range, range]): Read a sub-range of the image.
    vector_pixels (bool): If True, then the returned image will have vector pixels representing
                          the channels, otherwise it will be a 4D image where the fourth index
                          represents the channel.
    convert_to_mm (bool): The returned image origin and spacing are in the native units (e.g. um)
                          or in mm, native SimpleITK units. This is relevant for registration
                          purposes. If original units are um and they are converted to mm it
                          can lead to computational instabilities because we are dealing with
                          very small numeric values.

    Returns
    -------
    image (SimpleITK.Image): Either a 3D or 4D SimpleITK image, depending on the vector_pixels
                             parameter.
    """
    meta_data_dict = read_metadata(file_name)
    num_channels = len(meta_data_dict["channels_information"])

    # Validate the input.
    if convert_to_mm and meta_data_dict["unit"] not in unit2mm_conversion.keys():
        raise ValueError(
            f'Cannot convert to mm, image units ({meta_data_dict["unit"]}) do not appear in the conversion dictionary.'
        )
    if time_index not in range(len(meta_data_dict["times"])):
        raise ValueError(
            f'Given time index ({time_index}) is outside valid range [0,{len(meta_data_dict["times"])}).'
        )
    if resolution_index not in range(len(meta_data_dict["spacings"])):
        raise ValueError(
            f'Given resolution index ({resolution_index}) is outside valid range [0,{len(meta_data_dict["spacings"])}).'
        )

    if channel_index is not None:
        try:
            _ = iter(channel_index)
        except TypeError:
            channel_index = [channel_index]
        for ci in channel_index:
            if ci not in range(num_channels):
                raise ValueError(
                    f"Given channel index ({ci}) is outside valid range [0,{num_channels})."
                )
    else:
        channel_index = range(num_channels)

    image_origin = meta_data_dict["origin"]
    image_spacing = meta_data_dict["spacings"][resolution_index]
    image_size = meta_data_dict["sizes"][resolution_index]
    read_ranges = [range(0, sz) for sz in image_size]
    if sub_ranges:  # Check that given sub ranges are inside the full image range
        for fr, sr in zip(read_ranges, sub_ranges):
            if sr.start not in fr or (sr.stop - 1) not in fr:
                raise ValueError("Sub ranges are outside the full image extent.")
        read_ranges = sub_ranges
        image_origin = [
            org + sr.start * spc
            for org, spc, sr in zip(image_origin, image_spacing, sub_ranges)
        ]
    if convert_to_mm:
        image_origin = [
            v * unit2mm_conversion[meta_data_dict["unit"]] for v in image_origin
        ]
        image_spacing = [
            v * unit2mm_conversion[meta_data_dict["unit"]] for v in image_spacing
        ]

    with h5py.File(
        file_name, "r", rdcc_nbytes=30 * 1048576
    ) as f:  # open file with 30Mb chunk cache
        dataset_dirname = f.attrs["DataSetDirectoryName"].tobytes().decode("UTF-8")
        sitk_imaris_channels_list = []
        for ci in channel_index:
            sitk_imaris_channels_list.append(
                sitk.GetImageFromArray(
                    f[dataset_dirname][f"ResolutionLevel {resolution_index}"][
                        f"TimePoint {time_index}"
                    ][f"Channel {ci}"]["Data"][
                        read_ranges[2].start : read_ranges[2].stop,  # noqa: E203
                        read_ranges[1].start : read_ranges[1].stop,  # noqa: E203
                        read_ranges[0].start : read_ranges[0].stop,  # noqa: E203
                    ]
                )
            )
            sitk_imaris_channels_list[-1].SetOrigin(image_origin)
            sitk_imaris_channels_list[-1].SetSpacing(image_spacing)
    if len(sitk_imaris_channels_list) > 1:
        if vector_pixels:
            image = sitk.Compose(sitk_imaris_channels_list)
        else:
            image = sitk.JoinSeries(sitk_imaris_channels_list)
    else:
        image = sitk_imaris_channels_list[0]

    image.SetMetaData(
        unit_metadata_key, meta_data_dict["unit"] if not convert_to_mm else "mm"
    )
    image.SetMetaData(
        time_metadata_key,
        datetime.datetime.strftime(
            meta_data_dict["times"][time_index], time_str_format
        ),
    )

    # Encode the Imaris channels information in xml.
    image.SetMetaData(
        channels_metadata_key,
        channels_information_list2xmlstr(
            [meta_data_dict["channels_information"][ci] for ci in channel_index]
        ),
    )

    return image


def channels_information_xmlstr2list(channels_information_xml_str):
    """
    Convert the xml string representing the Imaris channel information to a
    list containing that information, same as in the dictionary returned by
    the read_metadata function.

    Parameters
    ----------
    channels_information_xml_str (string with xml structure):

    Returns
    -------
    List with channel information.
    """
    channels_information = []
    channels_xml_information = list(et.fromstring(channels_information_xml_str))
    for i, channel_xml_info in enumerate(channels_xml_information):
        channel_info = {}
        channel_info["name"] = channel_xml_info.find("name").text
        if channel_info["name"] is None:
            channel_info["name"] = ""
        channel_info["description"] = channel_xml_info.find("description").text
        if channel_info["description"] is None:
            channel_info["description"] = ""
        if channel_xml_info.find("color") is not None:
            channel_info["color"] = [
                float(c) / 255
                for c in channel_xml_info.find("color").text.replace(",", " ").split()
            ]
        elif channel_xml_info.find("color_table") is not None:
            channel_info["color_table"] = [
                float(c) / 255
                for c in channel_xml_info.find("color_table")
                .text.replace(",", " ")
                .split()
            ]
        channel_info["range"] = [
            float(c)
            for c in channel_xml_info.find("range").text.replace(",", " ").split()
        ]
        if channel_xml_info.find("gamma") is not None:  # Gamma is optional
            channel_info["gamma"] = float(channel_xml_info.find("gamma").text)
        channel_info["alpha"] = float(channel_xml_info.find("alpha").text)
        channels_information.append([i, channel_info])
    return channels_information


def channels_information_list2xmlstr(channels_information_list):
    """
    Convert the list containing the Imaris channel information to a
    xml string. Used for encoding the information in a SimpleITK.Image metadata
    dictionary.

    Parameters
    ----------
    channels_information_list (list): list with channel information.

    Returns
    -------
    XML string representation of the channel information.
    """
    # Encode the Imaris channels information in xml.
    xml_root = et.Element(channels_metadata_key)
    xml_root.append(et.Comment("generated by SimpleITK"))

    for _, channel_information in channels_information_list:
        child = et.SubElement(xml_root, "channel")
        current_field = et.SubElement(child, "name")
        current_field.text = channel_information["name"]
        current_field = et.SubElement(child, "description")
        current_field.text = channel_information["description"]
        # set the color information
        if "color" in channel_information:
            current_field = et.SubElement(child, "color")
            color_info = channel_information["color"]
        elif "color_table" in channel_information:
            current_field = et.SubElement(child, "color_table")
            color_info = channel_information["color_table"]
        current_field.text = ", ".join([str(int(c * 255 + 0.5)) for c in color_info])
        current_field = et.SubElement(child, "range")
        current_field.text = (
            f'{channel_information["range"][0]}, {channel_information["range"][1]}'
        )
        current_field = et.SubElement(child, "alpha")
        current_field.text = str(channel_information["alpha"])
        if "gamma" in channel_information:  # Some images have gamma value some not
            current_field = et.SubElement(child, "gamma")
            current_field.text = str(channel_information["gamma"])

    # Specify encoding as unicode to get a regular string, default is bytestring
    return et.tostring(xml_root, encoding="unicode")


def write(sitk_image, file_name):
    """
    Write the given image to the file in Imaris format. If the SimpleITK image
    metadata dictionary contains information describing the channels and their
    display settings in Imaris these are used otherwise a default repetitive
    RGB color scheme is used.

    Parameters
    ----------
    sitk_image (SimpleITK.Image): Input image in SimpleITK format.
    file_name (string): Output file name.
    """
    vector_pixels = sitk_image.GetNumberOfComponentsPerPixel() > 1
    if vector_pixels:
        number_of_channels = sitk_image.GetNumberOfComponentsPerPixel()
    elif sitk_image.GetDimension() == 4:
        number_of_channels = sitk_image.GetSize()[3]
    else:
        number_of_channels = 1
    # Validate the input.
    if sitk_image.GetPixelID() not in supported_pixel_types:
        raise TypeError(
            f"Imaris format does not support pixel type {sitk_image.GetPixelIDTypeAsString()}.\nSupported types include: "  # noqa: E501
            + ", ".join(list(supported_pixel_types.values()))
            + "."
        )
    if not (
        np.isclose(
            np.array(sitk_image.GetDirection()),
            np.eye(sitk_image.GetDimension()).ravel(),
        )
    ).all():
        raise TypeError(
            "Imaris format does not support non-identity direction cosine matrix."
        )

    meta_data_dict = {}
    channels_information = []
    try:
        channels_information = channels_information_xmlstr2list(
            sitk_image.GetMetaData(channels_metadata_key)
        )
        if len(channels_information) != number_of_channels:
            raise ValueError(
                f"Corrupt SimpleITK image, number of channels does not match meta data dictionary entry (key: {channels_metadata_key})"  # noqa: E501
            )
    except RuntimeError:  # channels information is missing, we'll create it
        default_colors = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
        for i in range(number_of_channels):
            channel_info = {}
            channel_info["name"] = f"ch {i+1}"
            channel_info["description"] = ""
            channel_info["color"] = default_colors[i % len(default_colors)]
            channel_info["range"] = [0.0, 255.0]
            channel_info["gamma"] = 1.0
            channel_info["alpha"] = 1.0
            channels_information.append((i, channel_info))

    meta_data_dict["channels_information"] = channels_information
    write_channels_metadata(
        meta_data_dict=meta_data_dict, file_name=file_name, access_mode="w"
    )

    with h5py.File(file_name, "a") as f:
        dataset_info_dirname = default_dataset_info_dirname
        dataset_dirname = default_dataset_dirname

        f.create_group(dataset_info_dirname + "/TimeInfo")
        _ims_set_nullterm_str_attribute(
            f[dataset_info_dirname]["TimeInfo"], "DatasetTimePoints", b"1"
        )
        _ims_set_nullterm_str_attribute(
            f[dataset_info_dirname]["TimeInfo"], "FileTimePoints", b"1"
        )
        # For some reason the TimePoint attributes start with 1 and not 0.
        _ims_set_nullterm_str_attribute(
            f[dataset_info_dirname]["TimeInfo"],
            "TimePoint1",
            (
                sitk_image.GetMetaData(time_metadata_key).encode("UTF-8")
                if sitk_image.HasMetaDataKey(time_metadata_key)
                else str(datetime.datetime.now()).encode("UTF-8")
            ),
        )
        f.create_group(dataset_info_dirname + "/Image")
        unit_str = (
            sitk_image.GetMetaData(unit_metadata_key)
            if sitk_image.HasMetaDataKey(unit_metadata_key)
            else "mm"
        )
        _ims_set_nullterm_str_attribute(
            f[dataset_info_dirname]["Image"], "Unit", unit_str.encode("UTF-8")
        )
        image_size = sitk_image.GetSize()[
            0:3
        ]  # Get the size for vector or scalar pixel types
        _ims_set_nullterm_str_attribute(
            f[dataset_info_dirname]["Image"], "X", str(image_size[0]).encode("UTF-8")
        )
        _ims_set_nullterm_str_attribute(
            f[dataset_info_dirname]["Image"], "Y", str(image_size[1]).encode("UTF-8")
        )
        _ims_set_nullterm_str_attribute(
            f[dataset_info_dirname]["Image"], "Z", str(image_size[2]).encode("UTF-8")
        )
        image_origin = sitk_image.GetOrigin()[0:3]
        image_spacing = sitk_image.GetSpacing()[0:3]
        min_ext = [org - 0.5 * spc for org, spc in zip(image_origin, image_spacing)]
        image_edge = (
            sitk_image.TransformIndexToPhysicalPoint(image_size)
            if vector_pixels or number_of_channels == 1
            else sitk_image.TransformIndexToPhysicalPoint(image_size + (0,))[0:3]
        )
        max_ext = [edg - 0.5 * spc for edg, spc in zip(image_edge, image_spacing)]
        _ims_set_nullterm_str_attribute(
            f[dataset_info_dirname]["Image"],
            "ExtMin0",
            str(min_ext[0]).encode("UTF-8"),
        )
        _ims_set_nullterm_str_attribute(
            f[dataset_info_dirname]["Image"],
            "ExtMin1",
            str(min_ext[1]).encode("UTF-8"),
        )
        _ims_set_nullterm_str_attribute(
            f[dataset_info_dirname]["Image"],
            "ExtMin2",
            str(min_ext[2]).encode("UTF-8"),
        )
        _ims_set_nullterm_str_attribute(
            f[dataset_info_dirname]["Image"],
            "ExtMax0",
            str(max_ext[0]).encode("UTF-8"),
        )
        _ims_set_nullterm_str_attribute(
            f[dataset_info_dirname]["Image"],
            "ExtMax1",
            str(max_ext[1]).encode("UTF-8"),
        )
        _ims_set_nullterm_str_attribute(
            f[dataset_info_dirname]["Image"],
            "ExtMax2",
            str(max_ext[2]).encode("UTF-8"),
        )

        for i in range(number_of_channels):
            grp = f.create_group(
                dataset_dirname + f"/ResolutionLevel 0/TimePoint 0/Channel {i}"
            )
            _ims_set_nullterm_str_attribute(
                grp, "ImageSizeX", str(image_size[0]).encode("UTF-8")
            )
            _ims_set_nullterm_str_attribute(
                grp, "ImageSizeY", str(image_size[1]).encode("UTF-8")
            )
            _ims_set_nullterm_str_attribute(
                grp, "ImageSizeZ", str(image_size[2]).encode("UTF-8")
            )
            if vector_pixels:
                channel = sitk.VectorIndexSelectionCast(sitk_image, i)
            elif number_of_channels > 1:
                channel = sitk_image[:, :, :, i]
            else:
                channel = sitk_image
            # Save the channel information using the hdf5 chunking mechanism and compress.
            # Imaris recommends a 3D chunk size corresponding to about 1Mb. This is a bit
            # complicated so we let the hdf5 automatically guess a good chunk size by setting
            # chunks=True.
            # Imaris only supports gzip and example files have compression level 2 (options are in [0,9]).
            channel_arr_view = sitk.GetArrayViewFromImage(channel)
            grp.create_dataset(
                "Data",
                data=channel_arr_view,
                chunks=True,
                compression="gzip",
                compression_opts=2,
            )
            _write_channel_histogram(grp, channel_arr_view, channel.GetPixelID())


def _write_channel_histogram(grp, channel_arr_view, pixel_id):
    min_pixel_value = channel_arr_view.min()
    max_pixel_value = channel_arr_view.max()
    _ims_set_nullterm_str_attribute(
        grp, "HistogramMin", f"{min_pixel_value:.3f}".encode("UTF-8")
    )
    _ims_set_nullterm_str_attribute(
        grp, "HistogramMax", f"{max_pixel_value:.3f}".encode("UTF-8")
    )
    channel_histogram, _ = np.histogram(channel_arr_view, bins=256)
    grp.create_dataset(
        "Histogram",
        data=channel_histogram,
        chunks=True,
        compression="gzip",
        compression_opts=2,
    )
    # A pixel type which has a range larger than [0,255], file also has a
    # histogram of 1024 bins for these types
    if pixel_id in [sitk.sitkFloat32, sitk.sitkUInt16, sitk.sitkUInt32]:
        _ims_set_nullterm_str_attribute(
            grp, "HistogramMin1024", f"{min_pixel_value:.3f}".encode("UTF-8")
        )
        _ims_set_nullterm_str_attribute(
            grp, "HistogramMax1024", f"{max_pixel_value:.3f}".encode("UTF-8")
        )
        channel_histogram, _ = np.histogram(channel_arr_view, bins=1024)
        grp.create_dataset(
            "Histogram1024",
            data=channel_histogram,
            chunks=True,
            compression="gzip",
            compression_opts=2,
        )


def _get_chunk_size(image_size, sitk_pixel_type):
    # Sizes for 1Mb chunks based on pixel type
    chunk_sizes = {
        sitk.sitkUInt8: [
            (1, 1024, 1024),
            (4, 512, 512),
            (16, 256, 256),
            (64, 128, 128),
        ],
        sitk.sitkUInt16: [(2, 512, 512), (8, 256, 256), (32, 128, 128)],
        sitk.sitkFloat32: [(4, 256, 256), (16, 128, 128)],
    }
    try:
        chunk_options = chunk_sizes[sitk_pixel_type]
    except Exception:
        raise ValueError("Cannot determine chunk size, given unsupported pixel type.")
    c_index = 0
    z_diff = abs(image_size[2] - chunk_options[0][0])
    for i, co in enumerate(chunk_options[1:], 1):
        cur_z_diff = abs(image_size[2] - co[0])
        if cur_z_diff < z_diff:
            c_index = i
            z_diff = cur_z_diff
    # chunk shape must not be greater than data shape in any dimension.
    return tuple(
        np.minimum(
            chunk_options[c_index], (image_size[2], image_size[1], image_size[0])
        )
    )


def append_channels(sitk_image, file_name, time_index=0):
    """
    Append a single or multi-channel SimpleITK image to a specific time point.
    Note that a valid Imaris file is expected to have the same number of channels
    at every time point. Thus, this function should be called for all time points.

    The rationale for allowing the setting of a single time point is that it is
    a common case, single time point images. Also, when dealing with multi time
    point images, we do not want to keep a 4D dataset in memory for appending.
    This function allows the user to use 3D multi-channel images per time point,
    and write them in turn. It is up to the caller to ensure that all channels
    have been added to all time points.

    Parameters
    ----------
    sitk_image (SimpleITK.Image): A 3D or 4D image.
    file_name (string): Imaris format file name to which we append.
    time_index (int>=0): Time index to which the data is appended.
    """

    # Data validation
    existing_image_metadata = read_metadata(file_name)
    # Compare existing and new image sizes.
    new_image_size = sitk_image.GetSize()[
        0:3
    ]  # Get the size for vector or scalar pixel types
    for esz, nsz in zip(existing_image_metadata["sizes"][0], new_image_size):
        if esz != nsz:
            raise ValueError(
                "New channels image size does not match existing channel size."
            )

    if (
        pixel_type_to_scalar_type[sitk_image.GetPixelID()]
        != existing_image_metadata["sitk_pixel_type"]
    ):
        raise ValueError(
            "New channels image pixel type does not match existing channels image pixel type."
        )

    # Compare existing and new image origins and spacings using SimpleITK epsilon.
    existing_image = sitk.Image([1, 1, 1], existing_image_metadata["sitk_pixel_type"])
    existing_image.SetOrigin(existing_image_metadata["origin"])
    existing_image.SetSpacing(existing_image_metadata["spacings"][0])
    new_image = sitk.Image([1, 1, 1], existing_image_metadata["sitk_pixel_type"])
    new_image.SetOrigin(sitk_image.GetOrigin()[0:3])
    new_image.SetSpacing(sitk_image.GetSpacing()[0:3])
    try:
        existing_image + new_image
    except Exception:
        raise ValueError(
            "New channels do not have same origin or spacing as existing image."
        )

    # Convert to vector pixels, SimpleITK does not support resampling 4D images which
    # we need in order to create the imaris pyramid structure.
    if sitk_image.GetDimension() == 4:
        sitk_image = sitk.Compose(
            [sitk_image[:, :, :, i] for i in range(sitk_image.GetSize()[3])]
        )

    number_of_channels = sitk_image.GetNumberOfComponentsPerPixel()
    # Start by appending the channels as the metadata writing checks that the channels already exist.
    with h5py.File(file_name, "a") as f:
        dataset_dirname = f.attrs["DataSetDirectoryName"].tobytes().decode("UTF-8")
        current_sitk_image = sitk_image
        # Need to append the channels at all resolution levels.
        for res_index in range(len(f[dataset_dirname])):
            resolution_name = f"ResolutionLevel {res_index}"
            if res_index == 0:
                cur_image_size = sitk_image.GetSize()
                current_sitk_image = sitk_image
            else:
                cur_image_size = [
                    int(
                        f[dataset_dirname][resolution_name]["TimePoint 0"]["Channel 0"]
                        .attrs["ImageSizeX"]
                        .tobytes()
                    ),
                    int(
                        f[dataset_dirname][resolution_name]["TimePoint 0"]["Channel 0"]
                        .attrs["ImageSizeY"]
                        .tobytes()
                    ),
                    int(
                        f[dataset_dirname][resolution_name]["TimePoint 0"]["Channel 0"]
                        .attrs["ImageSizeZ"]
                        .tobytes()
                    ),
                ]
                # Compute the new spacing, if there is a single slice along any dimension then we set the spacing to one.  # noqa: E501
                new_spacing = [
                    (ns - 1) * nspc / (cs - 1) if cs > 1 else 1
                    for ns, nspc, cs in zip(
                        new_image_size, sitk_image.GetSpacing(), cur_image_size
                    )
                ]
                current_sitk_image = sitk.Resample(
                    sitk_image,
                    cur_image_size,
                    sitk.Transform(),
                    sitk.sitkLinear,
                    sitk_image.GetOrigin(),
                    new_spacing,
                    sitk_image.GetDirection(),
                    0,
                    sitk_image.GetPixelID(),
                )

            # Get the chunking and compression level from existing channel
            existing_chunk_size = f[dataset_dirname][resolution_name]["TimePoint 0"][
                "Channel 0"
            ]["Data"].chunks
            existing_compression = f[dataset_dirname][resolution_name]["TimePoint 0"][
                "Channel 0"
            ]["Data"].compression
            existing_compression_opts = f[dataset_dirname][resolution_name][
                "TimePoint 0"
            ]["Channel 0"]["Data"].compression_opts
            # As chunk size cannot be larger than the image dimensions we may need to zero pad the written numpy array
            padding = [
                (0, csz - isz) if isz < csz else (0, 0)
                for isz, csz in zip(
                    current_sitk_image.GetSize()[::-1], existing_chunk_size
                )
            ]
            time_index_existing_number_of_channels = len(
                f[dataset_dirname][resolution_name][f"TimePoint {time_index}"]
            )
            for i in range(
                time_index_existing_number_of_channels,
                number_of_channels + time_index_existing_number_of_channels,
            ):
                grp = f.create_group(
                    dataset_dirname
                    + "/"
                    + resolution_name
                    + f"/TimePoint {time_index}/Channel {i}"
                )
                _ims_set_nullterm_str_attribute(
                    grp,
                    "ImageSizeX",
                    f[dataset_dirname][resolution_name]["TimePoint 0"]["Channel 0"]
                    .attrs["ImageSizeX"]
                    .tobytes(),
                )
                _ims_set_nullterm_str_attribute(
                    grp,
                    "ImageSizeY",
                    f[dataset_dirname][resolution_name]["TimePoint 0"]["Channel 0"]
                    .attrs["ImageSizeY"]
                    .tobytes(),
                )
                _ims_set_nullterm_str_attribute(
                    grp,
                    "ImageSizeZ",
                    f[dataset_dirname][resolution_name]["TimePoint 0"]["Channel 0"]
                    .attrs["ImageSizeZ"]
                    .tobytes(),
                )
                if number_of_channels > 1:
                    channel = sitk.VectorIndexSelectionCast(
                        current_sitk_image, i - time_index_existing_number_of_channels
                    )
                else:
                    channel = current_sitk_image
                # Save the channel information using the hdf5 chunking mechanism and compress.
                # Use the settings from an exsiting channel.
                channel_arr_view = sitk.GetArrayViewFromImage(channel)
                grp.create_dataset(
                    "Data",
                    data=np.pad(channel_arr_view, padding),
                    chunks=existing_chunk_size,
                    compression=existing_compression,
                    compression_opts=existing_compression_opts,
                )
                _write_channel_histogram(grp, channel_arr_view, channel.GetPixelID())

        # Create the additional channels metadata groups that are expected to
        # exist by the write_channels_metadata method.
        # We also accomodate for inconsistant imaris behavior where a channel
        # was removed and the DataSetInfo group associated with the channel was
        # not removed. In such a case, we won't try to create it as that will
        # cause an exception.
        existing_number_of_channels_metadata = len(
            existing_image_metadata["channels_information"]
        )
        for i in range(
            existing_number_of_channels_metadata,
            number_of_channels + time_index_existing_number_of_channels,
        ):
            new_group_name = (
                f.attrs["DataSetInfoDirectoryName"].tobytes().decode("UTF-8")
                + f"/Channel {i}"
            )  # Make the file consistent.
            if new_group_name in f:
                for a_name in f[new_group_name].attrs:
                    del f[new_group_name].attrs[a_name]
            else:
                f.create_group(new_group_name)

    # We're adding channels that don't already have associated metadata, so add the metadata too
    if existing_number_of_channels_metadata < (
        number_of_channels + time_index_existing_number_of_channels
    ):
        meta_data_dict = {}
        channels_information = []
        try:
            channels_information = channels_information_xmlstr2list(
                sitk_image.GetMetaData(channels_metadata_key)
            )
        except RuntimeError:  # channels information is missing, we'll create it
            default_colors = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
            for i in range(number_of_channels):
                channel_info = {}
                channel_info["name"] = "ch"
                channel_info["description"] = ""
                channel_info["color"] = default_colors[i % len(default_colors)]
                channel_info["range"] = [0.0, 255.0]
                channel_info["gamma"] = 1.0
                channel_info["alpha"] = 1.0
                channels_information.append([i, channel_info])

        channels_information = channels_information[
            -(
                number_of_channels
                + time_index_existing_number_of_channels
                - existing_number_of_channels_metadata
            ) :  # noqa: E203
        ]
        for ci, channel_information in enumerate(
            channels_information, existing_number_of_channels_metadata
        ):
            channel_information[0] = ci
        meta_data_dict["channels_information"] = channels_information
        # Write the metadata after writing the channels because it checks that the channels already exist.
        write_channels_metadata(meta_data_dict, file_name, "a")


def append_timepoint(sitk_image, image_time, file_name):
    """
    Append a timepoint to the given Imaris file, the time associated
    with this last frame in the video, image_time, is assumed to be valid.

    Parameters
    ----------
    sitk_image (SimpleITK.Image): Image we want to append in the temporal dimension.
                                  Image has to have the same pixel type, size,
                                  spacing and origin as the existing timepoints in the Imaris file.
    image_time (datetime.datetime): Time associated with the image, it is assumed this time is after
                                    the last timepoint in the existing image.
    file_name (string): Imaris file to which we append the given image.
    """
    # Data validation
    existing_image_metadata = read_metadata(file_name)
    # Compare new time and the last time in the video
    if image_time <= existing_image_metadata["times"][-1]:
        raise ValueError(
            f'Given image_time ({image_time}) is not after last image time ({existing_image_metadata["times"][-1]}).'
        )
    # Compare existing and new image sizes.
    new_image_size = sitk_image.GetSize()[
        0:3
    ]  # Get the size for vector or scalar pixel types
    for esz, nsz in zip(existing_image_metadata["sizes"][0], new_image_size):
        if esz != nsz:
            raise ValueError(
                "New time point image size does not match existing time points size."
            )

    if (
        pixel_type_to_scalar_type[sitk_image.GetPixelID()]
        != existing_image_metadata["sitk_pixel_type"]
    ):
        raise ValueError(
            "New time point pixel type does not match existing time points pixel type."
        )

    # Compare existing and new image origins and spacings using SimpleITK epsilon.
    existing_image = sitk.Image([1, 1, 1], existing_image_metadata["sitk_pixel_type"])
    existing_image.SetOrigin(existing_image_metadata["origin"])
    existing_image.SetSpacing(existing_image_metadata["spacings"][0])
    new_image = sitk.Image([1, 1, 1], existing_image_metadata["sitk_pixel_type"])
    new_image.SetOrigin(sitk_image.GetOrigin()[0:3])
    new_image.SetSpacing(sitk_image.GetSpacing()[0:3])
    try:
        existing_image + new_image
    except Exception:
        raise ValueError(
            "New time point image does not have same origin or spacing as existing time points."
        )
    # Compare the number of channels, new time point needs to match existing time points
    vector_pixels = sitk_image.GetNumberOfComponentsPerPixel() > 1
    if vector_pixels:
        number_of_channels = sitk_image.GetNumberOfComponentsPerPixel()
    elif sitk_image.GetDimension() == 4:
        number_of_channels = sitk_image.GetSize()[3]
    else:
        number_of_channels = 1
    existing_number_of_channels = len(existing_image_metadata["channels_information"])
    if existing_number_of_channels != number_of_channels:
        raise ValueError(
            "New time point image does not have same number of channels as existing time points."
        )

    with h5py.File(file_name, "a") as f:
        dataset_dirname = f.attrs["DataSetDirectoryName"].tobytes().decode("UTF-8")
        dataset_info_dirname = (
            f.attrs["DataSetInfoDirectoryName"].tobytes().decode("UTF-8")
        )

        new_time_point_num = len(existing_image_metadata["times"]) + 1
        _ims_set_nullterm_str_attribute(
            f[dataset_info_dirname]["TimeInfo"],
            "DatasetTimePoints",
            str(new_time_point_num).encode("UTF-8"),
        )
        _ims_set_nullterm_str_attribute(
            f[dataset_info_dirname]["TimeInfo"],
            "FileTimePoints",
            str(new_time_point_num).encode("UTF-8"),
        )
        _ims_set_nullterm_str_attribute(
            f[dataset_info_dirname]["TimeInfo"],
            f"TimePoint{new_time_point_num}",
            str(image_time).encode("UTF-8"),
        )

        for res_index in range(len(f[dataset_dirname])):
            resolution_name = f"ResolutionLevel {res_index}"
            if res_index == 0:
                cur_image_size = sitk_image.GetSize()
                current_sitk_image = sitk_image
            else:
                cur_image_size = [
                    int(
                        f[dataset_dirname][resolution_name]["TimePoint 0"]["Channel 0"]
                        .attrs["ImageSizeX"]
                        .tobytes()
                    ),
                    int(
                        f[dataset_dirname][resolution_name]["TimePoint 0"]["Channel 0"]
                        .attrs["ImageSizeY"]
                        .tobytes()
                    ),
                    int(
                        f[dataset_dirname][resolution_name]["TimePoint 0"]["Channel 0"]
                        .attrs["ImageSizeZ"]
                        .tobytes()
                    ),
                ]
                # Compute the new spacing, if there is a single slice along any dimension then we set the spacing to one.  # noqa: E501
                new_spacing = [
                    (ns - 1) * nspc / (cs - 1) if cs > 1 else 1
                    for ns, nspc, cs in zip(
                        new_image_size, sitk_image.GetSpacing(), cur_image_size
                    )
                ]
                current_sitk_image = sitk.Resample(
                    sitk_image,
                    cur_image_size,
                    sitk.Transform(),
                    sitk.sitkLinear,
                    sitk_image.GetOrigin(),
                    new_spacing,
                    sitk_image.GetDirection(),
                    0,
                    sitk_image.GetPixelID(),
                )

            # Get the chunking and compression level from existing channel
            existing_chunk_size = f[dataset_dirname][resolution_name]["TimePoint 0"][
                "Channel 0"
            ]["Data"].chunks
            existing_compression = f[dataset_dirname][resolution_name]["TimePoint 0"][
                "Channel 0"
            ]["Data"].compression
            existing_compression_opts = f[dataset_dirname][resolution_name][
                "TimePoint 0"
            ]["Channel 0"]["Data"].compression_opts
            # As chunk size cannot be larger than the image dimensions we may need to zero pad the written numpy array
            padding = [
                (0, csz - isz) if isz < csz else (0, 0)
                for isz, csz in zip(
                    current_sitk_image.GetSize()[::-1], existing_chunk_size
                )
            ]

            for i in range(existing_number_of_channels):
                grp = f.create_group(
                    dataset_dirname
                    + f"/{resolution_name}/TimePoint {new_time_point_num-1}/Channel {i}"
                )
                _ims_set_nullterm_str_attribute(
                    grp, "ImageSizeX", str(new_image_size[0]).encode("UTF-8")
                )
                _ims_set_nullterm_str_attribute(
                    grp, "ImageSizeY", str(new_image_size[1]).encode("UTF-8")
                )
                _ims_set_nullterm_str_attribute(
                    grp, "ImageSizeZ", str(new_image_size[2]).encode("UTF-8")
                )
                if vector_pixels:
                    channel = sitk.VectorIndexSelectionCast(current_sitk_image, i)
                elif number_of_channels > 1:
                    channel = current_sitk_image[:, :, :, i]
                else:
                    channel = current_sitk_image
                # Save the channel information using the hdf5 chunking mechanism and compress.
                # Use the settings from an existing channel.
                channel_arr_view = sitk.GetArrayViewFromImage(channel)
                grp.create_dataset(
                    "Data",
                    data=np.pad(channel_arr_view, padding),
                    chunks=existing_chunk_size,
                    compression=existing_compression,
                    compression_opts=existing_compression_opts,
                )
                _write_channel_histogram(grp, channel_arr_view, channel.GetPixelID())
