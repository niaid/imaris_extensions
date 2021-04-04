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

#
#  Register a set of images and resample onto one of them.
#
#
#    <CustomTools>
#      <Menu>
#      <Submenu name="SimpleITK Algorithms">
#       <Item name="Affine registration of z-stacks using common channel" icon="Python3" tooltip="Affine registration of z-stacks using correlation of common channel.">  # noqa: E501
#         <Command>Python3XT::XTRegisterSameChannel(%i)</Command>
#       </Item>
#      </Submenu>
#      </Menu>
#    </CustomTools>

import os
import numpy as np
import json
import hashlib
import inspect
import matplotlib
import matplotlib.pyplot as plt
import logging
import traceback

from PySide2.QtWidgets import (
    QWidget,
    QApplication,
    QFileDialog,
    QComboBox,
    QTextEdit,
    QLabel,
    QPushButton,
    QStackedWidget,
    QMessageBox,
    QVBoxLayout,
    QHBoxLayout,
    QCheckBox,
    QLineEdit,
    QProgressBar,
)
from PySide2.QtCore import Qt, QThread, Signal
from PySide2.QtGui import QTextCursor
import qdarkstyle

import SimpleITK as sitk
import sitk_ims_file_io as sio
import sitkibex
from help_dialog import HelpDialog
import imaris_extension_base as ieb

matplotlib.use("Agg")


def file_md5(file_name):
    md5 = hashlib.md5()
    with open(file_name, "rb") as fp:
        for mem_block in iter(lambda: fp.read(128 * md5.block_size), b""):
            md5.update(mem_block)
    return md5.hexdigest()


def XTRegisterSameChannel(imaris_id=None):
    app = QApplication([])
    app.setStyle(ieb.style)  # Consistent setting of style for all applications
    app.setStyleSheet(qdarkstyle.load_stylesheet(qt_api="pyside2"))
    registration_dialog = RegisterSameChannelDialog()  # noqa: F841
    app.exec_()


