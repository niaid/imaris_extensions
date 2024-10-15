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
# Colocalization analysis using SimpleITK.
#    <CustomTools>
#      <Menu>
#      <Submenu name="SimpleITK Algorithms">
#       <Item name="Colocalization Analysis" icon="Python3" tooltip="Compute various quantities characterizing colocalization."> # noqa: E501
#         <Command>Python3XT::XTColocalizationAnalysis(%i)</Command>
#       </Item>
#      </Submenu>
#      </Menu>
#    </CustomTools>

import inspect
import traceback
import os
import numpy as np
import pandas as pd
import scipy.stats

from PySide6.QtWidgets import (
    QStackedWidget,
    QWidget,
    QApplication,
    QFileDialog,
    QTextEdit,
    QLabel,
    QComboBox,
    QPushButton,
    QMessageBox,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QCheckBox,
    QProgressBar,
    QScrollArea,
    QGroupBox,
    QButtonGroup,
    QLineEdit,
)
from PySide6.QtCore import Qt, QObject, QRunnable, Signal, QThreadPool
import qdarkstyle

import SimpleITK as sitk
import sitk_ims_file_io as sio
import imaris_extension_base as ieb
from help_dialog import HelpDialog


def XTColocalizationAnalysis(imaris_id=None):
    app = QApplication([])
    app.setStyle(ieb.style)  # Consistent setting of style for all applications
    app.setStyleSheet(qdarkstyle.load_stylesheet(qt_api="pyside6"))
    colocalization_analysis_dialog = ColocalizationAnalysisDialog()  # noqa: F841
    app.exec()


