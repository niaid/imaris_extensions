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
import os

from PySide2.QtWidgets import (
    QStackedWidget,
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
    QGridLayout,
    QCheckBox,
    QProgressBar,
    QColorDialog,
    QScrollArea,
)
from PySide2.QtCore import Qt, QObject, QRunnable, Signal, QThreadPool
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

    This program enables one to specify arithmetic expressions which are used to
    create new channels. The basic arithmetic operations are supported: +,-,*,/,**.
    More advanced operations that run short `SimpleITK <https://simpleitk.org/>`_
    code snippets are also supported.

    Channels are referenced using square brackets and the channel index, starting
    at **zero**. To apply an expression to all channels, use the channel index 'i'.

    When creating a single new channel, the arithmetic expression consists of literal
    channel numbers, one can select a name and color for the new channel. When
    creating multiple new channels, the arithmetic expression is applied to all channels,
    the postfix '_modified' is appended to the original channel names and the original
    color is copied over. Note that for all channels created by the program the
    channel description will include the arithmetic expression used to create that
    channel. This transparently supports your efforts to conduct reproducible
    research.

    Because an Imaris image has a specific pixel type (8, 16, 32 bit unsigned integer
    and 32 bit floating point) all computations are performed using a 32 bit floating
    point representation and then clamped to the range of the image's pixel type.

    The program allows you to use the same expression on multiple files. In this
    case literal channel values are limited by the number of shared channels. Thus,
    if working with two files one with three channels and one with four channels,
    the valid literal channel values are limited to 0, 1, 2. We cannot use 3 as it does not
    exist in all files. On the other hand, if our autofluorescence channel is one
    of these channels, e.g. channel 0, we can subtract it from all channels in
    both files, `[i]-[0]`.

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
        self.channel_pattern = re.compile(r"\[(0|[1-9]\d*)\]")

        # Use QT's global threadpool, documentation says: "This global thread pool
        # automatically maintains an optimal number of threads based on the
        # number of cores in the CPU."
        self.threadpool = QThreadPool.globalInstance()

        # Configure the help dialog.
        self.help_dialog = HelpDialog(w=700, h=500)
        self.help_dialog.setWindowTitle("Channel Arithmetic Help")
        self.help_dialog.set_rst_text(
            inspect.getdoc(self), pygments_css_file_name="pygments_dark.css"
        )

        self.__create_gui()
        self.setWindowTitle("Channel Arithmetic")
        self.processing_error = False

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

        select_files_widget = self.__create_select_files_widget()
        arithmetic_widget = self.__create_arithmetic_widget()

        self.stack = QStackedWidget(self)
        self.stack.addWidget(select_files_widget)
        self.stack.addWidget(arithmetic_widget)
        gui_layout.addWidget(self.stack)

        self.status_bar = self.statusBar()

    def closeEvent(self, event):
        """
        Override the closeEvent method so that clicking the 'x' button also
        closes all of the dialogs.
        """
        self.help_dialog.close()
        event.accept()

    def __create_arithmetic_widget(self):
        wid = QWidget(self)
        arithmetic_layout = QVBoxLayout()
        wid.setLayout(arithmetic_layout)

        self.valid_indexes_label = QLabel("")
        arithmetic_layout.addWidget(self.valid_indexes_label)

        layout = QHBoxLayout()
        layout.setAlignment(Qt.AlignLeft)
        layout.addWidget(QLabel("Enter new channel arithmetic expression:"))
        arithmetic_layout.addLayout(layout)

        self.arithmetic_expression_text_edit = QTextEdit()
        arithmetic_layout.addWidget(self.arithmetic_expression_text_edit)

        self.slice_by_slice_checkbox = QCheckBox(
            "Slice by slice (smaller memory footprint)."
        )
        arithmetic_layout.addWidget(self.slice_by_slice_checkbox)

        layout = QHBoxLayout()
        layout.addWidget(QLabel("New channel name:"))
        self.new_channel_name_line_edit = QLineEdit()
        layout.addWidget(self.new_channel_name_line_edit)
        arithmetic_layout.addLayout(layout)

        layout = QHBoxLayout()
        layout.addWidget(QLabel("New channel color:"))
        self.new_channel_color_button = QPushButton()
        self.new_channel_color_button.clicked.connect(self.__select_color_callback)
        layout.addWidget(self.new_channel_color_button)
        arithmetic_layout.addLayout(layout)

        self.apply_button = QPushButton("Apply")
        self.apply_button.clicked.connect(self.__channel_arithmetic_wrapper)
        arithmetic_layout.addWidget(self.apply_button)

        progress_wid = QWidget()
        self.progress_grid_layout = QGridLayout()
        progress_wid.setLayout(self.progress_grid_layout)
        scroll_area = QScrollArea()
        scroll_area.setWidget(progress_wid)
        scroll_area.setWidgetResizable(True)
        arithmetic_layout.addWidget(scroll_area)

        layout = QHBoxLayout()
        layout.setAlignment(Qt.AlignLeft)
        self.processing_prev_button = QPushButton("Prev")
        self.processing_prev_button.clicked.connect(
            lambda: self.stack.setCurrentIndex(0)
        )
        layout.addWidget(self.processing_prev_button)
        arithmetic_layout.addLayout(layout)

        return wid

    def __configure_and_show_arithmetic_widget(self):
        file_names = self.input_files_edit.toPlainText().split("\n")
        num_channels = []
        problematic_images = []
        for file_name in file_names:
            try:
                meta_data = sio.read_metadata(file_name)
                num_channels.append(len(meta_data["channels_information"]))
            except Exception:
                problematic_images.append(file_name)
        if problematic_images:
            self._error_function(
                "Problem encountered reading the following file(s):\n"
                + "\n".join(problematic_images)
            )
            return
        self.max_channel_index = min(num_channels) - 1
        self.valid_indexes_label.setText(
            f"Valid channel indexes: 0...{self.max_channel_index}, i"
        )
        self.arithmetic_expression_text_edit.clear()
        self.slice_by_slice_checkbox.setChecked(False)
        self.new_channel_name_line_edit.clear()

        # Remove all widgets from layout, done in reverse order because
        # removing from the begining shifts the rest of the items
        for i in reversed(range(self.progress_grid_layout.count())):
            self.progress_grid_layout.itemAt(i).widget().setParent(None)

        for i, file_name in enumerate(file_names):
            self.progress_grid_layout.addWidget(
                QLabel(os.path.basename(file_name)), i, 0
            )
            progress_bar = QProgressBar()
            progress_bar.setMaximum(100)
            self.progress_grid_layout.addWidget(progress_bar, i, 1)

        self.stack.setCurrentIndex(1)

    def __create_select_files_widget(self):
        wid = QWidget()
        input_layout = QVBoxLayout()
        wid.setLayout(input_layout)

        layout = QHBoxLayout()
        layout.addWidget(QLabel("File names:"))
        layout.setAlignment(Qt.AlignLeft)
        button = QPushButton("Browse")
        button.setToolTip("Select input files for arithmetic operation.")
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
            self.__configure_and_show_arithmetic_widget
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
            self.input_files_next_button.setEnabled(True)

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
        color = self.new_channel_color_button.palette().button().color()

        if arithmetic_expression:
            # Get the explicit channel indexes that appear in the expression and
            # check that they are in the valid range.
            channel_indexes = re.findall(self.channel_pattern, arithmetic_expression)
            invalid_channels = [
                ci
                for ci in channel_indexes
                if int(ci) not in range(self.max_channel_index + 1)
            ]
            if invalid_channels:
                self._error_function(
                    "The following channels specified in the arithmetic expression"
                    + f" are outside the valid range [0,{self.max_channel_index}]: "
                    + ", ".join(invalid_channels)
                )
                return

            # Disable the UI interaction during computation
            self.arithmetic_expression_text_edit.setReadOnly(True)
            self.slice_by_slice_checkbox.setEnabled(False)
            self.new_channel_name_line_edit.setReadOnly(True)
            self.new_channel_color_button.setEnabled(False)
            self.apply_button.setEnabled(False)
            self.processing_prev_button.setEnabled(False)

            QApplication.setOverrideCursor(Qt.WaitCursor)
            file_names = self.input_files_edit.toPlainText().split("\n")
            self.num_threads_left = len(file_names)
            for i, input_file_name in enumerate(file_names):
                # Configure and perform computation in another thread.
                arithmetic_calculator = ArithmeticCalculator(self.channel_pattern)
                arithmetic_calculator.signals.finished.connect(
                    self.__arithmetic_finished
                )
                arithmetic_calculator.signals.processing_error.connect(
                    self._processing_error_function
                )
                arithmetic_calculator.signals.progress_signal.connect(
                    self.progress_grid_layout.itemAtPosition(i, 1).widget().setValue
                )
                arithmetic_calculator.signals.update_state_signal.connect(
                    self.status_bar.showMessage
                )
                arithmetic_calculator.input_file_name = input_file_name
                arithmetic_calculator.arithmetic_expression = arithmetic_expression
                arithmetic_calculator.new_channel_color = [
                    color.red() / 255.0,
                    color.green() / 255.0,
                    color.blue() / 255.0,
                ]
                arithmetic_calculator.new_channel_alpha = color.alpha() / 255.0
                arithmetic_calculator.new_channel_name = (
                    self.new_channel_name_line_edit.text().strip()
                )
                arithmetic_calculator.slice_by_slice = (
                    self.slice_by_slice_checkbox.isChecked()
                )
                self.threadpool.start(arithmetic_calculator)
        else:
            self._error_function("No action taken: arithmetic expression not set.")

    def __arithmetic_finished(self):
        self.num_threads_left = self.num_threads_left - 1
        if self.num_threads_left == 0:
            QApplication.restoreOverrideCursor()
            self.status_bar.clearMessage()
            for i in range(self.progress_grid_layout.rowCount()):
                self.progress_grid_layout.itemAtPosition(i, 1).widget().setValue(0)
            # Enable the UI interaction after computation
            self.arithmetic_expression_text_edit.setReadOnly(False)
            self.slice_by_slice_checkbox.setEnabled(True)
            self.new_channel_name_line_edit.setReadOnly(False)
            self.new_channel_color_button.setEnabled(True)
            self.apply_button.setEnabled(True)
            self.processing_prev_button.setEnabled(True)

            # Inform the user that the calculations completed. If processing errors
            # occured then the desired operation may not have happened, but the
            # calculation was completed.
            QMessageBox().information(self, "Message", "Calculation completed.")
            self.processing_error = False


