#!/usr/bin/env python


import fileseq
import logging
import os
import time
import traceback

from Qt.QtWidgets import (QApplication, QMainWindow, QWidget, QFrame,
    QTreeView, QPushButton, QCheckBox, QLabel, QSplitter, QProgressBar,
    QVBoxLayout, QHBoxLayout, QSizePolicy)
from Qt.QtGui import (QFont, QColor, QIcon, QPixmap)
from Qt.QtCore import (Qt, QModelIndex, Signal,
    QSize, QSortFilterProxyModel, QEventLoop)

import srnd_qt.base.utils
from srnd_qt.ui_framework.widgets import base_window

from srnd_multi_shot_render_submitter import utils
from srnd_multi_shot_render_submitter.constants import Constants
from srnd_multi_shot_render_submitter.validation import validation_system_base


##############################################################################


constants = Constants()

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)

DIALOG_WH = (1675, 900)
TIME_TAKEN_MSG = 'Time taken to "{}": {}s'

ICONS_DIR = os.path.join(
    os.getenv('SRND_MULTI_SHOT_RENDER_SUBMITTER_ROOT', str()),
    'icons')
ICON_PATH = os.path.join(
    ICONS_DIR,
    'Multi_Shot_Render_Submitter_logo_01_128x128.png')
SRND_QT_ROOT = os.getenv('SRND_QT_ROOT')
SRND_QT_ICONS_DIR = os.path.join(SRND_QT_ROOT, 'res', 'icons')


##############################################################################


