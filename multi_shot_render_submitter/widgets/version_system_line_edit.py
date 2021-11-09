

from Qt.QtWidgets import (QLineEdit, QCompleter, QHBoxLayout, QSizePolicy)
from Qt.QtCore import Qt

from srnd_qt.ui_framework.widgets.triangle_drop_down_button import TriangleDropDownToolButton

from srnd_multi_shot_render_submitter.validators import version_system_validator


##############################################################################


class VersionSystemLineEdit(QLineEdit):
    '''
    A widget to pick a custom version int, or from a particular
    system string, such as "V+".
    Note: Might want to move this to srnd_qt later.

    Args:
        margins (tuple):
        fixed_width (int):
    '''

    def __init__(
            self,
            margins=(3, 3, 3, 3),
            fixed_width=75,
            parent=None):
        super(VersionSystemLineEdit, self).__init__(parent=parent)

        self._horizontal_layout = QHBoxLayout(self)
        self._horizontal_layout.setSpacing(0)
        self._horizontal_layout.setContentsMargins(*margins)

        self._horizontal_layout.addStretch(100)

        self._tool_button_suggestions = TriangleDropDownToolButton()
        self._horizontal_layout.addWidget(
            self._tool_button_suggestions,
            1,
            Qt.AlignRight)
        self._horizontal_layout.addSpacing(5)

        self.setText(version_system_validator.DEFAULT_CG_VERSION_SYSTEM)
        validator = version_system_validator.VersionSystemValidator()
        self.setValidator(validator)

        self._completer = QCompleter(
            version_system_validator.CG_VERSION_SYSTEMS,
            parent=self)
        self._completer.setCaseSensitivity(Qt.CaseInsensitive)
        self._completer.setCompletionMode(QCompleter.UnfilteredPopupCompletion)
        self.setCompleter(self._completer)

        self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        if fixed_width and isinstance(fixed_width, int):
            self.setFixedWidth(fixed_width)

        self._tool_button_suggestions.clicked.connect(self._completer.complete)


    def keyPressEvent(self, event):
        '''
        Call fixup first on key press enter and return event.

        Args:
            event (QtCore.QEvent):
        '''
        if event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
            validator = self.validator()
            if validator:
                validator.fixup(self)
                self.returnPressed.emit()
                popup_widget = self._completer.popup()
                if popup_widget:
                    popup_widget.setVisible(False)
                return
        QLineEdit.keyPressEvent(self, event)


    def focusOutEvent(self, event):
        '''
        Call fixup first on focusOutEvent.
        '''
        validator = self.validator()
        if validator:
            validator.fixup(self)
        QLineEdit.focusOutEvent(self, event)