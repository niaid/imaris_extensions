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
# Channel arithmetic using SimpleITK. Also allows for use of comparitve operators (e.g. >=) to
# create masks for selecting subregions in channels.
#    <CustomTools>
#      <Menu>
#      <Submenu name="SimpleITK Algorithms">
#       <Item name="Channel Arithmetic" icon="Python3" tooltip="Perform arithmetic operations using channels.">
#         <Command>Python3XT::XTChannelArithmetic(%i)</Command>
#       </Item>
#      </Submenu>
#      </Menu>
#    </CustomTools>

import re
import inspect
import traceback

from PySide2.QtWidgets import (
    QWidget,
    QApplication,
    QFileDialog,
    QTextEdit,
    QLabel,
    QPushButton,
    QMessageBox,
    QLineEdit,
    QVBoxLayout,
    QHBoxLayout,
    QCheckBox,
    QProgressBar,
    QColorDialog,
)
from PySide2.QtCore import Qt
from PySide2.QtCore import QThread, Signal
import qdarkstyle

import SimpleITK as sitk
import sitk_ims_file_io as sio
import imaris_extension_base as ieb
from help_dialog import HelpDialog


def XTChannelArithmetic(imaris_id=None):

    app = QApplication([])
    app.setStyle(ieb.style)  # Consistent setting of style for all applications
    app.setStyleSheet(qdarkstyle.load_stylesheet(qt_api="pyside2"))
    channel_arithmetic_dialog = ChannelArithmeticDialog()  # noqa: F841
    app.exec_()


