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

from PySide2.QtWidgets import QWidget, QVBoxLayout, QTextBrowser
from docutils.core import publish_string


class HelpDialog(QWidget):
    """
    Dialog for displaying a single html page with text converted from
    a reStructuredText (rst) string. The string is usually a class's
    docstring documentation. As the string may contain code examples
    the docutils package uses the pygments library for syntax highlighting.
    Depending on the GUI theme the default pygments CSS may not be appropriate
    (e.g. white text on white background). To use a specific style you need
    to generate a CSS which will be given as input to the set_rst_text:
    pygmentize -S monokai -f html -a pre.code > monokai.css
    To see available styles:
    pygmentize -L styles
    """

    def __init__(self, w=500, h=600):
        super(HelpDialog, self).__init__()
        layout = QVBoxLayout()
        self.setLayout(layout)
        # Use the QTextBrowser and configure it to allow clickable hyperlinks.
        self.help_text_edit = QTextBrowser()
        self.help_text_edit.setOpenLinks(True)
        self.help_text_edit.setOpenExternalLinks(True)
        layout.addWidget(self.help_text_edit)
        self.resize(w, h)

    def set_rst_text(self, txt, pygments_css_file_name=None):
        # Use docutils publish_string method to convert the rst to html.
        # Then insert the css into the html and display that.
        html_str = publish_string(txt, writer_name="html").decode("utf-8")
        if pygments_css_file_name:
            style_idx = html_str.index("</style>")
            with open(pygments_css_file_name, "r") as fp:
                css_str = fp.read()
                html_str = html_str[:style_idx] + css_str + html_str[style_idx:]
        self.help_text_edit.setHtml(html_str)
