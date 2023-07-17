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

from PySide6.QtWidgets import QMainWindow, QErrorMessage
from PySide6.QtCore import Signal, QObject
import PySide6.QtGui
import SimpleITK as sitk
import logging

# The PySide6 Qt applications support multiple styles (look and feels).
# As our user base is primarily on windows we set the style via the
# extension base class variable to 'Windows'. Thus the extensions look the
# same on windows or mac.
# To see what styles are available on a system:
# import PySide6.QtWidgets; print(PySide6.QtWidgets.QStyleFactory.keys())
# The 'macOS' style is only available on OSX.
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
        error_dialog.showMessage(PySide6.QtGui.Qt.convertFromPlainText(message))

    def _processing_error_function(self, message):
        self.processing_error = True
        self._error_function(message)


class SimpleITKLogger(sitk.LoggerBase):
    """
    Adapter between the SimpleITK/ITK logging and the Python logging framework. Enables handling of messages
    coming from ITK and SimpleTK via Python logging. Original code copied from the SimpleITK Examples/Logging.

    To use the adapter the LoggerBase.SetAsGlobalITKLogger method must be called, either explicitly in the code
    or implicitly when the adapter is used as a context manager (__enter__ and __exit__ methods). If explicitly
    setting a SimpleITKLogger as the global ITK logger, you may want to hold on to the original
    ITK logger returned by the SetAsGlobalITKLogger and restore it to the original state at a later point in the code.

    To enable detailed debugging information from SimpleITK objects, if available, turn the "Debug" property on
    (object's DebugOn(), DebugOff() methods).
    """

    def __init__(self, logger):
        """
        Initializes with a Logger object to handle the messages emitted from SimpleITK/ITK.
        """
        super(SimpleITKLogger, self).__init__()
        self._logger = logger

    @property
    def logger(self):
        return self._logger

    @logger.setter
    def logger(self, logger):
        self._logger = logger

    def __enter__(self):
        self._old_logger = self.SetAsGlobalITKLogger()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._old_logger.SetAsGlobalITKLogger()
        del self._old_logger

    def DisplayText(self, s):
        # Remove newline endings from SimpleITK/ITK messages since the
        # Python logger adds them.
        self._logger.info(s.rstrip())

    def DisplayErrorText(self, s):
        self._logger.error(s.rstrip())

    def DisplayWarningText(self, s):
        self._logger.warning(s.rstrip())

    def DisplayGenericOutputText(self, s):
        self._logger.info(s.rstrip())

    def DisplayDebugText(self, s):
        self._logger.debug(s.rstrip())


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
