

import os

from Qt.QtGui import QIcon, QTextOption
from Qt.QtWidgets import (QWidget, QToolButton, QCheckBox, 
    QComboBox, QPlainTextEdit, QLabel, 
    QGridLayout, QHBoxLayout, QFormLayout, QSizePolicy)
from Qt.QtCore import Qt, QSize

from srnd_qt.ui_framework.widgets import group_box_collapsible


from srnd_multi_shot_render_submitter.constants import Constants
constants = Constants()

ICONS_DIR = os.path.join(
    os.getenv('SRND_MULTI_SHOT_RENDER_SUBMITTER_ROOT', str()),
    'icons')

STYLESHEET_PLAINTEXTEDIT_DISABLED = '''QPlainTextEdit {
border-style: solid;
border-width: 0px;
color: rgb(200, 200, 200);
background-color: rgb(80, 80, 80);}'''
STYLESHEET_PLAINTEXTEDIT_DISABLED_KATANA = '''QPlainTextEdit {
border-style: solid;
border-width: 0px;
color: rgb(200, 200, 200);
background-color: rgb(70, 70, 70);}'''    
STYLE_EXPANDABLE_CHECKBOX = 'QCheckBox::indicator {width: 18px;height: 18px;}'
STYLE_EXPANDABLE_CHECKBOX += 'QCheckBox::indicator:unchecked {image: url(' 
STYLE_EXPANDABLE_CHECKBOX += os.path.join(ICONS_DIR, 'collapsed_s01.png') + ')}'
STYLE_EXPANDABLE_CHECKBOX += 'QCheckBox::indicator:checked {image: url(' 
STYLE_EXPANDABLE_CHECKBOX += os.path.join(ICONS_DIR, 'expanded_s01.png') + ')}'


#@############################################################################


