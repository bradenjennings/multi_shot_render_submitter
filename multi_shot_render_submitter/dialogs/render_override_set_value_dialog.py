#!/usr/bin/env python


import logging
import os

from Qt.QtWidgets import (QDialog, QPushButton, QSpinBox, QCheckBox,
    QDoubleSpinBox, QComboBox, QLineEdit, QPlainTextEdit, QLabel, QWidget,
    QVBoxLayout, QHBoxLayout, QSizePolicy)
from Qt.QtGui import QIcon
from Qt.QtCore import Qt, Signal


from srnd_qt.ui_framework.options_box import OptionsBox
from srnd_qt.ui_framework.widgets.base_widget import BaseWidget

from srnd_multi_shot_render_submitter import utils
from srnd_multi_shot_render_submitter.render_overrides import render_override_item_abstract


ICONS_DIR = os.path.join(
    os.getenv('SRND_MULTI_SHOT_RENDER_SUBMITTER_ROOT', str()),
    'icons')
ICON_PATH = os.path.join(
    ICONS_DIR,
    'Multi_Shot_Render_Submitter_logo_01_128x128.png')

WINDOW_SIZE = (650, 220)
FS = '<b><font color="#33CC33">'
FE = '</b></font>'
FS_DIM = '<b><font color="#0099ff">'

logging.basicConfig()
LOGGER = logging.getLogger('render_override_set_value_dialog')
LOGGER.setLevel(logging.DEBUG)


##############################################################################


