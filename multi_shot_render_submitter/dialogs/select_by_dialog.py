

import os
import re

from Qt.QtWidgets import (QApplication, QMainWindow, QTextEdit,
    QPushButton, QLabel, QHBoxLayout, QSizePolicy)
from Qt.QtGui import QTextOption, QIcon
from Qt.QtCore import Qt, Signal

import srnd_qt.base.utils
from srnd_qt.ui_framework.dialogs import base_popup_dialog


##############################################################################


fs = '<b><font color="#33CC33">'
fe = '</b></font>'

DESCRIPTION = 'Select by multishot UUIDs or Identifiers. '
DESCRIPTION += '<br><i>Note: UUID or Identifier should be provided per line or separated by space.</i>'
DESCRIPTION += '<br><i>Note: Environment and pass identifiers are human readable, '
DESCRIPTION += 'UUID is a more explicit and static internal id number for items.</i>'

ICONS_DIR = os.path.join(
    os.getenv('SRND_MULTI_SHOT_RENDER_SUBMITTER_ROOT', str()),
    'icons')
ICONS_DIR_QT = srnd_qt.base.utils.get_srnd_qt_icon_dir()
ICON_PATH = os.path.join(ICONS_DIR_QT, 'select_all_s01.png')
DIALOG_WH = (1000, 475)

fs = '<b><font color="#33CC33">'
fe = '</b></font>'


##############################################################################


class SelectByDialog(base_popup_dialog.BasePopupDialog):
    '''
    A dialog to let the user define multiple UUIDs or identifiers
    and then select them in the Multi Shot view.

    Args:
        identity_ids (list):
        identifiers (list):
    '''

    selectByRequested = Signal(list, list)

    def __init__(
            self,
            identity_ids=list(),
            identifiers=list(),
            icon_path=ICON_PATH,
            parent=None,
            **kwargs):
        super(SelectByDialog, self).__init__(
            tool_name='Select by multishot UUIDs or Identifiers',
            description=DESCRIPTION,
            description_by_title=True,
            description_is_dismissible=True,
            icon_path=icon_path,
            icon_size=25,
            parent=parent)

        self.resize(*DIALOG_WH)
        self.center()

        options_box_header = self.get_header_widget()
        style_sheet = 'QGroupBox {background: rgb(70, 70, 70);'
        style_sheet += 'border:rgb(70, 70, 70)}'
        options_box_header.setStyleSheet(style_sheet)
        options_box_header.set_title('Select by\nUUIDs or identifiers')

        vertical_layout_main = self.get_content_widget_layout()
        vertical_layout_main.setContentsMargins(8, 8, 8, 8)
        vertical_layout_main.setSpacing(8)

        horizontal_layout = QHBoxLayout()
        horizontal_layout.setContentsMargins(0, 0, 0, 0)
        horizontal_layout.setSpacing(10)
        vertical_layout_main.addLayout(horizontal_layout)
        horizontal_layout.addWidget(QLabel('UUIDs'))
        self._plain_text_widget_identity_ids = QTextEdit()
        self._plain_text_widget_identity_ids.setAcceptRichText(False)
        self._plain_text_widget_identity_ids.setWordWrapMode(QTextOption.NoWrap)
        self._plain_text_widget_identity_ids.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding)
        horizontal_layout.addWidget(self._plain_text_widget_identity_ids)

        horizontal_layout = QHBoxLayout()
        horizontal_layout.setContentsMargins(0, 0, 0, 0)
        horizontal_layout.setSpacing(10)
        vertical_layout_main.addLayout(horizontal_layout)
        horizontal_layout.addWidget(QLabel('Identifiers or\nenvironments'))
        self._plain_text_widget_identifiers = QTextEdit()
        self._plain_text_widget_identifiers.setAcceptRichText(False)
        self._plain_text_widget_identifiers.setWordWrapMode(QTextOption.NoWrap)
        self._plain_text_widget_identifiers.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding)
        self._plain_text_widget_identifiers.setFixedHeight(90)
        horizontal_layout.addWidget(self._plain_text_widget_identifiers)

        if identity_ids:
            identity_ids_str = '\n'.join(identity_ids)
            self._plain_text_widget_identity_ids.setPlainText(identity_ids_str)

        if identifiers:
            identifiers_str = '\n'.join(identifiers)
            self._plain_text_widget_identifiers.setPlainText(identifiers_str)

        self.build_okay_cancel_buttons()
        self._pushButton_okay.clicked.connect(self._emit_select_by_requested)

        # QApplication.setActiveWindow(self)


    def build_okay_cancel_buttons(self, okay_in_focus=True):
        '''
        Add okay cancel buttons.
        Subclasses should call this in context of where buttons should appear.

        Args:
            okay_in_focus (bool): whether the default provided Okay button is in focus

        Returns:
            buttons (bool): Okay is normally the 0th item
        '''
        layout = self.get_content_widget_layout()
        #layout.addStretch(100)
        layout.addSpacing(10)

        horizontal_layout_buttons = QHBoxLayout()
        horizontal_layout_buttons.setContentsMargins(0, 0, 0, 0)
        horizontal_layout_buttons.setSpacing(10)

        horizontal_layout_buttons.addStretch(100)

        buttons = list()

        self._pushButton_okay = QPushButton('Select')
        self._pushButton_okay.setAutoDefault(True)
        self._pushButton_okay.setFixedHeight(26)
        self._pushButton_okay.setMinimumWidth(75)
        self._pushButton_okay.setIcon(QIcon(ICON_PATH))
        horizontal_layout_buttons.addWidget(self._pushButton_okay)

        buttons.append(self._pushButton_okay)

        self.add_button_require_validation(self._pushButton_okay)

        layout.addLayout(horizontal_layout_buttons)

        if okay_in_focus and buttons:
            buttons[0].setFocus()

        return buttons


    def get_identity_ids_string(self):
        return str(self._plain_text_widget_identity_ids.toPlainText())


    def get_identifiers_string(self):
        return str(self._plain_text_widget_identifiers.toPlainText())


    def get_identity_ids(self):
        identity_ids_str = self.get_identity_ids_string()
        # Split at space or line break
        identity_ids = re.split('[ \n]', identity_ids_str)
        identity_ids_verified = list()
        for identity_id in identity_ids:
            if not identity_id:
                continue
            identity_id = str(identity_id)
            identity_ids_verified.append(identity_id)
        return identity_ids_verified


    def get_identifiers(self):
        identifiers_str = self.get_identifiers_string()
        # Split at space or line break
        identifiers = re.split('[ \n]', identifiers_str)
        identifiers_verified = list()
        for identifier in identifiers:
            if not identifier:
                continue
            identifier = str(identifier)
            identifiers_verified.append(identifier)
        return identifiers_verified


    def _emit_select_by_requested(self):
        identity_ids = self.get_identity_ids()
        identifiers = self.get_identifiers()
        self.selectByRequested.emit(identity_ids, identifiers)
        self.close()