class RegisterSameChannelDialog(ieb.ImarisExtensionBase):
    """
    Register Multiple Images Using a Common Channel
    ===============================================

    This program allows you to register multiple images using **affine** transformations
    and requires that there be a **common channel** across all images. Registration is
    based on maximization of correlation, hence the requirement for a common channel.
    The use of an affine transformation assumes that the images only undergo global
    transformations, that is, they are rotated, translated, scaled possibly with differnt
    scales per axis, and sheared. Local deformations are not accounted for.

    The program can be run either as an Imaris extension via the Imaris user interface
    or as a standalone program. It supports registration of multi-channel
    z-stacks (a.k.a. 3D images, volumes) and multi-channel 2D images
    (single slice z-stack). Sample datasets are freely availabe `on zenodo <https://doi.org/10.5281/zenodo.4632320>`_.

    The `source code for the registration <https://github.com/niaid/sitk-ibex>`_ is
    freely available on GitHub. This registration workflow was originally
    developed as part of the work described in: A. Radtke et al. "IBEX - A versatile multi-plex optical
    imaging approach for deep phenotyping and spatial analysis of cells in
    complex tissues", *Proc Natl Acad Sci*, 2020, `doi:10.1073/pnas.2018488117 <https://doi.org/10.1073/pnas.2018488117>`_.

    Input/Output
    ------------

    The program's input are two or more files in Imaris format that share at least
    one common channel. The channel to use for registration is based on the channel
    names in the file. A channel name consists of three parts:

        1. prefix
        2. separator character
        3. postfix

    The user can specify a separator character, which indicates that channels with the
    same postfix are the same channel, otherwise the whole channel name is used.
    For example, two files with channels named *Experiment1 : CD3_AF594* and
    *Experiment2 : CD3_AF594*. If we specify colon as the separator character
    these channels will be considered as the same channel, otherwise they are different.

    **Note:** Channel names in an input file are expected to be unique, as there
    can only be one registration channel per file. The uniqueness is based on the
    separator character scheme described above. For example, a file containing
    two channels named *step 1 : CD3* and *step 2 : CD3* is considered valid if
    the separator character is empty, but it would be invalid if we use colon or
    space as the separator character, in which case both channel names become *CD3*.

    The program will save the following outputs:

        1. A single Imaris file containing the resampled volumes. All channel information
           is copied over from the original volumes.
        2. A log file containing internal registration information (useful for debugging
           purposes understanding why a registration failed and how to configure the
           program to address the issue).
        3. A json file specifying the program settings used for registration (useful for
           reproducing the registration).
        4. Optional pdf files showing the correlation between channels before and after
           registration. This is useful for quantitatively evaluating the registration.

    Program Settings
    ----------------

    To see the current settings or modify them, press the "Advanced Registration Settings"
    button on the second screen. You can also load settings from previous registrations via the
    json configuration saved from a previous run (see above).

    Options include:

        1. z expand factor - Useful when the number of slices in the z-stack is small
           (~5). Setting this value will expand the number of slices in the stack
           via interpolation. The expansion utilizes the SimpleITK `ExpandImageFilter
           <https://simpleitk.org/doxygen/latest/html/classitk_1_1simple_1_1ExpandImageFilter.html>`_.
        2. FFT based initialization - initialize the translation using the SimpleITK
           `MaskedFFTNormalizedCorrelationImageFilter <https://simpleitk.org/doxygen/latest/html/classitk_1_1simple_1_1MaskedFFTNormalizedCorrelationImageFilter.html>`_.
        3. 2D affine - project the data along the z direction and perform an initial 2D affine registration which
           will then be used to initialize a 3D affine registration.
        4. 3D affine - perform 3D affine registration.
        5. Adjust spacing magnitude to be near 1 - resample the image so that the voxel sizes are not too small, e.g. 0.001.
           This improves the registration's numerical stability.
        6. Auto mask - limit voxels used in registration to non zero voxels.
        7. Samples per parameter - number of samples used during registration.

    z-stack Registration
    ++++++++++++++++++++

    Most of the time you can run the program using the default registration settings.

    **Note:** The first registration step, FFT based initialization, requires a significant
    amount of RAM. On lower end machines (32GB RAM or less) it may not work. This can be
    ameliorated by disabling this option and enabling the 2D affine initialization step.

    **Failure:** When the FFT based initialization step fails the whole registration may
    fail too. If this happens, disable the FFT option, enable the 2D affine initialization
    and redo the registration.

    2D Image Registration
    +++++++++++++++++++++

    To perform 2D registration use the default settings (2D affine enabled,
    FFT initialization and 3D affine disabled). If registration
    doesn't succeed you can try modifying masking and samples per parameter or
    the selection of the fixed image.

    """  # noqa

    def __init__(self):
        super(RegisterSameChannelDialog, self).__init__()
        self.register_images = RegisterImages()
        self.resample_images = ResampleImages()

        # Configure the help dialog.
        self.help_dialog = HelpDialog(w=700, h=500)
        self.help_dialog.setWindowTitle("Register Same Channel Help")
        self.help_dialog.set_rst_text(
            inspect.getdoc(self), pygments_css_file_name="pygments_dark.css"
        )

        self.__create_gui()
        self.__reset_gui()
        self.setWindowTitle("Register Same Channel")

        # Connect to QThread's signals
        self.register_images.finished.connect(self.__registration_finished)
        self.register_images.processing_error.connect(self._processing_error_function)

        # Create a Handler for the sitkibex package logger, attached during
        # registration and detached afterwards
        self.logging_handler = ieb.LoggingGUIHandler(logging.DEBUG)
        self.logging_handler.setFormatter(logging.Formatter(fmt="%(message)s\n"))
        self.logging_handler.signal_emitter.write_signal.connect(
            self.__update_registration_stdout_edit
        )

        self.resample_images.progress_signal.connect(self.__on_resample_progress)
        self.resample_images.finished.connect(self.__resampling_finished)
        self.resample_images.processing_error.connect(self._processing_error_function)
        self.resample_images.update_state_signal.connect(self.status_bar.showMessage)
        self.show()

    def __create_gui(self):
        # Advanced settings dialog
        self.advanced_settings_widget = self.__create_advanced_settings_widget()

        menu_bar = self.menuBar()
        # Force menubar to be displayed in the application on OSX/Linux, otherwise it
        # is displayed in the system menubar
        menu_bar.setNativeMenuBar(False)
        self.help_button = QPushButton("Help")
        self.help_button.clicked.connect(self.help_dialog.show)
        menu_bar.setCornerWidget(self.help_button, Qt.TopLeftCorner)

        # Central widget components
        central_widget = QWidget(self)
        gui_layout = QVBoxLayout()
        central_widget.setLayout(gui_layout)
        self.setCentralWidget(central_widget)

        select_files_widget = self.__create_select_files_widget()
        configure_registration_widget = self.__create_registration_setup_widget()
        correlation_widget = self.__create_correlation_analysis_widget()
        self.stack = QStackedWidget(self)
        self.stack.addWidget(select_files_widget)
        self.stack.addWidget(configure_registration_widget)
        self.stack.addWidget(correlation_widget)
        gui_layout.addWidget(self.stack)

        self.status_bar = self.statusBar()

    def __create_advanced_settings_widget(self):
        wid = QWidget()
        wid.setWindowTitle("Advanced Settings")
        input_layout = QVBoxLayout()
        wid.setLayout(input_layout)

        # All of the default GUI component values are set in the __reset_gui
        # method.
        layout = QHBoxLayout()
        layout.addWidget(QLabel("z expand factor:"))
        self.expand_factor_line_edit = QLineEdit()
        self.expand_factor_line_edit.setToolTip(
            "<html><head/><body><p>Integer denoting by how much to exapnd the slices in the z-stack. "
            + "This is useful when the number of slices is really small (e.g. less than 10).</p></body></html>"
        )
        layout.addWidget(self.expand_factor_line_edit)
        input_layout.addLayout(layout)

        self.do_fft_initialization_cb = QCheckBox(
            "Do FFT Initialization step (estimates translation)"
        )
        input_layout.addWidget(self.do_fft_initialization_cb)

        self.do_affine2d_cb = QCheckBox(
            "Do 2D affine alignment step (uses z projection)"
        )
        input_layout.addWidget(self.do_affine2d_cb)

        self.do_affine3d_cb = QCheckBox("Do 3D affine alignment step")
        input_layout.addWidget(self.do_affine3d_cb)

        self.ignore_spacing_cb = QCheckBox(
            "Internally adjust spacing magnitude to be near 1 to avoid numeric stability issues"
        )
        input_layout.addWidget(self.ignore_spacing_cb)

        layout = QHBoxLayout()
        layout.addWidget(QLabel("Gaussian smoothing sigma:"))
        self.sigma_line_edit = QLineEdit()
        layout.addWidget(self.sigma_line_edit)
        input_layout.addLayout(layout)

        self.auto_mask_cb = QCheckBox(
            "Auto mask (ignore zero valued pixels connected to the image border)"
        )
        input_layout.addWidget(self.auto_mask_cb)

        layout = QHBoxLayout()
        layout.addWidget(
            QLabel(
                "Samples per parameter (number of samples to use per transform parameter at full resolution):"
            )
        )
        self.samples_line_edit = QLineEdit()
        layout.addWidget(self.samples_line_edit)
        input_layout.addLayout(layout)

        layout = QHBoxLayout()
        app_config_button = QPushButton("Load Application Configuration")
        app_config_button.clicked.connect(self.__config_app)
        layout.addWidget(app_config_button)
        layout.addStretch()
        done_button = QPushButton("Done")
        done_button.clicked.connect(self.__validate_and_close_advanced_settings)
        layout.addWidget(done_button)
        input_layout.addLayout(layout)

        return wid

    def __config_app(self):
        try:
            file_name, _ = QFileDialog.getOpenFileName(
                self,
                "QFileDialog.getOpenFileName()",
                "",
                "JSON (*.json);;All Files (*)",
            )
            with open(file_name, "r") as fp:
                app_config = json.load(fp)
            # Compare md5 hashes to ensure that the images haven't been modified
            invalid_files = [
                file_name
                for file_name, md5_hash in app_config["file_names_and_md5"]
                if file_md5(file_name) != md5_hash
            ]
            if invalid_files:
                self._error_function(
                    "The following files md5 hash does not match their content (changed since last run):<br>"
                    + "<br>".join(invalid_files)
                )
                return
            file_names, _ = zip(*app_config["file_names_and_md5"])
            self.input_files_edit.setText("\n".join(file_names))
            self.channel_prefix_separator_line_edit.setText(
                app_config["prefix_separator_character"]
            )
            self.__configure_and_show_registration_setup_widget()
            # Configure previous selected combobox values (fixed image and registration channel)
            index = self.fixed_image_combo.findText(app_config["fixed_image"])
            if index >= 0:
                self.fixed_image_combo.setCurrentIndex(index)
            else:
                self._error_function(
                    "The fixed image name in the JSON configuration file does not match any of the image names."
                )
                return
            index = self.registration_channel_combo.findText(
                app_config["registration_channel_name"]
            )
            if index >= 0:
                self.registration_channel_combo.setCurrentIndex(index)
            else:
                self._error_function(
                    "The registration channel name in the JSON configuration file does not match any of the shared channels."  # noqa: E501
                )
                return

            self.expand_factor_line_edit.setText(
                str(app_config["expand_factor"]) if app_config["expand_factor"] else ""
            )
            self.do_fft_initialization_cb.setChecked(
                app_config["do_fft_initialization"]
            )
            self.do_affine2d_cb.setChecked(app_config["do_affine2d"])
            self.do_affine3d_cb.setChecked(app_config["do_affine3d"])
            self.ignore_spacing_cb.setChecked(app_config["ignore_spacing"])
            self.sigma_line_edit.setText(str(app_config["sigma"]))
            self.auto_mask_cb.setChecked(app_config["auto_mask"])
            self.samples_line_edit.setText(str(app_config["samples_per_parameter"]))
            self.start_resolution_combo.setCurrentIndex(app_config["start_resolution"])
            self.__validate_and_close_advanced_settings()
        except Exception:
            self._error_function(
                "Unexpected error occurred while setting program configuration. Please exit."
            )

    def __validate_and_close_advanced_settings(self):
        try:
            expand_factor_str = self.expand_factor_line_edit.text().strip()
            if expand_factor_str:
                expand_factor = int(expand_factor_str)
                if expand_factor <= 0:
                    raise ValueError(expand_factor_str)
        except Exception as e:
            self._error_function(
                "Invalid expand factor, required to be a positive integer, got: "
                + str(e)
            )
            return
        try:
            sigma_str = self.sigma_line_edit.text().strip()
            sigma = float(sigma_str)
            if sigma <= 0:
                raise ValueError(sigma_str)
        except Exception as e:
            self._error_function(
                "Invalid sigma value, required to be a positive value, got: " + str(e)
            )
            return
        try:
            samples_str = self.samples_line_edit.text().strip()
            if samples_str:
                samples = int(samples_str)
                if samples <= 0:
                    raise ValueError(samples_str)
        except Exception as e:
            self._error_function(
                "Invalid sample size, required to be a positive integer, got: " + str(e)
            )
            return

        self.advanced_settings_widget.hide()

    def __create_select_files_widget(self):
        wid = QWidget()
        input_layout = QVBoxLayout()
        wid.setLayout(input_layout)

        layout = QHBoxLayout()
        layout.addWidget(QLabel("File names:"))
        layout.setAlignment(Qt.AlignLeft)
        button = QPushButton("Browse")
        button.setToolTip("Select input files for registration.")
        button.clicked.connect(self.__browse_select_input_callback)
        layout.addWidget(button)
        input_layout.addLayout(layout)

        layout = QHBoxLayout()
        layout.addWidget(QLabel("Channel name prefix separator character:"))
        self.channel_prefix_separator_line_edit = QLineEdit()
        self.channel_prefix_separator_line_edit.setToolTip(
            "<html><head/><body><p>Character that separates the channel name into a prefix and postfix. The "
            + 'postfix is used as the actual channel name (e.g. space as separator "panel1 CD4",  colon as separator '
            + '"Experiment1 Panel3 : CD4") </p></body></html>'
        )
        layout.addWidget(self.channel_prefix_separator_line_edit)
        input_layout.addLayout(layout)

        self.input_files_edit = QTextEdit()
        self.input_files_edit.setReadOnly(True)
        input_layout.addWidget(self.input_files_edit)

        layout = QHBoxLayout()
        layout.setAlignment(Qt.AlignRight)
        self.input_files_next_button = QPushButton("Next")
        self.input_files_next_button.setEnabled(False)
        self.input_files_next_button.clicked.connect(
            self.__configure_and_show_registration_setup_widget
        )
        layout.addWidget(self.input_files_next_button)
        input_layout.addLayout(layout)

        return wid

    def __browse_select_input_callback(self):
        file_names, _ = QFileDialog.getOpenFileNames(
            self,
            "QFileDialog.getOpenFileNames()",
            "",
            "Imaris Images (*.ims);;All Files (*)",
        )
        if file_names:
            if len(file_names) == 1:
                self._error_function(
                    "Invalid input, only one file selected. Registration requires two or more files."
                )
                return
            self.input_files_edit.setText("\n".join(file_names))
            self.input_files_next_button.setEnabled(True)
            self.output_file_line_edit.setText(
                os.path.join(os.path.dirname(file_names[0]), "output.ims")
            )

    def __browse_select_output_callback(self):
        output_file_name, _ = QFileDialog.getSaveFileName(
            self, "Save Combined Volume", "", "ims(*.ims)"
        )
        if output_file_name:
            self.output_file_line_edit.setText(output_file_name)

    def __create_registration_setup_widget(self):
        wid = QWidget()
        input_layout = QVBoxLayout()
        wid.setLayout(input_layout)

        layout = QHBoxLayout()
        layout.addWidget(QLabel("Registration channel:"))
        self.registration_channel_combo = QComboBox()
        layout.addWidget(self.registration_channel_combo)
        input_layout.addLayout(layout)

        layout = QHBoxLayout()
        layout.addWidget(QLabel("Fixed image:"))
        self.fixed_image_combo = QComboBox()
        layout.addWidget(self.fixed_image_combo)
        input_layout.addLayout(layout)

        layout = QHBoxLayout()
        layout.addWidget(QLabel("Output file:"))
        self.output_file_line_edit = QLineEdit()
        self.output_file_line_edit.setReadOnly(True)
        layout.addWidget(self.output_file_line_edit)
        self.output_file_browse_button = QPushButton("Browse")
        self.output_file_browse_button.clicked.connect(
            self.__browse_select_output_callback
        )
        layout.addWidget(self.output_file_browse_button)
        input_layout.addLayout(layout)

        layout = QHBoxLayout()
        layout.addWidget(QLabel("Start registration at resolution:"))
        self.start_resolution_combo = QComboBox()
        layout.addWidget(self.start_resolution_combo)
        input_layout.addLayout(layout)

        layout = QHBoxLayout()
        self.advanced_settings_button = QPushButton("Advanced Registration Settings")
        self.advanced_settings_button.clicked.connect(
            self.advanced_settings_widget.show
        )
        layout.addWidget(self.advanced_settings_button)
        input_layout.addLayout(layout)

        self.registration_setup_register_button = QPushButton("Register")
        self.registration_setup_register_button.clicked.connect(self.__register)
        input_layout.addWidget(self.registration_setup_register_button)

        self.registration_stdout_edit = QTextEdit()
        self.registration_stdout_edit.setReadOnly(True)
        input_layout.addWidget(self.registration_stdout_edit)

        self.resample_button = QPushButton("Resample And Save Combined Image")
        self.resample_button.clicked.connect(self.__resample)
        self.resample_button.setEnabled(False)
        input_layout.addWidget(self.resample_button)

        self.resampling_progress = QProgressBar()
        self.resampling_progress.setMaximum(100)
        input_layout.addWidget(self.resampling_progress)

        return wid

    def __update_registration_stdout_edit(self, text):
        self.registration_stdout_edit.moveCursor(QTextCursor.End)
        self.registration_stdout_edit.insertPlainText(text)

    def __configure_and_show_registration_setup_widget(self):
        problematic_images = []
        self.all_channels = []
        file_names = self.input_files_edit.toPlainText().split("\n")
        channel_prefix_separator = self.channel_prefix_separator_line_edit.text()
        image_resolutions = []
        for file_name in file_names:
            metadata = sio.read_metadata(file_name)
            image_resolutions.append(len(metadata["sizes"]))
            current_channel_names = [
                (channel_info["name"].split(channel_prefix_separator)[-1]).strip()
                if channel_prefix_separator
                else channel_info["name"]
                for _, channel_info in metadata["channels_information"]
            ]
            self.all_channels.append(
                dict(zip(current_channel_names, range(len(current_channel_names))))
            )
            # Channel name appears more than once (when the dictionary is
            # created the last repetition of the channel name is kept, previous ones are overwritten)
            if len(current_channel_names) != len(self.all_channels[-1]):
                problematic_images.append(file_name)
        if problematic_images:
            self._error_function(
                "The following files contain multiple channels with same name (not allowed): "
                + "\n".join(problematic_images)
            )
            return
        joint_channel_names = [
            channel_name
            for channel_name in self.all_channels[0]
            if all(channel_name in d for d in self.all_channels[1:])
        ]
        if not joint_channel_names:
            self._error_function("Given files do not have a commonly named channel.")
            return
        self.fixed_image_combo.addItems(file_names)
        self.registration_channel_combo.addItems(joint_channel_names)
        # We cannot display actual resolutions because they will differ between
        # files, we just expect that resoultion levels are about the same across all
        # files (e.g. resolution zero is ~10Kx~8Kx~20 but it isn't exactly the same
        # for all files).
        resolution_strs = list(map(str, range(min(image_resolutions))))
        resolution_strs[0] = resolution_strs[0] + " (maximal resolution)"
        resolution_strs[-1] = resolution_strs[-1] + " (minimal resolution)"
        self.start_resolution_combo.addItems(resolution_strs)
        # Check image dimensions and set the registration defaults accordingly.
        metadata = sio.read_metadata(file_name)
        # 3D registration, default is FFT+3D affine
        if metadata["sizes"][0][2] > 1:
            self.do_fft_initialization_cb.setChecked(True)
            self.do_affine2d_cb.setChecked(False)
            self.do_affine3d_cb.setChecked(True)
        # 2D registration, default is 2D affine
        else:
            self.do_fft_initialization_cb.setChecked(False)
            self.do_affine2d_cb.setChecked(True)
            self.do_affine3d_cb.setChecked(False)

        self.stack.setCurrentIndex(1)

    def __create_correlation_analysis_widget(self):
        wid = QWidget()
        input_layout = QVBoxLayout()
        wid.setLayout(input_layout)

        self.correlation_cb_layout = QVBoxLayout()
        input_layout.addLayout(self.correlation_cb_layout)

        self.save_correlation_data_button = QPushButton(
            "Compute Correlations Before and After Registration"
        )
        self.save_correlation_data_button.clicked.connect(self.__compute_correlations)
        input_layout.addWidget(self.save_correlation_data_button)

        layout = QHBoxLayout()
        layout.setAlignment(Qt.AlignRight)
        self.restart_button = QPushButton("Restart")
        self.restart_button.clicked.connect(self.__restart)
        layout.addWidget(self.restart_button)
        input_layout.addLayout(layout)

        return wid

    def __restart(self):
        self.__reset_gui()
        self.processing_error = False
        self.stack.setCurrentIndex(0)

    def __configure_and_show_correlation_analysis_widget(self):
        for i in range(self.registration_channel_combo.count()):
            self.correlation_cb_layout.addWidget(
                QCheckBox(self.registration_channel_combo.itemText(i))
            )
            self.correlation_cb_layout.itemAt(i).widget().setChecked(True)

    def __compute_correlations(self):
        self.restart_button.setEnabled(False)
        self.save_correlation_data_button.setEnabled(False)
        selected_channel_names = [
            self.correlation_cb_layout.itemAt(i).widget().text()
            for i in range(self.correlation_cb_layout.count())
            if self.correlation_cb_layout.itemAt(i).widget().isChecked()
        ]

        for channel_name in selected_channel_names:
            images = []

            # Correlation before registration aligns the images to the resample_origin
            # so that the images overlap in physical space.
            for file_name, channel_indexes in zip(
                self.all_file_names, self.all_channels
            ):
                img = sio.read(
                    file_name=file_name, channel_index=channel_indexes[channel_name]
                )
                images.append(
                    sitk.Resample(
                        img,
                        self.resample_size,
                        sitk.TranslationTransform(
                            3,
                            [
                                io - ro
                                for io, ro in zip(img.GetOrigin(), self.resample_origin)
                            ],
                        ),
                        sitk.sitkLinear,
                        self.resample_origin,
                        self.resample_spacing,
                    )
                )
            corr_coef_before = np.corrcoef(
                [sitk.GetArrayViewFromImage(img).ravel() for img in images]
            )

            prev_index = 0
            images = []
            for file_name, channel_indexes in zip(
                self.all_file_names, self.all_channels
            ):
                index = prev_index + channel_indexes[channel_name]
                images.append(
                    sio.read(
                        file_name=self.output_file_line_edit.text(), channel_index=index
                    )
                )
                prev_index = prev_index + len(
                    sio.read_metadata(file_name)["channels_information"]
                )
            corr_coef_after = np.corrcoef(
                [sitk.GetArrayViewFromImage(img).ravel() for img in images]
            )

            output_prefix = os.path.splitext(self.output_file_line_edit.text())[0]
            label_names = [
                os.path.splitext(os.path.basename(file_name))[0]
                for file_name in self.all_file_names
            ]
            self.__save_correlation_matrix(
                corr_coef_before,
                title=channel_name + " Before Registration",
                output_file_name=output_prefix
                + "_before_registration_"
                + channel_name
                + ".pdf",
                file_name_labels=label_names,
            )
            self.__save_correlation_matrix(
                corr_coef_after,
                title=channel_name + " After Registration",
                output_file_name=output_prefix
                + "_after_registration_"
                + channel_name
                + ".pdf",
                file_name_labels=label_names,
            )

        QMessageBox().information(
            self, "Message", "Correlation computations completed."
        )
        self.restart_button.setEnabled(True)
        self.save_correlation_data_button.setEnabled(True)

    def __save_correlation_matrix(
        self, corr_mat, output_file_name, file_name_labels, title=None
    ):

        # Create an image from the correlation values, squares with color corrosponding
        # to value, default color map (viridis)
        fig, ax = plt.subplots(figsize=(15, 15))
        ax.set_aspect(1)
        im = ax.imshow(corr_mat, origin="lower", vmin=0, vmax=1.0)

        width, height = corr_mat.shape

        fontsize = "xx-small"
        if corr_mat.shape[0] < 10:
            fontsize = "small"
        fig.colorbar(im)

        # Write the correlation values onto the axes
        for i in range(width):
            for j in range(height):
                ax.text(
                    j,
                    i,
                    f"{corr_mat[i, j]:.2f}",
                    ha="center",
                    va="center",
                    color="w",
                    fontsize=fontsize,
                )
        # Write the file names as tick marks
        plt.yticks(range(width), file_name_labels[:width], rotation=90, va="center")
        plt.xticks(range(height), file_name_labels[:height])

        if title is not None:
            plt.title(title)
        # File format is determined from the file name extension. vector formats
        # (pdf, ps, eps, svg) are preferred.
        plt.savefig(output_file_name, dpi=150)

    def __register(self):
        self.registration_setup_register_button.setEnabled(False)
        self.advanced_settings_button.setEnabled(False)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        # The registration workflow is designed so that it is readily adapted
        # for groupwise registration. In the current implementation all images are
        # registered to one selected image.
        registration_channel_name = self.registration_channel_combo.currentText()
        self.all_file_names = self.input_files_edit.toPlainText().split("\n")

        # Configure the sitkibex top level logger to report everything and set a handler
        # which will post the messages to a GUI component by emitting a Qt signal
        self.original_logging_level = sitkibex.globals.logger.level
        sitkibex.globals.logger.setLevel(logging.DEBUG)
        sitkibex.globals.logger.addHandler(self.logging_handler)

        # Configure registration class and run in seperate thread
        self.register_images.reset()
        self.register_images.registration_channel_information = list(
            zip(
                self.all_file_names,
                [c_dict[registration_channel_name] for c_dict in self.all_channels],
            )
        )
        self.register_images.fixed_image_index = self.fixed_image_combo.currentIndex()
        self.register_images.do_fft_initialization = (
            self.do_fft_initialization_cb.isChecked()
        )
        self.register_images.do_affine2d = self.do_affine2d_cb.isChecked()
        self.register_images.do_affine3d = self.do_affine3d_cb.isChecked()
        self.register_images.ignore_spacing = self.ignore_spacing_cb.isChecked()
        self.register_images.auto_mask = self.auto_mask_cb.isChecked()
        self.register_images.sigma = float(self.sigma_line_edit.text().strip())
        self.register_images.samples_per_parameter = int(
            self.samples_line_edit.text().strip()
        )
        expand_factor_str = self.expand_factor_line_edit.text().strip()
        self.register_images.expand_factor = (
            int(expand_factor_str) if expand_factor_str else None
        )
        self.register_images.start_resolution = (
            self.start_resolution_combo.currentIndex()
        )
        self.register_images.start()

    def __registration_finished(self):
        QApplication.restoreOverrideCursor()
        self.registration_results = self.register_images.registration_results
        self.resample_size = self.register_images.resample_size
        self.resample_spacing = self.register_images.resample_spacing
        self.resample_origin = self.register_images.resample_origin

        # Undo the logging settings used for registration
        sitkibex.globals.logger.removeHandler(self.logging_handler)
        sitkibex.globals.logger.setLevel(self.original_logging_level)

        output_prefix = os.path.splitext(self.output_file_line_edit.text())[0]
        # Save the registration process log file.
        with open(output_prefix + ".log", "w") as fp:
            fp.write(self.registration_stdout_edit.toPlainText())
        # Save the application settings used for registration (reproducible registration)
        file_names, _ = zip(*self.register_images.registration_channel_information)
        application_settings = {
            "file_names_and_md5": [[name, file_md5(name)] for name in file_names],
            "registration_channel_name": self.registration_channel_combo.currentText(),
            "fixed_image": str(self.fixed_image_combo.currentText()),
            "prefix_separator_character": self.channel_prefix_separator_line_edit.text(),
            "do_fft_initialization": self.register_images.do_fft_initialization,
            "do_affine2d": self.register_images.do_affine2d,
            "do_affine3d": self.register_images.do_affine3d,
            "ignore_spacing": self.register_images.ignore_spacing,
            "sigma": self.register_images.sigma,
            "auto_mask": self.register_images.auto_mask,
            "samples_per_parameter": self.register_images.samples_per_parameter,
            "expand_factor": self.register_images.expand_factor,
            "start_resolution": self.start_resolution_combo.currentIndex(),
        }
        with open(output_prefix + ".json", "w") as fp:
            json.dump(application_settings, fp)

        if not self.processing_error:
            QMessageBox().information(self, "Message", "Registration completed.")
            self.resample_button.setEnabled(True)

    def __on_resample_progress(self, value):
        self.resampling_progress.setValue(value)

    def __resample(self):
        self.resample_button.setEnabled(False)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.resample_images.reset()
        self.resample_images.file_names = self.all_file_names
        self.resample_images.transformations = self.registration_results
        # The parameters describing the fixed image used for registration.
        self.resample_images.resample_size = self.resample_size
        self.resample_images.resample_spacing = self.resample_spacing
        self.resample_images.resample_origin = self.resample_origin
        self.resample_images.output_file_name = self.output_file_line_edit.text()
        self.resample_images.start()

    def __resampling_finished(self):
        QApplication.restoreOverrideCursor()
        self.status_bar.clearMessage()
        if not self.processing_error:
            QMessageBox().information(self, "Message", "Resampling completed.")
            self.__configure_and_show_correlation_analysis_widget()
            self.stack.setCurrentIndex(2)

    def __reset_gui(self):
        """
        Set all of the application default values.
        """
        self.advanced_settings_button.setEnabled(True)
        self.expand_factor_line_edit.setText("")
        self.do_fft_initialization_cb.setChecked(True)
        self.do_affine2d_cb.setChecked(False)
        self.do_affine3d_cb.setChecked(True)
        self.ignore_spacing_cb.setChecked(True)
        self.sigma_line_edit.setText("1.0")
        self.auto_mask_cb.setChecked(False)
        self.samples_line_edit.setText("5000")

        self.input_files_edit.setText("")
        self.channel_prefix_separator_line_edit.setText("")
        self.input_files_next_button.setEnabled(False)

        self.registration_channel_combo.clear()
        self.fixed_image_combo.clear()
        self.registration_setup_register_button.setEnabled(True)
        self.start_resolution_combo.clear()

        self.registration_stdout_edit.setText("")
        self.resampling_progress.setValue(0)
        self.resample_button.setEnabled(False)

        # Remove all widgets from layout, done in reverse order because
        # removing from the begining shifts the rest of the items
        for i in reversed(range(self.correlation_cb_layout.count())):
            self.correlation_cb_layout.itemAt(i).widget().setParent(None)

        self.status_bar.clearMessage()


