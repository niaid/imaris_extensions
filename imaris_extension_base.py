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

from PySide2.QtWidgets import QMainWindow, QErrorMessage
from PySide2.QtCore import Signal, QObject
import PySide2.QtGui

import logging

# The PySide2 Qt applications support multiple styles (look and feels).
# As our user base is primarily on windows we set the style via the
# extension base class variable to 'Windows'. Thus the extensions look the
# same on windows or mac.
# To see what styles are available on a system:
# import PySide2.QtWidgets; print(PySide2.QtWidgets.QStyleFactory.keys())
# The 'macintosh' style is only available on OSX.
style = "Windows"


class ImarisExtensionBase(QMainWindow):
    def __init__(self):
        super(ImarisExtensionBase, self).__init__()
        self.processing_error = False

    def _error_function(self, message):
        error_dialog = QErrorMessage(self)
        # The QErrorMessage dialog automatically identifies if text is rich text,
        # html or plain text. Unfortunately, it doesn't do a good job when some of
        # the text is describing Exceptions due to number comparisons that include
        # the '>' symbol. As all invocations of this function are done with plain
        # text we use the convertToPlainText method to ensure that it is displayed
        # correctly.
        error_dialog.showMessage(PySide2.QtGui.Qt.convertFromPlainText(message))

    def _processing_error_function(self, message):
        self.processing_error = True
        self._error_function(message)


class LoggingGUIHandler(logging.Handler):
    """
    Loosely connected logging handler which emits a signal for every message.
    A function connected to the signal is invoked with the message as input and
    can update a GUI component without tightly coupling this message handler to
    a specific GUI. The user is responsible for adding this handler to the logger.
    """

    class QtSignalEmitter(QObject):
        write_signal = Signal(str)

    def __init__(self, level):
        logging.Handler.__init__(self, level)
        self.signal_emitter = self.QtSignalEmitter()

    def emit(self, message):
        self.signal_emitter.write_signal.emit(self.format(message))
