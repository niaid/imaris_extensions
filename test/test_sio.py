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

import hashlib
import pytest
import pathlib
import shutil
import datetime
import json
import SimpleITK as sitk
import sitk_ims_file_io as sio
import numpy as np


class TestIO:
    def setup_method(self):
        # Path to testing data is expected in the following location:
        self.data_path = pathlib.Path(__file__).parent.absolute() / "data"

    def file_md5(self, file_name):
        md5 = hashlib.md5()
        with open(file_name, "rb") as fp:
            for mem_block in iter(lambda: fp.read(128 * md5.block_size), b""):
                md5.update(mem_block)
        return md5.hexdigest()

    def image_md5(self, sitk_image):
        return hashlib.md5(sitk.GetArrayViewFromImage(sitk_image)).hexdigest()

    @pytest.mark.parametrize(
        "file_name, metadata_md5_hash",
        [
            (
                "image_2D_six_channels_one_resolution_one_timepoint.ims",
                "680473bdcf3c4193b6f8f6696cc70925",
            ),
            (
                "image_2D_three_channels_one_resolution_four_timepoints.ims",
                "d5c3cb2c39772fa00002a00a26e9a00e",
            ),
            (
                "image_3D_six_channels_four_resolutions_one_timepoint.ims",
                "1a759b9fe112c1eb61a19cdabc56d8c0",
            ),
            (
                "image_3D_three_channels_two_resolutions_four_timepoints.ims",
                "4a12e67f0e26223400147ec1f05712b7",
            ),
        ],
    )
    def test_metadata_read(self, file_name, metadata_md5_hash):
        """
        Read the metadata, serialize to json representation and compare hash.
        """
        metadata = sio.read_metadata(self.data_path / file_name)
        # To compute a md5 hash of the metadata dictionary we want to serialize
        # it into a json dataset, which ensures the order (pickling doesn't).
        # We compute the hash on the json data. Unfortunatly, the datetime
        # type cannot be serialized to json (TypeError: Object of type datetime is not JSON serializable).
        # The ad-hoc solution here is to convert them to strings and then serialize to json.
        for i, dt in enumerate(metadata["times"]):
            metadata["times"][i] = datetime.datetime.strftime(dt, sio.time_str_format)

        # print the metadata information so that we can confirm it is correct.
        print(f"file name: {file_name}\nmeta data:\n" + str(metadata))
        assert (
            hashlib.md5(
                json.dumps(metadata, sort_keys=True).encode("utf-8")
            ).hexdigest()
            == metadata_md5_hash
        )

    @pytest.mark.parametrize(
        "file_name, image_md5_hash",
        [
            (
                "image_2D_six_channels_one_resolution_one_timepoint.ims",
                "6c5b5fb46ff761312de4028d02e5d35d",
            ),
            (
                "image_2D_three_channels_one_resolution_four_timepoints.ims",
                "76266ec9b4f72ef86d314455c079cd09",
            ),
            (
                "image_3D_six_channels_four_resolutions_one_timepoint.ims",
                "55460dfbef62e3a1e69f14c70197a7c4",
            ),
            (
                "image_3D_three_channels_two_resolutions_four_timepoints.ims",
                "4465fb02fc832921cea3cba5447ce258",
            ),
        ],
    )
    def test_basic_read(self, file_name, image_md5_hash):
        """
        Read the whole image and return output once with vector pixels and once
        with the channels as an additional dimension. The image_md5_hash is the
        hash for the image read with the channels as an additional dimension.
        """
        sitk_image = sio.read(
            self.data_path / file_name,
            time_index=0,
            resolution_index=0,
            channel_index=None,
            sub_ranges=None,
            vector_pixels=False,
            convert_to_mm=False,
        )
        sitk_vec_image = sio.read(
            self.data_path / file_name,
            time_index=0,
            resolution_index=0,
            channel_index=None,
            sub_ranges=None,
            vector_pixels=True,
            convert_to_mm=False,
        )
        hash_matches = self.image_md5(sitk_image) == image_md5_hash
        images_equal = all(
            [
                np.count_nonzero(
                    sitk.GetArrayFromImage(
                        sitk_image[:, :, :, i]
                        - sitk.VectorIndexSelectionCast(sitk_vec_image, i)
                    )
                )
                == 0
                for i in range(sitk_vec_image.GetNumberOfComponentsPerPixel())
            ]
        )
        assert hash_matches and images_equal

    @pytest.mark.parametrize(
        "file_name, sub_ranges, subregion_md5_hash",
        [
            (
                "image_2D_six_channels_one_resolution_one_timepoint.ims",
                [range(0, 1), range(0, 1), range(0, 1)],
                "55c91e731d709831dda1eb46a89d5fac",
            ),
            (
                "image_2D_three_channels_one_resolution_four_timepoints.ims",
                [range(0, 1), range(0, 1), range(0, 1)],
                "21de9d9bbdee8fec642421844750d5cc",
            ),
            (
                "image_3D_six_channels_four_resolutions_one_timepoint.ims",
                [range(0, 1), range(0, 1), range(0, 1)],
                "1d965b6ec922b222778595455efa42c3",
            ),
            (
                "image_3D_three_channels_two_resolutions_four_timepoints.ims",
                [range(0, 1), range(0, 1), range(0, 1)],
                "fbc5a342329f102a7988b14ddf5cb9e9",
            ),
        ],
    )
    def test_subregion_read(self, file_name, sub_ranges, subregion_md5_hash):
        """
        Read a subregion of the image (one voxel).
        """
        sitk_image = sio.read(
            self.data_path / file_name,
            time_index=0,
            resolution_index=0,
            channel_index=None,
            sub_ranges=sub_ranges,
            vector_pixels=False,
            convert_to_mm=False,
        )
        sitk_vec_image = sio.read(
            self.data_path / file_name,
            time_index=0,
            resolution_index=0,
            channel_index=None,
            sub_ranges=sub_ranges,
            vector_pixels=True,
            convert_to_mm=False,
        )
        hash_matches = self.image_md5(sitk_image) == subregion_md5_hash
        images_equal = all(
            [
                np.count_nonzero(
                    sitk.GetArrayFromImage(
                        sitk_image[:, :, :, i]
                        - sitk.VectorIndexSelectionCast(sitk_vec_image, i)
                    )
                )
                == 0
                for i in range(sitk_vec_image.GetNumberOfComponentsPerPixel())
            ]
        )
        assert hash_matches and images_equal

    @pytest.mark.parametrize(
        "file_name, resolution_index, resolution_md5",
        [
            ("image_2D_six_channels_one_resolution_one_timepoint.ims", 1, None),
            (
                "image_3D_six_channels_four_resolutions_one_timepoint.ims",
                2,
                "27e5f552fdf84ce7b8035da83d774b11",
            ),
        ],
    )
    def test_resolution_read(self, file_name, resolution_index, resolution_md5):
        try:
            sitk_image = sio.read(
                self.data_path / file_name,
                time_index=0,
                resolution_index=resolution_index,
                channel_index=None,
                sub_ranges=None,
                vector_pixels=False,
                convert_to_mm=False,
            )
            # A None value for the resolution_md5 indicates that we expect the read
            # to fail and throw an exception, assuming short circuit evaluation here.
            assert (
                resolution_md5 is not None
                and self.image_md5(sitk_image) == resolution_md5
            )
        except ValueError as e:
            # print the exception, it should be a ValueError, as we test for
            # invalid resolution requests
            print(e)
            assert resolution_md5 is None

    @pytest.mark.parametrize(
        "file_name, time_index, time_md5",
        [
            ("image_2D_six_channels_one_resolution_one_timepoint.ims", 1, None),
            (
                "image_2D_three_channels_one_resolution_four_timepoints.ims",
                2,
                "e3a8081e2426a0ecb52d0b7e6d202e5b",
            ),
        ],
    )
    def test_time_read(self, file_name, time_index, time_md5):
        try:
            sitk_image = sio.read(
                self.data_path / file_name,
                time_index=time_index,
                resolution_index=0,
                channel_index=None,
                sub_ranges=None,
                vector_pixels=False,
                convert_to_mm=False,
            )
            # A None value for the time_md5 indicates that we expect the read
            # to fail and throw an exception, assuming short circuit evaluation here.
            assert time_md5 is not None and self.image_md5(sitk_image) == time_md5
        except ValueError as e:
            # print the exception, it should be a ValueError, as we test for
            # invalid time requests
            print(e)
            assert time_md5 is None

    @pytest.mark.parametrize(
        "file_name, results_md5",
        [
            (
                "image_2D_six_channels_one_resolution_one_timepoint.ims",
                [
                    None,
                    (
                        "0de1fe80fca752b850adae0147d072bb",
                        "f0c7f3a53c991635a0a640ae28884909",
                    ),
                    (
                        "0de1fe80fca752b850adae0147d072bb",
                        "f0c7f3a53c991635a0a640ae28884909",
                    ),
                    (
                        "0d24fc17fbc414ada21a6d120379da7a",
                        "1adecfed18431a4ff29866551c8cf044",
                    ),
                    (
                        "0d24fc17fbc414ada21a6d120379da7a",
                        "1adecfed18431a4ff29866551c8cf044",
                    ),
                ],
            ),
            (
                "image_2D_three_channels_one_resolution_four_timepoints.ims",
                [
                    None,
                    (
                        "307a1361d5a7544078cd1ca365131ea9",
                        "783b45321e1efa291fc726328d60db36",
                    ),
                    (
                        "307a1361d5a7544078cd1ca365131ea9",
                        "783b45321e1efa291fc726328d60db36",
                    ),
                    (
                        "7b7b8ae148c50476b2fb624ad02040e1",
                        "ee35a4c0160bd817e3c81d63d618abdd",
                    ),
                    (
                        "7b7b8ae148c50476b2fb624ad02040e1",
                        "ee35a4c0160bd817e3c81d63d618abdd",
                    ),
                ],
            ),
            (
                "image_3D_six_channels_four_resolutions_one_timepoint.ims",
                [
                    None,
                    (
                        "f7eef2a2a9b955f79f01723e81ca100b",
                        "ae512812e69486142baa1be6f6648bd3",
                    ),
                    (
                        "f7eef2a2a9b955f79f01723e81ca100b",
                        "ae512812e69486142baa1be6f6648bd3",
                    ),
                    (
                        "665b1932a7fc0bdb0cdb6a7f96b0dc70",
                        "bd59776b260329d837f9b3ab0b0207e9",
                    ),
                    (
                        "665b1932a7fc0bdb0cdb6a7f96b0dc70",
                        "bd59776b260329d837f9b3ab0b0207e9",
                    ),
                ],
            ),
            (
                "image_3D_three_channels_two_resolutions_four_timepoints.ims",
                [
                    None,
                    (
                        "b4296ba509e3081183f034867939924e",
                        "57aa31c752efdd10bfbd31e280257edd",
                    ),
                    (
                        "b4296ba509e3081183f034867939924e",
                        "57aa31c752efdd10bfbd31e280257edd",
                    ),
                    (
                        "8658aee91c33c4ecc5e40741089e477c",
                        "e1117ba8ea7a32ecda2048af1b0630c5",
                    ),
                    (
                        "8658aee91c33c4ecc5e40741089e477c",
                        "e1117ba8ea7a32ecda2048af1b0630c5",
                    ),
                ],
            ),
        ],
    )
    def test_append_channels(self, file_name, results_md5, tmp_path):
        """
        NOTE: The hash information in the parametrizing fixture wrapping this function must
              match the images created in the function. First entry corrosponds to the hash
              of the data returned by sio.read and the second to the data returned by
              sio.read_metadata.
        """
        metadata = sio.read_metadata(self.data_path / file_name)

        appended_images = []
        # Invalid input
        appended_images.append(
            sitk.Image(
                [sz + 1 for sz in (metadata["sizes"][0])], metadata["sitk_pixel_type"]
            )
        )
        # Valid 3D image
        sitk_image = sitk.Image(metadata["sizes"][0], metadata["sitk_pixel_type"])
        sitk_image.SetSpacing(metadata["spacings"][0])
        sitk_image.SetOrigin(metadata["origin"])
        appended_images.append(sitk_image)
        # Valid vector image, 1 channel
        sitk_image = sitk.Compose(
            [sitk.Image(metadata["sizes"][0], metadata["sitk_pixel_type"])]
        )
        sitk_image.SetSpacing(metadata["spacings"][0])
        sitk_image.SetOrigin(metadata["origin"])
        appended_images.append(sitk_image)
        # Valid vector image, 3 channels
        sitk_image = sitk.Compose(
            [sitk.Image(metadata["sizes"][0], metadata["sitk_pixel_type"])] * 3
        )
        sitk_image.SetSpacing(metadata["spacings"][0])
        sitk_image.SetOrigin(metadata["origin"])
        appended_images.append(sitk_image)
        # Valid 4D image, 3 channels
        sitk_image = sitk.JoinSeries(
            [sitk.Image(metadata["sizes"][0], metadata["sitk_pixel_type"])] * 3
        )
        sitk_image.SetSpacing(metadata["spacings"][0] + [1])
        sitk_image.SetOrigin(metadata["origin"] + [0])
        appended_images.append(sitk_image)

        # To check that the resulting imaris file is valid we check the md5 hash of the image
        # content and the md5 hash of the metadata. Unfortuntaly, the md5 hash for the hdf5
        # file changes every time it is written. This has to do with the hdf5 file format and
        # the fact that there are time stamps in the header. The h5py create_dataset method
        # allows us to set the track_times to False, but this didn't seem to result in
        # consistent md5 hashs for the resulting hdf5 files even though the content was
        # exactly the same.
        # NOTE: To debug the testing code replace the usage of the tmp_path fixture with
        #       an actual directory so you can look at the results (they won't be in some
        #       obscure location).
        for sitk_image, result_md5 in zip(appended_images, results_md5):
            # Copy the test data to the temp dir fixture provided by pytest and run test there.
            # We don't want to run this test on the original data becuase it modifies its input.
            shutil.copy(self.data_path / file_name, tmp_path)
            modified_file_path = tmp_path / file_name
            try:
                for ti in range(len(metadata["times"])):
                    sio.append_channels(sitk_image, modified_file_path, time_index=ti)
                metadata = sio.read_metadata(modified_file_path)
                # To compute a md5 hash of the metadata dictionary we want to serialize
                # it into a json dataset, which ensures the order (pickling doesn't).
                # We compute the hash on the json data. Unfortunatly, the datetime
                # type cannot be serialized to json (TypeError: Object of type datetime is not JSON serializable).
                # The ad-hoc solution here is to convert them to strings and then serialize to json.
                for i, dt in enumerate(metadata["times"]):
                    metadata["times"][i] = datetime.datetime.strftime(
                        dt, sio.time_str_format
                    )

                print(
                    f"image content hash: {self.image_md5(sio.read(modified_file_path))}"
                )
                print(
                    f'image metadata hash: {hashlib.md5(json.dumps(metadata, sort_keys=True).encode("utf-8")).hexdigest()}'  # noqa: E501
                )

                assert (
                    result_md5 is not None
                    and self.image_md5(sio.read(modified_file_path)) == result_md5[0]
                    and hashlib.md5(
                        json.dumps(metadata, sort_keys=True).encode("utf-8")
                    ).hexdigest()
                    == result_md5[1]
                )
            except ValueError as e:
                # Print the exception, it should be a ValueError, as we test for
                # invalid appending
                print(e)
                assert result_md5 is None

    @pytest.mark.parametrize(
        "file_name, results_md5",
        [
            (
                "image_2D_six_channels_one_resolution_one_timepoint.ims",
                [
                    None,
                    (
                        "6c5b5fb46ff761312de4028d02e5d35d",
                        "17593eb49eb317ea2fbe6b8268e4cbc7",
                    ),
                ],
            ),
            (
                "image_2D_three_channels_one_resolution_four_timepoints.ims",
                [
                    None,
                    (
                        "76266ec9b4f72ef86d314455c079cd09",
                        "3b5effec60d16fd16f10bb84861b4e69",
                    ),
                ],
            ),
            (
                "image_3D_six_channels_four_resolutions_one_timepoint.ims",
                [
                    None,
                    (
                        "55460dfbef62e3a1e69f14c70197a7c4",
                        "9a3fad86eb33eda81c5d05dd7eda3f2a",
                    ),
                ],
            ),
            (
                "image_3D_three_channels_two_resolutions_four_timepoints.ims",
                [
                    None,
                    (
                        "4465fb02fc832921cea3cba5447ce258",
                        "1f6d253f324c02b065ad822199387094",
                    ),
                ],
            ),
        ],
    )
    def test_append_timepoint(self, file_name, results_md5, tmp_path):
        """
        NOTE: The hash information in the parametrizing fixture wrapping this function must
              match the images created in the function. First entry corrosponds to the hash
              of the data returned by sio.read and the second to the data returned by
              sio.read_metadata.
        """
        metadata = sio.read_metadata(self.data_path / file_name)

        appended_images_data = []
        # Invalid input
        sitk_image = sitk.Image(metadata["sizes"][0], metadata["sitk_pixel_type"])
        # Image has one more channel than exsiting image (as we don't set the
        # origin and spacing they are likely also incorrect, but we can't be sure of that).
        sitk_image = sitk.Compose(
            [sitk_image] * (len(metadata["channels_information"]) + 1)
        )
        if len(metadata["times"]) > 1:  # keep existing temporal difference
            new_time = metadata["times"][-1] + (
                metadata["times"][1] - metadata["times"][0]
            )
        else:  # New temporal difference of 33.3 milliseconds (30fps video rate)
            new_time = metadata["times"][0] + datetime.timedelta(milliseconds=33.3)
        appended_images_data.append((sitk_image, new_time))

        # Append frame with all zeros in all channels.
        sitk_image = sitk.Image(metadata["sizes"][0], metadata["sitk_pixel_type"])
        sitk_image.SetOrigin(metadata["origin"])
        sitk_image.SetSpacing(metadata["spacings"][0])
        sitk_image = sitk.Compose([sitk_image] * len(metadata["channels_information"]))
        if len(metadata["times"]) > 1:  # keep existing temporal difference
            new_time = metadata["times"][-1] + (
                metadata["times"][1] - metadata["times"][0]
            )
        else:  # New temporal difference of 33.3 milliseconds (30fps video rate)
            new_time = metadata["times"][0] + datetime.timedelta(milliseconds=33.3)
        appended_images_data.append((sitk_image, new_time))

        # To check that the resulting imaris file is valid we check the md5 hash of the image
        # content and the md5 hash of the metadata. Unfortuntaly, the md5 hash for the hdf5
        # file changes every time it is written. This has to do with the hdf5 file format and
        # the fact that there are time stamps in the header. The h5py create_dataset method
        # allows us to set the track_times to False, but this didn't seem to result in
        # consistent md5 hashs for the resulting hdf5 files even though the content was
        # exactly the same.
        # NOTE: To debug the testing code replace the usage of the tmp_path fixture with
        #       an actual directory so you can look at the results (they won't be in some
        #       obscure location).
        for image_and_time, result_md5 in zip(appended_images_data, results_md5):
            # Copy the test data to the temp dir fixture provided by pytest and run test there.
            # We don't want to run this test on the original data becuase it modifies its input.
            shutil.copy(self.data_path / file_name, tmp_path)
            modified_file_path = tmp_path / file_name
            try:
                sio.append_timepoint(
                    image_and_time[0], image_and_time[1], modified_file_path
                )
                metadata = sio.read_metadata(modified_file_path)
                # To compute a md5 hash of the metadata dictionary we want to serialize
                # it into a json dataset, which ensures the order (pickling doesn't).
                # We compute the hash on the json data. Unfortunatly, the datetime
                # type cannot be serialized to json (TypeError: Object of type datetime is not JSON serializable).
                # The ad-hoc solution here is to convert them to strings and then serialize to json.
                for i, dt in enumerate(metadata["times"]):
                    metadata["times"][i] = datetime.datetime.strftime(
                        dt, sio.time_str_format
                    )

                print(
                    f"image content hash: {self.image_md5(sio.read(modified_file_path))}"
                )
                print(
                    f'image metadata hash: {hashlib.md5(json.dumps(metadata, sort_keys=True).encode("utf-8")).hexdigest()}'  # noqa: E501
                )

                assert (
                    result_md5 is not None
                    and self.image_md5(sio.read(modified_file_path)) == result_md5[0]
                    and hashlib.md5(
                        json.dumps(metadata, sort_keys=True).encode("utf-8")
                    ).hexdigest()
                    == result_md5[1]
                )
            except ValueError as e:
                # Print the exception, it should be a ValueError, as we test for
                # invalid appending
                print(e)
                assert result_md5 is None

    @pytest.mark.parametrize(
        "file_name",
        [
            "image_2D_six_channels_one_resolution_one_timepoint.ims",
            "image_2D_three_channels_one_resolution_four_timepoints.ims",
            "image_3D_six_channels_four_resolutions_one_timepoint.ims",
            "image_3D_three_channels_two_resolutions_four_timepoints.ims",
        ],
    )
    def test_write(self, file_name, tmp_path):
        # Default read (resolution=0, time=0, all channels)
        sitk_image = sio.read(self.data_path / file_name)
        original_md5 = self.image_md5(sitk_image)
        # Write the image to the tmp dir using same image name
        sio.write(sitk_image, tmp_path / file_name)
        sitk_image = sio.read(tmp_path / file_name)
        assert original_md5 == self.image_md5(sitk_image)
