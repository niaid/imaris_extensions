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
#    <CustomTools>
#      <Menu>
#      <Submenu name="SimpleITK Algorithms">
#       <Item name="Virtual H/E Staining" icon="Python3" tooltip="Virtual H/E from fluorescence imaging.">
#         <Command>Python3XT::XTVirtualHEStain(%i)</Command>
#       </Item>
#      </Submenu>
#      </Menu>
#    </CustomTools>

import os
import inspect
import traceback

from PySide2.QtWidgets import (
    QWidget,
    QApplication,
    QFileDialog,
    QTextEdit,
    QLabel,
    QPushButton,
    QStackedWidget,
    QMessageBox,
    QVBoxLayout,
    QHBoxLayout,
    QComboBox,
    QProgressBar,
)
from PySide2.QtCore import Qt
from PySide2.QtCore import QThread, Signal
import qdarkstyle

import SimpleITK as sitk
import sitk_ims_file_io as sio
import imaris_extension_base as ieb
from help_dialog import HelpDialog


def XTVirtualHEStain(imaris_id=None):

    app = QApplication([])
    app.setStyle(ieb.style)  # Consistent setting of style for all applications
    app.setStyleSheet(qdarkstyle.load_stylesheet(qt_api="pyside2"))
    virtual_stainer_dialog = VirtualHEStainDialog()  # noqa: F841
    app.exec_()