class ChannelArithmeticDialog(ieb.ImarisExtensionBase):
    """
    Channel Arithmetic and Beyond
    =============================
    `View on GitHub <https://github.com/niaid/imaris_extensions>`_

    This program enables you to specify arithmetic expressions which are used to
    create new channels. The basic arithmetic operations are supported: +,-,*,/,**.
    More advanced operations that run short `SimpleITK <https://simpleitk.org/>`_
    code snippets are also supported.

    Channels are referenced using square brackets and the channel index, starting
    at **zero**. To apply an expression to all channels, use the channel index 'i'.

    When creating a single new channel, the arithmetic expression consists of literal
    channel numbers, you can select a name and color for the new channel. When
    creating multiple new channels, the arithmetic expression is applied to all channels,
    the postfix '_modified' is appended to the original channel names and the original
    color is copied over. Note that for all channels created by the program the
    channel description will include the arithmetic expression used to create that
    channel. This transparently supports your efforts to conduct reproducible
    research.

    Because an Imaris image has a specific pixel type (8, 16, 32 bit unsigned integer
    and 32 bit floating point) all computations are performed using a 32 bit floating
    point representation and then clamped to the range of the image's pixel type.

    Basic Examples
    --------------

    Multiply channels zero and three:

    .. code-block:: Python

      [0]*[3]

    Multiply channels zero and three and subtract the result from channel four:

    .. code-block:: Python

      [4] - ([0]*[3])

    Duplicate all channels:

    .. code-block:: Python

      [i]

    Subtract channel zero from all channels:

    .. code-block:: Python

      [i]-[0]


    Advanced Examples
    -----------------

    Threshold channel one using a value of 100, resulting image is binary
    values in {0,1}:

    .. code-block:: Python

      [1]>100

    Threshold a specific channel to create a binary result using the Otsu
    filter:

    .. code-block:: Python

      sitk.OtsuThreshold([1], 0, 1)

    Threshold a specific channel retaining the values above the threshold:

    .. code-block:: Python

      sitk.Cast([1]>100, sitk.sitkFloat32)*[1]

    Threshold a specific channel, get all connected components, then
    sort the components according to size, discarding those smaller than a minimum
    size and create a binary mask corresponding to the largest component, which is
    the first label(second largest component label is 2 etc.)

    .. code-block:: Python

      sitk.RelabelComponent(sitk.ConnectedComponent([1]>100), minimumObjectSize = 50)==1

    Create a binary mask representing the colocalization of two channels,
    intensity values below 20 are considred noise:

    .. code-block:: Python

      ([1]>20)*([2]>20)

    Create a binary mask representing the colocalization of two channels.
    We are interested in all pixels in channel 2 that have a value above 20
    and that are less than 1.0um away from pixels in channel 1 that have a value
    above 100 (**note**: this operation yields different results when run using
    a slice-by-slice approach vs. a volumetric approach):

    .. code-block:: Python

        (sitk.Cast([2]>20, sitk.sitkFloat32) *
         sitk.Abs(sitk.SignedMaurerDistanceMap([1]>100, insideIsPositive=False, squaredDistance=False, useImageSpacing=True)))<=1.0

    Create a binary mask using thresholding and then perform morphological
    closing (dilation followed by erosion) with distance maps, useful
    for filling holes:

    .. code-block:: Python

      sitk.SignedMaurerDistanceMap(sitk.SignedMaurerDistanceMap([1]>100, insideIsPositive=False, squaredDistance=False, useImageSpacing=True) < 1.0, insideIsPositive=False, squaredDistance=False, useImageSpacing=True)<-1.0

    Create a binary mask using thresholding and then perform morphological
    opening (erosion followed by dilation) with distance maps, useful
    for removing small islands:

    .. code-block:: Python

      sitk.SignedMaurerDistanceMap(sitk.SignedMaurerDistanceMap([1]>100, insideIsPositive=False, squaredDistance=False, useImageSpacing=True) < -0.2, insideIsPositive=False, squaredDistance=False, useImageSpacing=True)<0.2
    """  # noqa

    def __init__(self):
        super(ChannelArithmeticDialog, self).__init__()
        # Channel indexes in the arithmetic calculator are denoted using a
        # regular expression: one or more digits in square brackets (e.g. [1234]).
        # First digit is zero and nothing afterwards or first digit is in [1-9] and
        # there are possibly more digits afterwards.
        # Starting index is zero.
        self.arithmetic_calculator = ArithmeticCalculator(
            re.compile(r"\[(0|[1-9]\d*)\]")
        )

        # Configure the help dialog.
        self.help_dialog = HelpDialog(w=700, h=500)
        self.help_dialog.setWindowTitle("Channel Arithmetic Help")
        self.help_dialog.set_rst_text(
            inspect.getdoc(self), pygments_css_file_name="pygments_dark.css"
        )

        self.__create_gui()
        self.setWindowTitle("Channel Arithmetic")
        self.arithmetic_calculator.progress_signal.connect(
            self.computation_progress_bar.setValue
        )
        self.arithmetic_calculator.update_state_signal.connect(
            self.status_bar.showMessage
        )
        self.processing_error = False
        self.arithmetic_calculator.processing_error.connect(
            self._processing_error_function
        )
        # Connect to QThreads finished signal
        self.arithmetic_calculator.finished.connect(self.__arithmetic_finished)

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
        gui_layout = QVBoxLayout()
        central_widget.setLayout(gui_layout)
        self.setCentralWidget(central_widget)

        layout = QHBoxLayout()
        layout.addWidget(QLabel("File name:"))
        self.input_file_line_edit = QLineEdit()
        self.input_file_line_edit.setReadOnly(True)
        self.input_file_line_edit.setToolTip(
            "Select ims file for channel manipulation."
        )
        layout.addWidget(self.input_file_line_edit)
        self.browse_button = QPushButton("Browse")
        self.browse_button.clicked.connect(self.__browse_callback)
        layout.addWidget(self.browse_button)
        gui_layout.addLayout(layout)

        self.valid_indexes_label = QLabel("")
        gui_layout.addWidget(self.valid_indexes_label)

        layout = QHBoxLayout()
        layout.setAlignment(Qt.AlignLeft)
        layout.addWidget(QLabel("Enter new channel arithmetic expression:"))
        gui_layout.addLayout(layout)

        self.arithmetic_expression_text_edit = QTextEdit()
        gui_layout.addWidget(self.arithmetic_expression_text_edit)

        self.slice_by_slice_checkbox = QCheckBox(
            "Slice by slice (smaller memory footprint)."
        )
        gui_layout.addWidget(self.slice_by_slice_checkbox)

        layout = QHBoxLayout()
        layout.addWidget(QLabel("New channel name:"))
        self.new_channel_name_line_edit = QLineEdit()
        layout.addWidget(self.new_channel_name_line_edit)
        gui_layout.addLayout(layout)

        layout = QHBoxLayout()
        layout.addWidget(QLabel("New channel color:"))
        self.new_channel_color_button = QPushButton()
        self.new_channel_color_button.clicked.connect(self.__select_color_callback)
        layout.addWidget(self.new_channel_color_button)
        gui_layout.addLayout(layout)

        self.apply_button = QPushButton("Apply")
        self.apply_button.clicked.connect(self.__channel_arithmetic_wrapper)
        gui_layout.addWidget(self.apply_button)

        self.computation_progress_bar = QProgressBar()
        self.computation_progress_bar.setMaximum(100)
        gui_layout.addWidget(self.computation_progress_bar)

        self.status_bar = self.statusBar()

    def __browse_callback(self):
        file_name, _ = QFileDialog.getOpenFileName(
            self,
            "QFileDialog.getOpenFileName()",
            "",
            "Imaris Images (*.ims);;All Files (*)",
        )
        self.input_file_line_edit.setText(file_name)
        meta_data = sio.read_metadata(file_name)
        self.valid_indexes_label.setText(
            f'Valid channel indexes: 0...{len(meta_data["channels_information"])-1}, i'
        )

    def __select_color_callback(self):
        color = QColorDialog.getColor()
        if color.isValid():
            self.new_channel_color_button.setStyleSheet(
                f"background-color :rgb({color.red()},{color.green()},{color.blue()})"
            )

    def __channel_arithmetic_wrapper(self):
        # Get the arithmetic expression after removing all whitespace
        arithmetic_expression = "".join(
            self.arithmetic_expression_text_edit.toPlainText().split()
        )
        input_file_name = self.input_file_line_edit.text().strip()
        color = self.new_channel_color_button.palette().button().color()

        if input_file_name and arithmetic_expression:
            meta_data = sio.read_metadata(input_file_name)
            channel_indexes = re.findall(
                self.arithmetic_calculator.channel_pattern, arithmetic_expression
            )
            invalid_channels = [
                ci
                for ci in channel_indexes
                if int(ci) not in range(len(meta_data["channels_information"]))
            ]
            if invalid_channels:
                self._error_function(
                    "The following channels specified in the arithmetic expression"
                    + f' are outside the valid range [0,{len(meta_data["channels_information"])}): '
                    + ", ".join(invalid_channels)
                )
                return

            # Disable the UI during computation
            self.browse_button.setEnabled(False)
            self.new_channel_name_line_edit.setReadOnly(True)
            self.new_channel_color_button.setEnabled(False)
            self.arithmetic_expression_text_edit.setReadOnly(True)
            self.apply_button.setEnabled(False)

            # Configure and perform computation in another thread.
            self.arithmetic_calculator.input_file_name = input_file_name
            self.arithmetic_calculator.arithmetic_expression = arithmetic_expression
            self.arithmetic_calculator.new_channel_color = [
                color.red() / 255.0,
                color.green() / 255.0,
                color.blue() / 255.0,
            ]
            self.arithmetic_calculator.new_channel_alpha = color.alpha() / 255.0
            self.arithmetic_calculator.new_channel_name = (
                self.new_channel_name_line_edit.text().strip()
            )
            self.arithmetic_calculator.slice_by_slice = (
                self.slice_by_slice_checkbox.isChecked()
            )
            QApplication.setOverrideCursor(Qt.WaitCursor)
            self.arithmetic_calculator.start()
        else:
            self._error_function(
                "No action taken: input file not selected or arithmetic expression not set."
            )

    def __arithmetic_finished(self):
        QApplication.restoreOverrideCursor()
        self.input_file_line_edit.clear()
        self.valid_indexes_label.setText("")
        self.arithmetic_calculator.reset()
        self.computation_progress_bar.setValue(0)
        self.status_bar.clearMessage()
        self.browse_button.setEnabled(True)
        self.new_channel_name_line_edit.clear()
        self.new_channel_name_line_edit.setReadOnly(False)
        self.new_channel_color_button.setEnabled(True)
        self.arithmetic_expression_text_edit.clear()
        self.arithmetic_expression_text_edit.setReadOnly(False)
        self.apply_button.setEnabled(True)
        if not self.processing_error:
            QMessageBox().information(self, "Message", "Calculation completed.")
        self.processing_error = False


