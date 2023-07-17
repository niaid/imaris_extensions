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

import sys
import os
import glob
import importlib
from functools import partial
import xml.etree.ElementTree as et
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow
from PySide6.QtGui import QAction
import qdarkstyle

"""
This script serves as a driver for Imaris extensions allowing us to run them
without requiring the Imaris program. This only works for the extensions that
were designed with this in mind (standalone GUI programs). The locations of the
extensions can be specified on the commandline as a list of paths. The default
location is assumed to be the same as the location of this script.
"""


class ExtensionDriverDialog(QMainWindow):
    def __init__(self, extension_paths):
        super(ExtensionDriverDialog, self).__init__()
        self.__create_gui(self.__load_extensions(extension_paths))
        self.setWindowTitle("Imaris Extensions Driver")
        self.show()

    def __load_extensions(self, extension_paths):
        # The imaris convention assumes the extensions are in files with a file
        # extension of '.py', this is also important when loading with importlib
        # otherwise the importlib code below needs to be modified. The extension
        # description is found in a comment in the file with the following xml
        # structure (Submenu tag is optional).
        #    <CustomTools>
        #      <Menu>
        #       <Submenu name="Name of Sub Menu">
        #         <Item name="Name of Extension" icon="Python3" tooltip="Extension tooltip">
        #           <Command>Python3XT::ExtensionFunctionName(%i)</Command>
        #         </Item>
        #       </Submenu>
        #      </Menu>
        #    </CustomTools>
        potential_extension_files = []
        for path in extension_paths:
            potential_extension_files.extend(
                glob.glob(os.path.join(os.path.abspath(path), "*.py"))
            )
        extensions = []
        for file_name in potential_extension_files:
            with open(file_name, "r") as fp:
                lines = fp.readlines()
            # The extension description is contained as xml in a comment so
            # get all comments from the file.
            comments = []
            current_comment = ""
            for ln in lines:
                if ln.strip().startswith("#"):
                    current_comment = current_comment + ln.strip(" \t\n#")
                elif current_comment:
                    comments.append(current_comment)
                    current_comment = ""
            for comment in comments:
                # Search for the imaris xml data in each comment.
                xml_start = comment.find("<CustomTools>")
                xml_end = comment.find("</CustomTools>") + len("</CustomTools>")
                if xml_start != -1 and xml_end != -1:
                    comment = comment[xml_start:xml_end]
                    try:
                        elem = et.fromstring(comment)
                        if elem.tag == "CustomTools":  # This is an extension
                            elem = elem.find("Menu")
                            submenu_name = None  # optional sub menu
                            if elem.find("Submenu"):
                                elem = elem.find("Submenu")
                                submenu_name = elem.get("name")
                            elem = elem.find("Item")
                            ext_name = elem.get("name")
                            ext_tooltip = elem.get("tooltip")
                            # Clunky parsing of the command string, but I prefer two splits over 'import re'
                            ext_command = (
                                elem.find("Command").text.split(":")[-1].split("(")[0]
                            )
                            # import the extension and get the pointer to the function, ensures that this is
                            # an imaris extension.
                            spec = importlib.util.spec_from_file_location(
                                os.path.split(file_name)[1][:-3], file_name
                            )
                            module = importlib.util.module_from_spec(spec)
                            spec.loader.exec_module(module)
                            getattr(module, ext_command)
                            # extensions.append([submenu_name, ext_name, ext_tooltip, getattr(module,ext_command)])
                            extensions.append(
                                [submenu_name, ext_name, ext_tooltip, file_name]
                            )
                            break  # Ignore any additional extension descriptions in the file
                    except Exception:
                        pass
        return extensions

    def __launch(self, script_to_run):
        # running a function in another process doesn't seem to work on OSX,
        # crashes, appears to be a known bug: https://bugs.python.org/issue33725
        # from multiprocessing import Process
        # p = Process(target=f)
        # p.daemon = True
        # p.start()
        import subprocess

        subprocess.Popen(
            [sys.executable, script_to_run],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )

    def __create_gui(self, extensions_list):

        menu_bar = self.menuBar()
        # Force menubar to be displayed in the application on OSX/Linux, otherwise it
        # is displayed in the system menubar
        menu_bar.setNativeMenuBar(False)
        extensions_menu = menu_bar.addMenu("Imaris Extensions")
        sub_menus = {}
        for extension in extensions_list:
            if extension[0]:
                try:
                    sub_menu = sub_menus[extension[0]]
                except Exception:  # create the sub menu only once
                    sub_menu = extensions_menu.addMenu(extension[0])
                    sub_menus[extension[0]] = sub_menu
            else:
                sub_menu = extensions_menu

            extensionAction = QAction(extension[1], self)
            extensionAction.setToolTip(extension[2])

            extensionAction.triggered.connect(partial(self.__launch, extension[3]))
            sub_menu.addAction(extensionAction)
            sub_menu.setToolTipsVisible(True)

        self.setCentralWidget(
            QLabel(
                "This program allows you to run imaris extensions that are designed to work as standalone programs.\n"
                + "Select the extension you want to run from the menu-bar."
            )
        )


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle(
        "Windows"
    )  # Always use windows style as that is our users' main platform
    app.setStyleSheet(qdarkstyle.load_stylesheet(qt_api="pyside6"))

    # default directory containing extensions is the same as the one containing
    # this script (don't use '.' as that refers to the working directory).
    extenstions_directories = [os.path.dirname(os.path.abspath(__file__))]
    for dir_name in sys.argv[1:]:
        if os.path.isdir(dir_name):
            extenstions_directories.append(dir_name)
    driver = ExtensionDriverDialog(extension_paths=extenstions_directories)
    sys.exit(app.exec())
