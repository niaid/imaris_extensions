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
#      <Submenu name="SimpleITK Utilities">
#       <Item name="Batch Configure Channel Settings" icon="Python3" tooltip="Configure Channel Information">
#         <Command>Python3XT::XTBatchConfigureChannelSettings(%i)</Command>
#       </Item>
#      </Submenu>
#      </Menu>
#    </CustomTools>

from functools import partial
import numpy as np
import copy
import pandas as pd
import inspect
import os
import sitk_ims_file_io as sio
import imaris_extension_base as ieb
from help_dialog import HelpDialog

from PySide6.QtWidgets import (
    QWidget,
    QApplication,
    QFileDialog,
    QCheckBox,
    QTextEdit,
    QLineEdit,
    QLabel,
    QPushButton,
    QStackedWidget,
    QMessageBox,
    QVBoxLayout,
    QHBoxLayout,
    QErrorMessage,
)
from PySide6.QtCore import Qt
import qdarkstyle


def XTBatchConfigureChannelSettings(imaris_id=None):

    app = QApplication([])
    app.setStyle(ieb.style)  # Consistent setting of style for all applications
    app.setStyleSheet(qdarkstyle.load_stylesheet(qt_api="pyside6"))
    channel_settings_dialog = ConfigureChannelSettingsDialog()  # noqa: F841
    app.exec()


