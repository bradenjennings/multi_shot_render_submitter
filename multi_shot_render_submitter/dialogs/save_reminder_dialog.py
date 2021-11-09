

import logging
import os

from Qt.QtWidgets import QPushButton, QCheckBox, QHBoxLayout
from Qt.QtGui import QIcon
from Qt.QtCore import Signal

import srnd_qt.base.utils
from srnd_qt.ui_framework.dialogs import base_popup_dialog


fs = '<b><font color="#33CC33">'
fe = '</b></font>'
DESCRIPTION = '{} was altered since the last load or save '
DESCRIPTION += 'operation or never saved. '
DESCRIPTION += '<br><i>Do you want to save now?</i>'
DIALOG_WH = (750, 165)

SRND_QT_ROOT = os.getenv('SRND_QT_ROOT')
SRND_QT_ICONS_DIR = os.path.join(SRND_QT_ROOT, 'res', 'icons')


##############################################################################


class SaveReminderDialog(base_popup_dialog.BasePopupDialog):
    '''
    A dialog to remined the user to save, and has a button to not show again.

    Args:
        show_save_and_continue (bool):
        host_app_document (str):
        icon_path (str):
        icon_path (str):
    '''
    
    logMessage = Signal(str, int)
    
    SaveAndContinue = 1
    SaveAs = 2
    Continue = 3

    def __init__(
            self,
            show_save_and_continue=True,
            host_app_document='project',
            icon_path=None,
            parent=None,
            **kwargs):
        host_app_document = host_app_document.lower()
        tool_name = 'Save {}'.format(host_app_document)
        description = DESCRIPTION.format(host_app_document.title())
        super(SaveReminderDialog, self).__init__(
            tool_name=tool_name,
            description=description,
            description_by_title=False,
            description_is_dismissible=False,
            do_validate=False,
            icon_path=icon_path,
            icon_size=20,
            parent=parent)

        vertical_layout = self.get_content_widget_layout()
        vertical_layout.setContentsMargins(0, 0, 0, 0)

        options_box_header = self.get_header_widget()
        style_sheet = 'QGroupBox {background: rgb(70, 70, 70);'
        style_sheet += 'border:rgb(70, 70, 70)}'
        options_box_header.setStyleSheet(style_sheet)
        options_box_header.set_title(tool_name)

        horizontal_layout_buttons = QHBoxLayout()
        horizontal_layout_buttons.setContentsMargins(0, 0, 0, 0)
        horizontal_layout_buttons.setSpacing(8)
        vertical_layout.addLayout(horizontal_layout_buttons)

        self._checkBox_dont_show_again = QCheckBox('Don\'t show again')
        self._checkBox_dont_show_again.setChecked(False)
        horizontal_layout_buttons.addWidget(self._checkBox_dont_show_again)

        horizontal_layout_buttons.addStretch(100)

        self._pushButton_save_and_continue = QPushButton('Save & continue')
        self._pushButton_save_and_continue.setFixedHeight(32)
        self._pushButton_save_and_continue.setMinimumWidth(75)
        self._pushButton_save_and_continue.setIcon(QIcon(icon_path))
        self._pushButton_save_and_continue.clicked.connect(
            lambda *x: self._set_result_and_close(self.SaveAndContinue))
        horizontal_layout_buttons.addWidget(self._pushButton_save_and_continue)
        self._pushButton_save_and_continue.setVisible(show_save_and_continue)

        self._pushButton_save_as = QPushButton('Save as')
        self._pushButton_save_as.setFixedHeight(32)
        self._pushButton_save_as.setMinimumWidth(75)
        self._pushButton_save_as.setIcon(QIcon(icon_path))
        self._pushButton_save_as.clicked.connect(
            lambda *x: self._set_result_and_close(self.SaveAs))        
        horizontal_layout_buttons.addWidget(self._pushButton_save_as)

        self._pushButton_continue = QPushButton('Continue without save')
        self._pushButton_continue.setFixedHeight(32)
        self._pushButton_continue.setMinimumWidth(75)
        self._pushButton_continue.clicked.connect(
            lambda *x: self._set_result_and_close(self.Continue))            
        horizontal_layout_buttons.addWidget(self._pushButton_continue)

        self._pushButton_cancel = QPushButton('Cancel launch')
        self._pushButton_cancel.setAutoDefault(True)
        self._pushButton_cancel.setFixedHeight(28)
        self._pushButton_cancel.setMinimumWidth(75)         
        horizontal_layout_buttons.addWidget(self._pushButton_cancel)

        self._pushButton_cancel.clicked.connect(
            lambda *x: self._set_result_and_close(self.Rejected))

        self.setMinimumWidth(700)
        self.setFixedHeight(165)
        self.center()            
    

    def _set_result_and_close(self, result):
        '''
        Callback to set dialog result, and then close with accept or reject.

        Args:
            result (int):
        '''
        msg = 'Closing save reminder dialog with result: {}'.format(result)
        self.logMessage.emit(msg, logging.INFO)
        self.close()
        self.setResult(result)
        

    def get_dont_show_again(self):
        '''
        Get the result from dont show again.

        Returns:
            value (bool):
        '''
        return self._checkBox_dont_show_again.isChecked()