class VirtualHEStainDialog(ieb.ImarisExtensionBase):
    """
    Virtual H&E Staining
    ====================
    `View on GitHub <https://github.com/niaid/imaris_extensions>`_

    This program creates a virtual Hematoxylin and Eosin (H&E) image
    from a fluorescence microscopy image. Similar to H&E staining, where
    Hematoxylin stains the cell nuclei and Eosin stains the extracellular matrix and
    cytoplasm, this program creates a virtual H&E image using a fluorescence channel
    corresponding to a nuclear stain (e.g. DAPI, Hoechest) and a channel which
    corresponds to the extracellular matrix and cytoplasm
    (e.g. Desmin-AF488, CD45-AF532).

    This is an implementation of the algorithms described in:

    1. D. S. Gareau, "The feasibility of digitally stained multimodal confocal mosaics to
       simulate histopathology", J Biomed Opt, 14(3):03405, 2009,
       `doi: 10.1117/1.3149853 <https://doi.org/10.1117/1.3149853>`_.
    2. M. G. Giacomelli et al., "Virtual Hematoxylin and Eosin Transillumination Microscopy Using
       Epi-Fluorescence Imaging", PLoS One, 11(8):e0159337 2016,
       `doi: 10.1371/journal.pone.0159337 <https://doi.org/10.1371/journal.pone.0159337>`_.

    Input/Output
    ------------

    The program will allow you to create virtual H&E staining for one or more
    images. You will need to specify which channel to use as a surrogate for
    Hematoxylin and which for Eosin. Therefore, if you intend to work
    on a batch of images, the same surrogates for H&E are expected to
    appear in all of them (channel equivalence is based on the channels having
    the same name in all the files).

    The program adds three new channels to the original image simulating the
    RGB colors of an H&E stain. The channels are named "virtual H&E ch1" (red channel),
    "virtual H&E ch2" (green channel) and "virtual H&E ch3" (blue channel).
    Note that the channel description for each of these new channels will include
    the algorithm used to create it and the surrogate H&E channels it utilized.
    This transparently supports your efforts to conduct reproducible
    research.
    """

    def __init__(self):
        super(VirtualHEStainDialog, self).__init__()
        self.virtual_stainer = VirtualHEStainer()
        self.output_directory = ""

        # Configure the help dialog.
        self.help_dialog = HelpDialog(w=700, h=500)
        self.help_dialog.setWindowTitle("Virtual H&E Staining Help")
        self.help_dialog.set_rst_text(
            inspect.getdoc(self), pygments_css_file_name="pygments_dark.css"
        )

        self.__create_gui()
        self.setWindowTitle("Virtual H&E Staining from Fluorescence Imaging")
        self.virtual_stainer.progress_signal.connect(self.__on_progress)
        self.virtual_stainer.staining_signal.connect(self.__on_staining)
        self.virtual_stainer.saving_image_signal.connect(self.__on_saving_file)
        # Connect to QThreads finished signal
        self.virtual_stainer.finished.connect(self.__stain_finished)
        self.show()

    def __create_gui(self):
        menu_bar = self.menuBar()
        # Force menubar to be displayed in the application on OSX/Linux, otherwise it
        # is displayed in the system menubar
        menu_bar.setNativeMenuBar(False)
        self.help_button = QPushButton("Help")
        self.help_button.clicked.connect(self.help_dialog.show)
        menu_bar.setCornerWidget(self.help_button, Qt.TopLeftCorner)

        central_widget = QWidget(self)
        layout = QVBoxLayout()
        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)

        select_input_files_widget = self.__create_select_input_widget()
        select_he_surrogates_widget = self.__create_he_surrogates_widget()
        apply_widget = self.__create_apply_widget()

        self.stack = QStackedWidget(self)
        self.stack.addWidget(select_input_files_widget)
        self.stack.addWidget(select_he_surrogates_widget)
        self.stack.addWidget(apply_widget)
        layout.addWidget(self.stack)

        self.status_bar = self.statusBar()

    def __show_stacked_widget(self, i):
        self.stack.setCurrentIndex(i)

    def __create_select_input_widget(self):
        wid = QWidget()
        input_layout = QVBoxLayout()
        wid.setLayout(input_layout)

        layout = QHBoxLayout()
        layout.addWidget(QLabel("File names:"))
        layout.setAlignment(Qt.AlignLeft)
        button = QPushButton("Browse")
        button.setToolTip("Select input files for batch processing.")
        button.clicked.connect(self.__browse_select_input_callback)
        layout.addWidget(button)
        input_layout.addLayout(layout)

        self.input_files_edit = QTextEdit()
        self.input_files_edit.setReadOnly(True)
        input_layout.addWidget(self.input_files_edit)

        layout = QHBoxLayout()
        layout.setAlignment(Qt.AlignRight)
        self.input_files_next_button = QPushButton("Next")
        self.input_files_next_button.setEnabled(False)
        self.input_files_next_button.clicked.connect(
            lambda: self.__show_stacked_widget(1)
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
            self.input_files_edit.setText("\n".join(file_names))
            # get all channel names and make sure that there are at least two common
            # channels across the files.
            channel_names = []
            self.total_pixel_num = 0
            for f in file_names:
                metadata_dict = sio.read_metadata(f)
                channel_names.append(
                    [c["name"] for _, c in metadata_dict["channels_information"]]
                )
                self.total_pixel_num += (
                    metadata_dict["sizes"][0][0]
                    * metadata_dict["sizes"][0][1]
                    * metadata_dict["sizes"][0][2]
                )
            shared_channels = set(channel_names[0])
            for c in channel_names[1:]:
                shared_channels = shared_channels & set(c)
            if len(shared_channels) < 2:  # The files don't share enough channels
                self.__error_function(
                    "Selected files do not share two or more channels.<br>"
                    + "Cannot apply batch virtual H&E staining."
                )
                return
            # Add names to dropbox
            self.h_combo.addItems(list(shared_channels))
            self.e_combo.addItems(list(shared_channels))
            self.input_files_next_button.setEnabled(True)

    def __create_he_surrogates_widget(self):
        wid = QWidget()
        input_layout = QVBoxLayout()
        wid.setLayout(input_layout)

        layout = QHBoxLayout()
        layout.addWidget(QLabel("Hematoxylin Surrogate:"))
        self.h_combo = QComboBox()
        self.h_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        layout.addWidget(self.h_combo)
        input_layout.addLayout(layout)

        layout = QHBoxLayout()
        layout.addWidget(QLabel("Eosin Surrogate:"))
        self.e_combo = QComboBox()
        self.e_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        layout.addWidget(self.e_combo)
        input_layout.addLayout(layout)

        layout = QHBoxLayout()
        layout.setAlignment(Qt.AlignRight)
        next_button = QPushButton("Next")
        next_button.clicked.connect(lambda: self.__show_stacked_widget(2))
        layout.addWidget(next_button)

        input_layout.addLayout(layout)
        return wid

    def __create_apply_widget(self):
        wid = QWidget()
        apply_layout = QVBoxLayout()
        wid.setLayout(apply_layout)

        layout = QHBoxLayout()
        layout.addWidget(QLabel("Select algorithm:"))
        self.algorithm_combo = QComboBox()
        self.algorithm_combo.addItems(self.virtual_stainer.get_algorithm_names())
        layout.addWidget(self.algorithm_combo)
        apply_layout.addLayout(layout)

        self.progress = QProgressBar()
        self.progress.setMaximum(100)
        apply_layout.addWidget(self.progress)

        self.apply_button = QPushButton("Apply")
        self.apply_button.clicked.connect(self.__virtual_stain_wrapper)
        apply_layout.addWidget(self.apply_button)

        return wid

    def __on_progress(self, value):
        self.progress.setValue(value)

    def __on_saving_file(self, file_name):
        QMessageBox().information(
            self, "Message", "Computation completed, starting to write to disk."
        )
        self.status_bar.clearMessage()
        self.status_bar.showMessage(f"Saving {file_name}...")

    def __on_staining(self, file_name):
        self.status_bar.clearMessage()
        self.status_bar.showMessage(f"Virtual staining {file_name}...")

    def __browse_output_dir_callback(self):
        dir_name = str(
            QFileDialog.getExistingDirectory(self, "Select Output Directory")
        )
        if dir_name:
            self.output_dir_line_edit.setText(dir_name)

    def __virtual_stain_wrapper(self):
        self.apply_button.setEnabled(False)
        self.virtual_stainer.input_file_names = (
            self.input_files_edit.toPlainText().split("\n")
        )
        self.virtual_stainer.h_str = str(self.h_combo.currentText())
        self.virtual_stainer.e_str = str(self.e_combo.currentText())
        self.virtual_stainer.algorithm_name = str(self.algorithm_combo.currentText())
        self.virtual_stainer.total_pixels = self.total_pixel_num
        self.virtual_stainer.start()

    def __stain_finished(self):
        self.virtual_stainer.reset()
        self.progress.setValue(0)
        self.status_bar.clearMessage()
        self.apply_button.setEnabled(True)
        if not self.processing_error:
            QMessageBox().information(self, "Message", "Virtual staining completed.")
        self.processing_error = False


class VirtualHEStainer(QThread):
    progress_signal = Signal(int)
    saving_image_signal = Signal(str)
    staining_signal = Signal(str)

    def __init__(self):
        super(VirtualHEStainer, self).__init__()
        self.algorithms = {
            "Giacomelli 2016": self.__giacomelli_virtual_stain,
            "Gareau 2009": self.__gareau_virtual_stain,
        }
        self.reset()

    def reset(self):
        self.input_file_names = []
        # self.output_directory = ''
        self.h_str = ""
        self.e_str = ""
        self.algorithm_name = list(self.algorithms.keys())[0]
        # only parameter that is related to the GUI
        self.total_pixels = None

    def __gareau_virtual_stain(self, h_channel, e_channel):
        virtual_he = [
            1.0 - 0.7 * h_channel,
            1.0 - 0.8 * h_channel - 0.45 * e_channel,
            1.0 - 0.12 * e_channel,
        ]
        return sitk.Compose(
            [
                sitk.Clamp(c * 255.0, sitk.sitkUInt8, lowerBound=0, upperBound=255)
                for c in virtual_he
            ]
        )

    def __giacomelli_virtual_stain(self, h_channel, e_channel):
        virtual_he = [
            (sitk.Exp(-0.125 * e_channel) - 0.0821)
            * (sitk.Exp(-2.15 * h_channel) - 0.0821)
            * 1.18679236,
            (sitk.Exp(-2.5 * e_channel) - 0.0821)
            * (sitk.Exp(-2.5 * h_channel) - 0.0821)
            * 1.18679236,
            (sitk.Exp(-1.36 * e_channel) - 0.0821)
            * (sitk.Exp(-0.75 * h_channel) - 0.0821)
            * 1.18679236,
        ]
        return sitk.Compose(
            [
                sitk.Clamp(c * 255.0, sitk.sitkUInt8, lowerBound=0, upperBound=255)
                for c in virtual_he
            ]
        )

    def get_algorithm_names(self):
        return list(self.algorithms.keys())

    def run(self):
        if (
            not self.input_file_names
            or not self.h_str
            or not self.e_str
            or self.total_pixels is None
        ):
            return
        try:
            current_work_done = 0
            for file_name in self.input_file_names:
                self.staining_signal.emit(os.path.basename(file_name))
                metadata_dict = sio.read_metadata(file_name)
                channel_settings_list = metadata_dict["channels_information"]
                channel_names = [c["name"] for _, c in channel_settings_list]
                h_index = channel_names.index(self.h_str)
                e_index = channel_names.index(self.e_str)
                image_size = metadata_dict["sizes"][0]
                slice_pixel_num = image_size[0] * image_size[1]

                # We process the images slice by slice due to memory constraints.
                virtual_he_slices = []
                for slc_index in range(image_size[2]):
                    hematoxlin_surrogate_channel = sio.read(
                        file_name,
                        channel_index=h_index,
                        sub_ranges=[
                            slice(0, image_size[0]),
                            slice(0, image_size[1]),
                            slice(slc_index, slc_index + 1),
                        ],
                    )[:, :, 0]
                    eosin_surrogate_channel = sio.read(
                        file_name,
                        channel_index=e_index,
                        sub_ranges=[
                            slice(0, image_size[0]),
                            slice(0, image_size[1]),
                            slice(slc_index, slc_index + 1),
                        ],
                    )[:, :, 0]
                    if hematoxlin_surrogate_channel.GetPixelID() == sitk.sitkUInt8:
                        hematoxlin_surrogate_channel = (
                            sitk.Cast(hematoxlin_surrogate_channel, sitk.sitkFloat32)
                            / 255.0
                        )
                        eosin_surrogate_channel = (
                            sitk.Cast(eosin_surrogate_channel, sitk.sitkFloat32) / 255.0
                        )
                    h_channel = sitk.RescaleIntensity(
                        hematoxlin_surrogate_channel, 0.0, 1.0
                    )
                    e_channel = sitk.RescaleIntensity(eosin_surrogate_channel, 0.0, 1.0)
                    virtual_he_slices.append(
                        self.algorithms[self.algorithm_name](h_channel, e_channel)
                    )
                    current_work_done += slice_pixel_num
                    self.progress_signal.emit(
                        int(100 * current_work_done / self.total_pixels)
                    )
                virtual_he = sitk.JoinSeries(virtual_he_slices)
                virtual_he.SetOrigin(metadata_dict["origin"])
                virtual_he.SetSpacing(metadata_dict["spacings"][0])

                channel_description = (
                    f"SimpleITK generated virtual H&E staining (algorithm: {self.algorithm_name},"
                    + f"H surrogate channel: {self.h_str}, E surrogate channel: {self.e_str})"
                )
                channels_information = [
                    (
                        0,
                        {
                            "name": "virtual H&E ch1",
                            "description": channel_description,
                            "color": [1.0, 0.0, 0.0],
                            "range": [0.0, 255.0],
                            "alpha": 1.0,
                            "gamma": 1.0,
                        },
                    ),
                    (
                        1,
                        {
                            "name": "virtual H&E ch2",
                            "description": channel_description,
                            "color": [0.0, 1.0, 0.0],
                            "range": [0.0, 255.0],
                            "alpha": 1.0,
                            "gamma": 1.0,
                        },
                    ),
                    (
                        2,
                        {
                            "name": "virtual H&E ch3",
                            "description": channel_description,
                            "color": [0.0, 0.0, 1.0],
                            "range": [0.0, 255.0],
                            "alpha": 1.0,
                            "gamma": 1.0,
                        },
                    ),
                ]
                virtual_he.SetMetaData(
                    sio.channels_metadata_key,
                    sio.channels_information_list2xmlstr(channels_information),
                )
                self.saving_image_signal.emit(os.path.basename(file_name))
                sio.append_channels(virtual_he, file_name)
        # Use the stack trace as the error message to provide enough
        # detailes for debugging.
        except RuntimeError:
            self.processing_error.emit(
                "Exception occurred during computation:\n" + traceback.format_exc()
            )


if __name__ == "__main__":
    XTVirtualHEStain()
