#!/usr/bin/env python


import logging
import os
import traceback

from Qt.QtWidgets import (QMainWindow, QPlainTextEdit,
    QPushButton, QComboBox, QLabel, QHBoxLayout, QSizePolicy)
from Qt.QtGui import QTextOption, QFont, QIcon
from Qt.QtCore import Qt, Signal

import srnd_qt.base.utils
from srnd_qt.ui_framework.dialogs import base_popup_dialog


##############################################################################


fs = '<b><font color="#33CC33">'
fe = '</b></font>'

DESCRIPTION_WAIT_ON = '<br><i>Note: These dependencies are applied to jobs on next submission, '
DESCRIPTION_WAIT_ON += 'assuming source & target item/s are submitted.</i>'
DESCRIPTION_WAIT_ON += '<br><i>Note: You can copy & paste these from the details panel.</i>'

DESCRIPTION_PLOW_IDS = 'Define existing {0}Plow Job/s{1} and '.format(fs, fe)
DESCRIPTION_PLOW_IDS += 'optionally {0}Plow Layer or Task Id/s{1} '.format(fs, fe)
DESCRIPTION_PLOW_IDS += 'for the selected Multi Shot items to depend on. '
DESCRIPTION_PLOW_IDS += '<i><br>Note: Specify a single Plow Job id per line & '
DESCRIPTION_PLOW_IDS += 'optionally a Plow Layer or Task id (space-separated).</i>'
DESCRIPTION_PLOW_IDS += '<i><br>Note: These dependencies are applied to jobs '
DESCRIPTION_PLOW_IDS += 'on next submission, assuming the Plow Jobs (and Layers & Tasks) '
DESCRIPTION_PLOW_IDS += 'are still in progress.</i> '

ICONS_DIR_QT = srnd_qt.base.utils.get_srnd_qt_icon_dir()
ICONS_DIR = os.path.join(
    os.getenv('SRND_MULTI_SHOT_RENDER_SUBMITTER_ROOT', str()),
    'icons')
ICON_PATH = os.path.join(ICONS_DIR, 'wait_20x20_s01.png')
DIALOG_WH = 1025, 775

fs = '<b><font color="#33CC33">'
fe = '</b></font>'


##############################################################################


