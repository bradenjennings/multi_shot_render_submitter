

import os

from Qt.QtWidgets import (QWidget, QPushButton, QLabel, QHBoxLayout)
from Qt.QtGui import QFont, QPixmap
from Qt.QtCore import Signal

from srnd_multi_shot_render_submitter.constants import Constants
constants = Constants()


##############################################################################


class SessionAutoSaveStateWidget(QWidget):
    '''
    A widget to visualize if session auto save is active, and
    hint at warnings if not.
    '''

    AUTO_SAVE_SESSION_PROJECT_UNSAVED = 'Project is new & unsaved! '
    AUTO_SAVE_SESSION_PROJECT_UNSAVED += 'Auto save session will be skipped!'
    AUTO_SAVE_SESSION_IS_OKAY = 'Auto save session enabled and on {}s timer'
    AUTO_SAVE_SESSION_DISABLED = 'auto save session is disabled'
    ICON_HEIGHT = 18

    saveProjectRequest = Signal()
    saveSessionRequest = Signal()


    def __init__(self, parent=None):
        super(SessionAutoSaveStateWidget, self).__init__(parent=parent)

        self._session_auto_save_enabled = True
        self._session_auto_save_duration = 180
        self._project_is_saved = False

        horizontal_layout = QHBoxLayout()
        horizontal_layout.setContentsMargins(0, 0, 0, 0)
        horizontal_layout.setSpacing(0)
        self.setLayout(horizontal_layout)

        self._label_state_icon = QLabel()
        horizontal_layout.addWidget(self._label_state_icon)

        horizontal_layout.addSpacing(10)

        font = QFont()
        font.setFamily(constants.FONT_FAMILY)
        font.setItalic(True)
        # font.setPointSize(8)

        self._label_state_string = QLabel()
        self._label_state_string.setFont(font)
        horizontal_layout.addWidget(self._label_state_string)

        horizontal_layout.addSpacing(15)

        msg = 'The Current Project Is New And Has Never Been Saved!'
        msg += '<br><i>Note: Auto Session Data Is Saved As A Resource Of The '
        msg += 'Open Project File. So Press This Button To Open Save Dialog '
        msg += 'And Then Session Data Will Be Automatically '
        msg += 'Saved When The Auto Save Duration Timeer Is Reached.</i>'
        self._pushButton_save_project = QPushButton('Save project')
        self._pushButton_save_project.setFixedHeight(20)
        self._pushButton_save_project.setVisible(False)
        horizontal_layout.addWidget(self._pushButton_save_project)

        msg = 'Save The Session Data Immediately As A Resource Of '
        msg += 'The Currently Open Project Product.'
        msg += '<br><i>Note: Otherwise Session Will Be Auto Saved '
        msg += 'The Next Time The Auto Save Duration Timer Is Reached.'
        self._pushButton_save_session = QPushButton('Save session now')
        self._pushButton_save_session.setFixedHeight(20)
        self._pushButton_save_session.setToolTip(msg)
        self._pushButton_save_session.setVisible(False)
        horizontal_layout.addWidget(self._pushButton_save_session)

        self._pushButton_save_project.clicked.connect(
            self._emit_save_project_request)
        self._pushButton_save_session.clicked.connect(
            self._emit_save_session_request)


    def set_project_is_saved(self, saved):
        '''
        Update the auto save session hint to project never saved state.
        '''
        self._project_is_saved = saved
        self._update_state()


    def set_session_auto_save_enabled(self, enabled):
        '''
        Set whether session auto save enabled state.

        Args:
            enabled (bool):
        '''
        self._session_auto_save_enabled = enabled
        self._update_state()


    def set_session_auto_save_duration(self, duration):
        '''
        Update the session auto save duration.

        Args:
            duration (int):
        '''
        self._session_auto_save_duration = duration
        self._update_state()


    def _update_state(self):
        '''
        Update this widgets auto save state text hint, icon and
        show or hide various buttons.
        '''
        show_button = not bool(self._project_is_saved)
        self._pushButton_save_project.setVisible(show_button)

        self._pushButton_save_session.setVisible(bool(self._project_is_saved))

        if self._project_is_saved:
            if self._session_auto_save_enabled:
                label_str = self.AUTO_SAVE_SESSION_IS_OKAY.format(self._session_auto_save_duration)
                icon_path = os.path.join(constants.ICONS_DIR, 'okay.png')
            else:
                label_str = self.AUTO_SAVE_SESSION_DISABLED
                icon_path = os.path.join(constants.ICONS_DIR, 'warning.png')
        else:
            label_str = self.AUTO_SAVE_SESSION_PROJECT_UNSAVED
            icon_path = os.path.join(constants.ICONS_DIR, 'warning.png')

        self._label_state_string.setText(label_str)

        pixmap = QPixmap(icon_path)
        pixmap = pixmap.scaledToHeight(self.ICON_HEIGHT)
        self._label_state_icon.setPixmap(pixmap)


    def _emit_save_project_request(self):
        self.saveProjectRequest.emit()

    def _emit_save_session_request(self):
        self.saveSessionRequest.emit()