class RegisterImages(QThread):
    """
    Perform registration in a separate thread. This allows us to potentially use
    a progress bar in the GUI. Currently, the sitkibex.registration() method prints
    information using a Logger. We attach a logging.Handler to it during registration
    and display the information in the GUI.
    """

    processing_error = Signal(str)

    def __init__(self):
        super(RegisterImages, self).__init__()
        self.reset()

    def reset(self):
        # Registration configuration
        self.do_fft_initialization = True
        self.do_affine2d = False
        self.do_affine3d = True
        self.ignore_spacing = True
        self.sigma = 1.0
        self.auto_mask = False
        self.samples_per_parameter = 5000
        self.expand_factor = None
        self.start_resolution = None

        self.registration_channel_information = None
        self.transformations = None
        self.registration_results = None

        # The parameters describing the fixed image used for registration. This
        # can either be an actual image as selected by the fixed_image_index or
        # a mean image if we use groupwise registration to moving mean. The registration
        # algorithm updates these values in the run() method.
        self.resample_size = None
        self.resample_spacing = None
        self.resample_origin = None

    def run(self):
        if (
            self.registration_channel_information is None
            or self.fixed_image_index is None
        ):
            return
        # Get the data used for resampling after registration. Registration may not necesserily
        # use the full resolution image and we want resampling to be on the full resolution.
        meta_data = sio.read_metadata(
            self.registration_channel_information[self.fixed_image_index][0]
        )
        self.resample_size = meta_data["sizes"][0]
        self.resample_spacing = meta_data["spacings"][0]
        self.resample_origin = meta_data["origin"]

        try:
            fixed_image = sio.read(
                file_name=self.registration_channel_information[self.fixed_image_index][
                    0
                ],
                channel_index=self.registration_channel_information[
                    self.fixed_image_index
                ][1],
                resolution_index=self.start_resolution,
            )
            self.registration_results = [None] * len(
                self.registration_channel_information
            )
            self.registration_results[self.fixed_image_index] = sitk.Transform()
            for i, image_data in enumerate(self.registration_channel_information):
                if i != self.fixed_image_index:
                    moving_image = sio.read(
                        file_name=image_data[0],
                        channel_index=image_data[1],
                        resolution_index=self.start_resolution,
                    )
                    self.registration_results[i] = sitkibex.registration(
                        fixed_image,
                        moving_image,
                        do_fft_initialization=self.do_fft_initialization,
                        do_affine2d=self.do_affine2d,
                        do_affine3d=self.do_affine3d,
                        ignore_spacing=self.ignore_spacing,
                        sigma=self.sigma,
                        auto_mask=self.auto_mask,
                        samples_per_parameter=self.samples_per_parameter,
                        expand=self.expand_factor,
                    )
        # Use the stack trace as the error message to provide enough
        # detailes for debugging.
        except Exception:
            self.processing_error.emit(
                "Exception occurred during computation:\n" + traceback.format_exc()
            )