class SetDependsDialog(base_popup_dialog.BasePopupDialog):
    '''
    Dialog to choose dependencies to other MSRS items or to
    other external Plow Job/s (and optionally Layer/s and Task/s thereof)

    Args:
        multi_shot_render_view (MultiShotRenderView): the view which has the selected multi shot items, to
            apply WAIT on dependencies to
        wait_on_multi_shot (list): list of UUIDS dependencies
        wait_on_plow_ids (list): list of lists. each containing a Plow Job id (and optionally a task id).
            NOTE: If only Plow Job id provided then dependency type to later create will be to entire Job.
            NOTE: If Plow Job and Task ids provided then dependency type to later create will be to
                specific Task of Job.
        wait_on_multi_shot_input_mode (str): currently can provide either "Identifiers" or "UUIDs"
        auto_validate_on_close (bool):
        version (str):
    '''

    waitOnModified = Signal() # WAIT On other Multi Shot items or Plow ids modified

    def __init__(
            self,
            multi_shot_render_view,
            wait_on_multi_shot=None,
            wait_on_plow_ids=None,
            wait_on_multi_shot_input_mode='UUIDs', # starts off internally in UUIDs mode
            auto_validate_on_close=True,
            version=None,
            host_app='GEN',
            parent=None,
            **kwargs):
        super(SetDependsDialog, self).__init__(
            tool_name='Set dependencies',
            description='Placeholder',
            description_by_title=True,
            description_is_dismissible=True,
            version=version,
            icon_path=ICON_PATH,
            icon_size=20,
            parent=parent)

        self.HOST_APP = str(host_app or str())

        layout_main = self.layout()

        self._tree_view = multi_shot_render_view
        self._wait_on_multi_shot = wait_on_multi_shot or list()
        self._wait_on_multi_shot_input_mode = str(wait_on_multi_shot_input_mode)
        self._wait_on_plow_ids = wait_on_plow_ids or list()
        self._auto_validate_on_close = bool(auto_validate_on_close)

        self.resize(*DIALOG_WH)
        self.center()

        options_box_header = self.get_header_widget()
        style_sheet = 'QGroupBox {background: rgb(70, 70, 70);'
        style_sheet += 'border:rgb(70, 70, 70)}'
        options_box_header.setStyleSheet(style_sheet)
        options_box_header.set_title('Set\ndependencies')

        vertical_layout_main = self.get_content_widget_layout()
        vertical_layout_main.setContentsMargins(8, 8, 8, 8)
        vertical_layout_main.setSpacing(8)

        ######################################################################

        font_bold = QFont()
        font_bold.setBold(True)

        self._label_selection_info = QLabel()
        self._label_selection_info.setFont(font_bold)
        self._label_selection_info.setMargin(8)
        self._label_selection_info.setStyleSheet('color: rgba(255, 255, 0, 255);')
        self._label_selection_info.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Fixed)
        layout_main.insertWidget(1, self._label_selection_info)

        ######################################################################

        group_box = self.add_group_box(
            title_str='Depend on other Multi Shot item/s',
            editable_title=False,
            collapsed=False,
            closeable=False,
            icon_path_section=ICON_PATH)
        group_box.set_can_be_collapsed(False)
        group_box.set_dark_stylesheet_darker()
        vertical_layout = group_box.get_content_widget_layout()
        vertical_layout.setSpacing(5)
        vertical_layout.setContentsMargins(0, 0, 0, 0)
        group_box.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding)

        from srnd_qt.ui_framework.widgets.options_box import ToolDescription
        self._tool_description_wait_on = ToolDescription(description=DESCRIPTION_WAIT_ON)
        self._tool_description_wait_on.set_dark_stylesheet()
        self._tool_description_wait_on.get_close_button_widget().setVisible(False)
        vertical_layout.addWidget(self._tool_description_wait_on)

        horizontal_layout = QHBoxLayout()
        horizontal_layout.setContentsMargins(0, 0, 0, 0)
        horizontal_layout.setSpacing(10)
        vertical_layout.addLayout(horizontal_layout)

        horizontal_layout.addWidget(QLabel('Input mode'))

        self._comboBox_wait_on_multi_shot_input_mode = QComboBox()
        msg = 'Choose whether to input (and view) identifiers '
        msg += 'or UUIDs to define dependencies to other multishot items. '
        self._comboBox_wait_on_multi_shot_input_mode.setToolTip(msg)
        INPUT_MODES = ['Identifiers', 'UUIDs']
        self._comboBox_wait_on_multi_shot_input_mode.addItems(INPUT_MODES)
        horizontal_layout.addWidget(self._comboBox_wait_on_multi_shot_input_mode)
        self._comboBox_wait_on_multi_shot_input_mode.currentIndexChanged[str].connect(
            self.set_wait_on_multi_shot_items_input_mode)

        horizontal_layout.addStretch(100)

        self._plain_text_widget_wait_on_multi_shot_items = QPlainTextEdit()
        self._plain_text_widget_wait_on_multi_shot_items.setWordWrapMode(QTextOption.NoWrap)
        self._plain_text_widget_wait_on_multi_shot_items.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding)
        vertical_layout.addWidget(self._plain_text_widget_wait_on_multi_shot_items)

        ######################################################################

        group_box = self.add_group_box(
            title_str='Depend on existing Plow ids',
            editable_title=False,
            collapsed=False,
            closeable=False,
            icon_path_section=ICON_PATH)
        group_box.set_can_be_collapsed(False)
        group_box.set_dark_stylesheet_darker()
        vertical_layout = group_box.get_content_widget_layout()
        vertical_layout.setSpacing(5)
        vertical_layout.setContentsMargins(0, 0, 0, 0)
        group_box.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding)

        tool_description = ToolDescription(description=DESCRIPTION_PLOW_IDS)
        tool_description.set_dark_stylesheet()
        tool_description.get_close_button_widget().setVisible(False)
        vertical_layout.addWidget(tool_description)

        self._plain_text_widget_plow_wait_on_ids = QPlainTextEdit()
        self._plain_text_widget_plow_wait_on_ids.setWordWrapMode(QTextOption.NoWrap)
        self._plain_text_widget_plow_wait_on_ids.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding)
        vertical_layout.addWidget(self._plain_text_widget_plow_wait_on_ids)

        self._plain_text_widget_plow_wait_on_ids.setContextMenuPolicy(Qt.CustomContextMenu)
        self._plain_text_widget_plow_wait_on_ids.customContextMenuRequested.connect(
            self._create_context_menu_wait_on_existing_ids)

        ######################################################################

        vertical_layout.addStretch(100)

        self._build_dialog_buttons()

        ######################################################################
        # Initial UI setup

        if wait_on_multi_shot:
            self.set_wait_on_multi_shot_items(wait_on_multi_shot)

        # Force Multi Show WAIT on to be shown as Identifiers on startup
        wait_on_multi_shot_input_mode = 'Identifiers'
        if wait_on_multi_shot_input_mode:
            self.set_wait_on_multi_shot_items_input_mode(wait_on_multi_shot_input_mode)

        if wait_on_plow_ids:
            self.set_wait_on_plow_ids(wait_on_plow_ids)

        self._update_selection_info()

        ######################################################################
        # Signals

        self._pushButton_set_wait_on.clicked.connect(self._emit_wait_on_modified)
        self._pushButton_validate_wait_on.clicked.connect(self.validate_wait_on)
        self._pushButton_clear_wait_on.clicked.connect(self.clear_wait_on)
        self._pushButton_close.clicked.connect(self.reject)


    ##########################################################################


    def _build_dialog_buttons(self):
        '''
        Build all the required dialog buttons for accept, close and other operations.

        Returns:
            buttons (list): list of QPushButton
        '''
        layout_main = self.layout()
        layout_main.addSpacing(10)

        horizontal_layout_buttons = QHBoxLayout()
        horizontal_layout_buttons.setContentsMargins(0, 0, 0, 0)
        horizontal_layout_buttons.setSpacing(10)

        horizontal_layout_buttons.addStretch(100)

        buttons = list()

        self._pushButton_set_wait_on = QPushButton('Set Dependencies')
        self._pushButton_set_wait_on.setAutoDefault(False)
        self._pushButton_set_wait_on.setFixedHeight(26)
        self._pushButton_set_wait_on.setMinimumWidth(75)
        self._pushButton_set_wait_on.setIcon(QIcon(str(ICON_PATH)))
        horizontal_layout_buttons.addWidget(self._pushButton_set_wait_on)
        buttons.append(self._pushButton_set_wait_on)

        self._pushButton_validate_wait_on = QPushButton('Validate Dependencies')
        self._pushButton_validate_wait_on.setAutoDefault(False)
        self._pushButton_validate_wait_on.setFixedHeight(26)
        self._pushButton_validate_wait_on.setMinimumWidth(75)
        horizontal_layout_buttons.addWidget(self._pushButton_validate_wait_on)

        self._pushButton_clear_wait_on = QPushButton('Clear Dependencies')
        self._pushButton_clear_wait_on.setAutoDefault(False)
        self._pushButton_clear_wait_on.setFixedHeight(26)
        self._pushButton_clear_wait_on.setMinimumWidth(75)
        horizontal_layout_buttons.addWidget(self._pushButton_clear_wait_on)

        self._pushButton_close = QPushButton('Close')
        self._pushButton_close.setAutoDefault(False)
        msg = 'Exit dialog without editing WAIT-on for selected items'
        self._pushButton_close.setToolTip(msg)
        self._pushButton_close.setFixedHeight(26)
        self._pushButton_close.setMinimumWidth(75)
        horizontal_layout_buttons.addWidget(self._pushButton_close)
        buttons.append(self._pushButton_set_wait_on)
        buttons.append(self._pushButton_set_wait_on)

        self._pushButton_set_wait_on.setAutoDefault(True)

        self.add_button_require_validation(self._pushButton_set_wait_on)

        layout_main.addLayout(horizontal_layout_buttons)

        return buttons


    def _create_context_menu_wait_on_existing_ids(self, pos):
        '''
        Build a QMenu for the wait on exi0sting Plow ids QPlainTextEdit widget.

        Returns:
            menu (QtGui.QMenu):
        '''
        from Qt.QtWidgets import QMenu
        from Qt.QtGui import QCursor

        import srnd_qt.base.utils

        menu = QMenu('Plow Job id actions', self)

        action = srnd_qt.base.utils.context_menu_add_menu_item(
            self,
            'Add all active Plow Job ids by user')
        action.triggered.connect(
            lambda *x: self.add_plow_job_ids_by_user())
        menu.addAction(action)

        menu.exec_(QCursor.pos())

        return menu


    def add_plow_job_ids_by_user(
            self,
            show_dialog=True,
            user=os.getenv('USER')):
        '''
        Add all currently active Plow job ids by user.

        Args:
            show_dialog (bool):
            user (str):
        '''
        user = user or os.getenv('USER', str())

        if show_dialog:
            from Qt.QtWidgets import QDialog
            from srnd_qt.ui_framework.dialogs import input_dialog

            dialog = input_dialog.GetInputDialog(
                title_str='Choose user',
                input_type_required=str(),
                value=str(user),
                parent=self)
            window_title = 'Choose User to get Plow Job ids for'
            dialog.setWindowTitle(window_title)
            dialog.adjustSize()

            options_box_header = dialog.get_header_widget()
            style_sheet = 'QGroupBox {background: rgb(70, 70, 70);'
            style_sheet += 'border:rgb(70, 70, 70)}'
            options_box_header.setStyleSheet(style_sheet)
            result = dialog.exec_()
            if result == QDialog.Rejected or not dialog.get_result():
                msg = 'User cancelled get plow job ids'
                self.logMessage.emit(msg, logging.WARNING)
                return list()
            user = str(dialog.get_result() or str())

        import plow
        regex_str = '.*{}.*'.format(self.HOST_APP).title()
        try:
            jobs = plow.job.get_jobs(
                regex=regex_str,
                user=user,
                state=plow.JobState.RUNNING) or list()
            msg = 'Got jobs for user by regex: "{}". '.format(regex_str)
            msg += 'Jobs: "{}"'.format(jobs)
            self.logMessage.emit(msg, logging.INFO)
        except Exception:
            msg = 'Failed to get job for user: "{}". '.format(user)
            msg += 'Full exception: "{}".'.format(traceback.format_exc())
            self.logMessage.emit(msg, logging.WARNING)
            return list()

        current_wait_on_plow_ids = self.get_wait_on_plow_ids()
        # msg = 'Existing WAIT On Plow Ids: "{}"'.format(current_wait_on_plow_ids)
        # self.logMessage.emit(msg, logging.DEBUG)

        plow_job_ids = set()
        for job in jobs:
            plow_job_id = job.id
            # Check if the derived Plow Job id is already added or not
            new_id = True
            for ids in current_wait_on_plow_ids:
                if plow_job_id == ids[0]:
                    new_id = False
                    break
            if new_id:
                plow_job_ids.add(plow_job_id)

        plow_job_ids = list(plow_job_ids)
        wait_on_plow_ids = list()
        for plow_job_id in plow_job_ids:
            value_to_add = list()
            value_to_add.append(plow_job_id)
            wait_on_plow_ids.append(value_to_add)
        self.add_wait_on_plow_ids(wait_on_plow_ids)

        return plow_job_ids


    ##########################################################################


    def validate_wait_on(self):
        '''
        Validate the current WAIT on multi shot items and existing Plow ids.
        '''
        model = self._tree_view.model()

        msg = 'Validating WAIT-on...'
        self.logMessage.emit(msg, logging.WARNING)

        wait_on = self.get_wait_on_multi_shot_items()
        input_mode = self.get_wait_on_multi_shot_items_input_mode()

        # If input mode is Identifiers convert from identifiers to uuids first
        if input_mode == 'Identifiers':
            wait_on = model.convert_identifiers_to_uuids(wait_on)

        # Validate the UUIDs
        wait_on = model.validate_wait_on_multi_shot_uuids(wait_on) or list()

        # If input mode is Identifiers convert from uuid to identifiers
        if input_mode == 'Identifiers':
            wait_on = model.convert_uuids_to_identifiers(wait_on)

        self.set_wait_on_multi_shot_items(wait_on)

        scheduler_operations = model.get_scheduler_operations()

        # Then validate WAIT on to existing Plow ids
        wait_on_plow_ids = self.get_wait_on_plow_ids()
        validated_wait_on_plow_ids = scheduler_operations.validate_plow_ids(
            wait_on_plow_ids) or list()
        self.set_wait_on_plow_ids(validated_wait_on_plow_ids)


    def clear_wait_on(self):
        '''
        Clear the current WAIT on multi shot items and to existing Plow ids.
        '''
        self.set_wait_on_multi_shot_items(list())
        self.set_wait_on_plow_ids(list())


    def set_wait_on_multi_shot_items(self, wait_on=None):
        '''
        Set WAIT On multi shot item targets by providing list of UUIDs.

        Args:
            wait_on (list): list of UUIDs
        '''
        if not wait_on:
            wait_on = list()
        wait_on_str = '\n'.join(wait_on)
        self._plain_text_widget_wait_on_multi_shot_items.setPlainText(wait_on_str)


    def get_wait_on_multi_shot_items(self):
        '''
        Get current WAIT On multi shot item targets as list of UUIDs.

        Returns:
            wait_on (list): list of UUIDs or identifiers
        '''
        wait_on_list = self.get_wait_on_multi_shot_items_string().split('\n')
        wait_on_verified = list()
        for wait_on in wait_on_list:
            _wait_on_list = list()
            if ' ' in wait_on:
               _wait_on_list = wait_on.split(' ')
            else:
                _wait_on_list = [wait_on]
            for _wait_on in _wait_on_list:
                if not _wait_on:
                    continue
                if _wait_on in wait_on_verified:
                    continue
                wait_on_verified.append(_wait_on)
        return wait_on_verified


    def get_wait_on_multi_shot_items_uuids(self):
        '''
        Get current WAIT On multi shot item targets as list of UUIDs.

        Returns:
            wait_on_uuids (list): list of UUIDs
        '''
        model = self._tree_view.model()
        wait_on = self.get_wait_on_multi_shot_items()
        input_mode = self.get_wait_on_multi_shot_items_input_mode()
        if input_mode == 'Identifiers':
            wait_on = model.convert_identifiers_to_uuids(wait_on)
        return wait_on


    def get_wait_on_multi_shot_items_string(self):
        '''
        Get current WAIT On multi shot item targets as string (as inputted in widget).

        Returns:
            wait_on_str (str): string of UUIDs
        '''
        return str(self._plain_text_widget_wait_on_multi_shot_items.toPlainText())


    def get_wait_on_multi_shot_items_input_mode(self):
        '''
        Get whether WAIT on to other multi shot items is being defined
        by Identifiers or UUIDS.

        Returns:
            input_mode (str): currently can return either 'Identifiers' or 'UUIDs'
        '''
        return self._wait_on_multi_shot_input_mode


    def set_wait_on_multi_shot_items_input_mode(self, input_mode='Identifiers'):
        '''
        Set whether WAIT on to other multi shot items is being defined
        by Identifiers or UUIDS.

        Args:
            input_mode (str): currently can provide either "Identifiers" or "UUIDs"
        '''
        previous_input_mode = str(self._wait_on_multi_shot_input_mode)
        input_mode = str(input_mode or 'Identifiers')
        srnd_qt.base.utils.combo_box_set_index_from_str(
            self._comboBox_wait_on_multi_shot_input_mode,
            input_mode)
        self._wait_on_multi_shot_input_mode = input_mode

        if input_mode == 'Identifiers':
            msg = 'Define {0}Identifiers{1} or {0}Environments{1} '.format(fs, fe)
            msg += 'string (1 per line) for selected items to depend on. '
            msg += DESCRIPTION_WAIT_ON
        else:
            msg = 'Define {}UUIDs{} string (1 per line) '.format(fs, fe)
            msg += 'for selected items to depend on. '
            msg += DESCRIPTION_WAIT_ON
        self._tool_description_wait_on.set_description(msg)

        if input_mode == 'Identifiers':
            msg = 'Define dependencies by specifying which other '
            msg += 'Multi Shot {}identifiers{} '.format(fs, fe)
            msg += 'must complete first, before the selected items. '
        else:
            msg = 'Define dependencies by specifying which other '
            msg += 'Multi Shot {}UUIDs{} '.format(fs, fe)
            msg += 'must complete first, before the selected items. '
        msg = msg + 'Or define existing {}Plow Job/s{} '.format(fs, fe)
        msg += 'and optionally {}Layer or Task Id/s{} for '.format(fs, fe)
        msg += 'the selected items to depend on.'
        self.get_header_widget().set_description(msg)

        if input_mode != previous_input_mode:
            self.convert_wait_on_multi_shot_items_for_input_mode(
                input_mode,
                previous_input_mode)


    def convert_wait_on_multi_shot_items_for_input_mode(
            self,
            input_mode,
            previous_input_mode):
        '''
        Input mode changed for how Multi Shot item WAIT on is defined, so convert the
        identifiers to UUIDS, or UUIDs to identifiers.

        Args:
            input_mode (str):
            previous_input_mode (str):
        '''
        model = self._tree_view.model()

        msg = 'Converting MSRS WAIT-on items to: "{}"'.format(input_mode)
        self.logMessage.emit(msg, logging.WARNING)

        wait_on = self.get_wait_on_multi_shot_items()
        wait_on_updated = list()
        if previous_input_mode == 'Identifiers' and input_mode == 'UUIDs':
            wait_on_updated = model.convert_identifiers_to_uuids(wait_on)
        elif previous_input_mode == 'UUIDs' and input_mode == 'Identifiers':
            wait_on_updated = model.convert_uuids_to_identifiers(wait_on)

        msg = 'WAIT-on converted from: "{}". '.format(wait_on)
        msg += 'to: "{}". '.format(wait_on_updated)
        self.logMessage.emit(msg, logging.WARNING)

        self.set_wait_on_multi_shot_items(wait_on_updated)


    def set_wait_on_plow_ids(self, wait_on_plow_ids=None):
        '''
        Set WAIT On Plow ids as a list of lists.
        Each list might contain a single Plow job Id as index 0,
        and optionally a Plow Layer or Task id as index 1.
        NOTE: Plow ids are not verified automatically by this method.

        Args:
            wait_on_plow_ids (list): list of lists where index 0 is Plow Job id,
                and index 1 is optionally a Plow Layer or Task id

        Returns:
            wait_on_plow_ids (list): value actually set after removing null values
        '''
        if not wait_on_plow_ids:
            wait_on_plow_ids = list()
        # msg = 'Set WAIT On Plow Ids: "{}"'.format(wait_on_plow_ids)
        # self.logMessage.emit(msg, logging.WARNING)
        # Convert the incoming list of lists to plain text appropiate for widget
        wait_on_plow_ids_lines = list()
        for wait_on in wait_on_plow_ids:
            if not wait_on:
                continue
            if not isinstance(wait_on, (tuple, list)):
                continue
            plow_job_id = str(wait_on[0])
            # Doesn't appear to be valid id (no check needed)
            if len(plow_job_id) < 10:
                continue
            line_str = str(plow_job_id)
            plow_layer_or_task_id = None
            if len(wait_on) > 1:
                plow_layer_or_task_id = str(wait_on[1])
                # Might be a valid Layer or Task id will be validated later
                if len(plow_layer_or_task_id) > 10:
                    line_str += ' ' + plow_layer_or_task_id
            if line_str in wait_on_plow_ids_lines:
                continue
            wait_on_plow_ids_lines.append(line_str)
        wait_on_plow_ids_str = '\n'.join(wait_on_plow_ids_lines)
        self._plain_text_widget_plow_wait_on_ids.setPlainText(wait_on_plow_ids_str)
        return wait_on_plow_ids


    def get_wait_on_plow_ids(self):
        '''
        Get WAIT On Plow ids as a list of lists.
        NOTE: This are gathered from current widget without verifying Plow ids are valid.

        Returns:
            wait_on_plow_ids (list):
        '''
        wait_on_plow_ids_str = str(self._plain_text_widget_plow_wait_on_ids.toPlainText())
        wait_on_plow_ids = wait_on_plow_ids_str.split('\n')
        wait_on_plow_ids_verified = list()
        for wait_on in wait_on_plow_ids:
            if not wait_on:
                continue
            plow_job_id, plow_layer_or_task_id = None, None
            if ' ' in wait_on:
                wait_on_split = wait_on.split(' ')
                if wait_on_split:
                    plow_job_id = wait_on_split[0]
                if len(wait_on_split) > 1:
                    plow_layer_or_task_id = wait_on_split[1]
            else:
                plow_job_id = str(wait_on)
            if not plow_job_id:
                continue
            value_to_add = list()
            value_to_add.append(plow_job_id)
            if plow_layer_or_task_id:
                value_to_add.append(plow_layer_or_task_id)
            if value_to_add:
                wait_on_plow_ids_verified.append(list(value_to_add))
        return wait_on_plow_ids_verified


    def add_wait_on_plow_id(
            self,
            plow_job_id,
            plow_layer_id=None,
            plow_task_id=None):
        '''
        Add WAIT On Plow ids.
        NOTE: Plow ids are not verified automatically by this method.

        Args:
            plow_job_id (str):
            plow_layer_id (str):
            plow_task_id (str):
        '''
        if not plow_job_id:
            return
        wait_on_plow_ids = self.get_wait_on_plow_ids()
        value_to_add = list()
        value_to_add.append(plow_job_id)
        if plow_layer_id:
            value_to_add.append(plow_layer_id)
        elif plow_task_id:
            value_to_add.append(plow_task_id)
        msg = 'Add wait on plow ids: "{}"'.format(str(value_to_add))
        self.logMessage.emit(msg, logging.INFO)
        wait_on_plow_ids.append(value_to_add)
        self.set_wait_on_plow_ids(wait_on_plow_ids)


    def add_wait_on_plow_ids(self, wait_on_plow_ids):
        '''
        Add multiple WAIT On Plow ids.
        NOTE: Plow ids are not verified automatically by this method.

        Args:
            wait_on_plow_ids (list):
        '''
        if not wait_on_plow_ids:
            return
        msg = 'Add multiple wait on plow ids: "{}"'.format(wait_on_plow_ids)
        self.logMessage.emit(msg, logging.INFO)
        current_wait_on_plow_ids = self.get_wait_on_plow_ids()
        current_wait_on_plow_ids.extend(wait_on_plow_ids)
        self.set_wait_on_plow_ids(current_wait_on_plow_ids)


    def get_auto_validate_on_close(self):
        '''
        Get whether to auto validate, thus possibly removing values when dialog is accepted.

        Returns:
            value (bool):
        '''
        return self._auto_validate_on_close


    def set_auto_validate_on_close(self, value):
        '''
        Set whether to auto validate, thus possibly removing values when dialog is accepted.

        Args:
            value (bool):
        '''
        self._auto_validate_on_close = bool(value)


    ##########################################################################


    def accept(self):
        '''
        Reimplemented method.
        '''
        if self.get_auto_validate_on_close():
            self.validate_wait_on()
        base_popup_dialog.BasePopupDialog.accept(self)


    def _update_selection_info(self):
        '''
        Update a preview of selected multi shot tree view items, that WAIT On will
        be applied to, if the window is accepted.
        '''
        if self._tree_view:
            env_count = len(self._tree_view.get_selected_environment_items())
            pass_for_env_count = len(self._tree_view.get_selected_pass_for_env_items())
        else:
            env_count = 0
            pass_for_env_count = 0
        msg = 'Editing dependencies for selection. '
        if env_count:
            msg += '{} environment/s '.format(env_count)
        if pass_for_env_count:
            msg += '{} pass for env items'.format(pass_for_env_count)
        self._label_selection_info.setText(msg)


    def _emit_wait_on_modified(self):
        self.waitOnModified.emit()
        self.accept()


##############################################################################


def main(**kwargs):
    '''
    Start MultiShotSubmitterWindow as standalone app.
    '''
    import sys

    from Qt.QtWidgets import QApplication
    app = QApplication(sys.argv)

    from srnd_qt.ui_framework.styling import palettes
    palettes.style_app_dark(app)

    ui_window = SetDependsDialog(None)
    ui_window.show()

    sys.exit(app.exec_())


if __name__ == '__main__':
    main()