class ArithmeticCalculator(QThread):
    progress_signal = Signal(int)
    update_state_signal = Signal(str)
    processing_error = Signal(str)

    def __init__(self, channel_pattern):
        super(ArithmeticCalculator, self).__init__()
        self.channel_pattern = channel_pattern
        self.reset()

    def reset(self):
        self.input_file_name = ""
        # The arithmetic expression is expected to contain no white space. It is
        # the callers responsibility to ensure this.
        self.arithmetic_expression = ""
        self.new_channel_color = None
        self.new_channel_alpha = None
        self.new_channel_name = ""
        self.slice_by_slice = None

    def run(self):
        try:
            if self.slice_by_slice:
                self.process_slice_by_slice()
            else:
                self.process_vol_by_vol()
        # Use the stack trace as the error message to provide enough
        # detailes for debugging.
        except Exception:
            self.processing_error.emit(
                "Exception occurred during computation:\n" + traceback.format_exc()
            )

    def process_vol_by_vol(self):
        meta_data = sio.read_metadata(self.input_file_name)
        # Read a single pixel image to get the original pixel type
        original_pixel_type = sio.read(
            self.input_file_name,
            channel_index=0,
            sub_ranges=[range(0, 1), range(0, 1), range(0, 1)],
        ).GetPixelID()

        using_all_channels = False
        # Expression is applied to all channels.
        if "[i]" in self.arithmetic_expression:
            using_all_channels = True

        total_work = len(meta_data["times"]) * (
            len(meta_data["channels_information"]) if using_all_channels else 1
        )
        # Channel meta data.
        channel_description = (
            "SimpleITK generated channel from arithmetic expression: "
            + self.arithmetic_expression
        )
        channel_info = {}
        channel_info["color"] = self.new_channel_color
        channel_info["name"] = (
            self.new_channel_name if self.new_channel_name else " "
        )  # name has to have a value no matter what, so set to space
        channel_info["range"] = [0, 255]
        channel_info["alpha"] = self.new_channel_alpha

        if using_all_channels:
            time_entries = len(meta_data["times"])
            for i in range(len(meta_data["channels_information"])):
                for time_index in range(time_entries):
                    self.update_state_signal.emit("Evaluating arithmetic expression...")
                    read_float32_command_str = (
                        f'sitk.Cast(sio.read(file_name="{self.input_file_name}", time_index={time_index}, resolution_index=0, '  # noqa: E501
                        + "channel_index=\\1), sitk.sitkFloat32)"
                    )
                    read_float32_command_str_any_channel = (
                        f'sitk.Cast(sio.read(file_name="{self.input_file_name}", time_index={time_index}, resolution_index=0, '  # noqa: E501
                        + f"channel_index={i}), sitk.sitkFloat32)"
                    )
                    new_channel = sitk.Clamp(
                        eval(
                            self.channel_pattern.sub(
                                read_float32_command_str, self.arithmetic_expression
                            ).replace("[i]", read_float32_command_str_any_channel)
                        ),
                        original_pixel_type,
                    )
                    self.progress_signal.emit(
                        int(100 * (i * time_entries + time_index + 1) / total_work)
                    )
                    channel_info["name"] = (
                        meta_data["channels_information"][i][1]["name"] + "_modified"
                    )
                    channel_info["description"] = channel_description + f", i={i}"
                    if "color" in meta_data["channels_information"][i][1]:
                        channel_info["color"] = meta_data["channels_information"][i][1][
                            "color"
                        ]
                    elif "color_table" in meta_data["channels_information"][i][1]:
                        channel_info["color_table"] = meta_data["channels_information"][
                            i
                        ][1]["color_table"]
                        if "color" in channel_info:
                            del channel_info["color"]
                    channel_info["range"] = meta_data["channels_information"][i][1][
                        "range"
                    ]
                    channel_info["alpha"] = meta_data["channels_information"][i][1][
                        "alpha"
                    ]
                    new_channel.SetMetaData(
                        sio.channels_metadata_key,
                        sio.channels_information_list2xmlstr([(0, channel_info)]),
                    )
                    self.update_state_signal.emit("Saving channel...")
                    sio.append_channels(
                        new_channel, self.input_file_name, time_index=time_index
                    )
        else:
            channel_info["description"] = channel_description
            for time_index in range(len(meta_data["times"])):
                self.update_state_signal.emit("Evaluating arithmetic expression...")
                read_float32_command_str = (
                    f'sitk.Cast(sio.read(file_name="{self.input_file_name}", time_index={time_index}, resolution_index=0, '  # noqa: E501
                    + "channel_index=\\1), sitk.sitkFloat32)"
                )
                new_channel = sitk.Clamp(
                    eval(
                        self.channel_pattern.sub(
                            read_float32_command_str, self.arithmetic_expression
                        )
                    ),
                    original_pixel_type,
                )
                self.progress_signal.emit(int(100 * (time_index + 1) / total_work))
                new_channel.SetMetaData(
                    sio.channels_metadata_key,
                    sio.channels_information_list2xmlstr([(0, channel_info)]),
                )
                self.update_state_signal.emit("Saving channel...")
                sio.append_channels(
                    new_channel, self.input_file_name, time_index=time_index
                )

    def process_slice_by_slice(self):
        meta_data = sio.read_metadata(self.input_file_name)
        # Read a single pixel image to get the original pixel type
        original_pixel_type = sio.read(
            self.input_file_name,
            channel_index=0,
            sub_ranges=[range(0, 1), range(0, 1), range(0, 1)],
        ).GetPixelID()

        using_all_channels = False
        # Expression is applied to all channels.
        if "[i]" in self.arithmetic_expression:
            using_all_channels = True

        img_size = meta_data["sizes"][0]
        total_work = (
            len(meta_data["times"])
            * img_size[2]
            * (len(meta_data["channels_information"]) if using_all_channels else 1)
        )
        # Channel meta data.
        channel_description = (
            "SimpleITK generated channel from arithmetic expression: "
            + self.arithmetic_expression
        )
        channel_info = {}
        channel_info["color"] = self.new_channel_color
        channel_info["name"] = (
            self.new_channel_name if self.new_channel_name else " "
        )  # name has to have a value no matter what, so set to space
        channel_info["range"] = [0, 255]
        channel_info["alpha"] = self.new_channel_alpha

        if using_all_channels:
            time_entries = len(meta_data["times"])
            slice_entries = img_size[2]
            for i in range(len(meta_data["channels_information"])):
                for time_index in range(time_entries):
                    self.update_state_signal.emit("Evaluating arithmetic expression...")
                    z_slices = []
                    for z_index in range(slice_entries):
                        read_float32_command_str = (
                            f'sitk.Cast(sio.read(file_name="{self.input_file_name}", time_index={time_index}, resolution_index=0, '  # noqa: E501
                            + f"channel_index=\\1, sub_ranges=[range(0,{img_size[0]}), range(0,{img_size[1]}), range({z_index},{z_index+1})])[:,:,0], sitk.sitkFloat32)"  # noqa: E501
                        )
                        read_float32_command_str_any_channel = (
                            f'sitk.Cast(sio.read(file_name="{self.input_file_name}", time_index={time_index}, resolution_index=0, '  # noqa: E501
                            + f"channel_index={i}, sub_ranges=[range(0,{img_size[0]}), range(0,{img_size[1]}), range({z_index},{z_index+1})])[:,:,0], sitk.sitkFloat32)"  # noqa: E501
                        )
                        z_slices.append(
                            sitk.Clamp(
                                eval(
                                    self.channel_pattern.sub(
                                        read_float32_command_str,
                                        self.arithmetic_expression,
                                    ).replace(
                                        "[i]", read_float32_command_str_any_channel
                                    )
                                ),
                                original_pixel_type,
                            )
                        )
                        self.progress_signal.emit(
                            int(
                                100
                                * (
                                    i * time_entries * slice_entries
                                    + time_index * slice_entries
                                    + z_index
                                    + 1
                                )
                                / total_work
                            )
                        )
                    new_channel = sitk.JoinSeries(z_slices)
                    new_channel.SetOrigin(meta_data["origin"])
                    new_channel.SetSpacing(meta_data["spacings"][0])
                    channel_info["name"] = (
                        meta_data["channels_information"][i][1]["name"] + "_modified"
                    )
                    channel_info["description"] = channel_description + f", i={i}"
                    if "color" in meta_data["channels_information"][i][1]:
                        channel_info["color"] = meta_data["channels_information"][i][1][
                            "color"
                        ]
                    elif "color_table" in meta_data["channels_information"][i][1]:
                        channel_info["color_table"] = meta_data["channels_information"][
                            i
                        ][1]["color_table"]
                        if "color" in channel_info:
                            del channel_info["color"]
                    channel_info["range"] = meta_data["channels_information"][i][1][
                        "range"
                    ]
                    channel_info["alpha"] = meta_data["channels_information"][i][1][
                        "alpha"
                    ]
                    new_channel.SetMetaData(
                        sio.channels_metadata_key,
                        sio.channels_information_list2xmlstr([(0, channel_info)]),
                    )
                    self.update_state_signal.emit("Saving channel...")
                    sio.append_channels(
                        new_channel, self.input_file_name, time_index=time_index
                    )
        else:
            channel_info["description"] = channel_description
            for time_index in range(len(meta_data["times"])):
                self.update_state_signal.emit("Evaluating arithmetic expression...")
                z_slices = []
                for z_index in range(img_size[2]):
                    read_float32_command_str = (
                        f'sitk.Cast(sio.read(file_name="{self.input_file_name}", time_index={time_index}, resolution_index=0, '  # noqa: E501
                        + f"channel_index=\\1, sub_ranges=[range(0,{img_size[0]}), range(0,{img_size[1]}), range({z_index},{z_index+1})])[:,:,0], sitk.sitkFloat32)"  # noqa: E501
                    )
                    z_slices.append(
                        sitk.Clamp(
                            eval(
                                self.channel_pattern.sub(
                                    read_float32_command_str, self.arithmetic_expression
                                )
                            ),
                            original_pixel_type,
                        )
                    )
                    self.progress_signal.emit(
                        int((100 * time_index * img_size[2] + z_index + 1) / total_work)
                    )
                new_channel = sitk.JoinSeries(z_slices)
                new_channel.SetOrigin(meta_data["origin"])
                new_channel.SetSpacing(meta_data["spacings"][0])
                new_channel.SetMetaData(
                    sio.channels_metadata_key,
                    sio.channels_information_list2xmlstr([(0, channel_info)]),
                )
                self.update_state_signal.emit("Saving channel...")
                sio.append_channels(
                    new_channel, self.input_file_name, time_index=time_index
                )


if __name__ == "__main__":
    XTChannelArithmetic()