class ResampleImages(QThread):
    progress_signal = Signal(int)
    processing_error = Signal(str)
    update_state_signal = Signal(str)

    def __init__(self):
        super(ResampleImages, self).__init__()
        self.reset()

    def reset(self):
        # The file names and transformations from the registration phase.
        self.file_names = None
        self.transformations = None
        # The parameters describing the fixed image used for registration.
        self.resample_size = None
        self.resample_spacing = None
        self.resample_origin = None

        self.output_file_name = None

    def run(self):
        if (
            self.file_names is None
            or self.transformations is None
            or self.resample_size is None
            or self.resample_spacing is None
            or self.resample_origin is None
            or self.output_file_name is None
        ):
            return
        # Perform resampling on a per channel basis. Accommodates for larger
        # images or machines with less RAM. On windows when the resampling
        # was done on a per image basis, when running out of memory, the results
        # were corrupt, but no memory allocation exception was thrown, so the
        # original code was converted to per-channel resampling.
        try:
            progress_values = []
            channel_indexes = []
            fnames = []
            transforms = []
            for file_name, tx in zip(self.file_names, self.transformations):
                meta_data = sio.read_metadata(file_name)
                num_channels = len(meta_data["channels_information"])
                fnames.extend([file_name] * num_channels)
                channel_indexes.extend(list(range(num_channels)))
                progress_values.extend([np.prod(meta_data["sizes"][0])] * num_channels)
                transforms.extend([tx] * num_channels)
            progress_values = np.cumsum(progress_values)
            progress_values = list(
                map(int, progress_values / progress_values[-1] * 100)
            )
            first_channel = True
            for file_name, c_index, tx, prog in zip(
                fnames, channel_indexes, transforms, progress_values
            ):
                self.update_state_signal.emit("Reading channel...")
                sitk_image = sio.read(file_name, channel_index=c_index)
                self.update_state_signal.emit("Resampling channel...")
                resampled_image = sitk.Resample(
                    sitk_image,
                    self.resample_size,
                    tx,
                    sitk.sitkLinear,
                    self.resample_origin,
                    self.resample_spacing,
                )
                # Copy the meta-data dictionary to the resampled image.
                for k in sitk_image.GetMetaDataKeys():
                    resampled_image.SetMetaData(k, sitk_image.GetMetaData(k))
                self.update_state_signal.emit("Saving channel...")
                if first_channel:
                    sio.write(resampled_image, self.output_file_name)
                    first_channel = False
                else:
                    sio.append_channels(resampled_image, self.output_file_name)
                self.progress_signal.emit(prog)
        # Use the stack trace as the error message to provide enough
        # detailes for debugging.
        except Exception:
            self.processing_error.emit(
                "Exception occurred during computation:\n" + traceback.format_exc()
            )


if __name__ == "__main__":
    XTRegisterSameChannel()
