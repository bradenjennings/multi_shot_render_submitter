

import os

from Qt.QtWidgets import (QApplication, QMainWindow, QTextEdit,
    QPushButton, QLabel, QHBoxLayout, QSizePolicy)
from Qt.QtGui import QTextOption, QIcon
from Qt.QtCore import Qt, Signal

import srnd_qt.base.utils
from srnd_qt.ui_framework.dialogs import base_popup_dialog


##############################################################################


fs = '<b><font color="#33CC33">'
fe = '</b></font>'

DESCRIPTION = 'All render nodes are synced as multi-shot data. '
DESCRIPTION += 'Optionally filter nodes to be synced '
DESCRIPTION += 'by providing sync rule/s. '
# DESCRIPTION += 'Thus Providing A More Focused And Smaller Number Of Items Of Interest. '
DESCRIPTION += 'Sync rules may contain wildcards.<br>Examples: '
DESCRIPTION += '<i>"{0}thanos.*{1}", "{0}.*_cactus[1-9]{1}", '.format(fs, fe)
DESCRIPTION += '"{0}^env{1}", "{0}Man01${1}", "{0}^(char).*(Man01)${1}"'.format(fs, fe)
# DESCRIPTION += '"{0}^project://scene/image.background[1-9]*{1}".</i>'.format(fs, fe)
DESCRIPTION += '<br><i>Note: One sync rule can be defined per line. '
DESCRIPTION += 'Start a line with # to comment out rule.</i>'
DESCRIPTION += '<br><i>Note: Python / Perl style regular expressions are supported.</i>'
DESCRIPTION += '<br><i>Note: Session data is only serialized for nodes in multi-shot data.</i>'

ICONS_DIR = os.path.join(
    os.getenv('SRND_MULTI_SHOT_RENDER_SUBMITTER_ROOT', str()),
    'icons')
ICONS_DIR_QT = srnd_qt.base.utils.get_srnd_qt_icon_dir()
ICON_PATH = os.path.join(ICONS_DIR_QT, 'tool_s01.png')
DIALOG_WH = (950, 525)

fs = '<b><font color="#33CC33">'
fe = '</b></font>'


##############################################################################


class PassSyncRulesDialog(base_popup_dialog.BasePopupDialog):
    '''
    A dialog to modify  include and exclude pass sync rule/s.

    Args:
        include_rules (list):
        exclude_rules (list):
    '''

    syncRulesIncludeModified = Signal(list)
    syncRulesExcludeModified = Signal(list)

    def __init__(
            self,
            include_rules=list(),
            exclude_rules=list(),
            parent=None,
            **kwargs):
        super(PassSyncRulesDialog, self).__init__(
            tool_name='Pass Sync Rule/s',
            description=DESCRIPTION,
            description_by_title=True,
            description_is_dismissible=True,
            icon_path=ICON_PATH,
            icon_size=20,
            parent=parent)

        self.resize(*DIALOG_WH)
        self.center()

        options_box_header = self.get_header_widget()
        style_sheet = 'QGroupBox {background: rgb(70, 70, 70);'
        style_sheet += 'border:rgb(70, 70, 70)}'
        options_box_header.setStyleSheet(style_sheet)
        options_box_header.set_title('Pass Sync\nRule/s')

        vertical_layout_main = self.get_content_widget_layout()
        vertical_layout_main.setContentsMargins(8, 8, 8, 8)
        vertical_layout_main.setSpacing(8)

        horizontal_layout = QHBoxLayout()
        horizontal_layout.setContentsMargins(0, 0, 0, 0)
        horizontal_layout.setSpacing(10)
        vertical_layout_main.addLayout(horizontal_layout)
        horizontal_layout.addWidget(QLabel('Include'))
        self._plain_text_widget_include_rules = QTextEdit()
        self._plain_text_widget_include_rules.setAcceptRichText(False)
        self._plain_text_widget_include_rules.setWordWrapMode(QTextOption.NoWrap)
        self._plain_text_widget_include_rules.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding)
        horizontal_layout.addWidget(self._plain_text_widget_include_rules)

        horizontal_layout = QHBoxLayout()
        horizontal_layout.setContentsMargins(0, 0, 0, 0)
        horizontal_layout.setSpacing(10)
        vertical_layout_main.addLayout(horizontal_layout)
        horizontal_layout.addWidget(QLabel('Exclude'))
        self._plain_text_widget_exclude_rules = QTextEdit()
        self._plain_text_widget_exclude_rules.setAcceptRichText(False)
        self._plain_text_widget_exclude_rules.setWordWrapMode(QTextOption.NoWrap)
        self._plain_text_widget_exclude_rules.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding)
        self._plain_text_widget_exclude_rules.setFixedHeight(90)
        horizontal_layout.addWidget(self._plain_text_widget_exclude_rules)

        if include_rules:
            rules_str = '\n'.join(include_rules)
            self._plain_text_widget_include_rules.setPlainText(rules_str)

        if exclude_rules:
            rules_str = '\n'.join(exclude_rules)
            self._plain_text_widget_exclude_rules.setPlainText(rules_str)

        self.build_okay_cancel_buttons()
        self._pushButton_okay.clicked.connect(self._emit_sync_rules_modified)

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

        self._pushButton_okay = QPushButton('Apply')
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


    def get_include_rules_string(self):
        return str(self._plain_text_widget_include_rules.toPlainText())


    def get_exclude_rules_string(self):
        return str(self._plain_text_widget_exclude_rules.toPlainText())


    def get_include_rules(self):
        rules = self.get_include_rules_string().split('\n')
        rules_verified = list()
        for rule in rules:
            if not rule:
                continue
            rule = str(rule)
            rules_verified.append(rule)
        return rules_verified


    def get_exclude_rules(self):
        rules = self.get_exclude_rules_string().split('\n')
        rules_verified = list()
        for rule in rules:
            if not rule:
                continue
            rule = str(rule)
            rules_verified.append(rule)
        return rules_verified


    def _emit_sync_rules_modified(self):
        self.syncRulesIncludeModified.emit(self.get_include_rules())
        self.syncRulesExcludeModified.emit(self.get_exclude_rules())
        self.close()