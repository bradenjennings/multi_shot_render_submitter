
import os

from Qt.QtWidgets import QFormLayout, QSizePolicy
from Qt.QtGui import QIcon
from Qt.QtCore import Qt, Signal

import srnd_qt.base.utils
from srnd_qt.ui_framework.dialogs import base_popup_dialog


fs = '<b><font color="#33CC33">'
fe = '</b></font>'
DESCRIPTION = 'Change {}oz area{} for selected '.format(fs, fe)
DESCRIPTION += '{}environment{} item(s). '.format(fs, fe)

DIALOG_WH = (575, 200)

fs = '<b><font color="#33CC33">'
fe = '</b></font>'


##############################################################################


class ChangeAreaDialog(base_popup_dialog.BasePopupDialog):
    '''
    A dialog to choose a new Weta Area for the selected Environment items.

    Args:
        area (str): initial area to show in area chooser widget
        icon_path (str):
    '''

    addEnvironmentsRequest = Signal(list)

    def __init__(
            self,
            area=os.getenv('OZ_AREA'),
            icon_path=None,
            parent=None,
            **kwargs):
        super(ChangeAreaDialog, self).__init__(
            tool_name='Change area',
            description=DESCRIPTION,
            description_by_title=False,
            description_is_dismissible=False,
            do_validate=True,
            icon_path=icon_path,
            icon_size=20,
            parent=parent)

        area = area or os.getenv('OZ_AREA')

        self.resize(*DIALOG_WH)
        self.center()

        self.layout().setContentsMargins(6, 6, 6, 6)

        options_box_header = self.get_header_widget()
        style_sheet = 'QGroupBox {background: rgb(70, 70, 70);'
        style_sheet += 'border:rgb(70, 70, 70)}'
        options_box_header.setStyleSheet(style_sheet)
        options_box_header.set_title('Change area for selected')

        vertical_layout = self.get_content_widget_layout()
        vertical_layout.setContentsMargins(6, 6, 6, 6)

        from srnd_qt.ui_framework.widgets import oz_area_picker
        self._oz_area_picker = oz_area_picker.OzAreaPicker(
            oz_area=area,
            primary_oz_area=area,
            allow_project_change=True,
            include_subvariant=False,
            label_str='Oz Area')
        self._oz_area_picker.setFixedHeight(32)
        vertical_layout.addWidget(self._oz_area_picker)

        if self._do_validate:
            self._oz_area_picker.ozAreaChanged.connect(
                lambda *x: self.validate_child_widgets())

        vertical_layout.addStretch(100)

        buttons = self.build_okay_cancel_buttons()
        buttons[0].setText('Change environments')


    def get_area(self):
        '''
        Get the chosen Weta area to change selected Environments items to.

        Returns:
            area (list):
        '''
        return self._oz_area_picker.get_oz_area()


    def get_widgets_to_validate(self):
        '''
        List of child widgets to validate before dialog can be accepted.
        Reimplemented from super class.

        Returns:
            widgets (list):
        '''
        return [self._oz_area_picker]


    def showEvent(self, event):
        '''
        Reimplemented to set the environment widget in focus, and
        cursor position at end after dialog opens.
        NOTE: QLineEdit which is focus widget at this time, will have all the text
        selected, so set the focus after the dialog opens.
        Qt has some some internal signals which will trigger a deferred select all,
        which is not desired here.
        '''
        # NOTE: Calling super showEvent
        base_popup_dialog.BasePopupDialog.showEvent(self, event)
        # Select the environment after small delay
        from Qt.QtCore import QTimer
        QTimer.singleShot(50, self._set_environment_widget_in_focus)


    def _set_environment_widget_in_focus(self):
        line_edit = self._oz_area_picker.get_oz_area_line_edit()
        if line_edit:
            line_edit.setFocus()