class SummaryAndValidationWindow(base_window.BaseWindow):
    '''
    Modal window to show a summary of all Multi Shot Render operations
    about to be submitted, and any validation issues.

    Args:
        model (MultiShotRenderModel): the main MSRS model
        summary_model_object (SummaryModel): optionally pass a subclassed SummaryModel
            object (uninstantiated), to later become composed with this window.
        pass_for_env_items (bool): list of specific PassForEnvItem (or subclasses) to render
        interactive (bool): indicate to the summary window an interactive otherwise
            batch render is being done
        validation_system_object (ValidationSystemBase): optionally pass a subclassed validation system
            object, to instantiate it as a member of this object.
        validation_auto_start (bool):
        auto_scroll (bool):
        threaded (bool): use threading or not if the validation system support it
        build (bool): optionally defer building child widgets and validation system of window
            to after constructor and on demand
        version (str):
        debug_mode (bool):
    '''

    logMessage = Signal(str, int)

    def __init__(
            self,
            model,
            summary_model_object=None,
            pass_for_env_items=None,
            interactive=False,
            validation_system_object=None,
            validation_auto_start=True,
            auto_scroll=True,
            threaded=True,
            build=True,
            version=None,
            debug_mode=False,
            parent=None,
            **kwargs):

        tool_name  = 'Summary & Validation - {}'.format(constants.TOOL_NAME)

        super(SummaryAndValidationWindow, self).__init__(
            app_name=str(tool_name),
            window_size=DIALOG_WH,
            font_size=10,
            include_session_menu=False,
            include_view_menu=False,
            version=version,
            debug_mode=bool(debug_mode),
            parent=parent)

        self.setWindowModality(Qt.ApplicationModal)

        self.HOST_APP = constants.HOST_APP
        self.TOOL_NAME = str(tool_name)

        self._debug_mode = bool(debug_mode)
        self._threaded = bool(threaded)
        self._was_accepted = False

        self._source_model = model
        self._source_view = None
        if parent and hasattr(parent, 'get_view'):
            self._source_view = parent.get_view()

        self._pass_for_env_items = pass_for_env_items
        self._validation_auto_start = validation_auto_start
        self._auto_scroll = bool(auto_scroll)
        self._interactive = bool(interactive)

        self._environments = list()
        self._environment_count = 0
        self._cached_env_qmodelindices = dict()
        self._validation_time = None
        self._is_validating = False
        self._is_interrupted = False
        self._validations_complete = False

        self._render_categories_all = set()
        self._production_frames_warning_count = 0

        # Selected details
        self._enabled_pass_count = 0
        self._queued_pass_count = 0
        self._enabled_frame_count = 0
        self._queued_frame_count = 0

        self._summary_model_object = summary_model_object

        self._panel_details = None
        self._panel_job_options = None

        if build:
            self.build_child_widgets(
                validation_system_object=validation_system_object)


    ##########################################################################


    def _wire_events(self):
        '''
        Main UI events to connect
        '''
        # self._summary_view.activated.connect(self._on_activated)
        selection_model = self._summary_view.selectionModel()
        selection_model.selectionChanged.connect(self._summary_view_selection_changed)
        search_widget = self.get_search_widget()
        search_widget.searchRequest.connect(
            lambda x: self.filter_by_string(x))


    def _add_key_shortcuts(self):
        '''
        Build shortcut keys.
        '''
        from Qt.QtWidgets import QShortcut

        shortcut = QShortcut(self)
        # shortcut.setKey('CTRL+D')
        shortcut.activated.connect(self._summary_view.clearSelection)


    # def _on_activated(self, qmodelindex):
    #     if not qmodelindex.isValid():
    #         return
    #     if qmodelindex.column() != self._summary_model.COLUMN_OF_SUBMISSION_NOTE:
    #         return
    #     widget = self._summary_view.indexWidget(qmodelindex)
    #     if widget:
    #         widget.setFocus()


    ##########################################################################


    def show(self):
        '''
        Reimplemented show method to perform some last UI polish.
        '''
        # Hide summary widgets visibility
        self._summary_widgets_visible = dict()

        # Get the MSRS main window QSettings
        msrs_main_window = self.parent()
        is_main_window = isinstance(msrs_main_window, QMainWindow)
        qsettings = None
        if is_main_window:
            qsettings = msrs_main_window.saveState()

        # Move the panels from main MSRS window to this window
        self._prepare_panels()

        # Force particular column states
        header = self._summary_view.header()
        if header:
            column_widths = self._summary_view.get_column_widths() or dict()

            # Force render category column state
            if self._show_render_categories:
                visible = bool(self._render_categories_all)
                header.setSectionHidden(
                    self._summary_model.COLUMN_OF_RENDER_CATEGORY,
                    not visible)
                width = column_widths.get(self._summary_model.COLUMN_OF_RENDER_CATEGORY)
                if visible and width:
                    self._summary_view.setColumnWidth(
                        self._summary_model.COLUMN_OF_RENDER_CATEGORY,
                        width)
            else:
                header.setSectionHidden(
                    self._summary_model.COLUMN_OF_RENDER_CATEGORY,
                    True)

            # Force production frames column state
            visible = bool(self._production_frames_warning_count)
            header.setSectionHidden(
                self._summary_model.COLUMN_OF_PRODUCTION_FRAMES,
                not visible)
            width = column_widths.get(self._summary_model.COLUMN_OF_PRODUCTION_FRAMES)
            if visible and width:
                self._summary_view.setColumnWidth(
                    self._summary_model.COLUMN_OF_PRODUCTION_FRAMES,
                    width)                

        self.center()
        
        QMainWindow.show(self)

        self._summary_view_selection_changed()

        # Force the QMainWindow to be blocking like a QDialog
        self._event_loop = QEventLoop()
        self._event_loop.exec_()

        # Now revert the MSRS main window settings
        if is_main_window and qsettings:
            msrs_main_window.restoreState(qsettings)        


    def _prepare_panels(self):
        '''
        Take the details and job options panels from main MSRS window and 
        temporarily move them to this window.
        '''
        parent = self.parent()
        if not parent:
            return

        self._panel_details = None
        self._panel_job_options = None

        if hasattr(parent, '_panel_details'):
            self._panel_details = parent._panel_details
            self._panel_details.blockSignals(True)
            self._panel_details._was_visible = self._panel_details.isVisible()
            parent.removeDockWidget(self._panel_details)
            self.addDockWidget(Qt.RightDockWidgetArea, self._panel_details)
            show = False
            if hasattr(self._panel_details, '_visible_in_summary'):
                show = self._panel_details._visible_in_summary
            self._panel_details.setVisible(show)
            self._checkBox_show_details.setChecked(show)
            self._checkBox_show_details.toggled.connect(
                self._panel_details.setVisible)
            self._panel_details.visibilityChanged.connect(
                self._checkBox_show_details.setChecked)
            layout = self._panel_details.get_content_widget_layout()
            details_widget = layout.itemAt(0).widget()
            self._panel_details._badges_was_exposed = details_widget.get_expose_override_badges()
            details_widget.set_expose_override_badges(False)
            self._panel_details.blockSignals(False)

        if hasattr(parent, '_panel_job_options'):
            self._panel_job_options = parent._panel_job_options
            self._panel_job_options.blockSignals(True)
            layout = self._panel_job_options.get_content_widget_layout()
            job_options_widget = layout.itemAt(0).widget()
            self._panel_job_options._was_visible = self._panel_job_options.isVisible()
            parent.removeDockWidget(self._panel_job_options)
            self.addDockWidget(Qt.RightDockWidgetArea, self._panel_job_options)
            show = False
            if hasattr(self._panel_job_options, '_visible_in_summary'):
                show = self._panel_job_options._visible_in_summary
            self._panel_job_options.setVisible(show)
            self._checkBox_show_job_options.setChecked(show)
            self._checkBox_show_job_options.toggled.connect(
                self._panel_job_options.setVisible)
            self._panel_job_options.visibilityChanged.connect(
                self._checkBox_show_job_options.setChecked)            
            self._panel_job_options.blockSignals(False)
            widget = job_options_widget.get_global_job_identifier_widget()
            widget.textChanged.connect(self._update_job_identifier_column)


    def closeEvent(self, event):
        '''
        Reimplemented to revert panels back to main MSRS window.

        Args:
            event (QtCore.QEvent):
        '''
        parent = self.parent()

        # Move panels back to main MSRS window
        if parent:
            if self._panel_details:
                self._panel_details.blockSignals(True)
                self._panel_details._visible_in_summary = self._panel_details.isVisible()
                self.removeDockWidget(self._panel_details)
                parent.addDockWidget(Qt.RightDockWidgetArea, self._panel_details)
                if hasattr(self._panel_details, '_was_visible'):
                    self._panel_details.setVisible(self._panel_details._was_visible)
                layout = self._panel_details.get_content_widget_layout()
                details_widget = layout.itemAt(0).widget()
                if details_widget and hasattr(self._panel_details, '_badges_was_exposed'):
                    details_widget.set_expose_override_badges(self._panel_details._badges_was_exposed)
                self._panel_details.blockSignals(False)
            if self._panel_job_options:
                self._panel_job_options.blockSignals(True)
                self._panel_job_options._visible_in_summary = self._panel_job_options.isVisible()
                self.removeDockWidget(self._panel_job_options)
                parent.addDockWidget(Qt.RightDockWidgetArea, self._panel_job_options)
                if hasattr(self._panel_job_options, '_was_visible'):
                    self._panel_job_options.setVisible(self._panel_job_options._was_visible)
                self._panel_job_options.blockSignals(False)
                # Restore summary widgets visibility
                layout = self._panel_job_options.get_content_widget_layout()
                job_options_widget = layout.itemAt(0).widget()                
                for widget in self._summary_widgets_visible:
                    visible = self._summary_widgets_visible.get(widget)
                    if isinstance(visible, bool):
                        widget.setVisible(visible)
                # job_options_widget.get_session_auto_save_group_box().setVisible(False)

        self._panel_details = None
        self._panel_job_options = None

        self._event_loop.quit()

        QMainWindow.closeEvent(self, event)


    def keyPressEvent(self, event):
        '''
        Reimplemented to intercept the Escape button press.

        Args:
            event (QtCore.QEvent):
        '''
        if event.key() == Qt.Key_Escape:
            msg = 'Escape pressed. Stopping validations as soon as possible.'
            self.logMessage.emit(msg, logging.CRITICAL)
            self.request_interrupt()
            event.accept()
            self.validations_complete()
            return
        base_window.BaseWindow.keyPressEvent(self, event)


    ##########################################################################


    def get_validation_time(self):
        '''
        Get the length of time validation took (if enabled).

        Returns:
            validation_time (int): in seconds
        '''
        return self._validation_time


    def get_was_accepted(self):
        '''
        After this window is accepted by clicking start render or closed,
        get whether the window was accepted.

        Returns:
            was_accepted (bool):
        '''
        return self._was_accepted


    def request_interrupt(self):
        '''
        Request an interrupt during validation.
        '''
        if not constants.EXPOSE_VALIDATION:
            return
        self._is_interrupted = True
        self._is_validating = False
        if self._validation_adapter:
            self._validation_adapter.request_interrupt()
        self.validations_complete()


    def is_interrupted(self):
        '''
        Get whether interrupt has been / was called during validation or not.

        Returns:
            is_interrupted (bool):
        '''
        if constants.EXPOSE_VALIDATION and self._validation_adapter:
            return self._is_interrupted or self._validation_adapter.is_interrupted()
        else:
            return False


    def get_environment_items_proxy_indices(self):
        '''
        Get list of proxy model EnvironmentItem indices.
        Note: EnvironmentItem can only currently be at root of data model or under a group.
        TODO: Make this recursive method anyway, in anticipation of groups in
        groups being required later.

        Returns:
            environment_items_indices (list):
        '''
        model = self._summary_view.model()
        parent_index = QModelIndex()
        environment_items_indices = list()
        for row in range(model.rowCount(parent_index)):
            env_qmodelindex = model.index(row, 0, parent_index)
            if not env_qmodelindex.isValid():
                continue
            # Avoid getting the internal pointer from proxy model
            # https://bugreports.qt.io/browse/QTBUG-17504
            env_qmodelindex_source = model.mapToSource(env_qmodelindex)
            if not env_qmodelindex_source.isValid():
                continue
            item = env_qmodelindex_source.internalPointer()
            if item.is_environment_item():
                environment_items_indices.append(env_qmodelindex)
                continue
            elif item.is_group_item():
                row_count_depth2 = model.rowCount(env_qmodelindex)
                for row_depth2 in range(row_count_depth2):
                    qmodelindex_depth2 = model.index(row_depth2, 0, env_qmodelindex)
                    if not qmodelindex_depth2.isValid():
                        continue
                    # Avoid getting the internal pointer from proxy model
                    # https://bugreports.qt.io/browse/QTBUG-17504
                    env_qmodelindex_source_depth2 = model.mapToSource(qmodelindex_depth2)
                    if not env_qmodelindex_source_depth2.isValid():
                        continue
                    item_depth2 = env_qmodelindex_source_depth2.internalPointer()
                    if item_depth2.is_environment_item():
                        environment_items_indices.append(qmodelindex_depth2)

        return environment_items_indices


    ##########################################################################


    def get_summary_view(self):
        '''
        Get the actual summary view widget instantiated into this window.

        Returns:
            summary_view (SummaryView):
        '''
        return self._summary_view


    def get_search_widget(self):
        '''
        Get the search filter widget for this summary and validation window.

        Returns:
            line_edit_filter (SearchLineEdit):
        '''
        return self._lineEdit_filter


    def get_summary_view_object(self):
        '''
        Get the Summary TreeView widget which will visualize
        the supplied data model.
        Reimplement this if particular summary view is required for different host app.

        Returns:
            summary_view (SummaryView): or subclass
        '''
        from srnd_multi_shot_render_submitter.views import summary_view
        return summary_view.SummaryView


    def get_summary_model_object(self):
        '''
        Get the Summary model which extends the existing main model.
        Reimplement this if particular model is required for different host app.

        Returns:
            summary_model (SummaryModel): or subclass
        '''
        from srnd_multi_shot_render_submitter.models import summary_model
        return summary_model.SummaryModel


    def get_summary_delegates_object(self):
        '''
        Get the Summary delegates.
        Reimplement this if particular delegates is required for different host app.

        Returns:
            summary_delegates (SummaryDelegates): or subclass
        '''
        from srnd_multi_shot_render_submitter.delegates import summary_delegates
        return summary_delegates.SummaryDelegates


    ##########################################################################
    # Build UI


    def build_child_widgets(self, validation_system_object=None):
        '''
        Build all the child widgets of the SummaryAndValidation window.
        Optionally including the validation system and associated widget.

        Args:
            validation_system_object (ValidationSystemBase): optionally pass a subclassed validation system
                object, to instantiate it as a member of this object.
        '''
        layout = self.get_content_widget_layout()
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)

        ######################################################################

        self._splitter_main = QSplitter(Qt.Vertical)
        self._splitter_main.setLineWidth(10)
        self._splitter_main.setMidLineWidth(10)
        self._splitter_main.setHandleWidth(10)
        self._splitter_main.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding)
        layout.addWidget(self._splitter_main)

        self._summary_widget = self._build_summary_widget()
        self._splitter_main.addWidget(self._summary_widget)

        # Only build validation if host app config file requires it
        self._validation_adapter = None
        if constants.EXPOSE_VALIDATION:
            try:
                self._build_validation_system(validation_system_object)
            except Exception as error:
                msg = 'Failed to build validation system or widget. '
                msg += 'Full exception: "{}".'.format(traceback.format_exc())
                self.logMessage.emit(msg, logging.WARNING)

        self._summary_view.reset_column_sizes()
        self._prepare_view()

        self._wire_events()
        self._add_key_shortcuts()

        msg, pass_count, shot_count, frame_count = self._source_model.formulate_label_only_render_estimate(
            pass_for_env_items=self._pass_for_env_items,
            pass_count_all_queued=self._renderable_pass_count,
            shot_count_with_queued=len(self._environments))
        self._label_overview.setText(msg)

        # Do any final validation setup (if validation is exposed)
        self._pushButton_validation_state.setVisible(
            constants.EXPOSE_VALIDATION)
        if constants.EXPOSE_VALIDATION and self._validation_adapter:
            # Request call validation to be run now
            if self._validation_auto_start:
                self.run_all_validations()

            has_validation_system = self._validation_adapter.has_validation_system()
            if not has_validation_system:
                tool_tip = self._pushButton_validation_state.toolTip()
                msg = 'Validation system not available! '
                self._pushButton_validation_state.setToolTip(msg + '<br>' + tool_tip)
                self._pushButton_validation_state.setDisabled(True)

        # The submission notes delegates QLineEdit/s will be in focus with some older
        # Qt versions, so clear it now.
        self._summary_view.setFocus()


    def _build_summary_widget(self):
        '''
        Build the Summary model, view and delegates.

        Returns:
            summary_widget (QWidget):
        '''
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        ######################################################################

        horizontal_layout = QHBoxLayout()
        horizontal_layout.setContentsMargins(6, 6, 6, 6)
        horizontal_layout.setSpacing(8)
        layout.addLayout(horizontal_layout)

        label_emblem_icon = QLabel()
        pixmap = QPixmap(ICON_PATH)
        pixmap = pixmap.scaledToHeight(35, Qt.SmoothTransformation)
        label_emblem_icon.setPixmap(pixmap)
        horizontal_layout.addWidget(label_emblem_icon)

        horizontal_layout.addStretch(100)

        from srnd_qt.ui_framework import search_line_edit
        self._lineEdit_filter = search_line_edit.SearchLineEdit(
            include_options_menu=True)
        msg = 'Temporarily filter this summary view. '
        msg += '<br>Note: Search tokens are not supported.'
        self._lineEdit_filter.setToolTip(msg)
        self._lineEdit_filter.setFixedHeight(34)
        self._lineEdit_filter.setMinimumWidth(250)
        self._lineEdit_filter.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Fixed)
        horizontal_layout.addWidget(self._lineEdit_filter)

        ######################################################################

        summary_widget = QWidget(parent=self)
        summary_widget.setLayout(layout)
        summary_widget.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding)

        ######################################################################

        self._show_render_categories = self._source_model.get_cook_more_summary_details()

        _summary_view_object = self.get_summary_view_object()
        self._summary_view = _summary_view_object(
            show_render_categories=self._show_render_categories,
            parent=self)
        self._summary_view.updateMainViewRequest.connect(
            self._update_source_model_from_summary_model_index)
        layout.addWidget(self._summary_view)
        self._summary_view.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding)

        self._summary_view.reset_column_sizes()

        # Setup SummaryModel which acts on the data within the main MultiShotRenderModel
        _summary_model_object = self._summary_model_object or self.get_summary_model_object()
        self._summary_model = _summary_model_object(
            self._source_model,
            self._source_view,
            parent=self)

        # Proxy model to filter SummaryModel to renderables
        self._proxy_model = MultiShotRenderableProxyModel(
            pass_for_env_items=self._pass_for_env_items,
            parent=self)
        self._proxy_model.setSourceModel(self._summary_model)
        self._summary_view.setModel(self._proxy_model)

        # Setup delegates
        _summary_delegates_object = self.get_summary_delegates_object()
        self._summary_delegates = _summary_delegates_object(
            debug_mode=self._debug_mode,
            summary_model=self._summary_model,
            parent=self)
        self._summary_view.setItemDelegate(self._summary_delegates)

        self._summary_view.logMessage.connect(self.emit_message)
        self._summary_model.logMessage.connect(self.emit_message)
        self._summary_delegates.logMessage.connect(self.emit_message)
        
        # These columns always start hidden
        self._summary_view.setColumnHidden(
            self._summary_model.COLUMN_OF_WAIT_ON_IDENTIFIERS, True)
        self._summary_view.setColumnHidden(
            self._summary_model.COLUMN_OF_WAIT_ON_PLOW_IDS, True)

        ######################################################################

        horizontal_layout = QHBoxLayout()
        horizontal_layout.setContentsMargins(4, 4, 4, 4)
        horizontal_layout.setSpacing(8)
        layout.addLayout(horizontal_layout)        

        horizontal_layout.addWidget(QLabel('Show'))
        self._checkBox_show_job_options = QCheckBox('Job Options')
        horizontal_layout.addWidget(self._checkBox_show_job_options)

        self._checkBox_show_details = QCheckBox('Details')
        horizontal_layout.addWidget(self._checkBox_show_details)

        self._checkBox_show_validation = QCheckBox('Validation')
        self._checkBox_show_validation.setChecked(False)
        horizontal_layout.addWidget(self._checkBox_show_validation)
        self._checkBox_show_validation.setVisible(constants.EXPOSE_VALIDATION)

        horizontal_layout.addSpacing(20)
        line = srnd_qt.base.utils.get_line(
            vertical_line=True, 
            height=25)
        horizontal_layout.addWidget(line)
        horizontal_layout.addSpacing(20)

        ######################################################################

        font_italic = QFont()
        font_italic.setFamily(constants.FONT_FAMILY)
        font_italic.setItalic(True)
        self._label_overview = QLabel()
        self._label_overview.setFont(font_italic)
        horizontal_layout.addWidget(self._label_overview)

        horizontal_layout.addStretch(100)

        ######################################################################

        self._pushButton_okay = QPushButton('Launch')
        self._pushButton_okay.setStyleSheet('QPushButton {padding: 6px;}')
        self._pushButton_okay.setAutoDefault(False)
        self._pushButton_okay.setFixedHeight(32)
        self._pushButton_okay.setMinimumWidth(75)
        self._pushButton_okay.clicked.connect(self._accept_window)
        self._pushButton_okay.setIcon(QIcon(ICON_PATH))
        self._pushButton_okay.setIconSize(QSize(22, 22))
        horizontal_layout.addWidget(self._pushButton_okay)

        self._pushButton_validation_state = QPushButton('Start validations')
        self._pushButton_validation_state.setStyleSheet('QPushButton {padding: 6px;}')
        icon = QIcon(os.path.join(constants.ICONS_DIR, 'warning.png'))
        self._pushButton_validation_state.setIcon(icon)
        self._pushButton_validation_state.setAutoDefault(False)
        self._pushButton_validation_state.setFixedHeight(26)
        self._pushButton_validation_state.setMinimumWidth(75)
        self._pushButton_validation_state.clicked.connect(self.toggle_validation_state)
        horizontal_layout.addWidget(self._pushButton_validation_state)

        self.add_button_require_validation(self._pushButton_okay)

        self._pushButton_cancel = QPushButton('Cancel')
        self._pushButton_cancel.setAutoDefault(False)
        self._pushButton_cancel.setStyleSheet('QPushButton {padding: 6px;}')
        self._pushButton_cancel.setFixedHeight(26)
        self._pushButton_cancel.setMinimumWidth(50)
        self._pushButton_cancel.clicked.connect(self._reject_window)
        horizontal_layout.addWidget(self._pushButton_cancel)

        for button in [
                self._pushButton_okay,
                self._pushButton_validation_state,
                self._pushButton_cancel]:
            button.clearFocus()
        self._pushButton_validation_state.setFocus()

        ######################################################################

        self._checkBox_show_validation.toggled.connect(self._set_splitter_sizes)
        self._splitter_main.splitterMoved.connect(self._splitter_moved)

        # Add progress bar to show later
        self._progress_bar =  self._build_progress_bar()
        layout.addWidget(self._progress_bar)
        self._progress_bar.setVisible(False)

        return summary_widget


    def _build_validation_widget_container(self):
        '''
        Build the wrapped widget to contain the validation widget

        Returns:
            validation_widget_wrapped (QWidget):
        '''
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        STYLESHEET = 'QFrame#ValidationQFrame {background-color: rgb(70, 70, 70);}'

        validation_widget_wrapped = QFrame(parent=self)
        validation_widget_wrapped.setObjectName('ValidationQFrame')
        validation_widget_wrapped.setStyleSheet(STYLESHEET)
        validation_widget_wrapped.setLayout(layout)
        validation_widget_wrapped.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding)

        horizontal_layout = QHBoxLayout()
        horizontal_layout.setContentsMargins(6, 6, 6, 6)
        horizontal_layout.setSpacing(0)
        layout.addLayout(horizontal_layout)

        font_italic = QFont()
        font_italic.setFamily(constants.FONT_FAMILY)
        font_italic.setBold(True)
        font_italic.setPointSize(10)
        label = QLabel('Validation details')
        label.setFont(font_italic)
        horizontal_layout.addWidget(label)

        horizontal_layout.addSpacing(30)

        font_italic = QFont()
        font_italic.setFamily(constants.FONT_FAMILY)
        font_italic.setItalic(True)
        font_italic.setPointSize(9)
        self._label_validation_title = QLabel()
        self._label_validation_title.setFont(font_italic)
        horizontal_layout.addWidget(self._label_validation_title)
        self._label_validation_title.setVisible(False)

        horizontal_layout.addStretch(100)

        return validation_widget_wrapped


    ##########################################################################
    # UI setup and callbacks


    def _prepare_view(self):
        '''
        Open any required initial editors and any other view setup.
        '''
        self._summary_view.expandAll()

        self._environments = list()
        self._renderable_pass_count = 0
        self._cached_env_qmodelindices = dict()

        model = self._summary_view.model()

        self._render_categories_all = set()
        self._production_frames_warning_count = 0
        if not self._source_model.get_auto_refresh_from_shotgun():        
            self._production_frames_warning_count += 1
            
        for env_qmodelindex in self.get_environment_items_proxy_indices():
            if not env_qmodelindex.isValid():
                continue

            # Avoid getting the internal pointer from proxy model
            # https://bugreports.qt.io/browse/QTBUG-17504
            env_qmodelindex_source = model.mapToSource(env_qmodelindex)
            if not env_qmodelindex_source.isValid():
                continue
            env_item = env_qmodelindex_source.internalPointer()
            if not env_item.is_environment_item():
                continue

            env_item.set_validation_critical_counter(0)
            env_item.set_validation_warning_counter(0)

            if env_item.get_production_data_changed():
                self._production_frames_warning_count += 1

            pass_renderable_count = 0
            pass_row_count = model.rowCount(env_qmodelindex)
            for pass_row in range(pass_row_count):
                pass_qmodelindex = model.index(pass_row, 0, env_qmodelindex)
                if not pass_qmodelindex.isValid():
                    continue
                # Avoid getting the internal pointer from proxy model
                pass_qmodelindex_source = model.mapToSource(pass_qmodelindex)
                if not pass_qmodelindex_source.isValid():
                    continue
                pass_env_item = pass_qmodelindex_source.internalPointer()
                active = pass_env_item.get_active()
                self._renderable_pass_count += active
                pass_renderable_count += active
                if active:
                    for column in [
                            self._summary_model.COLUMN_OF_POST_TASK,
                            self._summary_model.COLUMN_OF_SUBMISSION_NOTE]:
                        post_task_qmodelindex = pass_qmodelindex.sibling(pass_row, column)
                        if post_task_qmodelindex.isValid():
                            self._summary_view.openPersistentEditor(post_task_qmodelindex)
                if self._show_render_categories:
                    render_item = pass_env_item.get_source_render_item()
                    if render_item and render_item.get_render_category():
                        self._render_categories_all.add(render_item.get_render_category())

            if bool(pass_renderable_count):
                oz_area = str(env_item.get_oz_area())
                self._environments.append(oz_area)
                self._environment_count += 1
                validation_qmodelindex = env_qmodelindex.sibling(
                    env_qmodelindex.row(),
                    self._summary_model.COLUMN_OF_VALIDATION)
                self._cached_env_qmodelindices[oz_area] = {
                    'validation_qmodelindex':
                    validation_qmodelindex}
                for column in [
                        self._summary_model.COLUMN_OF_VALIDATION,
                        self._summary_model.COLUMN_OF_POST_TASK,
                        self._summary_model.COLUMN_OF_KOBA_SHOTSUB,
                        self._summary_model.COLUMN_OF_SUBMISSION_NOTE]:
                    summary_qmodelindex = env_qmodelindex.sibling(
                        env_qmodelindex.row(),
                        column)
                    if summary_qmodelindex.isValid():
                        self._summary_view.openPersistentEditor(summary_qmodelindex)

        QApplication.processEvents()


    def filter_by_string(self, filter_str):
        '''
        Basic filtering of the summary tree view by searching for matches.
        TODO: Intoduce tokens here to help refine search.
        Note: This is a temporary view search filter only, so not filtering by proxy model here.
        Note: Indices should not be filtered out of the model by this search.
        Note: The proxy model of this summamy window has already been used to filter
        out unselected items from main multi shot model and view.

        Args:
            filter_str (QtCore.QString): filter by search string
        '''
        model = self._summary_view.model()
        if not model:
            return

        filter_str = str(filter_str).lower()
        # msg = 'Searching Summary View For: "{}"'.format(filter_str)
        # self.logMessage.emit(msg, logging.DEBUG)

        for env_qmodelindex in self.get_environment_items_proxy_indices():
            if not env_qmodelindex.isValid():
                continue
            # Avoid accessing internalPointer on proxy model
            env_qmodelindex_source = model.mapToSource(env_qmodelindex)
            if not env_qmodelindex_source.isValid():
                continue
            env_item = env_qmodelindex_source.internalPointer()
            found_env_hit = filter_str in env_item.get_oz_area() or \
                filter_str in (env_item.get_note_override() or str())
            found_pass_hit = False
            pass_row_count = model.rowCount(env_qmodelindex)
            for pass_row in range(pass_row_count):
                pass_qmodelindex = model.index(pass_row, 0, env_qmodelindex)
                if not pass_qmodelindex.isValid():
                    continue
                # Avoid accessing internalPointer on proxy model
                pass_qmodelindex_source = model.mapToSource(pass_qmodelindex)
                if not pass_qmodelindex_source.isValid():
                    continue
                pass_for_env_item = pass_qmodelindex_source.internalPointer()
                _found_hit = pass_for_env_item.search_for_string(filter_str)
                if _found_hit:
                    found_pass_hit = True
                # Hide the pass if not found pass hit and not have env hit
                self._summary_view.setRowHidden(
                    pass_qmodelindex.row(),
                    env_qmodelindex,
                    not _found_hit and not found_env_hit)
            # Hide the environment if not match, or no child pass match
            row = env_qmodelindex.row()
            self._summary_view.setRowHidden(
                row,
                env_qmodelindex.parent(),
                not any([found_env_hit, found_pass_hit]))


    def _summary_view_selection_changed(self):
        '''
        Selection just changed in summary view so perform callbacks.
        '''
        selection = self._summary_view.selectedIndexes()
        model = self._summary_view.model()

        shots_selected = set()
        shots_passes_selected = set()
        environments = set()
        for qmodelindex in self._summary_view.selectedIndexes():
            if not qmodelindex.isValid():
                continue
            qmodelindex_source = model.mapToSource(qmodelindex)
            if not qmodelindex_source.isValid():
                continue                
            item = qmodelindex_source.internalPointer()
            if item:
                if item.is_environment_item():
                    shots_selected.add(item)
                    environments.add(item.get_oz_area())                    
                elif item.is_pass_for_env_item():
                    shots_passes_selected.add(item)

        if self._panel_details:
            layout = self._panel_details.get_content_widget_layout()
            details_widget = layout.itemAt(0).widget()    

            # Populate details widget        
            details_widget.populate(
                shots_selected=shots_selected or None,
                shots_passes_selected=shots_passes_selected or None,
                only_when_visible=False)   

            # Collect counts from selection
            results = self._source_model.get_counts_for_shot_and_pass_selection(
                shots_selected,
                shots_passes_selected)
            self._enabled_pass_count = results.get('enabled_pass_count', 0)
            self._queued_pass_count = results.get('queued_pass_count', 0)
            self._enabled_frame_count = results.get('enabled_frame_count', 0)
            self._queued_frame_count = results.get('queued_frame_count', 0)

            # Update selection summary
            widget = details_widget.get_selection_summary_widget()
            widget.update_summary_info(  
                self._enabled_pass_count,
                self._enabled_frame_count,
                self._queued_pass_count,
                self._queued_frame_count)                       

        environments = sorted(list(environments))
        if not environments:
            msg = 'No environments selected so showing all validations.'
            self.logMessage.emit(msg, logging.DEBUG)
        else:
            msg = 'Updating validation view to show '
            msg += 'environments: {}.'.format(environments)
            self.logMessage.emit(msg, logging.DEBUG)

        if self._validation_adapter:
            self._validation_adapter.filter_view_to_environments(environments)


    def _update_source_model_from_summary_model_index(self, qmodelindex_source):
        '''
        Since the summary model has a different structure than the main MSRS
        model and even though they share the same data objects, the QModelIndices are differnt.
        So find the QModelIndex in main MSRS model given a UUID string.

        Args:
            qmodelindex_source (QModelIndex):
        '''
        item = qmodelindex_source.internalPointer()
        uuid = item.get_identity_id()
        qmodelindex = self._source_model.get_index_by_uuid(uuid)
        if qmodelindex:
            self._source_model.dataChanged.emit(qmodelindex, qmodelindex)
    

    def _update_job_identifier_column(self):
        '''
        Call data changed for every pass of job identifier column.
        '''
        model = self._summary_view.model()
        for env_qmodelindex in self.get_environment_items_proxy_indices():
            if not env_qmodelindex.isValid():
                continue
            model.dataChanged.emit(env_qmodelindex, env_qmodelindex)
        self._summary_view.update()


    def _splitter_moved(self, pos, index):
        '''
        Splitter was moved, do various callbacks.
        '''
        if index == 1:
            self._checkBox_show_validation.setChecked(
                pos < self._splitter_main.height() - 10)


    def _set_splitter_sizes(self, show):
        '''
        Set splitter sizes to appropiate sizes for validation.

        Args:
            show (bool):
        '''
        if not show:
            self._splitter_main.setSizes([self.height(), 0])
        else:
            self._splitter_main.setSizes(
                [int(self.height() * 0.6), int(self.height() * 0.4)])


    ##########################################################################
    # Validation


    def _build_validation_system(self, validation_system_object):
        '''
        Instantiate the provided validation system and internal widget to put in container.
        Optionally subclass this method if required to control
        how ValidationSystemBase subclass is instantiated.

        Args:
            validation_system_object (ValidationSystemBase):
        '''
        self._validation_widget_container = self._build_validation_widget_container()
        layout_validation = self._validation_widget_container.layout()

        # Instantiate the provided ValidationSystemBase subclass
        try:
            self._validation_adapter = validation_system_object(
                threaded=self._threaded,
                parent=self)
            self._validation_adapter.logMessage.connect(self.emit_message)
            # Build the widgets of validation system (if any)
            self._validation_adapter.build_validation_objects()
            self._validation_adapter.envValidationComplete.connect(
                self.validation_complete_for_env)
        except Exception:
            self._validation_adapter = None
            msg = 'Failed to build validation objects. '
            msg += 'Full exception: "{}".'.format(traceback.format_exc())
            self.logMessage.emit(msg, logging.WARNING)

        # Add validation system widget (if any) to validation widget container
        if self._validation_adapter:
            validation_widget = self._validation_adapter.get_validation_widget()
            if validation_widget:
                layout_validation.addWidget(validation_widget)

        self._splitter_main.addWidget(self._validation_widget_container)

        self._splitter_main.setSizes([self.height(), 0])


    def toggle_validation_state(self):
        '''
        Toggle the validation system state depending on other states.
        '''
        if self._is_validating:
            self.request_interrupt()
        elif not self._validations_complete and self._environments:
            self.run_all_validations()
        if not self._checkBox_show_validation.isChecked():
            self._checkBox_show_validation.setChecked(True)


    def run_all_validations(self):
        '''
        Setup and run all required validations.
        '''
        msg = 'No validation system available!'
        if not self._validation_adapter:
            self.logMessage.emit(msg, logging.WARNING)
            return
        has_validation_system = self._validation_adapter.has_validation_system()
        if not has_validation_system:
            self.logMessage.emit(msg, logging.WARNING)
            return

        if not self._environments:
            msg = 'No environment to run validations for!'
            self.logMessage.emit(msg, logging.WARNING)
            return

        self._is_validating = True

        # Reset interupt and clear the existing queue
        self._validation_adapter.reset()

        self._pushButton_validation_state.setDisabled(False)
        msg = 'Validations processing...(Press Esc)'
        self._pushButton_validation_state.setText(msg)
        icon = QIcon(os.path.join(constants.ICONS_DIR_QT, 'sync.png'))
        self._pushButton_validation_state.setIcon(icon)

        count = len(self._environments)
        msg = 'Running validations on {} environments - %p%'.format(count)
        self.update_progress_bar(0, progress_format=msg)

        self.show_progress_bar()

        QApplication.processEvents()

        # self._label_validation_title.setVisible(True)
        # self._label_validation_progress_movie.setVisible(True)
        # self._movie_validate_in_progress.start()

        model = self._summary_view.model()

        self._time_all_validations_start = time.time()
        for env_qmodelindex in self.get_environment_items_proxy_indices():
            if not env_qmodelindex.isValid():
                continue

            # Avoid accessing internalPointer on proxy model
            env_qmodelindex_source = model.mapToSource(env_qmodelindex)
            if not env_qmodelindex_source.isValid():
                continue
            env_item = env_qmodelindex_source.internalPointer()

            # Not in list of environments to process
            oz_area = env_item.get_oz_area()
            if oz_area not in self._environments:
                continue

            if self.is_interrupted():
                msg = 'Interrupt request, stopping progress.'
                self.logMessage.emit(msg, logging.WARNING)
                break

            # Collect valid render nodes
            render_nodes = env_item.get_renderable_nodes_in_host_app() or list()

            if not render_nodes:
                msg = 'No render nodes available to '
                msg += 'validate for environment: "{}"'.format(oz_area)
                self.logMessage.emit(msg, logging.WARNING)

            time_validation_start = time.time()
            self._cached_env_qmodelindices[oz_area]['start_time'] = time_validation_start

            # Queue these items for setup
            try:
                self._validation_adapter.setup(
                    environments=[oz_area],
                    nodes=render_nodes)
            except Exception:
                msg = 'Failed to setup validation system. '
                msg += 'Full exception: "{}".'.format(traceback.format_exc())
                self.logMessage.emit(msg, logging.WARNING)

        self._validation_adapter.run_checks()


    def validations_complete(self):
        '''
        Perform UI updates after all validations are complete.
        '''
        # Prevent updating UI again (when already completed)
        if self._validations_complete:
            return

        self._is_validating = False

        self.show_progress_bar(loading=False)

        all_enironments_validated = not self._environments
        self._pushButton_validation_state.setDisabled(True)

        if all_enironments_validated:
            self._validations_complete = True

            self._validation_time = int(time.time() - self._time_all_validations_start)
            msg = 'Time to run all environments validations. '
            self.logMessage.emit(
                TIME_TAKEN_MSG.format(msg, self._validation_time),
                logging.DEBUG)

            label_str = 'Validations complete'
            icon = QIcon(os.path.join(constants.ICONS_DIR, 'okay.png'))

            # Scroll back to start of SummaryView
            if self._auto_scroll:
                vertical_scroll_bar = self._summary_view.verticalScrollBar()
                vertical_scroll_bar.setSliderPosition(0)
        else:
            # label_str = 'Run Remaining Validations'
            label_str = 'Validations interrupted'
            icon = QIcon(os.path.join(constants.ICONS_DIR, 'warning.png'))

        self._pushButton_validation_state.setText(label_str)
        self._pushButton_validation_state.setIcon(icon)
        QApplication.processEvents()


    def validation_complete_for_env(
            self,
            summary_dict,
            append_only=False,
            oz_area=str()):
        '''
        All validations for a particular environment / graph state was just completed.

        Args:
            summary_dict (dict):
            append_only (bool):
            oz_area (str):

        Returns:
            success (bool):
        '''
        oz_area = str(oz_area)

        ui_update_start_time = time.time()

        if oz_area in self._environments:
            self._environments.remove(oz_area)

        count = len(self._environments)
        if count == 0:
            self.validations_complete()
        else:
            pos = self._environment_count - count
            percent = int((float(pos) / self._environment_count) * 100)
            msg = 'Running validations on {} environments - %p%'.format(count)
            self.update_progress_bar(percent, progress_format=msg)

        has_env = oz_area in self._cached_env_qmodelindices.keys()
        env_dict = self._cached_env_qmodelindices.get(oz_area, dict())
        validation_qmodelindex = env_dict.get('validation_qmodelindex')
        if not has_env or not validation_qmodelindex:
            # if self._debug_mode:
            msg = 'Completed environment scan. But not in requested checks '
            msg += 'or index unknown in summary view. Skipping update summary.'
            self.logMessage.emit(msg, logging.DEBUG)
            return False

        validation_qmodelindex = self._cached_env_qmodelindices[oz_area]['validation_qmodelindex']
        validation_start_time = self._cached_env_qmodelindices[oz_area].get('start_time')

        if self._debug_mode and validation_start_time:
            te = time.time() - validation_start_time
            msg = 'Validations complete for environment: "{}". '.format(oz_area)
            msg += 'Time since submitted to thread {}s. '.format(te)
            self.logMessage.emit(
                TIME_TAKEN_MSG.format(msg, te),
                logging.DEBUG)

        model = self._summary_view.model()

        # Avoid getting the internal pointer from proxy model
        # https://bugreports.qt.io/browse/QTBUG-17504
        validation_qmodelindex_source = model.mapToSource(validation_qmodelindex)
        if not validation_qmodelindex_source.isValid():
            # if self._debug_mode:
            msg = 'Summary index to update for environment '
            msg += 'Not valid: "{}". '.format(oz_area)
            self.logMessage.emit(
                TIME_TAKEN_MSG.format(msg, te),
                logging.DEBUG)
            return False

        env_item = validation_qmodelindex_source.internalPointer()

        # Update warning and critical counters
        c_count, w_count = self._validation_adapter.get_critical_and_warning_count(oz_area)
        env_item.set_validation_critical_counter(c_count)
        env_item.set_validation_warning_counter(w_count)

        model.dataChanged.emit(
            validation_qmodelindex,
            validation_qmodelindex)

        # Auto scroll to environment scan just complete
        if self._auto_scroll:
            self._summary_view.scrollTo(
                validation_qmodelindex)
                # QTreeView.PositionAtCenter)

        if self._debug_mode:
            te = time.time() - ui_update_start_time
            msg = 'Time to run summary UI updates for environment: "{}". '.format(oz_area)
            self.logMessage.emit(
                TIME_TAKEN_MSG.format(msg, te),
                logging.DEBUG)

        return True


    ##########################################################################
    # Progress bar methods


    def _build_progress_bar(self):
        '''
        Add progress bar to show later

        Returns:
            progress_bar (QProgressBar)
        '''
        progress_bar = QProgressBar()
        progress_bar.setMinimum(0)
        progress_bar.setMaximum(100)
        progress_bar.setValue(0)
        return progress_bar


    def show_progress_bar(self, loading=True):
        '''
        Show a QProgressBar bar and hide and disable UI elements during processing.

        Args:
            loading (bool):
        '''
        self._progress_bar.setVisible(loading)


    def update_progress_bar(self, value, progress_format=None):
        '''
        Show a QProgressBar bar and hide and disable UI elements during processing.

        Args:
            value (int):
            progress_format (str): update the QProgressBar format if different.
        '''
        if progress_format != None:
            self._progress_bar.setFormat(progress_format)
        self._progress_bar.setValue(value)


    ##########################################################################


    def _accept_window(self):
        '''
        When the user accepts the window, force the
        Validations to stop computing.
        '''
        self._was_accepted = True
        self.request_interrupt()
        self.close()


    def _reject_window(self):
        '''
        When the user rejects the window, force the
        Validations to stop computing.
        '''
        self.request_interrupt()
        self.close()


    def emit_message(self, message_str, message_type=logging.INFO):
        self.logMessage.emit(message_str, message_type)