class RenderOverrideSetValueDialog(QDialog, BaseWidget):
    '''
    A dialog to choose a render override value according to type.
    When Set Value button is pushed this dialog is accepted, and an
    external view can then act on this chosen value to add or edit a render override.
    NOTE: You can either reimplement this MSRS dialog to add other render override
    type support. Or reimplement the method choose_value_from_dialog on RenderOverrideItem,
    to skip calling this dialog entirely, and call your own separate dialog.

    Args:
        render_override_object (RenderOverrideItem): an uninstantiated render override object
        value (object): the initial value to apply to value widget of this window
    '''

    def __init__(
            self,
            render_override_object,
            value,
            window_size=WINDOW_SIZE,
            parent=None,
            **kwargs):
        super(RenderOverrideSetValueDialog, self).__init__(parent=parent)

        self._render_override_object = render_override_object

        # msg = 'Opening Render Overrides Set Value Dialog. '
        # msg += 'With Value: "{}"'.format(value)
        # LOGGER.info(msg)

        self.ICON_PATH = ICON_PATH
        title = 'Set value for render override'
        if render_override_object:
            if render_override_object.get_override_icon_path():
                self.ICON_PATH = render_override_object.get_override_icon_path()
            title += ' - "{}"'.format(render_override_object.OVERRIDE_LABEL)
        self.setWindowTitle(title)

        vertical_layout_main = QVBoxLayout()
        vertical_layout_main.setContentsMargins(8, 8, 8, 8)
        vertical_layout_main.setSpacing(5)
        self.setLayout(vertical_layout_main)

        options_box_header = OptionsBox(
            title_str='Placeholder',
            tool_description='Placeholder',
            description_is_dismissible=True,
            description_by_title=False,
            tool_icon=self.ICON_PATH,
            icon_size=20)
        options_box_header.set_darker_stylesheet()
        vertical_layout_main.addWidget(options_box_header)

        style_sheet = 'QGroupBox {background: rgb(70, 70, 70);'
        style_sheet += 'border:rgb(70, 70, 70)}'
        options_box_header.setStyleSheet(style_sheet)

        description_widget = options_box_header.get_description_widget()
        close_button = description_widget.get_close_button_widget()
        close_button.setVisible(False)

        msg = 'Set value for "{}" render override'.format(render_override_object.OVERRIDE_LABEL)
        options_box_header.set_title(msg)

        if render_override_object:
            msg = self.get_render_override_description(render_override_object)
            options_box_header.set_description(msg)

        self._value_widget = self._build_value_widget(value=value)

        vertical_layout_main = self.layout()
        vertical_layout_main.addStretch(100)

        self._build_buttons()
        self._pushButton_set_value.clicked.connect(self.accept)
        self._pushButton_close.clicked.connect(self.reject)

        self.setMinimumHeight(window_size[1])
        self.resize(*window_size)
        self.center()


    def get_render_override(self):
        '''
        Get the render override item of this dialog.

        Returns:
            render_override_object (RenderOverrideItem):
        '''
        return self._render_override_object


    def get_value(self):
        '''
        Get the value entered into this window UI, as type according to
        target render overrid item.

        Returns:
            value (object):
        '''
        if not self._value_widget:
            return

        OVERRIDE_TYPE = self._render_override_object.OVERRIDE_TYPE

        if OVERRIDE_TYPE in ['int', 'float']:
            return self._value_widget.value()

        elif OVERRIDE_TYPE == 'enum':
            return str(self._value_widget.currentText())

        elif OVERRIDE_TYPE == 'bool':
            return bool(self._value_widget.isChecked())

        elif OVERRIDE_TYPE == 'string':
            if self.STRING_OVERRIDE_IS_MULTILINE:
                return str(self._value_widget.toPlainText())
            else:
                return str(self._value_widget.currentText())

        elif OVERRIDE_TYPE == 'tuple':
            return self._value_widget[0].value(), self._value_widget[1].value()

        # Get multi values for value widget which stores multiple attributes.
        # If it has the get_value method available.
        elif OVERRIDE_TYPE == 'dict' and hasattr(self._value_widget, 'get_value'):
            return self._value_widget.get_value()


    def _build_value_widget(self, value=None):
        '''
        Build a value widget appropiate for type of render override item.

        Args:
            render_override_object (RenderOverrideItem): an uninstantiated render override object
            value (object): the initial value to apply to value widget of this window

        Returns:
            value_widget (QWidget): subclass of QWidget appropiate to edit value type
        '''
        if not self._render_override_object:
            return

        OVERRIDE_TYPE = self._render_override_object.OVERRIDE_TYPE
        OVERRIDE_DEFAULT_VALUE = self._render_override_object.OVERRIDE_DEFAULT_VALUE
        OVERRIDE_MIN_VALUE = self._render_override_object.OVERRIDE_MIN_VALUE
        OVERRIDE_MAX_VALUE = self._render_override_object.OVERRIDE_MAX_VALUE
        TUPLE_LABELS = self._render_override_object.TUPLE_LABELS

        if value == None:
            value = OVERRIDE_DEFAULT_VALUE

        # msg = 'Building Value Widget For Value: "{}". '.format(value)
        # msg += 'Override Type: "{}". '.format(OVERRIDE_TYPE)
        # msg += 'Default Value: "{}". '.format(OVERRIDE_DEFAULT_VALUE)
        # msg += 'Min Value: "{}". '.format(OVERRIDE_MIN_VALUE)
        # msg += 'Max Value: "{}"'.format(OVERRIDE_MAX_VALUE)
        # LOGGER.info(msg)

        vertical_layout_main = self.layout()
        vertical_layout_main.addSpacing(10)

        horizontal_layout_buttons = QHBoxLayout()
        horizontal_layout_buttons.setContentsMargins(0, 0, 0, 0)
        horizontal_layout_buttons.setSpacing(10)
        vertical_layout_main.addLayout(horizontal_layout_buttons)

        value_widget = None

        if OVERRIDE_TYPE in ['int', 'float']:
            label = QLabel('<i>Value</i>')
            label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
            horizontal_layout_buttons.addWidget(label)
            if OVERRIDE_TYPE == 'int':
                value_widget = QSpinBox()
            else:
                value_widget = QDoubleSpinBox()
            value_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            horizontal_layout_buttons.addWidget(value_widget)
            if isinstance(OVERRIDE_MIN_VALUE, (int, float)):
                value_widget.setMinimum(OVERRIDE_MIN_VALUE)
            if isinstance(OVERRIDE_MAX_VALUE, (int, float)):
                value_widget.setMaximum(OVERRIDE_MAX_VALUE)
            if isinstance(value, (int, float)):
                value_widget.setValue(value)

        elif OVERRIDE_TYPE == 'enum':
            label = QLabel('<i>Choose Preset</i>')
            label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
            horizontal_layout_buttons.addWidget(label)
            value_widget = QComboBox()
            value_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            value_widget.addItems(self._render_override_object.get_enum_options())
            # NOTE: Add long description and short name for each enum option (if available)
            descriptions = self._render_override_object.get_enum_options_descriptions() or list()
            enum_options_short = self._render_override_object.get_enum_options_short() or list()
            count = len(descriptions) or len(enum_options_short)
            for i in range(0, count, 1):
                tooltip = str()
                try:
                    description = descriptions[i]
                    if description:
                        tooltip += '<b>Description:</b> {}. '.format(description)
                except IndexError:
                    pass
                try:
                    label_short = enum_options_short[i]
                    if label_short:
                        tooltip += '<b>Short label:</b> {}. '.format(label_short)
                except IndexError:
                    pass
                if tooltip:
                    value_widget.setItemData(i, tooltip, Qt.ToolTipRole)
            horizontal_layout_buttons.addWidget(value_widget)
            if value and isinstance(value, basestring):
                import srnd_qt.base.utils
                srnd_qt.base.utils.combo_box_set_index_from_str(value_widget, str(value))

        elif OVERRIDE_TYPE == 'bool':
            label = QLabel('<i>State</i>')
            label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
            horizontal_layout_buttons.addWidget(label)
            value_widget = QCheckBox()
            value_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            horizontal_layout_buttons.addWidget(value_widget)
            if isinstance(value, bool):
                value_widget.setChecked(bool(value))

        elif OVERRIDE_TYPE == 'string':
            label = QLabel('<i>Value</i>')
            label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
            horizontal_layout_buttons.addWidget(label)
            if self.STRING_OVERRIDE_IS_MULTILINE:
                value_widget = QPlainTextEdit()
                value_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                horizontal_layout_buttons.addWidget(value_widget)
                if isinstance(value, basestring):
                    value_widget.setPlainText(str(value))
            else:
                value_widget = QLineEdit()
                value_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                horizontal_layout_buttons.addWidget(value_widget)
                if isinstance(value, basestring):
                    value_widget.setText(str(value))

        # NOTE: For now tuple only supports int values
        elif OVERRIDE_TYPE == 'tuple':
            value_1 = 1
            value_2 = 100
            label_1_str = '<i>Value 1</i>'
            label_2_str = '<i>Value 2</i>'
            if isinstance(TUPLE_LABELS, (tuple, list)) and len(TUPLE_LABELS) >= 2:
                label_1_str = '<i>{}</i>'.format(TUPLE_LABELS[0])
                label_2_str = '<i>{}</i>'.format(TUPLE_LABELS[1])
            if isinstance(value, (tuple, list)) and len(value) >= 2:
                value_1 = value[0]
                value_2 = value[1]

            label_1 = QLabel(label_1_str)
            label_1.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
            horizontal_layout_buttons.addWidget(label_1)
            value_1_widget = QSpinBox()
            value_1_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            horizontal_layout_buttons.addWidget(value_1_widget)

            label_2 = QLabel(label_2_str)
            label_2.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
            horizontal_layout_buttons.addWidget(label_2)
            value_2_widget = QSpinBox()
            value_2_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            horizontal_layout_buttons.addWidget(value_2_widget)

            for _widget, _value in [
                    (value_1_widget, value_1),
                    (value_2_widget, value_2)]:
                if isinstance(OVERRIDE_MIN_VALUE, (int, float)):
                    _widget.setMinimum(OVERRIDE_MIN_VALUE)
                if isinstance(OVERRIDE_MAX_VALUE, (int, float)):
                    _widget.setMaximum(OVERRIDE_MAX_VALUE)
                if isinstance(_value, (int, float)):
                    _widget.setValue(_value)

            value_widget = (value_1_widget, value_2_widget)

        return value_widget


    def _build_buttons(self):
        '''
        Build all the required window buttons for Okay, Remove Override and Cancel

        Returns:
            buttons (list): list of QPushButton
        '''
        vertical_layout_main = self.layout()
        vertical_layout_main.addSpacing(10)

        horizontal_layout_buttons = QHBoxLayout()
        horizontal_layout_buttons.setContentsMargins(0, 0, 0, 0)
        horizontal_layout_buttons.setSpacing(10)

        horizontal_layout_buttons.addStretch(100)

        buttons = list()

        self._pushButton_set_value = QPushButton('Set value')
        self._pushButton_set_value.setAutoDefault(False)
        self._pushButton_set_value.setFixedHeight(26)
        self._pushButton_set_value.setMinimumWidth(75)
        self._pushButton_set_value.setIcon(QIcon(str(self.ICON_PATH)))
        horizontal_layout_buttons.addWidget(self._pushButton_set_value)
        buttons.append(self._pushButton_set_value)

        self._pushButton_close = QPushButton('Close')
        self._pushButton_close.setAutoDefault(False)
        msg = 'Exit this choose render override value window'
        self._pushButton_close.setToolTip(msg)
        self._pushButton_close.setFixedHeight(26)
        self._pushButton_close.setMinimumWidth(75)
        horizontal_layout_buttons.addWidget(self._pushButton_close)
        buttons.append(self._pushButton_close)

        self._pushButton_set_value.setAutoDefault(True)

        self._pushButton_set_value.setFocus()

        vertical_layout_main.addLayout(horizontal_layout_buttons)

        return buttons


    def get_render_override_description(self, render_override_object=None):
        '''
        Get a description about render override to appear in this windows tool description.

        Args:
            render_override_object (RenderOverrideItem): an uninstantiated render override object

        Returns:
            msg (str):
        '''
        render_override_object = render_override_object or self._render_override_object
        if not render_override_object:
            return str()
        msg = '<i>'
        description = render_override_object.OVERRIDE_DESCRIPTION
        if description:
            msg += '<b>{}{}{}</b>'.format(FS, description, FE)
        msg += '<br>'
        if render_override_object.OVERRIDE_CATEGORY:
            msg += 'Category: <b>{}{}{}</b>. '.format(
                FS, render_override_object.OVERRIDE_CATEGORY, FE)
        # msg += 'Type: <b>{}{}{}</b>. '.format(FS_DIM, render_override_object.OVERRIDE_TYPE, FE)
        msg += 'Id: <b>{}{}{}</b>'.format(FS_DIM, render_override_object.OVERRIDE_ID, FE)
        if render_override_object.AUTHOR:
            msg += '<br>'
            msg += 'Override author: <b>{}{}{}</b>'.format(FS_DIM, render_override_object.AUTHOR, FE)
            if render_override_object.AUTHOR_DEPARTMENT:
                msg += '. Department: <b>{}{}{}</b>'.format(
                    FS_DIM, render_override_object.AUTHOR_DEPARTMENT, FE)
        msg += '</i>'
        return msg


##############################################################################


def main(**kwargs):
    '''
    Start RenderOverrideSetValueDialog as standalone app.
    '''
    import sys

    from Qt.QtWidgets import QApplication
    app = QApplication(sys.argv)

    from srnd_qt.ui_framework.styling import palettes
    palettes.style_app_dark(app)

    from srnd_multi_shot_render_submitter.render_overrides.render_overrides_manager import \
        RenderOverridesManager
    from_env_var = 'MSRS_RENDER_OVERRIDES'
    render_overrides_manager = RenderOverridesManager(from_env_var=from_env_var)
    render_overrides_manager.get_render_overrides_plugins()
    render_override_item = render_overrides_manager.get_render_override_object_by_id(
        'ResolutionCustomOverrideExample')

    ui_window = RenderOverrideSetValueDialog(render_override_item)
    ui_window.show()

    sys.exit(app.exec_())


if __name__ == '__main__':
    main()