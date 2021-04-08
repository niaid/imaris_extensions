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
#       <Item name="Export Channel Settings to csv" icon="Python3" tooltip="Export Channel Settings to csv file for convenient manual editing.">  # noqa: E501
#         <Command>Python3XT::XTExportChannelSettings(%i)</Command>
#       </Item>
#      </Submenu>
#      </Menu>
#    </CustomTools>


import pandas as pd
import sitk_ims_file_io as sio
import inspect
import os
import imaris_extension_base as ieb
from help_dialog import HelpDialog
from PySide2.QtWidgets import (
    QWidget,
    QApplication,
    QFileDialog,
    QLabel,
    QPushButton,
    QMessageBox,
    QVBoxLayout,
    QHBoxLayout,
    QErrorMessage,
    QLineEdit,
)
from PySide2.QtCore import Qt
import qdarkstyle


def XTExportChannelSettings(imaris_id=None):
    app = QApplication([])
    app.setStyle(ieb.style)  # Consistent setting of style for all applications
    app.setStyleSheet(qdarkstyle.load_stylesheet(qt_api="pyside2"))
    export_channel_settings_dialog = ExportChannelSettingsDialog()  # noqa: F841
    app.exec_()


class ExportChannelSettingsDialog(ieb.ImarisExtensionBase):
    """
    Export Channel Settings
    =======================
    `View on GitHub <https://github.com/niaid/imaris_extensions>`_

    This program enables you to export the channel settings from an imaris file
    to a comma separated values (csv) file. This is convenient for manual editing.
    Once modified the settings file can be applied to other imaris files using the
    `Configure Channel Settings extension  <http://niaid.github.io/imaris_extensions/XTConfigureChannelSettings.html>`_.

    Note: If the exported settings include color tables, these are exported as additional files that are referenced in
    the csv file.

    Example output csv file content::

        name,description,color,alpha,range,gamma
        Cytoplasm, first channel description,"0.0, 76.5, 0.0",1.0,"22.836, 162.388",1.0
        Nucleus,second channel description,glow_color_table.pal,1.0,"72.272, 158.038",1.0
        Vesicles,third channel description,"255.0,0.0,0.0",1.0,"62.164, 150.97",1.0

    The second channel used a color table instead of a single color. The file containing
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
    """

    def __init__(self):
        super(ExportChannelSettingsDialog, self).__init__()

        # Configure the help dialog.
        self.help_dialog = HelpDialog(w=700, h=500)
        self.help_dialog.setWindowTitle("Export Channel Settings Help")
        self.help_dialog.set_rst_text(
            inspect.getdoc(self), pygments_css_file_name="pygments_dark.css"
        )

        self.__create_gui()
        self.setWindowTitle("Export Channel Settings to csv File")
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

        input_file_layout = QHBoxLayout()
        input_file_layout.addWidget(QLabel("File:"))
        self.input_file_line_edit = QLineEdit()
        self.input_file_line_edit.setReadOnly(True)
        self.input_file_line_edit.setToolTip(
            "Select ims file whose channel information you want to export."
        )
        input_file_layout.addWidget(self.input_file_line_edit)
        button = QPushButton("Browse")
        button.clicked.connect(self.__browse_callback)
        input_file_layout.addWidget(button)
        layout.addLayout(input_file_layout)

        button = QPushButton("Export")
        button.clicked.connect(self.__export_channel_settings)
        layout.addWidget(button)

    def __browse_callback(self):
        file_name, _ = QFileDialog.getOpenFileName(
            self, "QFileDialog.getOpenFileName()", "", "Imaris (*.ims);;All Files (*)"
        )
        self.input_file_line_edit.setText(file_name)

    def __export_channel_settings(self):
        input_file_name = self.input_file_line_edit.text().strip()
        default_output_file_name = os.path.join(
            os.path.dirname(input_file_name), "channel_settings"
        )
        output_file_name, _ = QFileDialog.getSaveFileName(
            self, "Export Channel Settings", default_output_file_name, "csv(*.csv)"
        )
        metadata = sio.read_metadata(input_file_name)
        # Using known metadata dictionary structure from the sitk_ims_file_io module
        channel_settings_headings = [
            "name",
            "description",
            "color",
            "alpha",
            "range",
            "gamma",
        ]
        channel_settings = [None] * len(metadata["channels_information"])
        for i, cs in metadata["channels_information"]:
            current_settings = [cs["name"], cs["description"]]
            if "color" in cs:
                color_settings = ", ".join([str(c * 255) for c in cs["color"]])
            elif "color_table" in cs:
                color_table = "".join(
                    [
                        f"{c*255:.3f}\n" if (i % 3) == 0 else f"{c*255:.3f} "
                        for i, c in enumerate(cs["color_table"], 1)
                    ]
                )
                color_settings = (
                    os.path.splitext(output_file_name)[0]
                    + f"_color_table_channel{i}.pal"
                )
                with open(color_settings, "w") as fp:
                    fp.write(color_table)
            current_settings.extend(
                [
                    os.path.basename(color_settings),
                    cs["alpha"],
                    ", ".join([str(v) for v in cs["range"]]),
                ]
            )
            if "gamma" in cs:
                current_settings.append(cs["gamma"])
            channel_settings[i] = current_settings
        df = pd.DataFrame(
            channel_settings,
            columns=channel_settings_headings[
                0 : len(channel_settings[0])  # noqa: E203
            ],
        )
        df.to_csv(output_file_name, index=False)
        QMessageBox().information(self, "Message", "Succesfuly Exported")


if __name__ == "__main__":
    XTExportChannelSettings()