class ConfigureChannelSettingsDialog(ieb.ImarisExtensionBase):
    """
    Configure Channel Settings
    ==========================
    `View on GitHub <https://github.com/niaid/imaris_extensions>`_

    This program enables you to configure channel related settings for one or
    more files. The settings include:

    1. channel name
    2. description
    3. color or color table
    4. alpha
    5. range
    6. gamma

    The user provides a settings file, either a csv file or ims file. The settings
    from that file are transferred to the new set of files. As the user may be
    interested in only transferring a subset of the settings found in the settings
    file, they can select the relevant subset from the program's user interface.
    The settings file is expected to include at least one of the configurable settings
    (i.e. a single column csv file), otherwise the program will report an error.

    The contents of a complete configuration, three channel, csv file are displayed below::

        name,description,color,alpha,range,gamma
        Cytoplasm, first channel description,"0.0, 76.5, 0.0",1.0,"22.836, 162.388",1.0
        Nucleus,second channel description,glow_color_table.pal,1.0,"72.272, 158.038",1.0
        Vesicles,third channel description,"255.0,0.0,0.0",1.0,"62.164, 150.97",1.0

    The second channel uses a color table instead of a single color. The file containing
    the color table is specified using a relative path. The contents of a color table
    file are triplets, RGB values, in [0,255]. The specific file with 256 entries
    looks like this::

        0.000 0.000 0.000
        0.000 0.000 0.000
        4.080 0.000 0.000
        4.080 0.000 0.000
        7.905 0.000 0.000
        7.905 0.000 0.000
        11.985 0.000 0.000
        11.985 0.000 4.080
        16.065 0.000 4.080
        16.065 0.000 4.080
        19.890 0.000 4.080
        19.890 0.000 4.080
        ...
        ...
        250.920 250.920 235.110
        250.920 250.920 238.935
        250.920 250.920 243.015
        250.920 250.920 243.015
        250.920 250.920 247.095
        255.000 255.000 255.000

    You can export a settings file in csv format from an imaris file using the
    `Export Channel Settings extension  <http://niaid.github.io/imaris_extensions/XTExportChannelSettings.html>`_.

    **Note**: If there are fewer channels in the "settings" file, n, than in the
    file onto which the information is transferred,n<N, the final output dialog
    will report this after transferring the information to the first n channels.

    """

    def __init__(self):
        super(ConfigureChannelSettingsDialog, self).__init__()

        # Configure the help dialog.
        self.help_dialog = HelpDialog(w=700, h=500)
        self.help_dialog.setWindowTitle("Configure Channel Settings Help")
        self.help_dialog.set_rst_text(
            inspect.getdoc(self), pygments_css_file_name="pygments_dark.css"
        )

        self.__create_gui()
        self.setWindowTitle("Apply Preset Channel Names and Display Settings")
        self.show()

    def __error_function(self, message):
        error_dialog = QErrorMessage(self)
        error_dialog.showMessage(message)

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

        config_file_widget = self.__create_config_widget()
        select_input_files_widget = self.__create_select_input_widget()
        apply_widget = self.__create_apply_widget()

        self.stack = QStackedWidget(self)
        self.stack.addWidget(config_file_widget)
        self.stack.addWidget(select_input_files_widget)
        self.stack.addWidget(apply_widget)
        layout.addWidget(self.stack)

    def closeEvent(self, event):
        """
        Override the closeEvent method so that clicking the 'x' button also
        closes all of the dialogs.
        """
        self.help_dialog.close()
        event.accept()

    def __show_stacked_widget(self, i):
        self.stack.setCurrentIndex(i)

    def __create_config_widget(self):
        wid = QWidget()
        config_layout = QVBoxLayout()
        wid.setLayout(config_layout)

        config_file_layout = QHBoxLayout()
        config_file_layout.addWidget(QLabel("Channel settings file:"))
        self.config_file_line_edit = QLineEdit()
        self.config_file_line_edit.setReadOnly(True)
        self.config_file_line_edit.setToolTip(
            'Select csv file with columns "name", "description", "color", "alpha", "range", "gamma" or ims file.'
        )
        config_file_layout.addWidget(self.config_file_line_edit)
        button = QPushButton("Browse")
        button.clicked.connect(self.__browse_config_callback)
        config_file_layout.addWidget(button)
        config_layout.addLayout(config_file_layout)

        next_layout = QHBoxLayout()
        self.config_next_button = QPushButton("Next")
        self.config_next_button.setEnabled(False)
        self.config_next_button.clicked.connect(self.__config_and_start_app)
        next_layout.addWidget(self.config_next_button)
        next_layout.setAlignment(Qt.AlignRight)
        config_layout.addLayout(next_layout)
        return wid

    def __browse_config_callback(self):
        file_name, _ = QFileDialog.getOpenFileName(
            self,
            "QFileDialog.getOpenFileName()",
            "",
            "Comma Separated Value (*.csv);;Imaris (*.ims);;All Files (*)",
        )
        if file_name:
            self.config_file_line_edit.setText(file_name)
            self.config_next_button.setEnabled(True)

    def __config_and_start_app(self):
        file_name = self.config_file_line_edit.text().strip()
        if file_name:
            self.__validate_and_configure_apply_widget(file_name)

    def __create_apply_widget(self):
        wid = QWidget()
        self.apply_layout = QVBoxLayout()
        wid.setLayout(self.apply_layout)
        self.settings_checkboxes = []
        self.apply_button = QPushButton("Apply")
        self.apply_button.clicked.connect(self.__set_channel_information_callback)
        self.prev_layout = QHBoxLayout()
        self.prev_layout.setAlignment(Qt.AlignLeft)
        button = QPushButton("Prev")
        button.clicked.connect(lambda: self.__show_stacked_widget(1))
        self.prev_layout.addWidget(button)

        return wid

    def __validate_and_configure_apply_widget(self, file_name):
        self.channel_settings = []

        try:
            self.__load_csv_settings(file_name)
        except Exception:
            try:
                self.__load_ims_settings(file_name)
            except Exception:
                self.__error_function(
                    "Failed reading file ({0}).<br>".format(file_name)
                )
                return

        # Create or update the apply layout (first time through the wizard or
        # the user went back and updated the configuration file selection).
        keys_and_checkbox_titles = {
            "name": "set name",
            "description": "set description",
            "color": "set color",
            "color_table": "set color",
            "alpha": "set alpha",
            "range": "set range",
            "gamma": "set gamma",
        }
        self.checkbox_titles_2_keys = {
            "set name": ["name"],
            "set description": ["description"],
            "set color": ["color", "color_table"],
            "set alpha": ["alpha"],
            "set range": ["range"],
            "set gamma": ["gamma"],
        }

        # Get rid of all the checkboxes, if any.
        for cb in self.settings_checkboxes:
            cb.setParent(None)
            cb = None
        self.apply_layout.removeWidget(self.apply_button)
        self.apply_layout.removeItem(self.prev_layout)

        # Create the current set of relevant checkboxes.
        for k in keys_and_checkbox_titles.keys():
            if k in self.channel_settings[0][1]:
                self.settings_checkboxes.append(QCheckBox(keys_and_checkbox_titles[k]))
                self.settings_checkboxes[-1].setChecked(True)
                self.apply_layout.addWidget(self.settings_checkboxes[-1])

        self.apply_layout.addWidget(self.apply_button)
        self.apply_layout.addLayout(self.prev_layout)
        self.stack.setCurrentIndex(1)

    def __load_csv_settings(self, file_name):
        data = []
        df = pd.read_csv(file_name, header=0, index_col=False, dtype=str)
        # validate the data, find rows with missing values
        # ensure that:
        #   color information is correct:three floats in [0,255]
        #   range information is correct:two floats in [0,255]
        invalid_row_numbers, _ = np.where(df.isna())
        if invalid_row_numbers.size > 0:
            raise Exception(
                "Missing values in row(s): " + ",".join(map(str, invalid_row_numbers))
            )

        number_of_rows = len(df.index)
        if "color" in df.columns:
            color_list = list(
                df["color"].apply(
                    partial(
                        self.__str_2_colors,
                        original_file_path=os.path.dirname(file_name),
                        zero_one=True,
                    )
                )
            )
            invalid_row_numbers = [i for i, c in enumerate(color_list) if len(c) == 0]
            if len(invalid_row_numbers) > 0:
                raise Exception(
                    "Error in expected color setting [R,G,B] file ({0}) row(s): ".format(
                        os.path.basename(file_name)
                    )
                    + ",".join(map(str, invalid_row_numbers))
                )
            else:
                data.append(
                    [
                        ["color_table", c] if len(c) > 3 else ["color", c]
                        for c in color_list
                    ]
                )
        if "name" in df.columns:
            data.append(list(zip(["name"] * number_of_rows, list(df["name"]))))
        if "description" in df.columns:
            data.append(
                list(zip(["description"] * number_of_rows, list(df["description"])))
            )
        if "range" in df.columns:
            range_list = [
                [float(c) for c in r.replace(",", " ").split()]
                for r in list(df["range"])
            ]
            data.append(list(zip(["range"] * number_of_rows, range_list)))
        if "gamma" in df.columns:
            data.append(
                list(zip(["gamma"] * number_of_rows, list(df["gamma"].astype(float))))
            )
        if "alpha" in df.columns:
            data.append(
                list(zip(["alpha"] * number_of_rows, list(df["alpha"].astype(float))))
            )
        if not data:
            raise Exception(
                'File ({0}) does not contain any column with one of the expected headings ("name", "description", "color", "alpha", "range", "gamma").'.format(  # noqa E501
                    os.path.basename(file_name)
                )
            )
        else:
            number_of_columns = len(data)
            for i in range(number_of_rows):
                new_channel_info = {}
                for j in range(number_of_columns):
                    new_channel_info[data[j][i][0]] = data[j][i][1]
                self.channel_settings.append((i, new_channel_info))

    def __load_ims_settings(self, file_name):
        metadata_dict = sio.read_metadata(file_name)
        self.channel_settings = copy.deepcopy(metadata_dict["channels_information"])

    def __set_channel_information_callback(self):
        """
        Set the channel information for all the selected files based on the contents
        of the configuration file.
        """
        problematic_images = []

        channel_settings = copy.deepcopy(self.channel_settings)
        # Only use the subset of the settings the user selected.
        del_keys = []
        for cb in self.settings_checkboxes:
            if not cb.isChecked():
                del_keys.extend(self.checkbox_titles_2_keys[cb.text()])

        for cs in channel_settings:
            for del_key in del_keys:
                try:
                    del cs[1][del_key]
                except KeyError:
                    pass

        for file_name in self.input_files_edit.toPlainText().split("\n"):
            input_metadata = sio.read_metadata(file_name)
            input_len = len(input_metadata["channels_information"])
            if input_len > len(self.channel_settings):
                problematic_images.append(file_name)
            n = (
                len(self.channel_settings)
                if len(self.channel_settings) < input_len
                else input_len
            )
            sio.write_channels_metadata(
                {"channels_information": channel_settings[0:n]}, file_name
            )

        if problematic_images:
            error_dialog = QErrorMessage(self)
            error_dialog.showMessage(
                "Successfully Completed Batch Processing.<br><br>"
                + "The following files had more channels than those found in the settings file:<br>"
                + "<br>".join(problematic_images)
            )
        else:
            QMessageBox().information(
                self, "Message", "Successfully Completed Batch Processing."
            )

    def __str_2_colors(self, input_str, original_file_path, zero_one=False):
        """
        Convert a string to list of numbers. The string represents a triplet
        of numbers (color) or a file name containing triplets of numbers (color map).
        """
        try:
            res = [float(c) for c in input_str.replace(",", " ").split()]
            if len(res) != 3:
                return []
        except Exception:
            try:
                with open(os.path.join(original_file_path, input_str), "r") as fp:
                    color_table_str = fp.read()
                    res = [float(c) for c in color_table_str.split()]
                    if len(res) % 3 != 0:
                        return []
            except Exception:
                return []
        for val in res:
            if not 0.0 <= val <= 255.0:
                return []
        if zero_one:
            res = [v / 255.0 for v in res]
        return res

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
        input_files_prev_button = QPushButton("Prev")
        input_files_prev_button.clicked.connect(lambda: self.__show_stacked_widget(0))
        layout.addWidget(input_files_prev_button)
        self.input_files_next_button = QPushButton("Next")
        self.input_files_next_button.setEnabled(False)
        self.input_files_next_button.clicked.connect(
            lambda: self.__show_stacked_widget(2)
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


if __name__ == "__main__":
    XTBatchConfigureChannelSettings()