class ColocalizationAnalysisDialog(ieb.ImarisExtensionBase):
    """
    Colocalization Analysis
    =============================
    `View on GitHub <https://github.com/niaid/imaris_extensions>`_

    This program computes colocalization charecteristics of two channels, optionally
    using a third channel to define a sub-region of interest. Both the binary image defining
    the colocalized image region and the Region Of Interest (ROI) binary mask are added to
    the input image. The channels are named "colocalization of channels A and B" and
    "ROI used with colocalization of channels A and B", where A and B are the original
    channel names. The specific SimpleITK expressions used to create these channels appear
    in the channel description. The output includes a single or multiple comma-seperated-value
    file(s) with the values for each of the characteristics. Optinally, corresponding graphs
    are saved using output format(s) selected by the user.

    Usage of channel names to identify the channels allows batch processing of images where
    corresponding channels do not have the same index. For example CD3 may be in channel 0
    in one image and in channel 3 in another.

    **Note**: Repeated channel names in a file are considered invalid and the file will not
    be analyzed (e.g. Nuclei is the name of channels 0 and 2).

    For an overview of colocalization analysis in the context of fluorescence microscopy
    see:

    * J. S. Aaron, A. B. Taylor, T.-L. Chew, "Image co-localization – co-occurrence versus correlation", J Cell Sci, `doi:10.1242/jcs.211847 <https://doi.org/10.1242/jcs.211847>`_, 2018.
    * K. W. Dunn, M. M. Kamocka, J. H. McDonald, "A practical guide to evaluating colocalization in biological microscopy", Am J Physiol Cell Physiol., `doi: 10.1152/ajpcell.00462.2010 <https://doi.org/10.1152/ajpcell.00462.2010>`_, 2011.

    The characteristics include (open the settings dialog to select which characteristics to compute, default is all):

    #. Percentage dataset colocalized.
    #. Percentage of channel colocalized.
    #. Percentage colocalized in ROI.
    #. Percentage of material colocalized.
    #. Percentage of material colocalized in ROI.
    #. Manders coefficient.
    #. Manders coefficient in ROI.
    #. Pearson correlation coefficient.
    #. Pearson correlation coefficient in colocalization.
    #. Pearson correlation coefficient in ROI.
    #. Spearman correlation coefficient.
    #. Spearman correlation coefficient in colocalization.
    #. Spearman correlation coefficient in ROI.

    SimpleITK expressions are used to define binary masks, regions of interest.
    These can be trivial expressions such as simple thresholding or complex
    expressions which take into account object sizes and possibly distances from the
    objects. If no expression is provided all of the voxels are used when computing
    the colocalization characteristics.

    One can either type an expression in the "Mask expression" text box or use the "Preset
    mask expressions" to pre-populate the textbox and then edit it if needed (e.g. setting specific
    values for thresholds etc.).

    The program enables batch colocalization and comparison. When analyzing images (2D or 3D)
    that have a single time-point the output is a single csv file with all of the computed
    charcteristics and a corresponding bar graph. When analyzing images that have multiple time-points
    the output is a single csv file per input image and a line graph per variable.

    Examples of useful expressions
    ------------------------------

    To define the objects of interest in the two channels and the sub-region of interest
    we use SimpleITK expressions that yield binary masks. Below are various options for
    creating these binary masks ordered according to their complexity:

    #. Binary mask using a simple threshold:

        .. code-block:: Python

            [i] > 150

    #. Binary mask using the Otsu thresholding filter. Additional thresholding filters
       available in SimpleITK include *TriangleThreshold*, *HuangThreshold* and
       *MaximumEntropyThreshold* (for details, see the `SimpleITK documentation <https://simpleitk.org/doxygen/latest/html/>`_):

        .. code-block:: Python

            sitk.OtsuThreshold([i], 0, 1)

    #. Binary mask, intensities inside a range of values:

        .. code-block:: Python

            sitk.BinaryThreshold([i], lowerThreshold=50, upperThreshold=150)

    #. Rectangular binary mask, a 30x20x5 rectangular region of interest spanning indexes [5:35, 10:30, 0:5]:

        .. code-block:: Python

            sitk.Paste([i]*0, sitk.Image([30,20,5],[i].GetPixelID())+1, sourceSize=[30,20,5], sourceIndex=[0,0,0], destinationIndex=[5,10,0])

    #. Binary mask via thresholding and only retaining the largest connected component.
       Threshold the channel, get all connected components, then
       sort the components according to size, discarding those smaller than a minimum
       size and create a binary mask corresponding to the largest component, which
       has a label value of 1 (second largest component label is 2 etc.):

        .. code-block:: Python

            sitk.RelabelComponent(sitk.ConnectedComponent([i]>100), minimumObjectSize = 50)==1

    #. Binary mask via thresholding and only retaining connected components larger than a
       minimal object size in voxels. Threshold a specific channel, get all connected components,
       then sort the components according to size, discarding those smaller than a minimum
       size and create a binary mask from them (one can readily replace the single
       threshold with the expression denoting a range of values given above):

        .. code-block:: Python

            sitk.RelabelComponent(sitk.ConnectedComponent([i]>100), minimumObjectSize = 50)!=0

    #. Binary mask via thresholding and then enlarging the mask to include all voxels that are
       less than 5nm from the original mask (`dilation operation <https://en.wikipedia.org/wiki/Dilation_(morphology)>`_).

        .. code-block:: Python

            sitk.Abs(sitk.SignedMaurerDistanceMap(sitk.BinaryThreshold([i], lowerThreshold=50, upperThreshold=150),
                                                  insideIsPositive=False, squaredDistance=False,
                                                  useImageSpacing=True)) <= 5.0

    """  # noqa

    def __init__(self):
        super(ColocalizationAnalysisDialog, self).__init__()

        # Use QT's global threadpool, documentation says: "This global thread pool
        # automatically maintains an optimal number of threads based on the
        # number of cores in the CPU."
        self.threadpool = QThreadPool.globalInstance()

        # Configure the help dialog.
        self.help_dialog = HelpDialog(w=700, h=500)
        self.help_dialog.setWindowTitle("Colocalization Analysis Help")
        self.help_dialog.set_rst_text(
            inspect.getdoc(self), pygments_css_file_name="pygments_dark.css"
        )

        # Preset mask expressions that are selectable from dropdown so no
        # need to type them
        self.__preset_mask_expressions = {
            "": "",
            "Simple threshold (replace t)": "[i] > t",
            "Otsu threshold": "sitk.OtsuThreshold([i], 0, 1)",
            "Triangle threshold": "sitk.TriangleThreshold([i], 0, 1, np.iinfo(sitk.GetArrayViewFromImage([i]).dtype).max+1)",  # noqa E501
            "Huang threshold": "sitk.HuangThreshold([i], 0, 1, np.iinfo(sitk.GetArrayViewFromImage([i]).dtype).max+1)",
            "Maximum entropy threshold": "sitk.MaximumEntropy([i], 0, 1, np.iinfo(sitk.GetArrayViewFromImage([i]).dtype).max+1)",  # noqa E501
            "Threshold range (replace t1, t2)": "sitk.BinaryThreshold([i], lowerThreshold=t1, upperThreshold=t2)",
            "Threshold range and then enlarge the mask to include all voxels that are less than Dnm from it (replace, t1, t2, d)": "sitk.Abs(sitk.SignedMaurerDistanceMap(sitk.BinaryThreshold([i], lowerThreshold=t1, upperThreshold=t2), insideIsPositive=False, squaredDistance=False,useImageSpacing=True)) <= d",  # noqa E501
            "Rectangular mask (replace x_size, x_start...)": "sitk.Paste([i]*0, sitk.Image([x_size,y_size,z_size],[i].GetPixelID())+1, sourceSize=[x_size,y_size,z_size], sourceIndex=[0,0,0], destinationIndex=[x_start,y_start,z_start])",  # noqa E501
            "Simple thresholding and get the largest connected component which is larger than minimumObjectSize (replace t, mos)": "sitk.RelabelComponent(sitk.ConnectedComponent([i]>t), minimumObjectSize = mos)==1",  # noqa E501
            "Simple thresholding and get all connected components that are larger than minimumObjectSize (replace t, mos)": "sitk.RelabelComponent(sitk.ConnectedComponent([i] > t), minimumObjectSize=mos) != 0",  # noqa E501
        }

        self.__create_gui()
        self.setWindowTitle("Colocalization Analysis")
        self.processing_error = False
        self.show()

    def __create_gui(self):
        # Settings dialog
        self.settings_widget = self.__create_settings_widget()

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
        colocalization_widget = self.__create_colocalization_widget()

        self.stack = QStackedWidget(self)
        self.stack.addWidget(select_files_widget)
        self.stack.addWidget(colocalization_widget)
        gui_layout.addWidget(self.stack)

        self.status_bar = self.statusBar()

    def closeEvent(self, event):
        """
        Override the closeEvent method so that clicking the 'x' button also
        closes all of the dialogs.
        """
        self.help_dialog.close()
        event.accept()

    def __create_settings_widget(self):
        figure_saving_extensions = ["pdf", "svg", "png"]

        wid = QWidget()
        wid.setWindowTitle("Settings")
        input_layout = QVBoxLayout()
        wid.setLayout(input_layout)

        graph_settings_groupbox = QGroupBox("Graph options:")
        graph_settings_layout = QVBoxLayout()
        graph_settings_groupbox.setLayout(graph_settings_layout)
        layout = QHBoxLayout()
        layout.setAlignment(Qt.AlignLeft)
        graph_settings_layout.addLayout(layout)
        layout.addWidget(QLabel("File format:"))
        self.graph_type_buttongroup = QButtonGroup()
        self.graph_type_buttongroup.setExclusive(False)
        for ext in figure_saving_extensions:
            b = QCheckBox(ext)
            self.graph_type_buttongroup.addButton(b)
            layout.addWidget(b)
        # Set the first checkbox as the default graph file format.
        self.graph_type_buttongroup.buttons()[0].setChecked(True)
        self.create_joint_graphs_cb = QCheckBox("Create joint graphs for all images")
        graph_settings_layout.addWidget(self.create_joint_graphs_cb)

        input_layout.addWidget(graph_settings_groupbox)

        compute_characteristics_groupbox = QGroupBox("Compute characteristics:")
        input_layout.addWidget(compute_characteristics_groupbox)
        self.select_compute_characteristics_layout = QVBoxLayout()
        # Add all the characteristics that can be computed and their
        # "compute status", True==compute, False==skip.
        for k, v in ColocalizationCalculator.compute.items():
            cb = QCheckBox(k)
            cb.setChecked(v)
            self.select_compute_characteristics_layout.addWidget(cb)
        compute_characteristics_groupbox.setLayout(
            self.select_compute_characteristics_layout
        )
        checkbox = QCheckBox("select all")
        # if all the values are ticked (True) then set the overall checkbox to match
        checkbox.setChecked(all(ColocalizationCalculator.compute.values()))
        checkbox.stateChanged.connect(self.__select_all_changed)
        input_layout.addWidget(checkbox)

        done_button = QPushButton("Done")
        input_layout.addWidget(done_button)
        done_button.clicked.connect(wid.hide)
        return wid

    def __select_all_changed(self):
        new_value = self.sender().isChecked()
        for i in range(self.select_compute_characteristics_layout.count()):
            self.select_compute_characteristics_layout.itemAt(i).widget().setChecked(
                new_value
            )

    def __create_colocalization_widget(self):
        wid = QWidget(self)
        colocalization_layout = QVBoxLayout()
        wid.setLayout(colocalization_layout)

        # channel_and_expression_layout = QGridLayout()
        # colocalization_layout.addLayout(channel_and_expression_layout)

        channel_a_groupbox = QGroupBox("Channel A")
        channel_a_layout = QVBoxLayout()
        channel_a_groupbox.setLayout(channel_a_layout)
        layout = QHBoxLayout()
        layout.setAlignment(Qt.AlignLeft)
        layout.addWidget(QLabel("Name:"))
        self.a_channel_combo = QComboBox()
        layout.addWidget(self.a_channel_combo)
        layout.addWidget(QLabel("Preset mask expressions:"))
        self.a_channel_preset_mask_combo = QComboBox()
        self.a_channel_preset_mask_combo.addItems(self.__preset_mask_expressions.keys())
        self.a_channel_preset_mask_combo.currentTextChanged.connect(
            lambda s: self.__preset_mask_expression_changed(
                self.a_channel_expression_text_edit, s
            )
        )
        # Add the combobox text strings as tooltips too. Some of them are too long
        # to fully appear in the combobox.
        for i, k in enumerate(self.__preset_mask_expressions.keys()):
            self.a_channel_preset_mask_combo.setItemData(i, k, Qt.ToolTipRole)
        layout.addWidget(self.a_channel_preset_mask_combo)
        channel_a_layout.addLayout(layout)
        channel_a_layout.addWidget(QLabel("Mask expression:"))
        self.a_channel_expression_text_edit = QTextEdit()
        channel_a_layout.addWidget(self.a_channel_expression_text_edit)
        colocalization_layout.addWidget(channel_a_groupbox)

        channel_b_groupbox = QGroupBox("Channel B")
        channel_b_layout = QVBoxLayout()
        channel_b_groupbox.setLayout(channel_b_layout)
        layout = QHBoxLayout()
        layout.setAlignment(Qt.AlignLeft)
        layout.addWidget(QLabel("Name:"))
        self.b_channel_combo = QComboBox()
        layout.addWidget(self.b_channel_combo)
        layout.addWidget(QLabel("Preset mask expressions:"))
        self.b_channel_preset_mask_combo = QComboBox()
        self.b_channel_preset_mask_combo.addItems(self.__preset_mask_expressions.keys())
        self.b_channel_preset_mask_combo.currentTextChanged.connect(
            lambda s: self.__preset_mask_expression_changed(
                self.b_channel_expression_text_edit, s
            )
        )
        # Add the combobox text strings as tooltips too. Some of them are too long
        # to fully appear in the combobox.
        for i, k in enumerate(self.__preset_mask_expressions.keys()):
            self.b_channel_preset_mask_combo.setItemData(i, k, Qt.ToolTipRole)
        layout.addWidget(self.b_channel_preset_mask_combo)
        channel_b_layout.addLayout(layout)
        channel_b_layout.addWidget(QLabel("Mask expression:"))
        self.b_channel_expression_text_edit = QTextEdit()
        channel_b_layout.addWidget(self.b_channel_expression_text_edit)
        colocalization_layout.addWidget(channel_b_groupbox)

        roi_channel_groupbox = QGroupBox("ROI channel")
        roi_channel_layout = QVBoxLayout()
        roi_channel_groupbox.setLayout(roi_channel_layout)
        layout = QHBoxLayout()
        layout.setAlignment(Qt.AlignLeft)
        layout.addWidget(QLabel("Name:"))
        self.roi_channel_combo = QComboBox()
        layout.addWidget(self.roi_channel_combo)
        layout.addWidget(QLabel("Preset mask expressions:"))
        self.roi_channel_preset_mask_combo = QComboBox()
        self.roi_channel_preset_mask_combo.addItems(
            self.__preset_mask_expressions.keys()
        )
        self.roi_channel_preset_mask_combo.currentTextChanged.connect(
            lambda s: self.__preset_mask_expression_changed(
                self.roi_channel_expression_text_edit, s
            )
        )
        # Add the combobox text strings as tooltips too. Some of them are too long
        # to fully appear in the combobox.
        for i, k in enumerate(self.__preset_mask_expressions.keys()):
            self.roi_channel_preset_mask_combo.setItemData(i, k, Qt.ToolTipRole)
        layout.addWidget(self.roi_channel_preset_mask_combo)
        roi_channel_layout.addLayout(layout)
        roi_channel_layout.addWidget(QLabel("Mask expression:"))
        self.roi_channel_expression_text_edit = QTextEdit()
        roi_channel_layout.addWidget(self.roi_channel_expression_text_edit)
        colocalization_layout.addWidget(roi_channel_groupbox)

        layout = QHBoxLayout()
        layout.addWidget(QLabel("Output directory:"))
        self.output_dir_line_edit = QLineEdit()
        self.output_dir_line_edit.setReadOnly(True)
        layout.addWidget(self.output_dir_line_edit)
        self.output_dir_browse_button = QPushButton("Browse")
        self.output_dir_browse_button.clicked.connect(
            self.__browse_select_output_callback
        )
        layout.addWidget(self.output_dir_browse_button)
        colocalization_layout.addLayout(layout)

        self.settings_button = QPushButton("Settings")
        self.settings_button.clicked.connect(self.settings_widget.show)
        colocalization_layout.addWidget(self.settings_button)

        self.apply_button = QPushButton("Apply")
        self.apply_button.clicked.connect(self.__colocalization_wrapper)
        colocalization_layout.addWidget(self.apply_button)

        progress_wid = QWidget()
        self.progress_grid_layout = QGridLayout()
        progress_wid.setLayout(self.progress_grid_layout)
        scroll_area = QScrollArea()
        scroll_area.setWidget(progress_wid)
        scroll_area.setWidgetResizable(True)
        colocalization_layout.addWidget(scroll_area)

        layout = QHBoxLayout()
        layout.setAlignment(Qt.AlignLeft)
        self.processing_prev_button = QPushButton("Prev")
        self.processing_prev_button.clicked.connect(
            lambda: self.stack.setCurrentIndex(0)
        )
        layout.addWidget(self.processing_prev_button)
        colocalization_layout.addLayout(layout)

        return wid

    def __preset_mask_expression_changed(self, text_edit, expression_description):
        text_edit.setText(self.__preset_mask_expressions[expression_description])

    def __configure_and_show_colocalization_widget(self):
        file_names = self.input_files_edit.toPlainText().split("\n")
        problematic_read_images = []
        duplicate_channel_images = []
        self.file_and_channel_names = {}

        all_channels = {}
        for file_name in file_names:
            try:
                metadata = sio.read_metadata(file_name)
                # Get all non-empty channel names (empty ones are ignored)
                current_channel_names = [
                    channel_info["name"].strip()
                    for _, channel_info in metadata["channels_information"]
                    if channel_info["name"].strip()
                ]
                if len(current_channel_names) != len(set(current_channel_names)):
                    duplicate_channel_images.append(file_name)
                else:
                    all_channels[file_name] = dict(
                        zip(current_channel_names, range(len(current_channel_names)))
                    )
            except Exception:
                problematic_read_images.append(file_name)
        if duplicate_channel_images:
            self._error_function(
                "The following files contain multiple channels with same name (not allowed): "
                + "\n".join(duplicate_channel_images)
            )
        if problematic_read_images:
            self._error_function(
                "Problem encountered reading the following file(s):\n"
                + "\n".join(problematic_read_images)
            )
        if not all_channels:  # there were problems with all the files, nothing to do
            return
        all_channel_names = [set(v.keys()) for f, v in all_channels.items()]
        shared_channel_names = set.intersection(*all_channel_names)
        if not shared_channel_names:
            self._error_function(
                "The following files do not share any channel names, cannot be analyzed in batch mode:\n"
                + "\n".join(list(all_channels.keys()))
            )
            return

        # Input directory is set as default output directory which is obtained
        # from the path to the first input file, but only when the output_dir_line_edit
        # is empty, otherwise the existing directory is kept as is
        if not self.output_dir_line_edit.text():
            self.output_dir_line_edit.setText(os.path.split(file_names[0])[0])

        self.file_and_channel_names = all_channels

        self.a_channel_combo.addItems(shared_channel_names)
        self.b_channel_combo.addItems(shared_channel_names)
        self.roi_channel_combo.addItems(shared_channel_names)

        # Remove all widgets from layout, done in reverse order because
        # removing from the beginning shifts the rest of the items
        for i in reversed(range(self.progress_grid_layout.count())):
            self.progress_grid_layout.itemAt(i).widget().setParent(None)

        for i, file_name in enumerate(self.file_and_channel_names.keys()):
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
            self.__configure_and_show_colocalization_widget
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

    def __browse_select_output_callback(self):
        output_dir = QFileDialog.getExistingDirectory(
            self,
            "Output directory",
            "",
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks,
        )
        if output_dir:
            self.output_dir_line_edit.setText(output_dir)

    def __colocalization_wrapper(self):
        # Disable the UI interaction during computation
        self.a_channel_combo.setEnabled(False)
        self.a_channel_expression_text_edit.setReadOnly(True)
        self.b_channel_combo.setEnabled(False)
        self.b_channel_expression_text_edit.setReadOnly(True)
        self.roi_channel_combo.setEnabled(False)
        self.roi_channel_expression_text_edit.setReadOnly(True)
        self.settings_button.setEnabled(False)
        self.apply_button.setEnabled(False)
        self.processing_prev_button.setEnabled(False)

        # Reset the results
        self.all_results = []

        # Get the channel names
        c_a_name = self.a_channel_combo.currentText()
        c_b_name = self.b_channel_combo.currentText()
        c_roi_name = self.roi_channel_combo.currentText()

        # Get the arithmetic expressions after removing all whitespace.
        roi_a_expression = "".join(
            self.a_channel_expression_text_edit.toPlainText().split()
        )
        roi_b_expression = "".join(
            self.b_channel_expression_text_edit.toPlainText().split()
        )
        roi_focus_expression = "".join(
            self.roi_channel_expression_text_edit.toPlainText().split()
        )

        # Get the characteristics the user wants to compute
        for i in range(self.select_compute_characteristics_layout.count()):
            cb = self.select_compute_characteristics_layout.itemAt(i).widget()
            ColocalizationCalculator.compute[cb.text()] = cb.isChecked()

        QApplication.setOverrideCursor(Qt.WaitCursor)
        self.num_threads_left = len(self.file_and_channel_names)
        for i, input_file_name in enumerate(self.file_and_channel_names.keys()):
            # Configure and perform computation in another thread.
            colocalization_calculator = ColocalizationCalculator()
            colocalization_calculator.signals.finished.connect(
                self.__colocalization_finished
            )
            colocalization_calculator.signals.processing_error.connect(
                self._processing_error_function
            )
            colocalization_calculator.signals.progress_signal.connect(
                self.progress_grid_layout.itemAtPosition(i, 1).widget().setValue
            )
            colocalization_calculator.signals.update_state_signal.connect(
                self.status_bar.showMessage
            )
            colocalization_calculator.input_file_name = input_file_name
            # Set the indexes of the channels
            colocalization_calculator.c_a = self.file_and_channel_names[
                input_file_name
            ][c_a_name]
            colocalization_calculator.c_b = self.file_and_channel_names[
                input_file_name
            ][c_b_name]
            colocalization_calculator.c_roi = self.file_and_channel_names[
                input_file_name
            ][c_roi_name]
            # Set the colocalization masking expressions
            colocalization_calculator.roi_a_expression = roi_a_expression
            colocalization_calculator.roi_b_expression = roi_b_expression
            colocalization_calculator.roi_focus_expression = roi_focus_expression

            self.threadpool.start(colocalization_calculator)

    def __colocalization_finished(self, results):
        """
        Check if this is the last computation. If it is re-enable the GUI and notify
        the user using a message box. Otherwise, just keep track of remaining files to
        process.
        """
        self.num_threads_left = self.num_threads_left - 1
        # If the computation failed the result is an empty tuple otherwise it is
        # a two entry tuple (file_name, list(dicts)) the number of dictionaries
        # in the list matches the number of timepoints in the file.
        if results:
            self.all_results.append(results)
        # Last file was analyzed, write the output
        if self.num_threads_left == 0:
            self.status_bar.showMessage("Consolidating results and writing output...")
            if self.all_results:
                file_name_list, results_list = zip(*self.all_results)
                # Output for files with a single timepoint is different from that with multiple
                # timepoints
                if all([len(r) == 1 for r in results_list]):
                    self.__save_single_timepoint_data(file_name_list, results_list)
                else:
                    timepoints_lists = [
                        sio.read_metadata(fname)["times"] for fname in file_name_list
                    ]
                    self.__save_multi_timepoint_data(
                        file_name_list, results_list, timepoints_lists
                    )
            else:
                self._error_function(
                    "No results to write (there were problems with all input files)."
                )
            QApplication.restoreOverrideCursor()
            self.status_bar.clearMessage()
            for i in range(self.progress_grid_layout.rowCount()):
                self.progress_grid_layout.itemAtPosition(i, 1).widget().setValue(0)
            # Enable the UI interaction after computation
            self.a_channel_combo.setEnabled(True)
            self.a_channel_expression_text_edit.setReadOnly(False)
            self.b_channel_combo.setEnabled(True)
            self.b_channel_expression_text_edit.setReadOnly(False)
            self.roi_channel_combo.setEnabled(True)
            self.roi_channel_expression_text_edit.setReadOnly(False)
            self.settings_button.setEnabled(True)
            self.apply_button.setEnabled(True)
            self.processing_prev_button.setEnabled(True)

            # Inform the user that the calculations completed. If processing errors
            # occurred then the desired operation may not have happened, but the
            # calculation was completed.
            QMessageBox().information(self, "Message", "Calculations completed.")

    def __save_single_timepoint_data(self, file_name_list, results_list):
        # This method is invoked when the results list contains a single dictionary per file which
        # corresponds to a single timepoint. We can safely create a single dataframe from
        # the list of dictionaries and add the file names as the first column.
        df = pd.DataFrame([r[0] for r in results_list])
        df.insert(0, "file", file_name_list)
        df.to_csv(
            os.path.join(
                self.output_dir_line_edit.text(),
                "colocalization_analysis_results.csv",
            ),
            index=False,
        )
        # Save graphs in all user selected formats. If no format selected that means the user
        # doesn't want the graphs.
        graph_formats = [
            b.text() for b in self.graph_type_buttongroup.buttons() if b.isChecked()
        ]
        if graph_formats:
            print("saving graphs")

    def __save_multi_timepoint_data(
        self, file_name_list, results_list, timepoints_lists
    ):
        # This method is invoked when the results list contains a single dictionary per file which
        # corresponds to a single timepoint. We can safely create a single dataframe from
        # the list of dictionaries and add the file names as the first column.

        for f, r, t in zip(file_name_list, results_list, timepoints_lists):
            df = pd.DataFrame(r)
            df.insert(0, "time", t)
            fname = os.path.splitext(os.path.split(f)[1])[0]
            df.to_csv(
                os.path.join(
                    self.output_dir_line_edit.text(),
                    f"colocalization_analysis_results_{fname}.csv",
                ),
                index=False,
            )
        # Save graphs in all user selected formats. If no format selected that means the user
        # doesn't want the graphs.
        graph_formats = [
            b.text() for b in self.graph_type_buttongroup.buttons() if b.isChecked()
        ]
        if graph_formats:
            print("saving graphs")