class ArithmeticCalculatorSignals(QObject):
    progress_signal = Signal(int)
    update_state_signal = Signal(str)
    processing_error = Signal(str)
    finished = Signal()


class ArithmeticCalculator(QRunnable):
    def __init__(self, channel_pattern):
        super(ArithmeticCalculator, self).__init__()
        self.channel_pattern = channel_pattern
        self.signals = ArithmeticCalculatorSignals()

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
            self.signals.finished.emit()
        # Use the stack trace as the error message to provide enough
        # detailes for debugging.
        except Exception:
            self.signals.processing_error.emit(
                "Exception occurred during computation:\n" + traceback.format_exc()
            )
            self.signals.finished.emit()

    def process_vol_by_vol(self):
        meta_data = sio.read_metadata(self.input_file_name)
        message_fname = os.path.basename(self.input_file_name)
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
        )  # Name has to have a value no matter what, so set to space
        channel_info["range"] = [0, 255]
        channel_info["alpha"] = self.new_channel_alpha

        if using_all_channels:
            time_entries = len(meta_data["times"])
            for i in range(len(meta_data["channels_information"])):
                for time_index in range(time_entries):
                    self.signals.update_state_signal.emit(
                        f"Evaluating arithmetic expression ({message_fname})..."
                    )
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
                    self.signals.progress_signal.emit(
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
                    self.signals.update_state_signal.emit(
                        f"Saving channel ({message_fname})..."
                    )
                    sio.append_channels(
                        new_channel, self.input_file_name, time_index=time_index
                    )
        else:
            channel_info["description"] = channel_description
            for time_index in range(len(meta_data["times"])):
                self.signals.update_state_signal.emit(
                    f"Evaluating arithmetic expression ({message_fname})..."
                )
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
                self.signals.progress_signal.emit(
                    int(100 * (time_index + 1) / total_work)
                )
                new_channel.SetMetaData(
                    sio.channels_metadata_key,
                    sio.channels_information_list2xmlstr([(0, channel_info)]),
                )
                self.signals.update_state_signal.emit(
                    f"Saving channel ({message_fname})..."
                )
                sio.append_channels(
                    new_channel, self.input_file_name, time_index=time_index
                )

    def process_slice_by_slice(self):
        meta_data = sio.read_metadata(self.input_file_name)
        message_fname = os.path.basename(self.input_file_name)
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
        )  # Name has to have a value no matter what, so set to space
        channel_info["range"] = [0, 255]
        channel_info["alpha"] = self.new_channel_alpha

        if using_all_channels:
            time_entries = len(meta_data["times"])
            slice_entries = img_size[2]
            for i in range(len(meta_data["channels_information"])):
                for time_index in range(time_entries):
                    self.signals.update_state_signal.emit(
                        f"Evaluating arithmetic expression ({message_fname})..."
                    )
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
                        self.signals.progress_signal.emit(
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
                    self.signals.update_state_signal.emit(
                        f"Saving channel ({message_fname})..."
                    )
                    sio.append_channels(
                        new_channel, self.input_file_name, time_index=time_index
                    )
        else:
            channel_info["description"] = channel_description
            for time_index in range(len(meta_data["times"])):
                self.signals.update_state_signal.emit(
                    f"Evaluating arithmetic expression ({message_fname})..."
                )
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
                    self.signals.progress_signal.emit(
                        int((100 * time_index * img_size[2] + z_index + 1) / total_work)
                    )
                new_channel = sitk.JoinSeries(z_slices)
                new_channel.SetOrigin(meta_data["origin"])
                new_channel.SetSpacing(meta_data["spacings"][0])
                new_channel.SetMetaData(
                    sio.channels_metadata_key,
                    sio.channels_information_list2xmlstr([(0, channel_info)]),
                )
                self.signals.update_state_signal.emit(
                    f"Saving channel ({message_fname})..."
                )
                sio.append_channels(
                    new_channel, self.input_file_name, time_index=time_index
                )


if __name__ == "__main__":
    XTChannelArithmetic()