class SelectionSummaryWidget(
        group_box_collapsible.GroupBoxCollapsible):
    '''
    Widget to show number of shots, passes, and frames details for selected MSRS items.
    '''

    def __init__(
            self, 
            title_str='Selection summary',
            collapsible=False,
            collapsed=False,
            closeable=False,            
            parent=None):
        super(SelectionSummaryWidget, self).__init__(
            title_str=title_str,
            collapsible=bool(collapsible),
            collapsed=bool(collapsed),
            closeable=bool(closeable),
            content_margin=4,
            parent=parent)

        self._identifiers = set()
        self._identity_ids = set()

        vertical_layout = self.get_content_widget_layout()
        vertical_layout.setContentsMargins(2, 2, 2, 2)
        vertical_layout.setSpacing(4)

        self._widget_info = QWidget()
        self._gridLayout_info = QGridLayout()
        self._gridLayout_info.setContentsMargins(0, 0, 0, 0)
        self._gridLayout_info.setColumnStretch(1, 100)
        self._widget_info.setLayout(self._gridLayout_info)
        self._widget_info.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Minimum)
        vertical_layout.addWidget(self._widget_info)

        line_edit_widget = self.get_title_widget()
        font = line_edit_widget.font()
        font.setFamily(constants.FONT_FAMILY)
        font.setPointSize(8)
        line_edit_widget.setFont(font)

        # TODO: Later improve global styling system and reimplement
        # in srnd_katana_render_submitter repo
        if constants.IN_KATANA_UI_MODE:
            self.set_header_style(
                group_box_collapsible.STYLESHEET_GROUP_BOX_HEADER_70)
            self.set_group_box_style(
                constants.STYLESHEET_GROUPBOX_DETAILS_PANEL_BORDER)
        else:
            self.set_dark_stylesheet()

        row = 0
        column = 0

        self._label_pass_count = QLabel('Passes')
        self._label_pass_count.setFont(constants.PANEL_FONT_REGULAR)
        self._gridLayout_info.addWidget(self._label_pass_count, row, column)

        column += 1

        self._label_summary_pass_count = QLabel()
        self._label_summary_pass_count.setFont(constants.PANEL_FONT_ITALIC)
        self._gridLayout_info.addWidget(self._label_summary_pass_count, row, column)

        row += 1
        column = 0

        self._label_frame_count = QLabel('Frames')
        self._label_frame_count.setFont(constants.PANEL_FONT_REGULAR)
        self._gridLayout_info.addWidget(self._label_frame_count, row, column)

        column += 1

        self._label_summary_frame_count = QLabel()
        self._label_summary_frame_count.setFont(constants.PANEL_FONT_ITALIC)
        self._gridLayout_info.addWidget(self._label_summary_frame_count, row, column)

        ######################################################################

        vertical_layout.addSpacing(2)

        self._form_layout_identifiers = QFormLayout()
        self._form_layout_identifiers.setContentsMargins(0, 0, 0, 0)
        self._form_layout_identifiers.setSpacing(4)
        vertical_layout.addLayout(self._form_layout_identifiers)

        self._widget_identifiers = QWidget()
        horizontal_layout = QHBoxLayout()
        horizontal_layout.setContentsMargins(0, 0, 0, 0)
        horizontal_layout.setSpacing(8)
        self._widget_identifiers.setLayout(horizontal_layout)

        msg = 'Choose type of selection identifier to display. '
        msg += '<br><b>Identifiers</b> - a human readable string identity.'
        msg += '<br><b>UUID</b> - internal MSRS identity id (not human readable).'
        self._comboBox_copy_identifier_type = QComboBox()
        self._comboBox_copy_identifier_type.setToolTip(msg)
        self._comboBox_copy_identifier_type.addItems(
            ['Identifiers', 'UUIDs'])
        self._comboBox_copy_identifier_type.setSizePolicy(
            QSizePolicy.Minimum,
            QSizePolicy.Fixed)
        self._comboBox_copy_identifier_type.setFixedHeight(22)
        horizontal_layout.addWidget(self._comboBox_copy_identifier_type)

        msg = 'All human readable identifiers or uuid of selection'
        self._plainTextEdit_selection_identities = QPlainTextEdit() 
        self._plainTextEdit_selection_identities.setToolTip(msg)
        self._plainTextEdit_selection_identities.setFixedHeight(23)
        self._plainTextEdit_selection_identities.setReadOnly(True)
        self._plainTextEdit_selection_identities.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Fixed)            
        if constants.IN_KATANA_UI_MODE:
            self._plainTextEdit_selection_identities.setStyleSheet(
                STYLESHEET_PLAINTEXTEDIT_DISABLED_KATANA)
        else:
            self._plainTextEdit_selection_identities.setStyleSheet(
                STYLESHEET_PLAINTEXTEDIT_DISABLED)
        horizontal_layout.addWidget(self._plainTextEdit_selection_identities)

        self._toolButton_copy_identifiers = QToolButton()
        msg = 'Copy all human readable identifiers or uuid of selection shown here.'
        self._toolButton_copy_identifiers.setToolTip(msg)
        self._toolButton_copy_identifiers.setAutoRaise(True)
        self._toolButton_copy_identifiers.setIconSize(QSize(20, 20))
        self._toolButton_copy_identifiers.setFixedSize(20, 20)
        icon = QIcon(os.path.join(ICONS_DIR, 'copy_s01.png'))
        self._toolButton_copy_identifiers.setIcon(icon)
        horizontal_layout.addWidget(self._toolButton_copy_identifiers)

        is_expanded = False

        self._checkBox_expand_identifier = QCheckBox()
        self._checkBox_expand_identifier.setChecked(is_expanded)
        self._checkBox_expand_identifier.setStyleSheet(STYLE_EXPANDABLE_CHECKBOX)
        self._checkBox_expand_identifier.setSizePolicy(
            QSizePolicy.Fixed,
            QSizePolicy.Fixed)                    
        msg = 'Expand the field to see more details. '
        msg += 'Otherwise just copy to clipboard directly with button on left.'
        self._checkBox_expand_identifier.setToolTip(msg)            
        self._checkBox_expand_identifier.toggled.connect(
            self._on_expand_selection_identifiers)
        horizontal_layout.addWidget(self._checkBox_expand_identifier)

        self._form_layout_identifiers.addRow(
            self._widget_identifiers, 
            self._plainTextEdit_selection_identities)


        self._on_expand_selection_identifiers(is_expanded)

        # Don't need a header to show what this is
        header = self.get_header()
        if header:
            header.setVisible(False)

        self._wire_events()


    def _wire_events(self):
        '''
        Main UI events to connect
        '''
        self._toolButton_copy_identifiers.clicked.connect(
            self.copy_to_clipboard)
        self._comboBox_copy_identifier_type.currentIndexChanged.connect(
            self.show_identifiers_by_type)


    ##########################################################################


    def show_identifiers_by_type(self):
        '''
        Update whether human readable identifiers or UUIDs are being shown for selection.
        '''
        identifier_type = str(self._comboBox_copy_identifier_type.currentText())
        if identifier_type == 'UUIDs':
            msg = '\n'.join(self._identity_ids)
        else:
            msg = '\n'.join(self._identifiers)
        self._plainTextEdit_selection_identities.setPlainText(msg)
        self._plainTextEdit_selection_identities.setToolTip(msg)        


    def get_and_cache_identifiers_for_selection(self, selected_items):
        '''
        Gather all selected string identifiers (human readable), and UUIDs and cache.

        Args:
            selected_items (list):
        '''
        identifiers = set()
        identity_ids = set()
        for item in selected_items:
            if item.is_environment_item():
                identifier = item.get_environment_name_nice()
            else:
                identifier = item.get_identifier(nice_env_name=True)
            if identifier:
                identifiers.add(identifier)
            identity_id = item.get_identity_id()
            if identity_id:
                identity_ids.add(identity_id)
        self._identifiers = identifiers
        self._identity_ids = identity_ids


    def update_summary_info(
            self, 
            enabled_pass_count,
            enabled_frame_count,
            queued_pass_count,
            queued_frame_count):
        '''
        Update the selection summary info.

        Args:
            enabled_pass_count (int):
            enabled_frame_count (int):
            queued_pass_count (int):
            queued_frame_count (int):
        '''
        show_pass_count = bool(enabled_pass_count + queued_pass_count)

        msg = '{} ({} Queued)'.format(enabled_pass_count, queued_pass_count)
        self._label_summary_pass_count.setText(msg)
        self._label_summary_pass_count.setVisible(show_pass_count)
        self._label_pass_count.setVisible(show_pass_count)

        msg = '{} ({} Queued)'.format(enabled_frame_count, queued_frame_count)
        self._label_summary_frame_count.setText(msg)
        show_frame_count = bool(enabled_frame_count + queued_frame_count)
        self._label_summary_frame_count.setVisible(show_frame_count)
        self._label_frame_count.setVisible(show_frame_count)

        self.show_identifiers_by_type()


    def copy_to_clipboard(self):
        '''
        Copy Identifiers or UUIDs from widget to clipboard.

        Args:
            data_type (str):

        Returns:
            value (str): the value copied to clipboard
        '''
        display_value = None
        display_value = str(self._plainTextEdit_selection_identities.toPlainText())
        if not display_value:
            return

        values = display_value.split(' ') or list()
        value_str = '\n'.join(values)
        if not value_str:
            return

        from Qt.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        clipboard.setText(value_str)

        return value_str


    ##########################################################################


    def _on_expand_selection_identifiers(self, expanding):
        '''
        When selection identifiers is expanded or collapsed this method is called.

        Args:
            expanding (bool):
        '''
        scrollbars = list()
        scrollbars.append(self._plainTextEdit_selection_identities.horizontalScrollBar())
        scrollbars.append(self._plainTextEdit_selection_identities.verticalScrollBar())
        for scrollbar in scrollbars:
            scrollbar.setVisible(expanding)
        if expanding:
            vertical_layout = self.get_content_widget_layout()
            vertical_layout.addWidget(self._plainTextEdit_selection_identities)            
            self._plainTextEdit_selection_identities.setFixedHeight(100)
            self._plainTextEdit_selection_identities.setWordWrapMode(
                QTextOption.NoWrap)
        else:
            self._form_layout_identifiers.setWidget(
                0, 
                QFormLayout.FieldRole, 
                self._plainTextEdit_selection_identities)
            self._plainTextEdit_selection_identities.setFixedHeight(23)
            self._plainTextEdit_selection_identities.setWordWrapMode(
                QTextOption.WrapAnywhere)


    ##########################################################################


    def get_pass_count_widget(self):
        return self._label_pass_count

    def get_summary_pass_count_widget(self):
        return self._label_summary_pass_count

    def get_frame_count_widget(self):
        return self._label_frame_count

    def get_summary_frame_count_widget(self):
        return self._label_summary_frame_count

    def get_copy_identifier_type_widget(self):
        return self._comboBox_copy_identifier_type

    def get_selection_identities_widget(self):
        return self._plainTextEdit_selection_identities

    def get_copy_identifiers_widget(self):
        return self._toolButton_copy_identifiers