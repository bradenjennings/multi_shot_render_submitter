

from Qt.QtWidgets import QLineEdit
from Qt.QtGui import QIntValidator


CG_VERSION_SYSTEMS = ['VP+', 'V+', 'VS']
DEFAULT_CG_VERSION_SYSTEM = 'VP+'


class VersionSystemValidator(QIntValidator):
    '''
    A Validator that can accept any int value of version, or a particular
    version system name, such as "V+".

    Args:
        min (int):
        max (int):
        version_systems (list): list of strings of version system names
    '''

    def __init__(
            self,
            min_value=1,
            max_value=9999,
            version_systems=CG_VERSION_SYSTEMS,
            parent=None):
        super(VersionSystemValidator, self).__init__(
            int(min_value),
            int(max_value),
            parent)
        self._version_systems = version_systems


    def validate(self, text_str, pos):
        '''
        Note: By default, the pos parameter is not used by this validator.

        Args:
            text_str (str):
            pos (int):

        '''
        _text_str = str(text_str).lstrip('v')

        # Intemediate in case both ver
        if _text_str in self._version_systems:
            result = QIntValidator.Intermediate, text_str, pos

        elif _text_str.isdigit():
            value = int(_text_str)
            # QIntValidator will return Intermediate for values outside
            # range, which QLineEdit will accept. Instead return invalid for these.
            if value < self.bottom() or value > self.top():
                result = QIntValidator.Invalid, text_str, pos
            # Entering a int is valid, however fixup should be called to add "v" before string
            else:
                result = QIntValidator.Intermediate, text_str, pos
        else:
            if _text_str in self._version_systems:
                result = QIntValidator.Acceptable, text_str, pos
            # Start of input is number, so expect the rest to be number
            elif len(_text_str) > 1 and _text_str[0:-1].isdigit():
                result = QIntValidator.Invalid, text_str, pos
            # Can start with capital V for version system, but not other characters
            elif _text_str.isalpha() and not _text_str.startswith(('v', 'V')):
                result = QIntValidator.Invalid, text_str, pos
            else:
                result = QIntValidator.Intermediate, text_str, pos

        # NOTE: Result will be tuple of length 2 or 3 depending on PySide, PyQt and sip version
        return QIntValidator.validate(self, text_str, pos)


    def fixup(self, to_fixup=None):
        '''
        Validate the Version System or custom version int is valid.

        Args:
            to_fixup (str): QString in native QT, but a null object in Pyside1.
                might be overloading the argument to pass in the widget directly,
                via external signal connections, or calling this slot directly.
        '''
        widget = self.sender()
        is_line_edit = isinstance(to_fixup, QLineEdit)
        if widget or is_line_edit:
            widget = to_fixup if is_line_edit else widget

        if widget:
            to_fixup = str(widget.text()).lstrip('v')
        else:
            return

        if to_fixup in CG_VERSION_SYSTEMS:
            return

        if to_fixup.isdigit():
            widget.setText('v' + to_fixup)
            return

        # Revert to default version system
        widget.setText(DEFAULT_CG_VERSION_SYSTEM)