class ColocalizationCalculatorSignals(QObject):
    progress_signal = Signal(int)
    update_state_signal = Signal(str)
    processing_error = Signal(str)
    finished = Signal(tuple)


class ColocalizationCalculator(QRunnable):
    compute = {
        "percentage dataset colocalized": True,
        "percentage of channel colocalized": True,
        "percentage colocalized in ROI": True,
        "percentage of material colocalized": True,
        "percentage of material colocalized in ROI": True,
        "Manders coefficient": True,
        "Manders coefficient in ROI": True,
        "Pearson correlation coefficient": True,
        "Pearson correlation coefficient in colocalization": True,
        "Pearson correlation coefficient in ROI": True,
        "Spearman correlation coefficient": True,
        "Spearman correlation coefficient in colocalization": True,
        "Spearman correlation coefficient in ROI": True,
    }

    def __init__(
        self,
    ):
        super(ColocalizationCalculator, self).__init__()
        self.signals = ColocalizationCalculatorSignals()
        self.reset()

    def reset(self):
        self.input_file_name = ""
        # channel indexes used in colocalization computations
        self.c_a = 0
        self.c_b = 0
        self.c_roi_focus = 0
        # The expression is expected to contain no white space. It is
        # the callers responsibility to ensure this.
        self.roi_a_expression = ""
        self.roi_b_expression = ""
        self.roi_focus_expression = ""

        self.results = []

    def run(self):
        try:
            # Check that the inputs are valid, different channel indexes must
            # correspond to different channel names, because those are used
            # in the output (if they aren't different the output will be
            # missing data because it will be overwritten)
            meta_data = sio.read_metadata(self.input_file_name)
            if (
                self.c_a != self.c_b
                and meta_data["channels_information"][self.c_a][1]["name"].strip()
                == meta_data["channels_information"][self.c_b][1]["name"].strip()
            ):
                raise ValueError(
                    f"Different channels [{self.c_a},{self.c_b}] have the same name "
                    + f"({meta_data['channels_information'][self.c_a][1]['name'].strip()}), "
                    + "this is not allowed, please rename one of them"
                )
            self.process_vol_by_vol()
            self.signals.finished.emit((self.input_file_name, self.results))
        # Use the stack trace as the error message to provide enough
        # details for debugging.
        except Exception:
            self.signals.processing_error.emit(
                "Exception occurred during computation:\n" + traceback.format_exc()
            )
            self.signals.finished.emit(())

    def process_vol_by_vol(self):
        meta_data = sio.read_metadata(self.input_file_name)
        message_fname = os.path.basename(self.input_file_name)

        total_work = len(meta_data["times"])

        data_info = {
            "c_a": [self.c_a, self.roi_a_expression],
            "c_b": [self.c_b, self.roi_b_expression],
            "roi_focus": [self.c_roi_focus, self.roi_focus_expression],
        }
        for time_index in range(len(meta_data["times"])):
            # dictionary containing pairs of image and corresponding binary ROI
            image_roi = {}
            # read the channels and compute the binary masks using the user provided SimpleITK expressions
            for key, info in data_info.items():
                image_roi[key] = [
                    sio.read(
                        file_name=self.input_file_name,
                        time_index=time_index,
                        resolution_index=0,
                        channel_index=info[0],
                    )
                ]
                if info[1].strip():
                    image_roi[key].append(
                        sitk.Cast(
                            eval(info[1].replace("[i]", f"image_roi['{key}'][0]")),
                            meta_data["sitk_pixel_type"],
                        )
                    )
                else:  # no ROI specified this means it is the whole volume
                    current_roi = (
                        sitk.Image(meta_data["sizes"][0], meta_data["sitk_pixel_type"])
                        + 1
                    )
                    current_roi.CopyInformation(image_roi[key][-1])
                    image_roi[key].append(current_roi)
            c_a_name = sio.channels_information_xmlstr2list(
                image_roi["c_a"][0].GetMetaData("imaris_channels_information")
            )[0][1]["name"].strip()
            if not c_a_name:
                c_a_name = str(self.c_a)
            c_b_name = sio.channels_information_xmlstr2list(
                image_roi["c_b"][0].GetMetaData("imaris_channels_information")
            )[0][1]["name"].strip()
            if not c_b_name:
                c_b_name = str(self.c_b)
            # colocalization binary mask
            sitk_c_a_c_b_roi = image_roi["c_a"][1] * image_roi["c_b"][1]

            # Get numpy views on the SimpleITK data
            arr_c_a = sitk.GetArrayViewFromImage(image_roi["c_a"][0])
            arr_c_a_roi = sitk.GetArrayViewFromImage(image_roi["c_a"][1])
            arr_c_b = sitk.GetArrayViewFromImage(image_roi["c_b"][0])
            arr_c_b_roi = sitk.GetArrayViewFromImage(image_roi["c_b"][1])
            arr_c_a_c_b_roi = sitk.GetArrayViewFromImage(sitk_c_a_c_b_roi)
            arr_roi_focus_roi = sitk.GetArrayViewFromImage(image_roi["roi_focus"][1])
            arr_focused_colocalized = arr_c_a_c_b_roi * arr_roi_focus_roi

            # Compute colocalization characteristics
            n_colocalized = np.sum(arr_c_a_c_b_roi)

            # Use a dictionary to collect the analysis results. If the same channel is
            # used for A and B this ensures that the final dictionary only has one entry
            # per characteristic because they are overwritten due to the key being the
            # same channel name. If channels A and B are different, then we have separate
            # dictionary entries (we are guaranteed that channel names are unique per file
            # because this is checked in __configure_and_show_colocalization_widget).
            current_results = {}

            # information about the number and size of the colocalizations in the whole image and in
            # the ROI
            colocalized_cc = sitk.ConnectedComponent(sitk_c_a_c_b_roi)
            shape_stats_filter = sitk.LabelShapeStatisticsImageFilter()
            # Intensive, more detailed, computations are turned off (possibly turn on in the future).
            shape_stats_filter.ComputeFeretDiameterOff()
            shape_stats_filter.ComputeOrientedBoundingBoxOff()
            shape_stats_filter.ComputePerimeterOff()
            shape_stats_filter.Execute(colocalized_cc)
            current_results[
                "number of colocalization connected components"
            ] = shape_stats_filter.GetNumberOfLabels()
            current_results[
                f"connected component sizes ({meta_data[sio.unit_metadata_key]})"
            ] = [
                shape_stats_filter.GetPhysicalSize(i)
                for i in range(1, shape_stats_filter.GetNumberOfLabels() + 1)
            ]
            # colocalized connected components in focused ROI
            shape_stats_filter.Execute(
                colocalized_cc
                * sitk.Cast(image_roi["roi_focus"][1], colocalized_cc.GetPixelID())
            )
            current_results[
                "number of colocalization connected components in ROI"
            ] = shape_stats_filter.GetNumberOfLabels()
            current_results[
                f"connected component sizes in ROI ({meta_data[sio.unit_metadata_key]})"
            ] = [
                shape_stats_filter.GetPhysicalSize(i)
                for i in range(1, shape_stats_filter.GetNumberOfLabels() + 1)
            ]

            if ColocalizationCalculator.compute["percentage dataset colocalized"]:
                current_results[
                    "percentage dataset colocalized"
                ] = n_colocalized / np.prod(meta_data["sizes"][0])
            if ColocalizationCalculator.compute["percentage of channel colocalized"]:
                current_results[
                    f"percentage of channel [{c_a_name}] colocalized"
                ] = n_colocalized / np.sum(arr_c_a_roi)
                current_results[
                    f"percentage of channel [{c_b_name}] colocalized"
                ] = n_colocalized / np.sum(arr_c_b_roi)
            if ColocalizationCalculator.compute["percentage colocalized in ROI"]:
                current_results["percentage colocalized in ROI"] = np.sum(
                    arr_focused_colocalized
                ) / np.sum(arr_roi_focus_roi)

            # information about the material/intensity distribution in the colocalized region
            # across the whole image and in the ROI
            if ColocalizationCalculator.compute["percentage of material colocalized"]:
                current_results[
                    f"percentage of material channel [{c_a_name}] colocalized"
                ] = np.sum(arr_c_a_c_b_roi * arr_c_a) / np.sum(arr_c_a_roi * arr_c_a)
                current_results[
                    f"percentage of material channel [{c_b_name}] colocalized"
                ] = np.sum(arr_c_a_c_b_roi * arr_c_b) / np.sum(arr_c_b_roi * arr_c_b)
            if ColocalizationCalculator.compute[
                "percentage of material colocalized in ROI"
            ]:
                current_results[
                    f"percentage of material channel [{c_a_name}] colocalized in ROI"
                ] = np.sum(arr_focused_colocalized * arr_c_a) / np.sum(
                    arr_roi_focus_roi * arr_c_a
                )
                current_results[
                    f"percentage of material channel [{c_b_name}] colocalized in ROI"
                ] = np.sum(arr_focused_colocalized * arr_c_b) / np.sum(
                    arr_roi_focus_roi * arr_c_b
                )
            if ColocalizationCalculator.compute["Manders coefficient"]:
                current_results[f"Manders coefficient channel [{c_a_name}]"] = np.sum(
                    arr_c_a * arr_c_b_roi
                ) / np.sum(arr_c_a)
                current_results[f"Manders coefficient channel [{c_b_name}]"] = np.sum(
                    arr_c_b * arr_c_a_roi
                ) / np.sum(arr_c_b)
            if ColocalizationCalculator.compute["Manders coefficient in ROI"]:
                current_results[
                    f"Manders coefficient channel [{c_a_name}] in ROI"
                ] = np.sum(arr_c_a * arr_c_b_roi * arr_roi_focus_roi) / np.sum(
                    arr_c_a * arr_roi_focus_roi
                )
                current_results[
                    f"Manders coefficient channel [{c_b_name}] in ROI"
                ] = np.sum(arr_c_b * arr_c_a_roi * arr_roi_focus_roi) / np.sum(
                    arr_c_b * arr_roi_focus_roi
                )

            # Pearson and Spearman correlation statistics and associated p-values
            correlation_coefficients = {
                "Pearson": scipy.stats.pearsonr,
                "Spearman": scipy.stats.spearmanr,
            }
            for corr_type, f in correlation_coefficients.items():
                if ColocalizationCalculator.compute[
                    f"{corr_type} correlation coefficient"
                ]:
                    current_results[
                        f"{corr_type} correlation coefficient and p-value channels [{c_a_name}, {c_b_name}]"
                    ] = f(arr_c_a.ravel(), arr_c_b.ravel())
                if ColocalizationCalculator.compute[
                    f"{corr_type} correlation coefficient in colocalization"
                ]:
                    current_results[
                        f"{corr_type} correlation coefficient and p-value in colocalization channels [{c_a_name}, {c_b_name}]"  # noqa: E501
                    ] = f(
                        arr_c_a[arr_c_a_c_b_roi.astype(bool)],
                        arr_c_b[arr_c_a_c_b_roi.astype(bool)],
                    )
                if ColocalizationCalculator.compute[
                    f"{corr_type} correlation coefficient in ROI"
                ]:
                    current_results[
                        f"{corr_type} correlation coefficient and p-value in ROI channels [{c_a_name}, {c_b_name}]"
                    ] = f(
                        arr_c_a[arr_roi_focus_roi.astype(bool)],
                        arr_c_b[arr_roi_focus_roi.astype(bool)],
                    )
            self.results.append(current_results)

            # Add colocalization and ROI channels.
            channel_info = {}
            channel_info["color"] = [255, 255, 255]
            channel_info["range"] = [0, 255]
            channel_info["alpha"] = 1
            actual_c_a_roi = (
                data_info["c_a"][1].replace("[i]", f"[{data_info['c_a'][0]}]")
                if data_info["c_a"][1]
                else f"[{data_info['c_a'][0]}]*0+1"
            )
            actual_c_b_roi = (
                data_info["c_b"][1].replace("[i]", f"[{data_info['c_b'][0]}]")
                if data_info["c_b"][1]
                else f"[{data_info['c_b'][0]}]*0+1"
            )
            colocalization_expression = f"({actual_c_a_roi})*({actual_c_b_roi})"

            channel_description = (
                "SimpleITK generated channel from colocalization expression: "
                + colocalization_expression
            )
            channel_info["description"] = channel_description
            channel_info[
                "name"
            ] = f"colocalization of channels {self.c_a} and {self.c_b}"
            sitk_c_a_c_b_roi.SetMetaData(
                sio.channels_metadata_key,
                sio.channels_information_list2xmlstr([(0, channel_info)]),
            )
            self.signals.update_state_signal.emit(
                f"Saving colocalization channel ({message_fname})..."
            )
            sio.append_channels(
                sitk_c_a_c_b_roi, self.input_file_name, time_index=time_index
            )
            roi_expression = (
                data_info["roi_focus"][1].replace(
                    "[i]", f"[{data_info['roi_focus'][0]}]"
                )
                if data_info["roi_focus"][1]
                else f"[{data_info['roi_focus'][0]}]*0+1"
            )
            channel_description = (
                "SimpleITK generated channel from ROI expression: " + roi_expression
            )
            channel_info["description"] = channel_description
            channel_info[
                "name"
            ] = f"ROI used with colocalization of channels {self.c_a} and {self.c_b}"

            image_roi["roi_focus"][1].SetMetaData(
                sio.channels_metadata_key,
                sio.channels_information_list2xmlstr([(0, channel_info)]),
            )
            self.signals.update_state_signal.emit(
                f"Saving ROI channel ({message_fname})..."
            )
            sio.append_channels(
                image_roi["roi_focus"][1], self.input_file_name, time_index=time_index
            )
            self.signals.progress_signal.emit(int(100 * (time_index + 1) / total_work))


if __name__ == "__main__":
    XTColocalizationAnalysis()
    # cc = ColocalizationCalculator()
    # for c in cc.compute.keys():
    #     cc.compute[c] = False
    # cc.compute["Pearson correlation coefficient in ROI"] = True
    # cc.input_file_name = (
    #     "/Users/yanivz/development/microscopy/data/channelArithmetic/ziv1.ims"
    # )
    # # channel indexes used in colocalization computations
    # cc.c_a = 0
    # cc.c_b = 1
    # cc.c_roi_focus = 2
    # # The expression is expected to contain no white space. It is
    # # the callers responsibility to ensure this.
    # cc.roi_a_expression = "[i]>20"
    # cc.roi_b_expression =  "sitk.BinaryThreshold([i], lowerThreshold=50, upperThreshold=150)" #"[i]>10"
    # cc.roi_focus_expression = "sitk.Paste([i]*0, sitk.Image([30,20,5],[i].GetPixelID())+1,
    # sourceSize=[30,20,5], sourceIndex=[0,0,0], destinationIndex=[5,5,0])" #"[i]>30"
    # cc.process_vol_by_vol()