##############################################################################


class MultiShotRenderableProxyModel(QSortFilterProxyModel):
    '''
    Filter the MultiShotRenderModel for only renderable items.
    Which are queued and enabled items.
    '''

    def __init__(self, pass_for_env_items=None, parent=None):
        super(MultiShotRenderableProxyModel, self).__init__(parent=parent)
        self._pass_for_env_items = pass_for_env_items


    def filterAcceptsRow(self, row, parent):
        '''
        Reimplemented to hide EnvironmentItem/s with no enabled pass for env items.
        And also to hide any PassForEnvItem/s that are not queued and enabled.

        Args:
            row (int):
            parent (QModelIndex):
        '''
        model = self.sourceModel()
        source_index = model.index(row, 0, parent)
        if not source_index.isValid():
            return False
        item = source_index.internalPointer()

        is_group_item = item.is_group_item()
        if item and any([item.is_environment_item(), is_group_item]):
            if is_group_item:
                env_items = item.children()
            else:
                env_items = [item]
            for env_item in env_items:
                for pass_env_item in env_item.get_pass_for_env_items():
                    # Check item is in specific PassForEnvItem list
                    in_selection = True
                    if self._pass_for_env_items:
                        if pass_env_item not in self._pass_for_env_items:
                            continue
                    # Item must be enabled and queued
                    if pass_env_item.get_active():
                        return True
            return False
        elif item and item.is_pass_for_env_item():
            # Check item is in specific PassForEnvItem list
            if self._pass_for_env_items:
                if item not in self._pass_for_env_items:
                    return False
            # Item must be enabled and queued
            if item.get_active():
                return True
            return False
        elif item and item.is_group_item():
            return False
        else:
            return QSortFilterProxyModel.filterAcceptsRow(self, row, parent)