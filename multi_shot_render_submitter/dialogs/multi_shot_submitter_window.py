#!/usr/bin/env python


import copy
import functools
import logging
import os
import time

from Qt.QtWidgets import (QApplication, QWidget, QPushButton, QCheckBox,
    QToolButton, QSlider, QMessageBox, QLabel, QMenu, QSpacerItem,
    QProgressBar, QHBoxLayout, QVBoxLayout, QSizePolicy)
from Qt.QtGui import QFont, QIcon, QCursor, QColor
from Qt.QtCore import Qt, QSize, Signal

import srnd_qt.base.utils
from srnd_qt.data import ui_session_data
from srnd_qt.ui_framework.widgets import (
    base_window,
    clickable_label,
    log_widget,
    widget_frame)

from srnd_multi_shot_render_submitter.widgets.session_auto_save_widget \
    import SessionAutoSaveStateWidget
from srnd_multi_shot_render_submitter.widgets.render_estimate_widget \
    import RenderEstimateWidget
from srnd_multi_shot_render_submitter import factory
from srnd_multi_shot_render_submitter import utils


##############################################################################


# Build the shared Constants module for the first time (for host app)
from srnd_multi_shot_render_submitter.constants import Constants
constants = Constants()

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.DEBUG)

DIALOG_WH = (1600, 950)
BASE_WINDOW_STYLESHEET = base_window.DEFAULT_BASE_WINDOW_STYLESHEET

STYLESHEET_BORDER = '''
QScrollArea, QTreeView {
border-style: solid;
border-left-width: 0px;
border-right-width: 0px;
border-top-width: 0px;
border-bottom-width: 0px;
border-left-color: rgb(60, 60, 60);
border-right-color: rgb(60, 60, 60);
border-top-color: rgb(60, 60, 60);
border-bottom-color: rgb(60, 60, 60);}
'''

USER = os.getenv('USER')
ICONS_DIR = os.path.join(
    os.getenv('SRND_MULTI_SHOT_RENDER_SUBMITTER_ROOT', str()),
    'icons')
ICON_PATH = os.path.join(
    ICONS_DIR,
    'Multi_Shot_Render_Submitter_logo_01_128x128.png')
SRND_QT_ROOT = os.getenv('SRND_QT_ROOT')
SRND_QT_ICONS_DIR = os.path.join(SRND_QT_ROOT, 'res', 'icons')
HOST_APP_ICON = str(ICON_PATH)
LINK = 'https://twiki.wetafx.co.nz/ShotsRnD/KatanaMultiShotRenderSubmitter'

FORCE_UPDATE_OVERVIEW_BUTTON_VISIBLE = False


##############################################################################


class MultiShotSubmitterWindow(base_window.BaseWindow):
    '''
    A user interface window to configure multiple Render nodes
    to render over multiple environments for different host applications.
    Note: This generic Multi Shot Render Submitter dialog is composed of a
    subclassed model, view and delegate, for a particular host app
    render submitter implementation. The model is composed of a hierarchy of
    subclassed data objects, some of which represent and act on host app nodes.
    Note: Some methods require implementation for particular host app.
    Note: This is part of a reusable framework for building applications
    that require a multi shot rendering system.

    Args:
        project (str): optionally load a project file on startup
        session_file_path (str): load a session on startup. choosing this
            will disregard any specified project file or environment/s.
        render_environments (set): optionally specify multiple environments to add on startup
        shot_assignments_project (str): optionally override the project shot assignments
            should be queried and populated from
        shot_assignments_user (str): optionally override the user shot assignments
            should be queried and populated from
        update_host_app (bool): as various actions are performed, whether data is
            changed in host app. Provided for development purposes only.
        project_product_types (list):
        project_file_types (list):
        populate (bool):
        show (bool): automatically show the widget after window setup
            and before sync is performed
        host_app (str):
        version (str):
        debug_mode (bool):
    '''

    def __init__(
            self,
            project=None,
            session_file_path=None,
            render_environments=None,
            shot_assignments_project=os.getenv('FILM'),
            shot_assignments_user=USER,
            project_product_types=list(),
            project_file_types=list(),
            populate=True,
            window_size=DIALOG_WH,
            show=True,
            link=LINK,
            stylesheet=BASE_WINDOW_STYLESHEET,
            icon_path=ICON_PATH,
            icon_size=35,
            version=None,
            debug_mode=False,
            parent=None,
            **kwargs):

        self.TOOL_NAME = constants.TOOL_NAME
        self.TOOL_VERSION = version
        self.ORGANIZATION_NAME = 'Weta_Digital'

        super(MultiShotSubmitterWindow, self).__init__(
            app_name=self.TOOL_NAME,
            window_size=window_size,
            link=link,
            stylesheet=stylesheet,
            build_header=True,
            include_emblem_title=False,
            description=None,
            icon_path=icon_path,
            icon_size=icon_size,
            version=version,
            debug_mode=debug_mode,
            parent=parent)

        self.HOST_APP = constants.HOST_APP
        self.HOST_APP_DOCUMENT = constants.HOST_APP_DOCUMENT
        self.HOST_APP_RENDERABLES_LABEL = constants.HOST_APP_RENDERABLES_LABEL
        self.WIKI_LINK = 'https://twiki.wetafx.co.nz/ShotsRnD'
        self.WIKI_LINK += '/{}MultiShotRenderSubmitter'.format(self.HOST_APP.title())
        self.HOST_APP_ICON = HOST_APP_ICON

        ######################################################################

        # Project state
        self._show_save_dialog_on_submit = True
        self._use_hydra_browser = True
        self._auto_derive_project = True
        self._project_product_types = project_product_types
        self._project_file_types = project_file_types

        # Other state
        self._shot_assignments_project = shot_assignments_project
        self._shot_assignments_user = shot_assignments_user
        self._show_advanced_search = True
        self._listen_to_jobs_was_enabled = False
        self._is_loading_session = False
        self._render_summary_mode = 'Graph'
        self._columns_widths_cached = None
        self._debug_mode = bool(debug_mode)

        # Session state
        self._session_auto_save_on_timer = True
        self._session_auto_save_duration = 180
        self._session_auto_save_path = None
        self._auto_save_was_enabled = True
        self._session_save_on_close = True
        self._session_save_on_load_project = True
        self._session_recall_when_loading_project = True

        # Selected state
        self._enabled_pass_count = 0
        self._queued_pass_count = 0
        self._enabled_frame_count = 0
        self._queued_frame_count = 0

        # Callback state
        self._callback_add_pass_on_render_node_create = False
        self._callback_remove_pass_on_render_node_delete = False
        self._callback_update_pass_name_on_render_node_rename = False
        self._callback_save_session_on_project_save = False
        self._callback_restore_session_on_project_load = False
        self._callback_disabled_when_not_active_tab = False

        ######################################################################
        # Build all required UI widgets

        vertical_layout_main = self.get_content_widget_layout()
        vertical_layout_main.setContentsMargins(5, 5, 5, 5)
        vertical_layout_main.setSpacing(5)

        widget = self.centralWidget()
        widget.setStyleSheet(STYLESHEET_BORDER)

        self._tree_view = self._build_tree_view()

        self._build_menu_corner_widget()

        self._build_additional_splash_screen_widgets()

        from srnd_multi_shot_render_submitter.widgets.multi_shot_overlay_widget import MultiShotOverlayWidget
        self._overlay_widget = MultiShotOverlayWidget(
            self._tree_view,
            parent=self._toggle_visible_widget)
        self._overlay_widget.logMessage.connect(self.add_log_message)
        # self._overlay_widget.setViewport(self._tree_view.viewport())
        vertical_layout_main.addWidget(self._toggle_visible_widget)
        self._overlay_widget.raise_()

        self._tree_view.set_overlays_widget(self._overlay_widget)

        self._build_details_panel()
        self._build_lighting_info_panel()

        self._build_job_options_panel()

        tool_name_camel_case = self.TOOL_NAME.title().replace(' ', str())
        log_file_location = os.path.join(
            os.path.sep,
            'tmp',
            USER,
            tool_name_camel_case + '.txt')

        self._panel_log_viewer = self.build_log_panel(
            title_str='Log',
            area=Qt.BottomDockWidgetArea,
            include_detach_button=False,
            log_to_file=True,
            log_file_location=log_file_location, # use a single log file and clear it every time app opens
            cleanup_previous_log=True)
        self._panel_log_viewer.setVisible(False)

        # Build the footer, including the render button
        self._build_footer()

        # Add progress bar to show later
        self._progress_bar =  self._build_progress_bar()
        vertical_layout_main.addWidget(self._progress_bar)
        self._progress_bar.setVisible(False)

        self._status_bar = self.statusBar()

        self._toolButton_duplicate_environments.setVisible(False)
        self._toolButton_delete_environments.setVisible(False)

        # Build a widget to visualize the current auto save session state
        self._build_session_auto_save_widget()

        ######################################################################
        # Check if a dispatcher plugin is available for required host app

        from srnd_multi_shot_render_submitter.dispatcher.abstract_multi_shot_dispatcher import \
            AbstractMultiShotDispatcher

        dispatcher = AbstractMultiShotDispatcher.get_dispatcher_for_host_app(
            self.HOST_APP)

        # Hide the deferred widget if no dispatcher plugin is availble
        widget = self._job_options_widget.get_dispatch_deferred_widget()
        widget.setVisible(bool(dispatcher))
        widget = self._job_options_widget.get_snapshot_before_dispatch_widget()
        widget.setVisible(bool(dispatcher))

        if not bool(dispatcher):
            msg = 'Found no dispatcher for host: "{}". '.format(self.HOST_APP)
            msg += 'Defer dispatching will be hidden.'
            self.add_log_message(msg, logging.WARNING)
        else:
            msg = 'Found dispatcher for host: "{}". '.format(self.HOST_APP)
            self.add_log_message(msg, logging.INFO)

        ######################################################################

        # Add edit menu which also contains Overrides (as sub menu)
        menu_bar = self.menuBar()

        self._menu_edit = self._build_menu_edit(self)
        self._menu_edit.aboutToShow.connect(self._populate_edit_menu)
        menu_bar.insertMenu(self._menu_view.menuAction(), self._menu_edit)

        self._menu_shots = self._build_menu_shots(self)
        self._menu_shots.aboutToShow.connect(self._populate_shots_menu)
        menu_bar.insertMenu(self._menu_view.menuAction(), self._menu_shots)

        self._menu_sync = self._build_menu_sync(self)
        self._menu_sync.aboutToShow.connect(self._populate_sync_menu)
        menu_bar.insertMenu(self._menu_view.menuAction(), self._menu_sync)

        self._menu_render = self._build_menu_render(self)
        self._menu_render.aboutToShow.connect(self._populate_render_menu)
        menu_bar.insertMenu(self._menu_view.menuAction(), self._menu_render)

        # Populate view menu with stuff from base class and extra items
        self._populate_view_menu()

        # Register widgets to be tracked in session data
        self._register_widgets()

        self._wire_events()
        self._add_key_shortcuts()

        if show:
            self.show()

        # Prepare system to listen to already launched Plow Jobs for progress updates
        self._listen_to_previously_launched_jobs()

        # Prepare system for auto save session
        self._session_data_prepare_autosave(
            start=self._session_auto_save_on_timer)

        # Force users MSRS preference to be applied to MSRS objects now
        self._model.apply_preferences()

        msg = 'MSRS is set to populate on startup: {}'.format(populate)
        self.add_log_message(msg, logging.WARNING)

        # Optionally load project and / or session on startup, or sync from host app project or MSRS resource
        if populate:
            do_sync = True
            # Optionally load a particular project on startup
            if project:
                menu_bar_header_widget = self.get_menu_bar_header_widget()
                menu_bar_header_widget.set_project(project)
                do_sync = False
            # Then apply session data in regards to current host app project
            if session_file_path and os.path.isfile(session_file_path):
                self.session_load(session_file_path)
                do_sync = False
            # Otherwise optionally sync all passes on startup
            if do_sync and self._model.get_preference_value('add_passes_on_startup'):
                if self._model.get_in_host_app_ui():
                    self.sync_render_nodes_and_environments(
                        recall_session_from_resource=True)
                # Add any extra default provided environments
                if render_environments:
                    self._model.add_environments(render_environments)
            # Update search after session load
            search_filter_widget = self.get_menu_bar_header_widget().get_search_filter_widget()
            _search_text = search_filter_widget.get_search_text()
            _search_filters = search_filter_widget.get_search_filters()
            if any([_search_text, _search_filters]):
                self.search_view_by_filters(_search_text)

        config_path = constants.get_config_path()
        msg = 'Session data defaults will be derived from '
        msg += 'External config: "{}". '.format(config_path)
        msg += 'Requested config name: "{}". '.format(constants.CONFIG_NAME)
        self.add_log_message(msg, logging.DEBUG)

        self._version = self._model.get_multi_shot_render_submitter_version()

        # Instrumentation to track how this multi shot tool is used
        msg = 'Opened {}'.format(self.TOOL_NAME)
        utils.log_with_winstrumentation(
            self.TOOL_NAME,
            function_key=msg,
            host_app=self.HOST_APP)


    def _wire_events(self):
        '''
        Main UI events to connect
        '''
        # Signals for this QMainWindow itself
        self.logMessage.connect(self.add_log_message)

        # Connect main menu bar widget signals
        self._widget_menu_bar_header.syncRequest.connect(
            self.sync_request)
        self._widget_menu_bar_header.newEnvironmentRequest.connect(
            lambda *x: self._model.add_environment(show_dialog=True))
        self._widget_menu_bar_header.populateAssignedShotsForProjectAndSequenceRequest.connect(
            lambda *x: self._model.populate_assigned_shots(
                sync_production_data=True,
                current_sequence_only=True))
        self._widget_menu_bar_header.projectChanged.connect(
            lambda x: self.load_project(x, show_dialog=False))

        browse_button = self._widget_menu_bar_header.get_browse_button()
        browse_button.clicked.connect(
            lambda *x: self.load_project(
                project=None,
                show_dialog=True))

        # Connect other widget signals
        self._pushButton_launch_summary.clicked.connect(
            lambda *x: self.multi_shot_render(
                selected=False,
                interactive=False))
        self._slider_column_scaling.sliderPressed.connect(
            self._scale_columns_start)
        self._slider_column_scaling.valueChanged.connect(
            self._scale_columns_in_progress)
        self._slider_column_scaling.sliderReleased.connect(
            self._scale_columns_finished)
        self._tree_view_header = self._tree_view.header()
        self._tree_view_header.sectionResized.connect(
            self._scale_column_update)
        self._toolButton_duplicate_environments.clicked.connect(
            lambda *x: self._tree_view._tree_view_operations(
                operation='Duplicate environments'))
        self._toolButton_group_shots.clicked.connect(
            lambda *x: self._tree_view.group_selected_items())
        self._toolButton_group_shots.setContextMenuPolicy(Qt.CustomContextMenu)
        self._toolButton_group_shots.customContextMenuRequested.connect(
            self._create_context_menu_group_options)
        self._toolButton_delete_environments.clicked.connect(
            self._tree_view.delete_items)
        self._toolButton_update_overview.clicked.connect(
            lambda *x: self._model.compute_all_summary_counters())
        self._panel_details.visibilityChanged.connect(
            self._details_widget._visibility_changed)
        self._panel_lighting_info.visibilityChanged.connect(
            self._lighting_info_widget._visibility_changed)

        # Connect model signals
        self._model.logMessage.connect(
            self._text_edit_log_viewer.add_log_message)
        self._model.toggleProgressBarVisible.connect(
            self.show_progress_bar)
        self._model.updateLoadingBarFormat.connect(
            self.update_progress_bar)
        self._model.updateOverviewRequested.connect(
            self.update_estimate)
        self._model.updateDetailsPanel.connect(
            self._update_details_panel)
        self._model.toggleShowFullEnvironments.connect(
            self._update_details_panel)
        self._model.renderSubmitStarted.connect(
            self.setup_ui_for_render)
        self._model.renderSubmitFinished.connect(
            self.revert_ui_after_render)
        self._model.versionSystemChanged.connect(
            self._details_widget.set_version_global_system)
        self._model.applyPreferenceRequest.connect(
            self.apply_preference)
        self._model.aboutToApplyPreferences.connect(
            self._tree_view.clearSelection)

        # Connect view signals
        self._tree_view.logMessage.connect(
            self._text_edit_log_viewer.add_log_message)
        self._tree_view.updateDetailsPanel.connect(
            self._update_details_panel)

        selection_model = self._tree_view.selectionModel()
        selection_model.selectionChanged.connect(
            self._tree_view.selection_changed)

        # Update the details panel after dragging is complete.
        # Optimization for performance.
        self._tree_view.draggingComplete.connect(self._update_panels)

        self._model.environmentAdded.connect(self.set_spalsh_screen_visible_if_items)
        self._model.environmentsAdded.connect(self.set_spalsh_screen_visible_if_items)
        self._model.environmentsRemoved.connect(self.set_spalsh_screen_visible_if_items)
        self._model.renderNodeAdded.connect(self.set_spalsh_screen_visible_if_items)
        self._model.renderNodesRemoved.connect(self.set_spalsh_screen_visible_if_items)
        self._model.groupAdded.connect(self.set_spalsh_screen_visible_if_items)
        self._model.itemsRemoved.connect(self.set_spalsh_screen_visible_if_items)

        # Menu bar signals
        search_widget = self.get_menu_bar_header_widget().get_search_widget()
        search_widget.searchRequest.connect(self.search_view_by_filters)
        search_filter_widget = self.get_menu_bar_header_widget().get_search_filter_widget()
        search_filter_widget.applySearchFiltersRequest.connect(self.search_view_by_filters)
        search_filter_widget.logMessage.connect(self.add_log_message)

        # Version global signals
        version_global_widget = self.get_menu_bar_header_widget().get_version_system_global_widget()
        version_global_widget.textChanged.connect(
            self._model.set_version_global_system)
        version_global_widget.editingFinished.connect(self._update_details_panel)
        version_global_widget.returnPressed.connect(self._update_details_panel)

        # Details widget signals
        self._details_widget.updateDetailsPanel.connect(self._update_details_panel)
        self._details_widget.removeOverrideRequest.connect(
            self._tree_view.remove_override_from_uuid)
        self._details_widget.editOverrideRequest.connect(
            self._tree_view.edit_override_from_uuid)

        # Lighting info signals
        self._lighting_info_widget.updateLightingInfoPanel.connect(
            self._update_lighting_info_panel)

        # Render estimate signals
        self._widget_render_estimate.logMessage.connect(self.add_log_message)
        self._widget_render_estimate.selectEnvironmentsRequested.connect(
            lambda x: self._tree_view.select_by_identity_uids(identifiers=x, scroll_to=True))

        # Session autosave state hint widget signals
        self._session_autosave_widget.saveProjectRequest.connect(
            self.save_project_as)
        self._session_autosave_widget.saveSessionRequest.connect(
            lambda *x: self.session_auto_save(force_save=True))

        ######################################################################
        # Global options

        widget = self._job_options_widget.get_email_additional_users_widget()
        widget.entriesChanged.connect(
            self._model.set_email_additional_users)

        widget = self._job_options_widget.get_global_job_identifier_widget()
        widget.textChanged.connect(
            self._model.set_global_job_identifier)

        widget = self._job_options_widget.get_global_submit_description_widget()
        widget.textChanged.connect(
            self._set_global_submit_description_from_widget)

        widget = self._job_options_widget.get_send_summary_email_on_submit()
        widget.toggled.connect(
            self._model.set_send_summary_email_on_submit)

        widget = self._job_options_widget.get_dispatch_deferred_widget()
        widget.toggled.connect(self._model.set_dispatch_deferred)

        widget = self._job_options_widget.get_snapshot_before_dispatch_widget()
        widget.toggled.connect(self._model.set_snapshot_before_dispatch)

        widget = self._job_options_widget.get_launch_paused_widget()
        widget.toggled.connect(self._model.set_launch_paused)

        widget = self._job_options_widget.get_launch_paused_expires_widget()
        widget.valueChanged.connect(self._model.set_launch_paused_expires)

        widget = self._job_options_widget.get_launch_zero_tier_widget()
        widget.toggled.connect(self._model.set_launch_zero_tier)

        widget = self._job_options_widget.get_apply_render_overrides_widget()
        widget.toggled.connect(self._model.set_apply_render_overrides)

        widget = self._job_options_widget.get_apply_dependencies_widget()
        widget.toggled.connect(self._model.set_apply_dependencies)

        ######################################################################
        # Threads setup

        thumbnail_prep_thread = self._tree_view.get_thumbnail_prep_thread()
        if thumbnail_prep_thread:
            self._model.requestEnvironmentsThumbnails.connect(
                self._tree_view._prepare_thumbnails_for_environments)


    def _add_key_shortcuts(self):
        '''
        Build shortcut keys.
        '''
        from Qt.QtWidgets import QShortcut

        shortcut = QShortcut(self)
        shortcut.setKey('CTRL+A')
        shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        shortcut.activated.connect(self._tree_view.selectAll)

        shortcut = QShortcut(self)
        shortcut.setKey('CTRL+D')
        shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        shortcut.activated.connect(self._tree_view.clearSelection)

        shortcut = QShortcut(self)
        shortcut.setKey('ALT+F')
        shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        search_widget = self.get_menu_bar_header_widget().get_search_widget()
        shortcut.activated.connect(search_widget.setFocus)

        shortcut = QShortcut(self)
        shortcut.setKey('CTRL+N')
        shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        shortcut.activated.connect(self.new_project)

        shortcut = QShortcut(self)
        shortcut.setKey('CTRL+L')
        shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        shortcut.activated.connect(self.load_project)

        shortcut = QShortcut(self)
        shortcut.setKey('CTRL+S')
        shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        shortcut.activated.connect(self.save_project_as)

        shortcut = QShortcut(self)
        shortcut.setKey('CTRL+SHIFT+E')
        shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        shortcut.activated.connect(
            lambda *x: self._model.add_environment(show_dialog=True))

        shortcut = QShortcut(self)
        shortcut.setKey('Q')
        shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        shortcut.activated.connect(
            lambda *x: self._tree_view.queue())

        shortcut = QShortcut(self)
        shortcut.setKey('D')
        shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        shortcut.activated.connect(
            lambda *x: self._tree_view._tree_view_operations(
                operation='Enabled'))

        shortcut = QShortcut(self)
        shortcut.setKey('CTRL+SHIFT+R')
        shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        shortcut.activated.connect(
            lambda *x: self.multi_shot_render(
                selected=True,
                interactive=False))

        shortcut = QShortcut(self)
        shortcut.setKey('CTRL+SHIFT+K')
        shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        shortcut.activated.connect(
            lambda *x: self.multi_shot_render(
                selected=True,
                interactive=True))

        shortcut = QShortcut(self)
        shortcut.setKey('V')
        shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        shortcut.activated.connect(
            lambda *x: self._tree_view._tree_view_operations(
                operation='Version up'))

        shortcut = QShortcut(self)
        shortcut.setKey('P')
        shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        shortcut.activated.connect(
            lambda *x: self._tree_view._tree_view_operations(
                operation='Version up (match passes)'))

        shortcut = QShortcut(self)
        shortcut.setKey('S')
        shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        shortcut.activated.connect(
            lambda *x: self._tree_view._tree_view_operations(
                operation='Version match scene'))

        shortcut = QShortcut(self)
        shortcut.setKey('SHIFT+V')
        shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        shortcut.activated.connect(
            lambda *x: self._tree_view._tree_view_operations(
                operation='Custom version'))

        shortcut = QShortcut(self)
        shortcut.setKey('O')
        shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        shortcut.activated.connect(
            lambda *x: self._tree_view._tree_view_operations(
                operation=constants.OVERRIDE_FRAMES_X1))

        shortcut = QShortcut(self)
        shortcut.setKey('T')
        shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        shortcut.activated.connect(
            lambda *x: self._tree_view._tree_view_operations(
                operation=constants.OVERRIDE_FRAMES_X10))

        shortcut = QShortcut(self)
        shortcut.setKey('F')
        shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        shortcut.activated.connect(
            lambda *x: self._tree_view._tree_view_operations(
                operation=constants.OVERRIDE_FRAMES_FML))

        shortcut = QShortcut(self)
        shortcut.setKey('I')
        shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        shortcut.activated.connect(
            lambda *x: self._tree_view._tree_view_operations(
                operation=constants.OVERRIDE_FRAMES_IMPORTANT))

        shortcut = QShortcut(self)
        shortcut.setKey('SHIFT+F')
        shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        shortcut.activated.connect(
            lambda *x: self._tree_view._tree_view_operations(
                operation=constants.OVERRIDE_FRAMES_CUSTOM))

        shortcut = QShortcut(self)
        shortcut.setKey('SHIFT+ALT+F')
        shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        shortcut.activated.connect(
            lambda *x: self._tree_view._tree_view_operations(
                operation=constants.OVERRIDE_FRAMES_NOT_CUSTOM))

        shortcut = QShortcut(self)
        shortcut.setKey('SHIFT+J')
        shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        shortcut.activated.connect(
            lambda *x: self._tree_view.edit_job_identifier_for_selection())

        shortcut = QShortcut(self)
        shortcut.setKey('SHIFT+CTRL+W')
        shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        shortcut.activated.connect(self._tree_view.edit_wait_on_for_selection)

        shortcut = QShortcut(self)
        shortcut.setKey('SHIFT+W')
        shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        shortcut.activated.connect(self._tree_view.enter_wait_on_interactive)

        shortcut = QShortcut(self)
        shortcut.setKey('SHIFT+N')
        shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        shortcut.activated.connect(
            lambda *x: self._tree_view.edit_note_for_selection())

        shortcut = QShortcut(self)
        shortcut.setKey('SHIFT+C')
        shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        shortcut.activated.connect(
            lambda *x: self._tree_view.edit_colour_for_selection())

        shortcut = QShortcut(self)
        shortcut.setKey('CTRL+SHIFT+C')
        shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        shortcut.activated.connect(
            lambda *x: self._tree_view.copy_overrides_for_selection())

        shortcut = QShortcut(self)
        shortcut.setKey('CTRL+SHIFT+V')
        shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        shortcut.activated.connect(
            lambda *x: self._tree_view.paste_overrides_for_selection())

        shortcut = QShortcut(self)
        shortcut.setKey('CTRL+BACKSPACE')
        shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        shortcut.activated.connect(
            lambda *x: self._tree_view._tree_view_operations(
                operation='Clear overrides'))

        shortcut = QShortcut(self)
        shortcut.setKey('X')
        shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        shortcut.activated.connect(
            lambda *x: self._tree_view._tree_view_operations(
                operation='Sync production data for environments'))

        shortcut = QShortcut(self)
        shortcut.setKey(Qt.SHIFT + Qt.ALT + Qt.Key_Equal)
        shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        shortcut.activated.connect(
            lambda *x: self.sync_render_nodes_and_environments(
                from_selected_nodes=True,
                emit_insertion_signals=True))

        shortcut = QShortcut(self)
        shortcut.setKey(Qt.SHIFT + Qt.ALT + Qt.Key_Minus)
        shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        shortcut.activated.connect(self._model.remove_selected_host_app_nodes)

        shortcut = QShortcut(self)
        shortcut.setKey('CTRL+SHIFT+D')
        shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        shortcut.activated.connect(
            lambda *x: self._tree_view._tree_view_operations(
                operation='Duplicate environments'))

        shortcut = QShortcut(self)
        shortcut.setKey('CTRL+G')
        shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        shortcut.activated.connect(
            lambda *x: self._tree_view.group_selected_items())

        shortcut = QShortcut(self)
        shortcut.setKey('DELETE')
        shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        shortcut.activated.connect(self._tree_view.delete_items)


    def toggle_debug_mode(self, debug_mode=None):
        '''
        Toggle debug mode on or off.

        Args:
            widget_name (bool):
        '''
        # Toggle existing debug mode
        if debug_mode == None:
            self._debug_mode = not bool(self._debug_mode)
        # Set debug mode from argument
        else:
            self._debug_mode = bool(debug_mode)

        msg = 'Setting debug mode: {}'.format(self._debug_mode)
        self.logMessage.emit(msg, logging.DEBUG)

        self._model.set_debug_mode(self._debug_mode)
        self._tree_view.set_debug_mode(self._debug_mode)
        self._delegates.set_debug_mode(self._debug_mode)
        self._details_widget.set_debug_mode(self._debug_mode)
        self._lighting_info_widget.set_debug_mode(self._debug_mode)


    def closeEvent(self, event):
        '''
        Save window layout when closing.

        Args:
            event (QtCore.QEvent):
        '''
        from Qt.QtWidgets import QApplication
        QApplication.restoreOverrideCursor()

        self.close_event_for_host_app()

        if self._timer_auto_save.isActive():
            self._timer_auto_save.stop()

        # Do auto save of session now, before closing window
        msg = 'Save session on close is: {}'.format(self._session_save_on_close)
        print(msg)
        # LOGGER.info(msg)
        if self._session_save_on_close:
            self.session_auto_save(force_save=True)

        self.get_window_and_panel_preset_by_name()


    def close_event_for_host_app(self):
        '''
        Host app specific close event logic.
        Reimplement to add any additional close event logic for host app.
        '''
        # Unregister project event handlers callbacks
        self.register_callback_project_save(register=False)
        self.register_callback_project_load(register=False)
        # Unregister render node callbacks
        self.register_callback_render_node_create(register=False)
        self.register_callback_render_node_delete(register=False)
        self.register_callback_render_node_renamed(register=False)


    def keyPressEvent(self, event):
        '''
        Intercept the Escape button press.

        Args:
            event (QtCore.QEvent):
        '''
        if event.key() == Qt.Key_Escape and self._model.get_is_rendering():
            msg = 'Escape pressed. Cancelling submission.'
            self.logMessage.emit(msg, logging.CRITICAL)
            self._model.request_interrupt()
            return
        base_window.BaseWindow.keyPressEvent(self, event)


    ##########################################################################


    def sync_render_nodes_and_environments(
            self,
            hyref=None,
            from_selected_nodes=False,
            limit_to=None,
            only_missing=False,
            keep_session_data=False,
            recall_session_from_resource=False,
            include_current_env=True,
            emit_insertion_signals=False,
            auto_toggle_splash_screen=True,
            **kwargs):
        '''
        Sync all environments and render nodes from host app.
        Optionally first open a project to perform sync on.

        Args:
            hyref (str): optional project to first open
            from_selected_nodes (bool): optionally only sync / populate from
                selected host app Render nodes
            limit_to (list): optionally provide a list of strings of renderable item names
                to limit which render nodes are populated into MSRS data model.
            only_missing (bool): on sync the render nodes not already in this view.
            keep_session_data (bool): whether to reapply previous session data, after sync
                from host app is called.
            recall_session_from_resource (bool):
            include_current_env (bool): optionally add the current oz Environment
                if no other environments were synced from host app
            emit_insertion_signals (bool): whether to batch update view, or emit signal
                as each row added. Note: batch update requires all editors to reopen.
            auto_toggle_splash_screen (bool):
        '''
        limit_to = limit_to or None

        # # If in initial state and non selective sync requested, then try to sync from MSRS session
        # force_recall = self._model.get_in_initial_state() and not any([
        #     from_selected_nodes,
        #     limit_to,
        #     only_missing])

        # # No session data to recall back to previous state (after sync)
        # if force_recall:
        #     keep_session_data = False

        self._overlay_widget.clear_all()

        selective_sync = any([from_selected_nodes, only_missing])
        if not selective_sync:
            self.set_spalsh_screen_visible_if_items()

        # Get the MSRS session related to current project (if any)
        session_path = str()
        if recall_session_from_resource: # force_recall
            current_project = self.get_current_project()
            hydra_resource, session_path = self._model.get_or_create_session_data_resource(
                current_project)
            if os.path.isfile(session_path):
                session_data = ui_session_data.UiSessionData.get_session_data(session_path)
                self._model.set_sync_rules_active(bool(session_data.get('sync_rules_active')))
                self._model.set_sync_rules_include(session_data.get('sync_rules_include', list()))
                self._model.set_sync_rules_exclude(session_data.get('sync_rules_exclude', list()))
                value = self._model.get_sync_only_if_already_in_session()
                # Collect the limit to from current renderables in session data
                if value and not limit_to:
                    multi_shot_data = session_data.get(constants.SESSION_KEY_MULTI_SHOT_DATA, dict())
                    render_nodes_data = multi_shot_data.get(constants.SESSION_KEY_RENDER_NODES, dict())
                    limit_to = sorted(render_nodes_data.keys())

        # Sync from current host app project and selected node/s or a subset of items
        self._tree_view.sync_render_nodes_and_environments(
            hyref=hyref,
            from_selected_nodes=from_selected_nodes,
            limit_to=limit_to,
            only_missing=only_missing,
            keep_session_data=keep_session_data,
            include_current_env=False,
            emit_insertion_signals=emit_insertion_signals)

        # Only sync project hyref / file name string, if returns valid result.
        # Standalone host app might return no current project, even though
        # it's already loaded and set on project widget.
        current_project = self.get_current_project()
        if current_project:
            self._update_project_widget(project=current_project)

        if session_path and os.path.isfile(session_path):
            msg = 'Attempting to recall session data '
            msg += 'associated with: "{}". '.format(current_project)
            msg += 'Session path: "{}"'.format(session_path)
            self.add_log_message(msg, logging.INFO)
            self.session_load(
                session_path=session_path, # session data to load
                load_project=False, # project already loaded
                start_new_session=False, # no need to clear existing session
                sync_from_project=False, # already synced
                show_dialog=False)

        # Add current shell environment context, if no environments added
        if include_current_env and not self._model.get_environment_items():
            self._model.add_environment(os.getenv('OZ_CONTEXT'))
            self._tree_view.setColumnWidth(0, self._tree_view.COLUMN_0_WIDTH)

        self._overlay_widget.update_overlays()

        if auto_toggle_splash_screen:
            self.set_spalsh_screen_visible_if_items()


    def modify_sync_rules(
            self,
            include_rules=None,
            exclude_rules=None,
            show_dialog=True):
        '''
        Modify and define new sync rules in optional dialog..

        Args:
            include_rules (list): sync rules to explicitly add if dialog is not shown.
            exclude_rules (list): sync rules to explicitly add if dialog is not shown.
            show_dialog (bool): whether to show dialog to let the user define rule/s

        Returns:
            include_rules, exclude_rules (tuple):
        '''
        if not include_rules:
            include_rules = self._model.get_sync_rules_include() or list()

        if not exclude_rules:
            exclude_rules = self._model.get_sync_rules_exclude() or list()

        if show_dialog:
            from srnd_multi_shot_render_submitter.dialogs import pass_sync_rules_dialog
            dialog = pass_sync_rules_dialog.PassSyncRulesDialog(
                include_rules,
                exclude_rules,
                parent=self)
            # Update sync rules when dialog Okay button is pushed (non modal / non blocking)
            dialog.syncRulesIncludeModified.connect(self._model.set_sync_rules_include)
            dialog.syncRulesExcludeModified.connect(self._model.set_sync_rules_exclude)
            dialog.show()
            return list(), list()

        self._model.set_sync_rules_include(include_rules)
        self._model.set_sync_rules_exclude(exclude_rules)

        return include_rules, exclude_rules


    def sync_request(self):
        '''
        Callback when main sync button is pressed.
        Prepare the final arguments for sync to be performed.
        '''
        keep_session_data = self._model.get_session_data_is_recalled_after_sync()
        recall_session_from_resource = self._model.get_session_data_recalled_from_resource_after_sync()
        self.sync_render_nodes_and_environments(
            keep_session_data=keep_session_data,
            recall_session_from_resource=recall_session_from_resource)


    def _update_project_widget(self, project=None):
        '''
        Update the project widget to the specified project hyref / file path,
        without firing any callbacks.

        Args:
            project (str):
            cast_to_hyref (bool): optionally automatically convert
                file path to hyref (if possible)
        '''
        hyref_widget = self.get_menu_bar_header_widget()
        hyref_widget._update_project_widget(project=project)


    def _update_panels(
            self,
            selection_details=None,
            resolve_versions=False):
        '''
        Update all info and details panels when selection changes or on other occassion.

        Args:
            selection_details (dict):
            resolve_versions (bool):
        '''
        # if not any([
        #         self._details_widget.isVisible(),
        #         self._lighting_info_widget.isVisible()]):
        #     msg = 'Skipping update any details or info widgets. '
        #     msg += 'Because not visible!'
        #     self.logMessage.emit(msg, logging.DEBUG)
        #     return

        selection_details = selection_details or self._filter_selection_to_items_by_type()
        shots_selected = selection_details.get('shots_selected', list())
        shots_passes_selected = selection_details.get('shots_passes_selected', list())
        groups_selected = selection_details.get('groups_selected', list())

        # Collect counts from selection
        results = self._model.get_counts_for_shot_and_pass_selection(
            shots_selected,
            shots_passes_selected)
        self._enabled_pass_count = results.get('enabled_pass_count', 0)
        self._queued_pass_count = results.get('queued_pass_count', 0)
        self._enabled_frame_count = results.get('enabled_frame_count', 0)
        self._queued_frame_count = results.get('queued_frame_count', 0)

        # Show and hide widgets depending on selection
        self._toolButton_duplicate_environments.setVisible(bool(shots_selected))
        can_delete = bool(shots_selected) or bool(groups_selected)
        self._toolButton_delete_environments.setVisible(can_delete)

        self._update_details_panel(
            selection_details=selection_details,
            resolve_versions=resolve_versions)

        self._update_lighting_info_panel(selection_details=selection_details)


    def _update_details_panel(
            self,
            selection_details=None,
            resolve_versions=False):
        '''
        Update the details panel after selection changes in the main MSRS view.

        Args:
            selection_details (dict):
            resolve_versions (bool): optionally force resolve versions to run.
                otherwise will use the internal auto_resolve_version member state.
        '''
        # if not self._details_widget.isVisible():
        #     msg = 'Skipping update details widget. '
        #     msg += 'Because not visible!'
        #     self.logMessage.emit(msg, logging.DEBUG)
        #     return

        # Do not update the details panels from main MSRS selection when in summary dialog.
        # NOTE: The summary dialog will take temporary ownership.
        if not self._panel_details.parent() == self:
            return

        selection_details = selection_details or self._filter_selection_to_items_by_type()
        shots_selected = selection_details.get('shots_selected', list())
        shots_passes_selected = selection_details.get('shots_passes_selected', list())

        shots_selected_count = selection_details.get('shots_selected_count', 0)
        shots_passes_selected_count = selection_details.get('shots_passes_selected_count', 0)
        msg = selection_details.get('message', str())

        # Populate details widget
        self._details_widget.populate(
            shots_selected=shots_selected,
            shots_passes_selected=shots_passes_selected,
            resolve_versions=resolve_versions)

        # Update selection summary
        widget = self._details_widget.get_selection_summary_widget()
        widget.update_summary_info(
            self._enabled_pass_count,
            self._enabled_frame_count,
            self._queued_pass_count,
            self._queued_frame_count)

        self.update_details_panel_title(msg)


    def _update_lighting_info_panel(
            self,
            selection_details=None,
            visible_render_node_names=None):
        '''
        Update the lighting info panel after selection changes in the main MSRS view.

        Args:
            selection_details (dict):
            visible_render_node_names (list): optionally limit passes to visible render node name list
        '''
        # if not self._lighting_info_widget.isVisible():
        #     msg = 'Skipping update lighting info widget. '
        #     msg += 'Because not visible!'
        #     self.logMessage.emit(msg, logging.DEBUG)
        #     return

        selection_details = selection_details or self._filter_selection_to_items_by_type()
        shots_selected = selection_details.get('shots_selected', list())
        shots_passes_selected = selection_details.get('shots_passes_selected', list())
        msg = selection_details.get('message', str())

        render_node_names = visible_render_node_names or self._tree_view.get_visible_render_node_names()

        # Populate lighting info model
        self._lighting_info_widget.populate(
            shots_selected=shots_selected,
            shots_passes_selected=shots_passes_selected,
            visible_render_node_names=render_node_names)

        # Update selection summary
        widget = self._lighting_info_widget.get_selection_summary_widget()
        widget.update_summary_info(
            self._enabled_pass_count,
            self._enabled_frame_count,
            self._queued_pass_count,
            self._queued_frame_count)

        self.update_lighting_info_panel_title(msg)


    def _filter_selection_to_items_by_type(self, selection=None):
        '''
        Filter the list of selected QModelIndices into a result dict organized
        by type, which can be used to help populate details and info panels.

        Returns:
            result (dict):
        '''
        if not selection:
            selection = self._tree_view.selectedIndexes()
        shots_selected = set()
        shots_passes_selected = set()
        groups_selected = set()
        for qmodelindex in selection:
            if not qmodelindex.isValid():
                continue
            item = qmodelindex.internalPointer()
            if not item:
                continue
            if item.is_environment_item():
                shots_selected.add(item)
            elif item.is_pass_for_env_item():
                shots_passes_selected.add(item)
            elif item.is_group_item():
                groups_selected.add(item)

        shots_selected = list(shots_selected)
        shots_passes_selected = list(shots_passes_selected)
        groups_selected = list(groups_selected)
        shots_selected_count = len(shots_selected)
        shots_passes_selected_count = len(shots_passes_selected)

        msg = 'Selected item details'
        if shots_selected_count > 1 and not shots_passes_selected_count:
            msg = '{} shots selected'.format(shots_selected_count)
        elif shots_passes_selected_count > 1 and not shots_selected_count:
            msg = '{} passes selected'.format(shots_passes_selected_count)
        elif shots_selected_count >= 1 and shots_passes_selected_count >= 1:
            msg = '{} shots & '.format(shots_selected_count)
            msg += '{} passes selected'.format(shots_passes_selected_count)
        elif shots_selected_count == 1 and not shots_passes_selected_count:
            msg = shots_selected[0].get_oz_area()
        elif shots_passes_selected_count == 1 and not shots_selected_count:
            item = shots_passes_selected[0]
            oz_area = self._model.get_item_environment(item)
            if oz_area:
                msg = str(oz_area)
                render_item = item.get_source_render_item()
                if render_item:
                    msg = ' - '.join([oz_area, render_item.get_pass_name()])

        result  = dict()
        result['shots_selected'] = shots_selected
        result['shots_passes_selected'] = shots_passes_selected
        result['groups_selected'] = groups_selected
        result['shots_selected_count'] = shots_selected_count
        result['shots_passes_selected_count'] = shots_passes_selected_count
        result['message'] = msg

        return result


    def _update_launch_render_label(self, show_summary=True):
        '''
        Update the launch render button depending on if show_summary summary is enabled.

        Args:
            show_summary (bool):
        '''
        show_summary = bool(show_summary)
        if show_summary:
            label = 'Launch summary'
        else:
            label = 'Launch'
        self._pushButton_launch_summary.setText(label)


    ##########################################################################
    # Column scaling / multiplier from UI slider.


    def _scale_columns_start(self):
        '''
        Cache all the column widths at start of drag operation.
        NOTE: During drag operation all columns are proportionately scaled.
        '''
        self._overlay_widget.set_active(False)
        self._overlay_widget.clear_all()

        if self._tree_view.get_in_wait_on_interactive_mode():
            self._tree_view.exit_wait_on_interactive()

        header = self._tree_view.header()
        self._columns_widths_cached = dict()
        for c in range(1, header.count(), 1):
            self._columns_widths_cached[c] = header.sectionSize(c)


    def _scale_columns_in_progress(self, value):
        '''
        Add the column offset to cached column width, and set all column widths.

        Args:
            value (int):
        '''
        if not self._columns_widths_cached:
            return
        render_items = self._model.get_render_items()
        MIN_COLUMN_WIDTH = 20
        MAX_COLUMN_WIDTH = 500
        header = self._tree_view.header()
        for c in range(1, header.count(), 1):
            width = self._columns_widths_cached.get(c)
            if not width:
                continue
            width += value
            if width < MIN_COLUMN_WIDTH:
                width = MIN_COLUMN_WIDTH
            elif width > MAX_COLUMN_WIDTH:
                width = MAX_COLUMN_WIDTH
            try:
                render_items[c - 1]._cached_width = width
            except IndexError:
                pass
            self._tree_view.setColumnWidth(c, width)


    def _scale_columns_finished(self):
        '''
        Reset the column scale slider to 100, for next drag operation.
        NOTE: Clear the cache column widths, as no longer needed.
        '''
        self._columns_widths_cached = None
        self._slider_column_scaling.blockSignals(True)
        self._slider_column_scaling.setValue(0)
        self._slider_column_scaling.blockSignals(False)

        self._overlay_widget.set_active(True)
        self._overlay_widget.update_overlays()


    def _scale_column_update(self, column, old_width, width):
        '''
        Cache the column width as the user adjusts an individual column.
        NOTE: This is necessary because headerData of model queries this
        cached value to set QFont for FontRole.

        Args:
            column (int):
            old_width (int):
            width (int):
        '''
        render_items = self._model.get_render_items()
        if render_items:
            try:
                render_items[column - 1]._cached_width = width
            except IndexError:
                pass
        self._model.headerDataChanged.emit(
            Qt.Horizontal,
            column,
            column)


    def _reset_column_sizes(self):
        '''
        Reset the column sizes and destroy the cached column width info.
        '''
        if self._tree_view.get_in_wait_on_interactive_mode():
            self._tree_view.exit_wait_on_interactive()
        # Clear the temporary column cache (created during click drag)
        self._columns_widths_cached = None
        # Clear the cached column widths on each render item.
        for render_item in self._model.get_render_items():
            render_item._cached_width = None
        self._slider_column_scaling.setValue(0)
        self._tree_view.reset_column_sizes()


    ##########################################################################
    # Search


    def search_view_by_filters(self, search_text=None):
        '''
        Search using the current search text, and including any defined
        search filters, provided by SearchWithFiltersWidget.

        Args:
            search_text (str): the value in current search widget to filter

        Returns:
            count (int): number of rows or columns toggled visible state
        '''
        search_filter_widget = self.get_menu_bar_header_widget().get_search_filter_widget()
        search_filters = dict()
        if self._show_advanced_search:
            search_filters = search_filter_widget.get_search_filters() or dict()
        invert = search_filter_widget.get_invert_results()
        # Add the current search text and type to search filters
        if search_text:
            search_text = str(search_text)
            search_filters = copy.deepcopy(search_filters)
            search_filters[search_text] = dict()
            search_filters[search_text]['active'] = True
        count = self._tree_view.search_view_by_filters(
            search_filters,
            invert=invert)
        return count


    def search_reset(self):
        '''
        reset the search widget to default state.
        '''
        search_filter_widget = self.get_menu_bar_header_widget().get_search_filter_widget()
        search_filter_widget.clear_search_filters()
        search_filter_widget.set_auto_update(True)
        search_filter_widget.set_invert_results(False)


    def search_show_advanced(self, value):
        '''
        Set whether to expose advanced search mode, which includes filters.

        Args:
            value (bool):
        '''
        search_filter_widget = self.get_menu_bar_header_widget().get_search_filter_widget()
        # Get the current search text and search filters
        search_text = search_filter_widget.get_search_text()
        search_filters_current = search_filter_widget.get_search_filters()
        had_search = any([search_text, search_filters_current])
        value = bool(value)
        if self._debug_mode:
            msg = 'Set show advanced search: "{}"'.format(value)
            self.logMessage.emit(msg, logging.DEBUG)
        # Expose the search filters or not
        search_filter_widget.set_expose_advanced_search(value)
        # Only perform search when turning off search filters and previously had search filters.
        # Otherwise leave the view alone.
        if not value and had_search:
            self.search_view_by_filters(search_filter_widget.get_search_text())


    ##########################################################################


    def update_estimate(self):
        '''
        Update the render summary from model.
        This will update every time an enable or queued event happens within model.

        Returns:
            frame_count (int):
        '''
        # frame_count = self._model.get_frame_count_all_queued()
        frame_count = self._widget_render_estimate.update_estimate()
        self._pushButton_launch_summary.setEnabled(bool(frame_count))


    def get_launch_button_widget(self):
        '''
        Get the launch button widget.

        Returns:
            widget (QPushButton):
        '''
        return self._pushButton_launch_summary


    def update_details_panel_title(self, title_str=str()):
        '''
        Updating the details panel title.

        Args:
            title_str (str):
        '''
        self._panel_details.set_title(title_str)


    def update_lighting_info_panel_title(self, title_str=str()):
        '''
        Updating the lighting info panel title.

        Args:
            title_str (str):
        '''
        self._panel_lighting_info.set_title(title_str)


    def set_search_filter(self, search_filter=str()):
        '''
        Set the search filter to particulat value

        Args:
            search_filter (str):
        '''
        search_widget = self.get_menu_bar_header_widget().get_search_widget()
        # search_widget.set_search_text(search_filter)
        search_widget.setText(search_filter)
        search_widget.textChanged.emit(search_filter)


    def set_spalsh_screen_visible_if_items(self):
        '''
        Set whether the splash screen is visible or the main view of app.
        '''
        has_items = any([
            self._model.get_render_items(),
            self._model.get_environment_items(),
            self._model.get_group_items()])
        if has_items:
            splash_screen_was_visible = self._toggle_visible_widget.get_initial_widget_visible()
            self._toggle_visible_widget.show_other_widget()
            if splash_screen_was_visible:
                self._reset_column_sizes()
        else:
            self._toggle_visible_widget.show_initial_widget()
        self._overlay_widget.setVisible(has_items)


    def _set_global_submit_description_from_widget(self):
        '''
        Set the global submit description in the model, from the
        QTextEdit (which has no default signal to carry text).
        '''
        description_widget = self._job_options_widget.get_global_submit_description_widget()
        description_global = description_widget.toPlainText()
        self._model.set_global_submit_description(description_global)


    def get_auto_resolve_versions(self):
        '''
        Get whether auto resolve versions is enabled.

        Returns:
            auto_resolve_versions (bool):
        '''
        return self._tree_view.get_auto_resolve_versions()


    def set_auto_resolve_versions(self, value):
        '''
        Set whether auto resolve versions is enabled.

        Args:
            value (bool):
        '''
        value = bool(value)
        self._details_widget.set_auto_resolve_versions(value)
        self._tree_view.set_auto_resolve_versions(value)


    def set_show_full_environments(self, value=True):
        '''
        Toggle show full environment or only Scene/Shot display model.

        Args:
            value (bool):
        '''
        self._model.set_show_full_environments(value)
        self._tree_view.resize_environment_column_to_optimal()


    def _toggle_show_full_environments(self):
        self._model.toggle_show_full_environments()
        self._tree_view.resize_environment_column_to_optimal()


    ##########################################################################
    # Context menus


    def _populate_sync_menu(self):
        '''
        Build a menu to contain all Sync actions.

        Returns:
            menu (QtGui.QMenu):
        '''
        menu = self._menu_sync
        if not menu:
            return
        menu.clear()

        font_italic = QFont()
        font_italic.setFamily(constants.FONT_FAMILY)
        font_italic.setItalic(True)

        action = srnd_qt.base.utils.context_menu_add_menu_item(
            self,
            constants.LABEL_SYNC,
            icon_path=os.path.join(constants.ICONS_DIR_QT, 'sync.png'))
        action.setStatusTip(constants.TOOLTIP_SYNC)
        action.triggered.connect(self.sync_request)
        menu.addAction(action)

        action = srnd_qt.base.utils.context_menu_add_menu_item(
            self,
            'Refresh from Shotgun',
            icon_path=os.path.join(constants.ICONS_DIR_QT, 'sync.png'))
        action.setStatusTip(constants.TOOLTIP_SYNC)
        action.triggered.connect(
            lambda *x: self._model.sync_production_data(force=True))
        menu.addAction(action)

        menu.addSeparator()

        ######################################################################

        host_app = self.HOST_APP.title()

        VERIFY_MSG = 'Note: Existing {} will be verified '.format(self.HOST_APP_RENDERABLES_LABEL)
        VERIFY_MSG += 'that they still exist '
        VERIFY_MSG += '({} no longer available will hidden).'.format(self.HOST_APP_RENDERABLES_LABEL)

        label = 'Add missing'
        action = srnd_qt.base.utils.context_menu_add_menu_item(
            self,
            label,
            icon_path=os.path.join(constants.ICONS_DIR_QT, 'add.png'))
        msg = 'Only sync render nodes that are not shown in current view. '
        action.setStatusTip(msg + VERIFY_MSG)
        action.triggered.connect(
            lambda *x: self.sync_render_nodes_and_environments(
                only_missing=True,
                emit_insertion_signals=True))
        menu.addAction(action)

        action = srnd_qt.base.utils.context_menu_add_menu_item(
            self,
            'Add passes',
            icon_path=os.path.join(constants.ICONS_DIR_QT, 'add.png'))
        msg = 'Choose which {} to add to multishot session.'.format(self.HOST_APP_RENDERABLES_LABEL)
        action.setStatusTip(msg + VERIFY_MSG)
        missing_render_nodes_menu = self._create_context_menu_missing_render_nodes()
        if missing_render_nodes_menu.actions():
            action.setMenu(missing_render_nodes_menu)
            menu.addAction(action)

        action = srnd_qt.base.utils.context_menu_add_menu_item(
            self,
            'Add selected',
            icon_path=os.path.join(constants.ICONS_DIR_QT, 'add.png'))
        msg = 'Sync details of selected {} '.format(self.HOST_APP_RENDERABLES_LABEL)
        msg += 'to multishot session.'
        action.setStatusTip(msg + VERIFY_MSG)
        action.setShortcut(Qt.SHIFT + Qt.ALT + Qt.Key_Equal)
        action.triggered.connect(
            lambda *x: self.sync_render_nodes_and_environments(
                from_selected_nodes=True,
                include_current_env=False,
                emit_insertion_signals=True))
        menu.addAction(action)

        msg = 'Remove selected'
        action = srnd_qt.base.utils.context_menu_add_menu_item(
            self,
            msg,
            icon_path=os.path.join(constants.ICONS_DIR_QT, 'remove.png'))
        action.setStatusTip(msg + VERIFY_MSG)
        action.setShortcut(Qt.SHIFT + Qt.ALT + Qt.Key_Minus)
        action.triggered.connect(self._model.remove_selected_host_app_nodes)
        menu.addAction(action)

        menu.addSeparator()

        ######################################################################

        msg = 'Whether all the defined sync rules are considered during next '
        msg += 'sync operation or not. When disabled all '
        msg += '{} are synced from host. '.format(self.HOST_APP_RENDERABLES_LABEL)

        action = srnd_qt.base.utils.context_menu_add_menu_item(
            self,
            'Sync rules active',
            checkable=True,
            checked=self._model.get_sync_rules_active())
        action.setStatusTip(msg)
        action.toggled.connect(self._model.set_sync_rules_active)
        menu.addAction(action)

        msg = 'Open dialog to choose pass sync rule/s to add. '
        msg += 'Sync rules will apply on next sync. '
        action = srnd_qt.base.utils.context_menu_add_menu_item(
            self,
            'Modify pass sync rule/s',
            icon_path=os.path.join(constants.ICONS_DIR_QT, 'tool_s01.png'))
        action.setStatusTip(msg)
        action.triggered.connect(
            lambda *x: self.modify_sync_rules(show_dialog=True))
        menu.addAction(action)

        menu.addSeparator()

        self._tree_view._populate_menu_with_pass_visibility_actions(menu)

        menu.addSeparator()

        return menu


    def _populate_and_show_sync_menu(self, pos=None):
        '''
        Populate then show the sync menu at cursor position.

        Args:
            pos (QPoint):
        '''
        menu = self._populate_sync_menu()
        pos = pos or QCursor.pos()
        menu.exec_(pos)


    def _create_context_menu_group_options(self, show=True):
        '''
        Build a QMenu for group and ungroup options.

        Args:
            show (bool):

        Returns:
            menu (QtGui.QMenu):
        '''
        menu = QMenu()

        msg = 'Group selected environment/s'
        action = srnd_qt.base.utils.context_menu_add_menu_item(self, msg)
        msg += 'or create empty group'
        action.setStatusTip(msg)
        action.triggered.connect(
            lambda *x: self._tree_view.group_selected_items())
        menu.addAction(action)

        msg = 'Ungroup selected environment/s'
        action = srnd_qt.base.utils.context_menu_add_menu_item(self, msg)
        action.setStatusTip(msg)
        action.triggered.connect(
            lambda *x: self._tree_view.ungroup_selected_items())
        menu.addAction(action)

        if show:
            pos = QCursor.pos()
            menu.exec_(pos)

        return menu


    def _create_context_menu_missing_render_nodes(self, show=False):
        '''
        Build a QMenu to show names of missing host app render nodes.

        Args:
            show (bool):

        Returns:
            menu (QtGui.QMenu):
        '''
        menu = QMenu()

        item_full_names = self._model.get_all_missing_host_app_render_node_names()

        for item_full_name in item_full_names:
            name = item_full_name.split('/')[-1]
            action = srnd_qt.base.utils.context_menu_add_menu_item(self, name)
            msg = 'Full name: {}'.format(item_full_name)
            action.setStatusTip(msg)
            method_to_call = functools.partial(
                self._model.add_render_nodes,
                [item_full_name])
            action.triggered.connect(method_to_call)
            menu.addAction(action)

        if show:
            pos = QCursor.pos()
            menu.exec_(pos)

        return menu


    def _populate_render_menu(self):
        '''
        Build a menu to contain all Render actions.

        Returns:
            menu (QtGui.QMenu):
        '''
        menu = self._menu_render
        if not menu:
            return
        menu.clear()

        font_italic = QFont()
        font_italic.setFamily(constants.FONT_FAMILY)
        font_italic.setItalic(True)

        # msg = 'Launch render summary'
        # action = srnd_qt.base.utils.context_menu_add_menu_item(self, msg)
        # action.setFont(font_italic)
        # menu.addAction(action)

        self._tree_view._add_render_actions_to_menu(menu, include_batch_all=True)

        return menu


    def _set_session_data_is_recalled_after_sync(self, value=True):
        '''
        Set whether the previous session data is recalled after Sync is performed.

        Args:
            value (bool):
        '''
        value = bool(value)
        self._model.set_session_data_is_recalled_after_sync(value)
        # This option disables another related option
        if value:
            self._model.set_session_data_recalled_from_resource_after_sync(False)


    def _set_session_data_recalled_from_resource_after_sync(self, value=True):
        '''
        Set whether to recall session data from multiShotSubmitter resource after sync is performed.

        Args:
            is_recalled (bool):
        '''
        value = bool(value)
        self._model.set_session_data_recalled_from_resource_after_sync(value)
        # This option disables another related option
        if value:
            self._model.set_session_data_is_recalled_after_sync(False)


    def _create_context_menu_get_assigned_shots(self, show=True):
        '''
        Build a QMenu for get assigned shots
        options (spawned from MenuBarHeaderWidget).

        Args:
            show (bool):

        Returns:
            menu (QtGui.QMenu):
        '''
        pos = QCursor.pos()

        menu = QMenu()

        action = srnd_qt.base.utils.context_menu_add_menu_item(
            self,
            constants.LABEL_GET_ALL_ASSIGNED_SHOTS_FOR_SEQUENCE,
            icon_path=os.path.join(constants.ICONS_DIR_QT, 'user_s01.png'))
        action.setStatusTip(constants.LABEL_GET_ALL_ASSIGNED_SHOTS_FOR_SEQUENCE)
        action.triggered.connect(
            lambda *x: self._model.populate_assigned_shots(
                sync_production_data=True,
                current_sequence_only=True))
        menu.addAction(action)

        action = srnd_qt.base.utils.context_menu_add_menu_item(
            self,
            constants.LABEL_GET_ALL_ASSIGNED_SHOTS_FOR_PROJECT,
            icon_path=os.path.join(constants.ICONS_DIR_QT, 'user_s01.png'))
        action.setStatusTip(constants.LABEL_GET_ALL_ASSIGNED_SHOTS_FOR_PROJECT)
        action.triggered.connect(
            lambda *x: self._model.populate_assigned_shots(
                sync_production_data=True))
        menu.addAction(action)

        action = srnd_qt.base.utils.context_menu_add_menu_item(
            self,
            constants.LABEL_GET_ALL_SHOTS_FOR_SEQUENCE,
            icon_path=os.path.join(constants.ICONS_DIR_QT, 'user_s01.png'))
        action.setStatusTip(constants.LABEL_GET_ALL_SHOTS_FOR_SEQUENCE)
        action.triggered.connect(
            lambda *x: self._model.add_environments_of_current_sequence())
        menu.addAction(action)

        action = srnd_qt.base.utils.context_menu_add_menu_item(
            self,
            "Add current oz",
            icon_path=os.path.join(constants.ICONS_DIR_QT, 'user_s01.png'))
        msg = "Add shot for current shells $OZ_CONTEXT."
        action.setStatusTip(msg)
        action.triggered.connect(
            lambda *x: self._model.add_environment_for_current_context())
        menu.addAction(action)

        if show:
            menu.exec_(pos)

        return menu


    def _create_context_menu_column_actions(self, show=True):
        '''
        Build a QMenu for column actions.

        Args:
            show (bool): show the menu after populating or not

        Returns:
            menu (QtGui.QMenu):
        '''
        pos = QCursor.pos()

        menu = QMenu('Column actions', self)

        font_italic = QFont()
        font_italic.setFamily(constants.FONT_FAMILY)
        font_italic.setItalic(True)

        msg = 'Column actions'
        action = srnd_qt.base.utils.context_menu_add_menu_item(self, msg)
        action.setFont(font_italic)
        menu.addAction(action)

        action = srnd_qt.base.utils.context_menu_add_menu_item(
            self,
            'Reset column widths')
        action.triggered.connect(self._reset_column_sizes)
        menu.addAction(action)

        action = srnd_qt.base.utils.context_menu_add_menu_item(
            self,
            'Alphabetize columns')
        action.triggered.connect(self._tree_view.setup_columns)
        menu.addAction(action)

        if show:
            menu.exec_(pos)

        return menu


    def _build_menu_edit(self, parent):
        '''
        Build a QMenu for Edit commands.
        Note: This menu is populated on demand when clicked.

        Args:
            parent (QtGui.QWidget): target Qt widget

        Returns:
            menu (QtGui.QMenu):
        '''
        menu = QMenu('Edit', parent)
        return menu


    def _build_menu_shots(self, parent):
        '''
        Build a QMenu for shots or assets commands.
        Note: This menu is populated on demand when clicked.

        Args:
            parent (QtGui.QWidget): target Qt widget

        Returns:
            menu (QtGui.QMenu):
        '''
        tree = 'shots'
        try:
            tree = os.getenv('OZ_CONTEXT').split('/')[2]
        except Exception:
            pass
        menu = QMenu(tree.title(), parent)
        return menu


    def _build_menu_sync(self, parent):
        '''
        Build a QMenu for Sync commands.
        Note: This menu is populated on demand when clicked.

        Args:
            parent (QtGui.QWidget): target Qt widget

        Returns:
            menu (QtGui.QMenu):
        '''
        menu = QMenu('Passes', parent)
        return menu


    def _build_menu_render(self, parent):
        '''
        Build a QMenu for Render commands.
        Note: This menu is populated on demand when clicked.

        Args:
            parent (QtGui.QWidget): target Qt widget

        Returns:
            menu (QtGui.QMenu):
        '''
        menu = QMenu('Render', parent)
        return menu


    def _populate_edit_menu(self):
        '''
        Build a menu to toggle certain panels visible or not.
        Reimplemented method.

        Returns:
            menu (QtGui.QMenu):
        '''
        menu = self._menu_edit
        if not menu:
            return
        menu.clear()

        selection_model = self._tree_view.selectionModel()
        selection = selection_model.selectedIndexes()

        has_selection = bool(selection)

        # action = srnd_qt.base.utils.context_menu_add_menu_item(self, 'Undo')
        # action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        # action.setDisabled(True)
        # # action.toggled.connect(self.undo)
        # menu.addAction(action)

        # action = srnd_qt.base.utils.context_menu_add_menu_item(self, 'Redo')
        # action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        # action.setDisabled(True)
        # # action.toggled.connect(self.undo)
        # menu.addAction(action)

        # menu.addSeparator()

        action = srnd_qt.base.utils.context_menu_add_menu_item(
            self,
            'Copy overrides',
            icon_path=os.path.join(ICONS_DIR, 'copy_s01.png'))
        action.setShortcut('CTRL+SHIFT+C')
        action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        action.triggered.connect(self._tree_view.copy_overrides_for_selection)
        action.setVisible(has_selection)
        menu.addAction(action)

        action = srnd_qt.base.utils.context_menu_add_menu_item(
            self,
            'Paste overrides',
            icon_path=os.path.join(ICONS_DIR, 'paste_s01.png'))
        action.setShortcut('CTRL+SHIFT+V')
        action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        action.triggered.connect(self._tree_view.paste_overrides_for_selection)
        action.setVisible(self._tree_view.is_overrides_ready_for_paste())
        menu.addAction(action)

        action = srnd_qt.base.utils.context_menu_add_menu_item(
            self,
            'Clear overrides',
            icon_path=os.path.join(SRND_QT_ICONS_DIR, 'dismiss.png'))
        action.setShortcut('CTRL+BACKSPACE')
        action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        action.triggered.connect(
            lambda *x: self._tree_view._tree_view_operations(
                operation='Clear overrides'))
        action.setVisible(has_selection)
        menu.addAction(action)

        overrides_menu = self._tree_view._create_context_menu(
            show=False,
            include_search=False)
        if overrides_menu and overrides_menu.actions():
            menu.addMenu(overrides_menu)

        menu.addSeparator()

        action = srnd_qt.base.utils.context_menu_add_menu_item(
            self,
            'Create item selection set',
            icon_path=os.path.join(SRND_QT_ICONS_DIR, 'select_all_s01.png'))
        action.triggered.connect(self._tree_view.create_item_selection_set)
        action.setVisible(has_selection)
        menu.addAction(action)

        selection_sets_names = self._tree_view.get_item_selection_sets_names()
        if selection_sets_names:
            menu_select_by_selection_set = QMenu(
                'Select items by selection set',
                menu)
            icon = QIcon(os.path.join(SRND_QT_ICONS_DIR, 'select_all_s01.png'))
            menu_select_by_selection_set.setIcon(icon)
            menu.addMenu(menu_select_by_selection_set)
            for selection_set_name in self._tree_view.get_item_selection_sets_names():
                action = srnd_qt.base.utils.context_menu_add_menu_item(
                    self,
                    selection_set_name)
                method_to_call = functools.partial(
                    self._tree_view.select_named_selection_set,
                    selection_set_name)
                action.triggered.connect(method_to_call)
                menu_select_by_selection_set.addAction(action)

            menu_update_selection_set = QMenu('Update selection set', menu)
            menu.addMenu(menu_update_selection_set)

            for selection_set_name in selection_sets_names:
                action = srnd_qt.base.utils.context_menu_add_menu_item(
                    self,
                    selection_set_name)
                method_to_call = functools.partial(
                    self._tree_view.update_selection_set_by_name,
                    selection_set_name)
                action.triggered.connect(method_to_call)
                menu_update_selection_set.addAction(action)

            menu_delete_selection_set = QMenu('Delete selection set', menu)
            icon = QIcon(os.path.join(ICONS_DIR, 'delete_s01.png'))
            menu_delete_selection_set.setIcon(icon)
            menu.addMenu(menu_delete_selection_set)

            for selection_set_name in selection_sets_names:
                action = srnd_qt.base.utils.context_menu_add_menu_item(
                    self,
                    selection_set_name)
                method_to_call = functools.partial(
                    self._tree_view.delete_selection_set_by_name,
                    selection_set_name)
                action.triggered.connect(method_to_call)
                menu_delete_selection_set.addAction(action)

            action = srnd_qt.base.utils.context_menu_add_menu_item(
                self,
                'Delete all selection sets',
                icon_path=os.path.join(ICONS_DIR, 'delete_s01.png'))
            action.triggered.connect(self._tree_view.delete_all_selection_sets)
            menu.addAction(action)

        menu.addSeparator()

        action = srnd_qt.base.utils.context_menu_add_menu_item(
            self,
            'Select by UUIDs or identifiers',
            icon_path=os.path.join(SRND_QT_ICONS_DIR, 'select_all_s01.png'))
        msg = 'Open dialog to paste UUIDs or identifiers to select'
        action.setStatusTip(msg)
        action.triggered.connect(self._tree_view.open_uuids_or_identifiers_select_dialog)
        menu.addAction(action)

        menu.addSeparator()

        action = srnd_qt.base.utils.context_menu_add_menu_item(
            self,
            'Preferences',
            icon_path=os.path.join(SRND_QT_ICONS_DIR, 'cog.png'))
        action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        action.triggered.connect(
            lambda *x: self._model.open_preferences_dialog())
        menu.addAction(action)

        return menu


    def _populate_shots_menu(self):
        '''
        Build a menu to toggle certain panels visible or not.
        Reimplemented method.

        Returns:
            menu (QtGui.QMenu):
        '''
        menu = self._menu_shots
        if not menu:
            return
        menu.clear()

        tree = os.getenv('TREE') or 'shots'
        shot_or_asset = tree.rstrip('s')

        # action = srnd_qt.base.utils.context_menu_add_menu_item(
        #     self,
        #     'Add {}s'.format(shot_or_asset),
        #     icon_path=os.path.join(constants.ICONS_DIR_QT, 'add.png'))
        # msg = 'Open dialog to add {}s'.format(shot_or_asset)
        # action.setStatusTip(msg)
        # action.setShortcut('CTRL+SHIFT+E')
        # action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        # action.triggered.connect(
        #     lambda *x: self._model.add_environment(show_dialog=True))
        # menu.addAction(action)

        menu_add_assigned_shots = self._create_context_menu_get_assigned_shots(show=False)
        if menu_add_assigned_shots:
            for action in menu_add_assigned_shots.actions():
                menu.addAction(action)

        menu.addSeparator()

        return menu


    def _populate_view_menu(self):
        '''
        Build a menu to toggle certain panels visible or not.
        Reimplemented method.

        Returns:
            menu (QtGui.QMenu):
        '''
        menu = base_window.BaseWindow._populate_view_menu(self)

        # Change default name of srnd_qt view menu to Layout
        menu.setTitle('Layout')

        before_action = menu.actions()[0]

        ######################################################################

        menu_column = self._create_context_menu_column_actions(show=False)
        if menu_column:
            menu.insertMenu(before_action, menu_column)

        menu.insertSeparator(before_action)

        return menu


    def set_status_bar_visible(self, visible):
        '''
        Override whether the status bar and auto save session widget
        is visible or not.

        Args:
            visible (bool):
        '''
        status_bar = self.statusBar()
        if status_bar:
            status_bar.setVisible(visible)


    ##########################################################################
    # Preferences


    def apply_preference(self, name, value):
        '''
        Apply a single preference with name and value to MSRS objects.
        This is callback for pref_changed of Preferences dialog, otherwise
        call this method directly with name and value to update MSRS objects.

        Args:
            name (str):
            value (object):

        Returns:
            handled (bool):
        '''
        if self._debug_mode:
            msg = 'Apply preference. Name: "{}". '.format(name)
            msg += 'Value: "{}"'.format(value)
            self.logMessage.emit(msg, logging.DEBUG)

        ######################################################################
        # General

        if name == 'callback_save_project':
            self.register_callback_project_save(bool(value))
            return True
        if name == 'callback_load_project':
            self.register_callback_project_load(bool(value))
            return True
        if name == 'callback_add_render_node':
            self.register_callback_render_node_create(bool(value))
            return True
        if name == 'callback_remove_render_node':
            self.register_callback_render_node_delete(bool(value))
            return True
        if name == 'callback_rename_render_node':
            self.register_callback_render_node_renamed(bool(value))
            return True
        if name == 'disable_callbacks_when_tab_not_active':
            self.set_callback_disabled_when_not_active_tab(bool(value))
            return True

        # Details
        if name == 'details_include_search':
            search_widget = self._details_widget.get_search_widget()
            if search_widget:
                search_widget.setVisible(bool(value))
            return True
        if name == 'details_show_selection_summary':
            self._details_widget.set_show_selection_summary(bool(value))
            return True
        if name == 'details_show_overrides':
            self._details_widget.set_show_overrides(bool(value))
            return True
        if name == 'details_show_override_badges':
            self._details_widget.set_show_override_badges(bool(value))
            return True
        if name == 'details_show_inherited_overrides':
            self._details_widget.set_show_inherited_overrides(bool(value))
            return True
        if name == 'details_limit_sections':
            self._details_widget.set_max_widget_count(int(value))
            return True
        if name == 'details_compute_version_preview_on_selection_change':
            self.set_auto_resolve_versions(bool(value))
            return True

        # Lighting info
        if name == 'lighting_info_show_selection_summary':
            self._lighting_info_widget.set_show_selection_summary(bool(value))
            return True

        # Panels
        if name == 'show_job_options_panel':
            value = str(value).lower()
            if 'hidden' in value:
                self._panel_job_options.setVisible(False)
            elif 'visible' in value:
                self._panel_job_options.setVisible(True)
            return True
        if name == 'show_lighting_info_panel':
            value = str(value).lower()
            if 'hidden' in value:
                self._panel_lighting_info.setVisible(False)
            elif 'visible' in value:
                self._panel_lighting_info.setVisible(True)
            return True
        if name == 'show_details_panel':
            value = str(value).lower()
            if 'hidden' in value:
                self._panel_details.setVisible(False)
            elif 'visible' in value:
                self._panel_details.setVisible(True)
            return True
        if name == 'show_log_panel':
            value = str(value).lower()
            if 'hidden' in value:
                self._panel_log_viewer.setVisible(False)
            elif 'visible' in value:
                self._panel_log_viewer.setVisible(True)
            return True
        if name == 'show_status_bar':
            status_bar = self.statusBar()
            if status_bar:
                status_bar.setVisible(bool(value))
            return True
        if name == 'show_toolbar':
            self._tool_bar_header.setVisible(bool(value))
            return True
        if name == 'show_context_buttons':
            self._widget_context_actions.setVisible(bool(value))
            return True
        if name == 'show_advanced_search':
            self.search_show_advanced(bool(value))
            return True
        if name == 'show_column_zoom':
            self._slider_column_scaling.setVisible(bool(value))
            return True
        # if name == 'show_menu_bar':
        #     menu_bar = self.menuBar()
        #     if menu_bar:
        #         menu_bar.setVisible(bool(value))
        #     return True

        # Passes
        if name == 'passes_refresh_behaviour':
            value = str(value).lower()
            if 'current session' in value:
                self._set_session_data_is_recalled_after_sync(True)
            elif 'saved session' in value:
                self._set_session_data_recalled_from_resource_after_sync(True)
            else:
                self._set_session_data_is_recalled_after_sync(False)
                self._set_session_data_recalled_from_resource_after_sync(False)
            return True
        if name == 'limit_refresh_to_existing_passes':
            self._model.set_sync_only_if_already_in_session(bool(value))
            return True

        # Session
        if name == 'session_auto_save_enabled':
            value = bool(value)
            self.set_session_auto_save(value)
            self._session_autosave_widget.set_session_auto_save_enabled(value)
            return True
        if name == 'session_auto_save_duration':
            self.set_session_auto_save_duration(int(value))
            return True
        if name == 'session_save_on_close':
            self.set_session_save_on_close(bool(value))
            return True
        if name == 'session_save_on_project_load':
            self.set_session_save_on_load_project(bool(value))
            return True
        if name == 'session_auto_recall_on_project_load':
            self.set_session_recall_when_loading_project(bool(value))
            return True

        # Shot / Asset
        if name == 'environment_frames_resolve_order':
            value = str(value).lower()
            env_first = 'environment first' in value
            self._model.set_frame_resolve_order_env_first_on_create(env_first)
            return True

        # Submission
        if name == 'show_save_reminder_dialog':
            self._show_save_dialog_on_submit = bool(value)
            return True
        # if name == 'auto_refresh_from_shotgun':
        #     self._model.set_auto_refresh_from_shotgun(bool(value))
        #     return True

        # Summary & validation
        if name == 'show_summary_dialog':
            show_summary = bool(value)
            self._model.set_show_summary_dialog(show_summary)
            self._update_launch_render_label(show_summary=show_summary)
            return True
        if name == 'cook_more_summary_details':
            self._model.set_cook_more_summary_details(bool(value))
            return True
        if name == 'validation_auto_start':
            self._model.set_validation_auto_start(bool(value))
            return True
        if name == 'summary_auto_scroll_to_validation':
            self._model.set_summary_auto_scroll_to_validation(bool(value))
            return True
        if name == 'render_summary':
            value = str(value)
            self._widget_render_estimate.set_render_summary_mode(value)
        if name == 'render_summary_graph_show_shot_labels':
            value = bool(value)
            self._widget_render_estimate.set_show_shot_labels(value)
        if name == 'render_summary_graph_show_pass_indicator_lines':
            value = bool(value)
            self._widget_render_estimate.set_show_pass_indicator_lines(value)
        if name == 'compute_render_estimate':
            value = bool(value)
            # Setter and compute at once
            self._model.compute_render_estimates_for_environments(compute=value)
            return True

        # View
        # if name == 'orientation_on_startup': # TODO: NotImplemented
        #     self.set_orientation(str(value))
        #     return True
        # if name == 'auto_orientation_threshold': # TODO: NotImplemented
        #     self.set_auto_orientation_threshold(int(value))
        #     return True

        if name == 'main_view_menu_style':
            some_actions_at_top = 'organized' not in str(value).lower()
            self._tree_view.set_menu_some_actions_at_top(some_actions_at_top)
            return True
        if name == 'main_view_include_search':
            self._tree_view.set_menu_include_search(bool(value))
            return True
        if name == 'draw_dependency_overlays':
            self._overlay_widget.set_draw_all_dependency_overlays(bool(value))
            return True
        if name == 'show_shotsub_thumbnails':
            self._tree_view.set_show_environment_thumbnails(value=bool(value))
            return True
        if name == 'shotsub_thumbnails_static':
            static = bool(value)
            show = self._model.get_preference_value('show_shotsub_thumbnails') or False
            self._tree_view.set_show_environment_thumbnails(
                value=bool(show),
                static=static)
            return True
        if name == 'show_full_environment_names':
            self.set_show_full_environments(bool(value))
            return True
        if name == 'show_render_item_disabled_hints':
            self._tree_view.header().set_draw_header_disabled_hint(bool(value))
            return True
        if name == 'show_render_item_colour_hints':
            self._tree_view.header().set_draw_header_node_colour(bool(value))
            return True
        if name == 'listen_to_jobs':
            self.set_listen_to_jobs(bool(value))
            return True
        if name == 'listen_to_jobs_frequency':
            self.set_listen_to_jobs_frequency(int(value))
            return True
        if name == 'pass_disabled_style':
            void = 'void' in str(value).lower()
            self._tree_view.set_disabled_passes_are_void_style(void)
            return True
        if name == 'environment_colour':
            color = QColor(str(value)) # hex
            rgb = [color.red(), color.green(), color.blue()]
            self._tree_view.set_environment_colour(rgb)
            lighting_info_view = self._lighting_info_widget.get_lighting_info_tree_view()
            lighting_info_view.update()
            return True
        if name == 'pass_colour':
            color = QColor(str(value)) # hex
            rgb = [color.red(), color.green(), color.blue()]
            self._tree_view.set_pass_colour(rgb)
            return True
        if name == 'unqueued_colour':
            color = QColor(str(value)) # hex
            rgb = [color.red(), color.green(), color.blue()]
            self._tree_view.set_unqueued_colour(rgb)
            return True
        if name == 'pass_disabled_colour':
            color = QColor(str(value)) # hex
            rgb = [color.red(), color.green(), color.blue()]
            self._tree_view.set_pass_disabled_colour(rgb)
            return True
        if name == 'render_node_colour':
            color = QColor(str(value)) # hex
            rgb = [color.red(), color.green(), color.blue()]
            self._tree_view.set_render_item_colour(rgb)
            return True
        if name == 'override_standard_colour':
            color = QColor(str(value)) # hex
            rgb = [color.red(), color.green(), color.blue()]
            self._tree_view.set_override_standard_colour(rgb)
            return True
        if name == 'override_standard_not_colour':
            color = QColor(str(value)) # hex
            rgb = [color.red(), color.green(), color.blue()]
            self._tree_view.set_override_standard_not_colour(rgb)
            return True
        if name == 'job_override_colour':
            color = QColor(str(value)) # hex
            rgb = [color.red(), color.green(), color.blue()]
            self._tree_view.set_job_override_colour(rgb)
            return True
        if name == 'render_override_standard_colour':
            color = QColor(str(value)) # hex
            rgb = [color.red(), color.green(), color.blue()]
            self._tree_view.set_render_override_standard_colour(rgb)
            return True
        if name == 'dependency_arrow_colours':
            color = QColor(str(value)) # hex
            rgb = [color.red(), color.green(), color.blue()]
            self._overlay_widget.set_dependency_arrow_colour(rgb)
            return True

        ######################################################################
        # Advanced

        # Other
        if name == 'debug_mode':
            self.toggle_debug_mode(bool(value))
            return True
        if name == 'modify_host_app':
            self._model.set_update_host_app(bool(value))
            return True

        msg = 'Apply preference not handled. Name: "{}". '.format(name)
        msg += 'Value: "{}"'.format(value)
        self.logMessage.emit(msg, logging.WARNING)

        return False


    ##########################################################################
    # Session methods


    def session_new(self, full=True):
        '''
        Start a new session in this Multi Shot Render Submitter.
        '''
        msg = 'Session New'
        self.add_log_message(msg, logging.INFO)

        current_project = self.get_current_project()

        # Reset any registered session widgets to default values
        session_data = base_window.BaseWindow.session_new(self)

        self._reset_other_options_to_defaults()

        # Force these signals to update.
        # Since callbacks are not triggered by session_new.
        self._slider_column_scaling.valueChanged.emit(
            self._slider_column_scaling.value())

        self._update_project_widget(str())

        self._session_autosave_widget.set_project_is_saved(False)

        if self._tree_view.get_in_wait_on_interactive_mode():
            self._tree_view.exit_wait_on_interactive()
        self._overlay_widget.clear_all()

        self._model.clear_data()

        self._model.set_sync_rules_active(constants.SYNC_RULES_ACTIVE)
        self._model.set_sync_rules_include(list())
        self._model.set_sync_rules_exclude(list())

        self._tree_view.clear_data()

        ######################################################################

        # Apply default preference states.
        value = self._model.get_preference_value('send_summary_emails_for_new_session')
        if isinstance(value, bool):
            widget = self._job_options_widget.get_send_summary_email_on_submit()
            widget.setChecked(value)
            self._model.set_send_summary_email_on_submit(value)

        ######################################################################
        # Perform any updates that occur on selection changed

        self._details_widget.clear_cached_states()
        self._update_panels()

        ######################################################################

        self._toggle_visible_widget.show_initial_widget()

        self.update_estimate()

        return session_data


    def session_load(
            self,
            session_path=None,
            load_project=True,
            start_new_session=True,
            sync_from_project=True,
            show_dialog=True):
        '''
        Session load - Get session json text file, parse dictionary,
        and apply state to model and view.
        Reimplemented from super class.

        Args:
            session_path (str): load a session at path or open dialog to pick
            load_project (bool): optionally load project specified in session data or not.
                if show dialog is True, then the user gets to pick this from dialog
            start_new_session (bool): optionally clear the existing session before loading
                a new session. Note: this is just to avoid the splash widget flashing up,
                if new session was started run before this.
            sync_from_project (bool):
            show_dialog (bool): optionally show popup dialog/s

        Returns:
            session_path (str): location where session was loaded or None
        '''
        self._is_loading_session = True

        # Disable features using timers and threads while loading session
        listen_to_jobs_was_enabled = self.get_listen_to_jobs()
        self.set_listen_to_jobs(False)
        auto_save_was_enabled = self.get_session_auto_save_enabled()
        self.set_session_auto_save(False)

        msg = 'Session load begin. Session path: "{}"'.format(session_path)
        self.add_log_message(msg, logging.INFO)

        # User picks a session file path from a dialog (or already provided),
        # and extract session data
        session_path, session_data = base_window.BaseWindow.session_load(
            self,
            session_path=session_path,
            apply_data=False, # defer apply data until after checking project
            clear_session=False, # defer clearing the session to later
            show_dialog=show_dialog)
        session_data = session_data or dict()

        if not session_path:
            msg = 'Skipped loading session data. No session path'
            self.add_log_message(msg, logging.WARNING)
            # Revert timers and threads back to previous state
            self.set_listen_to_jobs(listen_to_jobs_was_enabled)
            self.set_session_auto_save(auto_save_was_enabled)
            self._is_loading_session = False
            return

        msg = 'Loading session path: "{}"'.format(session_path)
        self.statusBar().showMessage(msg, 2000)

        # Project is specified in session data, verify it exists, and ask user if it should be opened
        project = session_data.get('project')
        if project and load_project:
            msg = 'Session data has {} '.format(self.HOST_APP)
            msg += '{}: "{}"'.format(self.HOST_APP_DOCUMENT, project)
            self.add_log_message(msg, logging.DEBUG)

            # Cast hyref to location
            project_location = project
            if project and project.startswith(('hyref:', 'urn:')):
                project_location, msg = utils.get_hyref_default_location(
                    project,
                    as_file_path=True)
                if not project_location and msg:
                    self.add_log_message(msg, logging.CRITICAL)

            # Check project is still actually on disc
            project_online = os.path.isfile(project_location) if project_location else False
            if project_location and not project_online:
                msg = '{} {} is no longer online. '.format(self.HOST_APP, self.HOST_APP_DOCUMENT)
                msg += '{}: <b>{}</b>. '.format(self.HOST_APP_DOCUMENT, project)
                msg += 'Session data cannot be synced. '
                self.add_log_message(msg, logging.CRITICAL)
                if show_dialog:
                    reply = QMessageBox.warning(
                        self,
                        '{} {} no longer available!'.format(self.HOST_APP, self.HOST_APP_DOCUMENT),
                        msg,
                        QMessageBox.Ok)

            # In UI mode, so ask user if project should also be loaded to sync data to
            if project and project_online and show_dialog:
                msg = 'Do you want to load the {} {}:'.format(self.HOST_APP, self.HOST_APP_DOCUMENT)
                msg += '<br><b>{}</b>'.format(project)
                msg += '<br>and sync session data. '
                msg += 'Otherwise click ignore to sync data to current project. '
                msg += '<br><br><i>Note: When syncing old session data created For '
                msg += 'another project to current project, {} '.format(self.HOST_APP_RENDERABLES_LABEL)
                msg += 'that no longer exist will not be shown.</i>'

                reply = QMessageBox.question(
                    self,
                    'Load Scene With Session Data?',
                    msg,
                    QMessageBox.Ok | QMessageBox.Ignore | QMessageBox.Close)
                if reply == QMessageBox.Close:
                    # Revert timers and threads back to previous state
                    self.set_listen_to_jobs(listen_to_jobs_was_enabled)
                    self.set_session_auto_save(auto_save_was_enabled)
                    self._is_loading_session = False
                    return

                load_project = reply == QMessageBox.Ok
                if load_project:
                    msg = 'Skipped loading project before applying session data'
                    self.add_log_message(msg, logging.WARNING)

        # Clear project from session data, to avoid callback running when setting hyref
        if 'project' in session_data:
            del session_data['project']

        # Clear MSRS data model and Job options widgets to defaults
        if start_new_session:
            self.session_new()

        # Avoid the callbacks running on particular widgets.
        project_widget = self.get_menu_bar_header_widget().get_project_widget()
        project_widget.blockSignals(True)

        # Now actually override global session data widgets
        session_path, session_data = base_window.BaseWindow.session_load(
            self,
            session_path=session_path,
            session_data=session_data, # use the previously extracted session data
            apply_data=True, # apply session data on global registered widgets now
            clear_session=False,
            show_dialog=show_dialog)

        self._model.set_sync_rules_active(bool(session_data.get('sync_rules_active')))
        self._model.set_sync_rules_include(session_data.get('sync_rules_include', list()))
        self._model.set_sync_rules_exclude(session_data.get('sync_rules_exclude', list()))

        search_filter_widget = self.get_menu_bar_header_widget().get_search_filter_widget()
        search_filters = session_data.get('search_filters', dict())
        # Disable updates
        search_filter_widget.set_auto_update(False)
        search_filter_widget.set_search_filters(search_filters)
        auto_update = session_data.get('auto_update', True)
        search_filter_widget.set_auto_update(bool(auto_update))

        # Enable callbacks on specific widgets
        project_widget.blockSignals(False)

        # Disable thread listening to Job/s while loading project
        listen_to_jobs_was_enabled = self.get_listen_to_jobs()
        self.set_listen_to_jobs(False)

        # Load the project from session data (if available)
        if load_project and project:
            # Unregister project and render callbacks
            callback_save_active = self.get_callback_save_session_on_project_save()
            callback_load_active = self.get_callback_restore_session_on_project_load()
            callback_add_pass = self.get_callback_add_pass_on_render_node_create()
            callback_remove_pass = self.get_callback_remove_pass_on_render_node_delete()
            callback_update_pass_name = self.get_callback_update_pass_name_on_render_node_rename()
            self.register_callback_project_save(register=False)
            self.register_callback_project_load(register=False)
            self.register_callback_render_node_create(register=False)
            self.register_callback_render_node_delete(register=False)
            self.register_callback_render_node_renamed(register=False)

            # Force auto save session off while loading project
            self.set_session_auto_save(False)

            # Open the project specified in session data, before syncing data from host app.
            # NOTE: This will also update the HyrefPreviewWidget with the project
            self.load_project(
                project=project,
                sync_from_project=False, # defer sync to below
                recall_session_data=False, # do not recall MSRS session resource of project
                show_dialog=False) # already recalling specified data directly in this method

            # Keep session auto save disabled
            self.set_session_auto_save(False)

            # Register project and render callbacks.
            # Only register callbacks if previously enabled.
            self.register_callback_project_load(register=callback_load_active)
            self.register_callback_project_save(register=callback_save_active)
            self.register_callback_render_node_create(register=callback_add_pass)
            self.register_callback_render_node_delete(register=callback_remove_pass)
            self.register_callback_render_node_renamed(register=callback_update_pass_name)

            # Fallback cached value, in case API cannot get current project when in standalone host app mode
            self._model._set_project_from_external_widget(project)

        # Now populate all Render nodes and environment from current project.
        # NOTE: Will call clear_model before sync is performed.
        if sync_from_project:
            limit_to = list()
            if self._model.get_sync_only_if_already_in_session() and session_data:
                multi_shot_data = session_data.get(constants.SESSION_KEY_MULTI_SHOT_DATA, dict())
                render_nodes_data = multi_shot_data.get(constants.SESSION_KEY_RENDER_NODES, dict())
                limit_to = sorted(render_nodes_data.keys())
            self.sync_render_nodes_and_environments(
                include_current_env=False,
                limit_to=limit_to) # limit sync to render nodes in session data

        # Apply the search filter
        search_filter = session_data.get('search_filter') or str()
        self.search_view_by_filters(search_filter)

        # Now apply the rest of session data to other widget and main model
        if session_data:
            session_data = constants.conform_session_data(session_data)
            self._load_other_options_from_session_data(session_data)
            self._tree_view.apply_session_data(session_data)

        self.apply_visibility(session_data)

        # Revert listen to jobs back to previously loaded session data
        self.set_listen_to_jobs(listen_to_jobs_was_enabled)

        self._overlay_widget.update_overlays()

        self.set_session_auto_save(auto_save_was_enabled)

        self._is_loading_session = False

        return session_path


    def apply_visibility(self, session_data):
        '''
        Resolve search filters then apply render node states, and then finally
        apply any cached row visibility states.

        Args:
            session_data (dict):
        '''
        # First apply the search filter
        search_filter = session_data.get('search_filter') or str()
        self.search_view_by_filters(search_filter)
        # Apply column states
        render_nodes_data = session_data.get(constants.SESSION_KEY_RENDER_NODES, dict())
        if render_nodes_data:
            self._tree_view.apply_render_nodes_session_data(render_nodes_data)
        # # Apply row visibility
        # visible_rows_data = session_data.get(constants.SESSION_KEY_VISIBLE_ROWS, dict())
        # if visible_rows_data:
        #     self._tree_view.apply_row_visibility_data(visible_rows_data)
        # Set column 0 size
        env_column_width = session_data.get(constants.SESSION_KEY_ENV_COLUMN_WIDTH, 0)
        if env_column_width and env_column_width > 40:
            self._tree_view.setColumnWidth(0, env_column_width)


    def session_get_data(self):
        '''
        Get session data for all widgets registered by BaseWindow.register_session_widget,
        and then also collect any other session data directly from MSRS sobjects.
        Reimplemented from super class.

        Returns:
            session_data (dict):
        '''
        # Get all data from registered Job Options widgets
        session_data = base_window.BaseWindow.session_get_data(self)

        # Get currently open project from host app
        current_project = self.get_current_project()
        if current_project:
            session_data['project'] = current_project

        session_data['session_data_version'] = '0.3'

        search_filter_widget = self.get_menu_bar_header_widget().get_search_filter_widget()
        filter_session_data = search_filter_widget.get_session_data()
        if filter_session_data:
            session_data.update(filter_session_data)

        # Get model data of MSRS items
        _session_data = self._tree_view.get_session_data() or dict()
        session_data.update(_session_data)

        return session_data


    def _register_widgets(self):
        '''
        Register widgets as important session data items.
        These registered items will automatically get reset to default
        values when New Session is performed, and the values are automatically
        gathered during Save Session, and loaded on Load Session.
        '''
        msg = 'Registering Session Widgets'
        self.add_log_message(msg, logging.DEBUG)

        ######################################################################
        # Register widgets inside MenuBarHeaderWidget

        self.register_session_widget(
            self.get_menu_bar_header_widget().get_version_system_global_widget(),
            'version_global_system',
            default=constants.DEFAULT_CG_VERSION_SYSTEM)

        msg = 'Choose {} scene to configure for '.format(self.HOST_APP)
        msg += 'multishot rendering.'
        self.register_session_widget(
            self.get_menu_bar_header_widget().get_project_widget(),
            'project',
            default=str(),
            tool_tip=msg)

        widget = self.get_menu_bar_header_widget().get_search_widget()
        self.register_session_widget(
            widget,
            'search_filter',
            default=str())

        ######################################################################
        # Register widgets inside JobOptionsWidget

        job_options_widget = self._job_options_widget

        widget = job_options_widget.get_dispatch_deferred_widget()
        self.register_session_widget(
            widget,
            'dispatch_deferred',
            default=constants.DISPATCH_DEFERRED,
            block_signals=False)

        widget = job_options_widget.get_snapshot_before_dispatch_widget()
        self.register_session_widget(
            widget,
            'snapshot_before_dispatch',
            default=constants.SNAPSHOT_BEFORE_DISPATCH,
            block_signals=False)

        widget = job_options_widget.get_launch_paused_widget()
        self.register_session_widget(
            widget,
            'launch_paused',
            default=constants.LAUNCH_PAUSED,
            block_signals=False)

        widget = job_options_widget.get_launch_paused_expires_widget()
        self.register_session_widget(
            widget,
            'launch_paused_expires',
            default=constants.LAUNCH_PAUSED_EXPIRES,
            block_signals=False)

        widget = job_options_widget.get_launch_zero_tier_widget()
        self.register_session_widget(
            widget,
            'launch_zero_tier',
            default=constants.LAUNCH_ZERO_TIER,
            block_signals=False)

        widget = job_options_widget.get_apply_render_overrides_widget()
        self.register_session_widget(
            widget,
            'apply_render_overrides',
            default=constants.APPLY_RENDER_OVERRIDES,
            block_signals=False)

        widget = job_options_widget.get_apply_dependencies_widget()
        self.register_session_widget(
            widget,
            'apply_dependencies',
            default=constants.APPLY_DEPEDENCIES,
            block_signals=False)

        widget = job_options_widget.get_email_additional_users_widget()
        self.register_session_widget(
            widget,
            'email_additional_users',
            default=constants.DEFAULT_EMAIL_ADDITIONAL_USERS,
            block_signals=False)

        widget = job_options_widget.get_global_job_identifier_widget()
        self.register_session_widget(
            widget,
            'global_job_identifier',
            default=constants.DEFAULT_GLOBAL_JOB_IDENTIFIER,
            tool_tip=constants.TOOLTIP_GLOBAL_JOB_IDENTIFIER,
            block_signals=False)

        widget = job_options_widget.get_global_submit_description_widget()
        self.register_session_widget(
            widget,
            'description_global',
            default=constants.DEFAULT_DESCRIPTION_GLOBAL,
            tool_tip=constants.TOOLTIP_DESCRIPTION_GLOBAL,
            block_signals=False)

        widget = job_options_widget.get_send_summary_email_on_submit()
        self.register_session_widget(
            widget,
            'send_summary_email_on_submit',
            default=constants.DEFAULT_SEND_SUMMARY_EMAIL_ON_SUBMIT,
            tool_tip=constants.TOOLTIP_SEND_EMAIL,
            block_signals=False)


    def _reset_other_options_to_defaults(self):
        '''
        Reset any other cached options when session new is invoked.
        NOTE: Any widgets registered via BaseWindow.register_session_widget will
        automatically revert to default value as the super session_new is called.
        NOTE: Preferences are separate and don't get reset between sessions.
        '''
        msg = 'Resetting other options to default values'
        self.add_log_message(msg, logging.DEBUG)

        self._columns_widths_cached = None

        self.search_reset()


    def _load_other_options_from_session_data(self, session_data=None):
        '''
        For widgets not registered via the BaseWindow.register_session_widget
        load from session data to MSRS data objects now.

        Args:
            session_data (dict):
        '''
        if not session_data:
            session_data = dict()

        msg = 'Loading session data to MSRS objects...'
        self.add_log_message(msg, logging.DEBUG)

        version_system = session_data.get('version_global_system')
        if version_system != None:
            version_global_widget = self.get_menu_bar_header_widget().get_version_system_global_widget()
            if isinstance(version_system, int) or str(version_system).isdigit():
                version_system = 'v' + str(version_system)
            version_global_widget.setText(str(version_system))


    ##########################################################################
    # Listen to already launched MSRS Plow jobs for render progress


    def _listen_to_previously_launched_jobs(
            self,
            start=False,
            every_num_seconds=None):
        '''
        Start listening to previously launched MSRS Plow job/s to gather render progress

        Args:
            start (bool): whether to start timer now
            every_num_seconds (int): how often to auto save file (in seconds)
        '''
        seconds = self._model.get_listen_to_jobs_frequency()
        every_num_seconds = every_num_seconds or seconds or constants.LISTEN_TO_JOBS_FREQUENCY

        from srnd_multi_shot_render_submitter import render_progress

        self._thread_listen_to_jobs = render_progress.CollectRenderProgressThread()
        self._thread_listen_to_jobs.set_frequency(every_num_seconds)
        self._thread_listen_to_jobs.collectedResults.connect(
            self._apply_render_progress_thread_result)

        if start:
            self.set_listen_to_jobs(True)


    def set_listen_to_jobs(self, value=True):
        '''
        Set whether to listen to previously launched Plow Job/s for render progress updates.

        Args:
           value (bool):
        '''
        # Update model listening value
        self._model.set_listen_to_jobs(value)

        # Clear any render progress hints from the MSRS view.
        self._clear_render_progress()

        # Update what to check for next render progress check
        details_to_collect = self._collect_details_for_render_progress_check() or dict()
        self._thread_listen_to_jobs.set_details_to_collect(details_to_collect)

        msg = 'Setting listen to previously launched MSRS job/s: {}'.format(value)
        self.logMessage.emit(msg, logging.DEBUG)

        # Request start or stop listening to previously launched Plow jobs
        if value:
            self._thread_listen_to_jobs.start_listening()
        else:
            self._thread_listen_to_jobs.stop_listening()


    def get_listen_to_jobs(self):
        '''
        Get whether listen to jobs is running or not.

        Args:
           enabled (bool):
        '''
        return self._thread_listen_to_jobs.isRunning()


    def set_listen_to_jobs_frequency(self, value):
        '''
        Set frequency of how often to ping previously launched Plow Job/s for render progress updates.

        Args:
            value (int):
        '''
        self._model.set_listen_to_jobs_frequency(value)
        value = self._model.get_listen_to_jobs_frequency()

        msg = 'Setting listen to previously launched MSRS '
        msg += 'jobs frequency: {}'.format(value)
        self.logMessage.emit(msg, logging.DEBUG)

        self._thread_listen_to_jobs.set_frequency(value)


    def _collect_details_for_render_progress_check(self):
        '''
        Collect details about previously launched MSRS jobs to be checked in separate thread.

        Returns:
            details_to_collect (dict):
        '''
        details_to_collect = dict()

        for qmodelindex in self._model.get_pass_for_env_items_indices():
            pass_env_item = qmodelindex.internalPointer()
            if not pass_env_item.get_active():
                continue

            # Plow Ids required to get render progress
            dispatcher_plow_job_id = pass_env_item.get_dispatcher_plow_job_id()
            plow_job_id_last = pass_env_item.get_plow_job_id_last()
            plow_layer_id_last = pass_env_item.get_plow_layer_id_last()
            if not dispatcher_plow_job_id and not all([plow_job_id_last, plow_layer_id_last]):
                continue

            msrs_uuid = pass_env_item.get_identity_id()

            details_to_collect[msrs_uuid] = dict()
            if dispatcher_plow_job_id:
                details_to_collect[msrs_uuid]['dispatcher_plow_job_id'] = dispatcher_plow_job_id
            if plow_job_id_last:
                details_to_collect[msrs_uuid]['plow_job_id'] = plow_job_id_last
            if plow_layer_id_last:
                details_to_collect[msrs_uuid]['plow_layer_id'] = plow_layer_id_last

        return details_to_collect


    def _apply_render_progress_thread_result(self, results=None):
        '''
        Apply the latest results from thread listening and collecting
        render progress from previously launched Jobs, and apply
        to MSRS items and update view.

        Args:
            results (dict):

        Returns:
            update_count (int):
        '''
        details_to_collect_current = self._thread_listen_to_jobs.get_details_to_collect()

        # Update what to check for next render progress check
        details_to_collect = self._collect_details_for_render_progress_check() or dict()
        self._thread_listen_to_jobs.set_details_to_collect(details_to_collect)

        results = results or self._thread_listen_to_jobs.get_last_results() or dict()

        # msg = 'Applying Render Progress To MSRS: "{}"'.format(results)
        # self.logMessage.emit(msg, logging.DEBUG)

        model = self._model

        update_count = 0
        for qmodelindex in self._model.get_pass_for_env_items_indices():
            pass_env_item = qmodelindex.internalPointer()
            if not pass_env_item.get_active():
                continue

            uuid = pass_env_item.get_identity_id()

            current_render_progress = pass_env_item.get_render_progress()

            render_progress = None

            in_current_results = uuid in results.keys()
            if in_current_results:
                details = results.get(uuid)
                render_progress = details.get('percent', 0)
                # After dispatcher job launches the actual Job and Layer ids are known
                plow_job_id_last = details.get('plow_job_id')
                plow_layer_id_last = details.get('plow_layer_id')
                if all([plow_job_id_last, plow_layer_id_last]):
                    if plow_job_id_last:
                        pass_env_item.set_plow_job_id_last(plow_job_id_last)
                    if plow_layer_id_last:
                        pass_env_item.set_plow_layer_id_last(plow_layer_id_last)
                    # Clear the dispatcher id
                    pass_env_item.set_dispatcher_plow_job_id(None)
            else:
                in_details = uuid in details_to_collect.keys()
                if in_details:
                    render_progress = 0

            # msg = 'Current Progress: "{}". '.format(current_render_progress)
            # msg += 'New Progress: "{}"'.format(render_progress)
            # self.logMessage.emit(msg, logging.DEBUG)

            # Render progress the same as previously cached progress
            if current_render_progress == render_progress:
                continue

            # import random
            # render_progress = random.randint(0, 100)
            pass_env_item.set_render_progress(render_progress)

            model.dataChanged.emit(qmodelindex, qmodelindex)
            update_count += 1

        return update_count


    def _clear_render_progress(self):
        '''
        Clear any render progress hints from the MSRS view.

        Returns:
            update_count (int):
        '''
        model = self._model

        update_count = 0
        for qmodelindex in self._model.get_pass_for_env_items_indices():
            pass_env_item = qmodelindex.internalPointer()
            if not pass_env_item.get_active():
                continue

            render_progress = pass_env_item.get_render_progress()

            pass_env_item.set_render_progress(None)
            model.dataChanged.emit(qmodelindex, qmodelindex)
            update_count += 1

        return update_count


    ##########################################################################
    # Auto save session data on duration timer (UI feature)


    def _session_data_prepare_autosave(self, start=True):
        '''
        Prepare the auto save session system for the first time.

        Args:
            start (bool): whether to start timer now
        '''
        every_num_seconds = 180
        min_duration = 10
        max_duration = 999

        msg = 'Setting up autosave session interval: {}'.format(every_num_seconds)
        self.logMessage.emit(msg, logging.DEBUG)

        from Qt.QtCore import QTimer
        self._timer_auto_save = QTimer(parent=self)
        self.set_session_auto_save_duration(every_num_seconds)
        self._timer_auto_save.timeout.connect(self.session_auto_save)

        if start:
            self._timer_auto_save.start()


    def set_session_auto_save(self, enabled=True):
        '''
        Get whether session data auto save is enabled or not.
        Start or stop the auto save session feature, when duration is reached.

        Args:
           enabled (bool):
        '''
        enabled = bool(enabled)
        msg = 'Toggling autosave interval enabled to: {}'.format(enabled)
        self.logMessage.emit(msg, logging.DEBUG)
        # self._session_auto_save = enabled
        if enabled:
            self._timer_auto_save.start()
        else:
            self._timer_auto_save.stop()


    # def get_session_auto_save(self):
    #     '''
    #     Get whether auto save state is enabled.
    #     NOTE: This check member variable rather than QTimer state.

    #     Returns:
    #        enabled (bool):
    #     '''
    #     return self._session_auto_save # self._timer.isRunning()


    def get_session_auto_save_enabled(self):
        '''
        Get whether session data auto save is enabled ot not.

        Args:
           enabled (bool):
        '''
        return self._timer_auto_save.isActive()


    def set_session_auto_save_duration(self, every_num_seconds):
        '''
        Set the duration how often session should be auto saved.

        Args:
            every_num_seconds (int):
        '''
        msg = 'Setting autosave interval to: {}'.format(every_num_seconds)
        self.logMessage.emit(msg, logging.DEBUG)
        self._session_auto_save_duration = every_num_seconds
        milliseconds = every_num_seconds * 1000
        self._timer_auto_save.setInterval(milliseconds)


    def session_auto_save(self, force_save=False):
        '''
        Callback to auto save the session data when save duration
        is reached, in reference to the current host app project.

        Args:
            force_save (bool): optionally only save session data if auto save session
                is enabled. Otherwise save anyway.

        Returns:
            success (bool):
        '''
        if not force_save and not self.get_session_auto_save_enabled():
            return False

        # Skip auto session save for blank sessions, in case project file
        # hasn't changed, and want to avoid auto save clearing previous session.
        render_item_count = len(self._model.get_render_items())
        if not render_item_count:
            msg = 'Skipping autosave - no render items. '
            msg += 'Avoiding overwriting last valid data. '
            self.logMessage.emit(msg, logging.WARNING)
            return False

        current_project = self._model.get_current_project()

        if force_save:
            msg = 'Now auto-force-saving session. '
            msg += 'Current project: "{}". '.format(current_project)
        else:
            msg = 'Now autosaving session after {} seconds '.format(self._session_auto_save_duration)
            msg += 'elapsed. Current project: "{}"'.format(current_project)
        self.logMessage.emit(msg, logging.INFO)

        if not current_project:
            msg = 'No current project to autosave session data for!'
            self.logMessage.emit(msg, logging.CRITICAL)
            return False

        session_data = self.session_get_data()
        if not session_data:
            msg = 'No session data serialized to autosave!'
            self.logMessage.emit(msg, logging.WARNING)
            return False

        hydra_resource, session_path = self._model.get_or_create_session_data_resource(
            current_project)

        # Write session data to Hydra multiShotRenderSubmitter resource
        if session_path:
            self._session_auto_save_session_path = session_path

            # Write session data to auto save session path
            self.session_write(session_path, session_data)

            if hydra_resource:
                msg = 'Writing session data to hydra '
                msg += 'resource: {}'.format(hydra_resource.location)
            else:
                msg = 'Writing session data to same folder & based on '
                msg += 'project file. '
                msg += 'Location: {}'.format(session_path)
            self.logMessage.emit(msg, logging.INFO)

            return True

        return False


    def set_session_recall_when_loading_project(self, value):
        '''
        Set whether to automatically reload session data associated with a host app
        project, when loading it.

        Args:
            value (bool):
        '''
        value = bool(value)
        msg = 'Setting recall session data when loading project to: {}'.format(value)
        self.logMessage.emit(msg, logging.DEBUG)
        self._session_recall_when_loading_project = value


    def set_session_save_on_close(self, value):
        '''
        Set whether to automatically save session data when closing this tool.

        Args:
            value (bool):
        '''
        value = bool(value)
        msg = 'Setting session save-on-close to: {}'.format(value)
        self.logMessage.emit(msg, logging.DEBUG)
        self._session_save_on_close = value


    def set_session_save_on_load_project(self, value):
        '''
        Set whether to automatically save session data for current project
        when about to load a different project.

        Args:
            value (bool):
        '''
        value = bool(value)
        msg = 'Setting session save-on-load to: {}'.format(value)
        self.logMessage.emit(msg, logging.DEBUG)
        self._session_save_on_load_project = value


    ##########################################################################
    # Project methods


    def new_project(
            self,
            show_dialog=True,
            sync_from_project=False):
        '''
        Start a new project, so clear the entire model data.

        Args:
            show_dialog (bool):
            sync_from_project (bool):
                optionally perform sync from current project after starting
                new Project (should be no Render nodes anyway).
        '''
        msg = 'Clearing current project!'
        self.add_log_message(msg, logging.WARNING)

        self.statusBar().showMessage(msg, 2000)

        if show_dialog:
            msg = 'Start new project?'
            reply = QMessageBox.question(
                self,
                'Clear current {} {}?'.format(self.HOST_APP, self.HOST_APP_DOCUMENT),
                msg,
                QMessageBox.Ok | QMessageBox.Cancel)
            if reply == QMessageBox.Cancel:
                return

        self.session_new()

        self._update_project_widget(project=str())

        # Clear current project in host app
        success = self._model.new_project_in_host_app()
        if not success:
            msg = 'Failed to create new {} in "{}". '.format(self.HOST_APP_DOCUMENT, self.HOST_APP)
            self.add_log_message(msg, logging.CRITICAL)

        # Optionally resync from current new project.
        # Will be nothing (so just show splash widget)
        if sync_from_project:
            self.sync_render_nodes_and_environments()
        else:
            self.set_spalsh_screen_visible_if_items()


    def save_project_as(self):
        '''
        Save a project as a user defined project path.

        Returns:
            project (str): hyref or file path
        '''
        msg = 'Save Current {} {} As'.format(self.HOST_APP, self.HOST_APP_DOCUMENT)
        self.add_log_message(msg, logging.INFO)

        self.statusBar().showMessage(msg, 2000)

        # Use an Asset / Hydra browser.
        # NOTE: Currently the srnd_qt AreaBrowserWidget isnt designed to
        # pick destination save product area.
        if self._use_hydra_browser and self._model.get_in_host_app():
            project = self.browse_for_project_in_host_app(
                start_area=os.getenv('OZ_CONTEXT'),
                title_str='Save {} {}'.format(self.HOST_APP, self.HOST_APP_DOCUMENT),
                save=True)

        # Otherwise use file dialog to choose where to save host app project
        else:
            from Qt.QtWidgets import QFileDialog

            file_types = ','.join(['*.{}'.format(ft) for ft in self._project_file_types])
            file_type_label = '{} {} files ({})'.format(
                self.HOST_APP,
                self.HOST_APP_DOCUMENT,
                file_types)

            _result = QFileDialog.getSaveFileName(
                None,
                'Save current {} {} as'.format(self.HOST_APP, self.HOST_APP_DOCUMENT),
                self.get_project_directory(),
                file_type_label)

            # NOTE: For different Python Qt Bindings
            if _result and isinstance(_result, (list, tuple)):
                _result = _result[0]
            if not _result:
                return

            project = str(_result)

        if not project:
            return

        msg = 'About to save current {} '.format(self.HOST_APP)
        msg += '{} as: "{}"'.format(self.HOST_APP_DOCUMENT, project)
        self.add_log_message(msg, logging.INFO)

        success = self._model.save_project_in_host_app(project)
        if success:
            self._update_project_widget(project=project)
        else:
            msg = 'Failed to save current {} as: "{}"'.format(self.HOST_APP_DOCUMENT, project)
            self.add_log_message(msg, logging.CRITICAL)

        return project


    def get_project_directory(self):
        '''
        Get default directory to open file dialog to pick project.
        Reimplement this for particular host app.

        Returns:
            project_dir (str):
        '''
        return os.path.join(os.getenv('OZ_CONTEXT'), 'shots')


    def browse_for_project_in_host_app(
            self,
            current_asset_hyref=str(),
            start_area=None,
            title_str=None,
            product_types=None,
            file_types=None,
            save=False,
            *args,
            **kwargs):
        '''
        Browse for a project in host app, and actually load it now.

        Returns:
            result (str): a hyref
        '''
        hyref = self._model.browse_for_product_in_host_app(
            start_area=start_area or os.getenv('OZ_CONTEXT'),
            title_str=title_str or 'Open {} {}'.format(self.HOST_APP, self.HOST_APP_DOCUMENT),
            product_types=product_types or self._project_product_types,
            file_types=file_types or self._project_file_types,
            save=save)
        if hyref and isinstance(hyref, basestring):
            return hyref


    def load_project(
            self,
            project=None,
            sync_from_project=True,
            recall_session_data=True,
            show_dialog=True):
        '''
        Load a host app project, and optionally sync from app.

        Args:
            project (str): hyref or file path
            sync_from_project (bool):
                optionally perform sync from project after loading it.
            recall_session_data (bool): optionally try to recall session data associated
                with project file itself. Note: This should be disanled when loading
                session data directly.
            show_dialog (bool):
        '''
        # Save the current session data, before loading new session
        if self._session_save_on_load_project:
            self.session_auto_save(force_save=True)

        # Disable features using timers and threads while loading session
        listen_to_jobs_was_enabled = self.get_listen_to_jobs()
        self.set_listen_to_jobs(False)
        auto_save_was_enabled = self.get_session_auto_save_enabled()
        self.set_session_auto_save(False)

        # If no project specified to load, get one from Hydra picker or file browser
        if not project and show_dialog:
            menu_bar_header_widget = self.get_menu_bar_header_widget()
            project = menu_bar_header_widget.get_project() or self.get_current_project() or str()

            # Browse for host app project using a Hyref browser
            if self._use_hydra_browser:
                project = self.browse_for_project_in_host_app(
                    current_asset_hyref=project,
                    start_area=os.getenv('OZ_CONTEXT'),
                    title_str='Open {} {}'.format(self.HOST_APP, self.HOST_APP_DOCUMENT))

            # Browse for a project using a file dialog
            else:
                project_dir = self.get_project_directory()

                # If have existing project, then cast hyref to file_path, and update project dir
                if project:
                    file_path = None
                    if project.startswith(('hyref:', 'urn:')):
                        file_path, msg = utils.get_hyref_default_location(
                            project,
                            as_file_path=True)
                    if file_path and os.path.isfile(file_path):
                        project_dir = os.path.dirname(file_path)

                file_types = ','.join(['*.{}'.format(ft) for ft in self._project_file_types])
                file_type_label = '{} {} files ({})'.format(
                    self.HOST_APP,
                    self.HOST_APP_DOCUMENT,
                    file_types)

                # Browse for a project at the project directory
                from Qt.QtWidgets import QFileDialog
                _result = QFileDialog.getOpenFileName(
                    None,
                    'Open {} {} file'.format(self.HOST_APP, self.HOST_APP_DOCUMENT),
                    project_dir,
                    file_type_label,
                    str())
                # NOTE: For different Python Qt Bindings, only return
                # the actual file path, not the file format label
                if isinstance(_result, (list, tuple)):
                    _result = _result[0]
                project = str(_result or str())

        if not project:
            msg = 'No {} to load!'.format(self.HOST_APP_DOCUMENT)
            self.add_log_message(msg, logging.WARNING)
            # Revert timers and threads back to previous state
            self.set_listen_to_jobs(listen_to_jobs_was_enabled)
            self.set_session_auto_save(auto_save_was_enabled)
            return

        msg = 'Loading {} {} - {}'.format(self.HOST_APP, self.HOST_APP_DOCUMENT, project)
        self.add_log_message(msg, logging.INFO)

        # Unregister project and render callbacks
        callback_save_active = self.get_callback_save_session_on_project_save()
        callback_load_active = self.get_callback_restore_session_on_project_load()
        callback_add_pass = self.get_callback_add_pass_on_render_node_create()
        callback_remove_pass = self.get_callback_remove_pass_on_render_node_delete()
        callback_update_pass_name = self.get_callback_update_pass_name_on_render_node_rename()
        self.register_callback_project_save(register=False)
        self.register_callback_project_load(register=False)
        self.register_callback_render_node_create(register=False)
        self.register_callback_render_node_delete(register=False)
        self.register_callback_render_node_renamed(register=False)

        success = self._model.load_project_in_host_app(str(project))

        has_current_project = bool(self.get_current_project() or project)
        project_is_saved_as_asset = bool(self._model.get_project_is_saved_as_asset())
        project_is_saved = has_current_project and project_is_saved_as_asset
        self._session_autosave_widget.set_project_is_saved(project_is_saved)

        if success:
            # Apply the picked project to the HyrefPreviewWidget (not triggering callbacks)
            self._update_project_widget(project=project)

            # Optionally resync after loading another project and throw away existing session data
            if sync_from_project:
                self.sync_render_nodes_and_environments()

            # Try to load session data associated to project file itself (if any)
            if recall_session_data and self._session_recall_when_loading_project:
                hydra_resource, session_path = self._model.get_or_create_session_data_resource(project)

                if os.path.isfile(session_path):
                    msg = 'Attempting to recall session data '
                    msg += 'Associated to project: "{}". '.format(project)
                    self.add_log_message(msg, logging.INFO)
                    self.session_load(
                        session_path=session_path, # session data to load
                        load_project=False, # project already loaded
                        start_new_session=False, # no need to clear existing session
                        show_dialog=False)
                else:
                    msg = 'No previous session data to recall '
                    msg += 'associated to project: "{}". '.format(project)
                    self.add_log_message(msg, logging.WARNING)
        else:
            msg = 'Failed to load project: "{}"'.format(project)
            self.add_log_message(msg, logging.CRITICAL)

        # Register project and render callbacks.
        # Only register callbacks if previously enabled.
        self.register_callback_project_save(register=callback_save_active)
        self.register_callback_project_load(register=callback_load_active)
        self.register_callback_render_node_create(register=callback_add_pass)
        self.register_callback_render_node_delete(register=callback_remove_pass)
        self.register_callback_render_node_renamed(register=callback_update_pass_name)

        # If not recalling session data then revert listen to jobs back to previous state
        if not recall_session_data:
            self.set_listen_to_jobs(listen_to_jobs_was_enabled)

        self.set_session_auto_save(auto_save_was_enabled)

        return project


    def get_current_project(self):
        '''
        Get the current host app project (if any).
        Requires reimplementation for particular host app.

        Returns:
            current_project (str):
        '''
        return None


    def _populate_session_menu(self, menu=None):
        '''
        Populate the session menu as it is requested.

        Args:
            menu (QMenu):

        Returns:
            menu (QtGui.QMenu):
        '''
        menu_session = base_window.BaseWindow._populate_session_menu(
            self,
            menu=menu)

        before_action = menu_session.actions()[-1]
        for action in menu_session.actions():
            action_str = str(action.text())
            # Where to insert the subsquent menu items
            if action_str == 'Load Session':
                before_action = action
            # # Rename with 'Local' in action name
            # if action_str in ['Load Session', 'Save Session', 'Save Session As']:
            #     _text_list = action_str.split(' ')
            #     _text_list.insert(1, 'Local')
            #     action_str = ' '.join(_text_list)
            #     action.setText(action_str)

        # if USER == 'bjennings':
        msg = 'Force update the multiShotRenderSubmitter resource '
        msg += 'associated to the current project now (if possible).'
        update_auto_save_session_action = srnd_qt.base.utils.context_menu_add_menu_item(
            self,
            'Update multiShotRenderSubmitter resource',
            icon_path=os.path.join(constants.ICONS_DIR_QT, 'save.png'))
        update_auto_save_session_action.setStatusTip(msg)
        update_auto_save_session_action.triggered.connect(
            lambda *x: self.session_auto_save(force_save=True))
        update_auto_save_session_action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        menu_session.insertAction(before_action, update_auto_save_session_action)

        before_action = menu_session.actions()[-1]

        # If in host app UI, the user can just close the tab or window itself
        if self._model.get_in_host_app_ui():
            before_action.setVisible(False)

        for action in menu_session.actions():
            action_str = str(action.text())
            action_str = action_str.replace(' Session', str())
            if action_str == 'Recents':
                action_str = 'Recent'
            action.setText(action_str)

        HOST_APP_TITLE = self.HOST_APP.title()

        if not self._model.get_in_host_app_ui():
            new_project_action = srnd_qt.base.utils.context_menu_add_menu_item(
                self,
                'New {}'.format(self.HOST_APP_DOCUMENT),
                icon_path=self.HOST_APP_ICON)
            msg = 'Clear the current {} {}, and '.format(HOST_APP_TITLE, self.HOST_APP_DOCUMENT)
            msg += 'sync view to no data. '
            new_project_action.setStatusTip(msg)
            new_project_action.triggered.connect(self.new_project)
            new_project_action.setShortcut('CTRL+N')
            new_project_action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            menu_session.insertAction(before_action, new_project_action)

            msg = 'Load a {} {}. This closes the '.format(HOST_APP_TITLE, self.HOST_APP_DOCUMENT)
            msg += 'current {}.'.format(self.HOST_APP_DOCUMENT)
            load_project_action = srnd_qt.base.utils.context_menu_add_menu_item(
                self,
                'Load {}'.format(self.HOST_APP_DOCUMENT),
                icon_path=self.HOST_APP_ICON)
            load_project_action.setStatusTip(msg)
            load_project_action.triggered.connect(self.load_project)
            load_project_action.setShortcut('CTRL+L')
            load_project_action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            menu_session.insertAction(before_action, load_project_action)

            save_project_action = srnd_qt.base.utils.context_menu_add_menu_item(
                self,
                'Save {} as'.format(self.HOST_APP_DOCUMENT),
                icon_path=self.HOST_APP_ICON)
            msg = 'Save the current {} {} as. '.format(HOST_APP_TITLE, self.HOST_APP_DOCUMENT)
            msg += 'Launches dialog to pick write location'
            save_project_action.setStatusTip(msg)
            save_project_action.triggered.connect(
                lambda *x: self.save_project_as())
            save_project_action.setShortcut('CTRL+S')
            save_project_action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            menu_session.insertAction(before_action, save_project_action)

            menu_session.insertSeparator(before_action)


    ##########################################################################


    def register_callback_render_node_create(self, register=True):
        '''
        Register a callback to peform actions when render node created in host app.
        Reimplement this method to setup callback for host app.

        Args:
            register (bool): whether to register or unregister the callback
        '''
        msg = 'Register callback_add_render_node has no implementation!'
        self.add_log_message(msg, logging.WARNING)


    def register_callback_render_node_delete(self, register=True):
        '''
        Register a callback to peform actions when render node deleted in host app.
        Reimplement this method to setup callback for host app.

        Args:
            register (bool): whether to register or unregister the callback
        '''
        msg = 'Register callback_remove_render_node has no implementation!'
        self.add_log_message(msg, logging.WARNING)


    def register_callback_render_node_renamed(self, register=True):
        '''
        Register a callback to peform actions when render node renamed in host app.
        Reimplement this method to setup callback for host app.

        Args:
            register (bool): whether to register or unregister the callback
        '''
        msg = 'Register callback_rename_render_node has no implementation!'
        self.add_log_message(msg, logging.WARNING)


    def register_callback_project_load(self, register=True):
        '''
        Register a callback to peform actions when project is loaded in host app.
        Reimplement this method to setup callback for host app.

        Args:
            register (bool): whether to register or unregister the callback
        '''
        msg = 'Register callback_load_project has no implementation!'
        self.add_log_message(msg, logging.WARNING)
        return


    def register_callback_project_save(self, register=True):
        '''
        Register a callback to peform actions when project is saved in host app.
        Reimplement this method to setup callback for host app.

        Args:
            register (bool): whether to register or unregister the callback
        '''
        msg = 'Register callback_save_project has no implementation!'
        self.add_log_message(msg, logging.WARNING)
        return


    def set_callback_disabled_when_not_active_tab(self, value):
        '''
        Toggle whether to disable callbacks when not active tab.

        Args:
            value (bool):
        '''
        value = bool(value)
        msg = 'Setting callback disable all when not active tab: {}'.format(value)
        self.logMessage.emit(msg, logging.DEBUG)
        self._callback_disabled_when_not_active_tab = value


    def get_callback_add_pass_on_render_node_create(self):
        return self._callback_add_pass_on_render_node_create

    def get_callback_remove_pass_on_render_node_delete(self):
        return self._callback_remove_pass_on_render_node_delete

    def get_callback_update_pass_name_on_render_node_rename(self):
        return self._callback_update_pass_name_on_render_node_rename

    def get_callback_save_session_on_project_save(self):
        return self._callback_save_session_on_project_save

    def get_callback_restore_session_on_project_load(self):
        return self._callback_restore_session_on_project_load

    def get_callback_disabled_when_not_active_tab(self):
        return self._callback_disabled_when_not_active_tab


    ##########################################################################


    def _build_menu_corner_widget(self):
        '''
        Build main menu bar corner widget, for other actions and functionality.
        Includes the input for scene hyref if in standalone mode.
        Should be reimplemented to provide the model, view and
        delegates appropiate for host application.
        '''
        menu_bar = self.menuBar()
        menu_bar.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding)

        from srnd_multi_shot_render_submitter.widgets import menu_bar_header_widget
        self._widget_menu_bar_header = menu_bar_header_widget.MenuBarHeaderWidget(
            project_product_types=self._project_product_types,
            project_file_types=self._project_file_types,
            parent=self)
        self._widget_menu_bar_header.setObjectName('MSRSHeaderWidget')

        horizontal_layout = self._widget_menu_bar_header.get_content_widget_layout()

        header_widget = self.get_header_widget()
        if header_widget:
            emblem_icon_widget = header_widget.get_emblem_icon_widget()
            msg = 'Open link:<br>'
            msg += '<b>{}</b>'.format(self.WIKI_LINK)
            msrs_version = utils.get_multi_shot_render_submitter_version()
            host_msrs_version = self._model.get_multi_shot_render_submitter_version()
            msg += '<br><br><b>Paks</b><br>{}'.format(msrs_version)
            msg += '<br>{}'.format(host_msrs_version)
            emblem_icon_widget.setToolTip(msg)
            horizontal_layout.insertWidget(0, emblem_icon_widget)
            header_widget.setVisible(False)
            header_widget.visibilityResolved.connect(self._toggle_spacer_after_emblem)
            self._toggle_spacer_after_emblem(True)

        self._widget_menu_bar_header.syncMenuRequested.connect(
            self._populate_and_show_sync_menu)

        # # The current Qt shim layer for Weta PyQt4 build doesn't
        # # expose setCornerWidget for QMenuBar
        self._tool_bar_header = self.addToolBar('Header')
        self._tool_bar_header.setObjectName('MSRSHeaderToolBar')
        self._tool_bar_header.addWidget(self._widget_menu_bar_header)
        # else:
        #     self._tool_bar_header.setCornerWidget(
        #         self._widget_menu_bar_header,
        #         Qt.TopRightCorner)


    def _toggle_spacer_after_emblem(self, visible):
        '''
        Destroy and create a QSpacerItem after tool emblem in
        menu bar header to retain nice spacing.

        Args:
            visible (bool) :
        '''
        horizontal_layout = self._widget_menu_bar_header.get_content_widget_layout()
        item = horizontal_layout.itemAt(1)
        item_is_spacer = isinstance(item, QSpacerItem)
        if visible and not item_is_spacer:
            horizontal_layout.insertSpacing(1, 20)
        elif not visible and item_is_spacer:
            horizontal_layout.takeAt(1)


    def _build_session_auto_save_widget(self):
        '''
        Build a widget in the status bar that shows current session auto save state,
        and also provides a button to save the current project, when not previously saved.
        '''
        self._session_autosave_widget = SessionAutoSaveStateWidget(
            parent=self)
        status_bar = self.statusBar()
        status_bar.addPermanentWidget(self._session_autosave_widget)

        has_current_project = bool(self.get_current_project())
        project_is_saved_as_asset = bool(self._model.get_project_is_saved_as_asset())
        project_is_saved = has_current_project and project_is_saved_as_asset
        self._session_autosave_widget.set_project_is_saved(project_is_saved)


    def get_menu_bar_header_widget(self):
        '''
        Get the cornder widget that appears in the main
        menuBar of this QMainWindow.

        Returns:
            widget_menu_corner (QWidget):
        '''
        return self._widget_menu_bar_header


    ##########################################################################
    # Get subclassed object types appropiate for dialog (via factory)


    @classmethod
    def get_multi_shot_view_object(cls):
        '''
        Get the multi shot view object in uninstantiated state.

        Returns:
            view (MultiShotRenderView):
        '''
        return factory.MultiShotFactory.get_multi_shot_view_object()


    @classmethod
    def get_multi_shot_model_object(cls):
        '''
        Get the multi shot model object in uninstantiated state.

        Returns:
            model (MultiShotRenderModel):
        '''
        return factory.MultiShotFactory.get_multi_shot_model_object()


    @classmethod
    def get_multi_shot_delegates_object(cls):
        '''
        Get the multi shot delegates object in uninstantiated state.

        Returns:
            delegate (MultiShotRenderDelegates):
        '''
        return factory.MultiShotFactory.get_multi_shot_delegates_object()


    @classmethod
    def get_spash_intro_object(cls):
        '''
        Get the splash intro widget object in uninstantiated state.

        Returns:
            splash_intro_widget (SplashIntroWidget):
        '''
        return factory.MultiShotFactory.get_spash_intro_object()


    @classmethod
    def get_job_options_widget_object(cls):
        '''
        Get the job options widget object in uninstantiated state.

        Returns:
            job_options_widget_object (JobOptionsWidget):
        '''
        return factory.MultiShotFactory.get_job_options_widget_object()


    ##########################################################################


    def _build_tree_view(self):
        '''
        Build the main model, view and delegates for this Multi Shot Render Submitter.

        Returns:
            tree_view (QtGui.QTreeView):
        '''
        from srnd_qt.ui_framework.widgets import toggle_visible_widget
        self._toggle_visible_widget = toggle_visible_widget.ToggleVisibleWidget()

        view_object = self.get_multi_shot_view_object()
        tree_view = view_object(
            include_context_menu=True,
            palette=None,
            debug_mode=self._debug_mode,
            parent=self)
        tree_view.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding)

        # Add initial splash intro widget
        header_str = 'Load a {} {} containing Render nodes & refresh.'.format(self.HOST_APP, self.HOST_APP_DOCUMENT)
        details_str = 'All Render nodes in the current project will be synced '
        details_str += 'to this tool on startup. '
        details_str += '<br>Alternatively, load a {} {} now or '.format(self.HOST_APP, self.HOST_APP_DOCUMENT)
        details_str += 'a json session (Optionally along with accompanying project). '

        footer_str = 'Click here for documentation about '
        footer_str += str(self.TOOL_NAME)

        spash_intro_object = self.get_spash_intro_object()
        self._splash_intro_widget = spash_intro_object(
            header_gap=30,
            header_str=header_str,
            details_str=details_str,
            footer_str=footer_str,
            link=self.WIKI_LINK,
            margins=(25, 0, 120, 0),
            parent=self)

        STYLESHEET_BACKGROUND = 'background: rgb(65, 65, 65);'
        self._splash_intro_widget.setStyleSheet(STYLESHEET_BACKGROUND)

        self._toggle_visible_widget.set_initial_widget(self._splash_intro_widget)
        self._toggle_visible_widget.set_other_widget(tree_view)

        model_object = self.get_multi_shot_model_object()
        self._model = model_object(
            shot_assignments_project=self._shot_assignments_project,
            shot_assignments_user=self._shot_assignments_user,
            debug_mode=self._debug_mode)
        tree_view.setModel(self._model)

        delegates_object = self.get_multi_shot_delegates_object()
        self._delegates = delegates_object(
            debug_mode=self._debug_mode,
            parent=self)
        tree_view.setItemDelegate(self._delegates)

        return tree_view


    def get_view(self):
        '''
        Get the main MSRS view of this window.

        Returns:
            tree_view (MultiShotRenderView):
        '''
        return self._tree_view


    def get_model(self):
        '''
        Get the MSRS main model of this window.

        Returns:
            model (MultiShotRenderModel):
        '''
        return self._model


    def _build_additional_splash_screen_widgets(self):
        '''
        Build additional splash screen widgets.
        '''
        vertical_layout_splash_screen = self._splash_intro_widget.layout()

        insert_at = vertical_layout_splash_screen.count() - 1

        vertical_layout_splash_screen.insertSpacing(insert_at, 60)

        insert_at += 1

        horizontal_layout = QHBoxLayout()
        horizontal_layout.setSpacing(8)
        horizontal_layout.setContentsMargins(8, 8, 8, 8)
        vertical_layout_splash_screen.insertLayout(insert_at, horizontal_layout)

        label_open_preferences_icon = clickable_label.ClickableLabel(
            lambda *x: self._model.open_preferences_dialog(),
            icon_path=os.path.join(SRND_QT_ICONS_DIR, 'cog.png'),
            icon_size=20,
            tool_tip='Open preferences dialog')
        horizontal_layout.addWidget(label_open_preferences_icon)

        label_open_preferences = clickable_label.ClickableLabel(
            lambda *x: self._model.open_preferences_dialog(),
            label='Open preferences',
            tool_tip='Open preferences dialog')
        label_open_preferences.setSizePolicy(
            QSizePolicy.Minimum,
            QSizePolicy.Fixed)
        _font = label_open_preferences.font()
        _font.setPointSize(10)
        label_open_preferences.setFont(_font)
        horizontal_layout.addWidget(label_open_preferences)

        horizontal_layout.addStretch(100)

        vertical_layout_splash_screen.addStretch(100)

        horizontal_layout = QHBoxLayout()
        horizontal_layout.setSpacing(8)
        horizontal_layout.setContentsMargins(8, 8, 8, 8)
        vertical_layout_splash_screen.addLayout(horizontal_layout)

        msrs_version = utils.get_multi_shot_render_submitter_version()
        host_msrs_version = self._model.get_multi_shot_render_submitter_version()

        font_italic = QFont()
        font_italic.setFamily(constants.FONT_FAMILY)
        font_italic.setPointSize(8)
        font_italic.setItalic(True)

        display_label = '\n'.join([msrs_version, host_msrs_version])
        label = QLabel(display_label)
        label.setFont(font_italic)
        horizontal_layout.addWidget(label)
        horizontal_layout.addStretch(100)

        vertical_layout_splash_screen.addSpacing(20)


    def _build_lighting_info_panel(self):
        '''
        Build MSRS lighting info.

        Returns:
            panel_lighting_info (BasePanel): subclass of QDockWidget
        '''
        title_str = 'Lighting info'
        self._panel_lighting_info = self.create_panel(
            title_str,
            icon_path=os.path.join(SRND_QT_ICONS_DIR, 'info_s01.png'),
            area=Qt.BottomDockWidgetArea, # Qt.RightDockWidgetArea
            horizontal_size_policy=QSizePolicy.Expanding,
            vertical_size_policy=QSizePolicy.Expanding,
            include_detach_button=False)

        vertical_layout = self._panel_lighting_info.get_content_widget_layout()
        vertical_layout.setContentsMargins(0, 0, 0, 0)

        from srnd_multi_shot_render_submitter.widgets import lighting_info_widget
        self._lighting_info_widget = lighting_info_widget.MultiShotLightingInfoWidget(
            self._model,
            self._tree_view,
            debug_mode=self._debug_mode)
        self._lighting_info_widget.logMessage.connect(self.add_log_message)

        vertical_layout.addWidget(self._lighting_info_widget)

        return self._panel_lighting_info


    def _build_details_panel(self):
        '''
        Build MSRS details panel.

        Returns:
            panel_details (BasePanel): subclass of QDockWidget
        '''
        title_str = 'Details'
        self._panel_details = self.create_panel(
            title_str,
            icon_path=os.path.join(SRND_QT_ICONS_DIR, 'info_s01.png'),
            area=Qt.RightDockWidgetArea,
            horizontal_size_policy=QSizePolicy.Minimum,
            vertical_size_policy=QSizePolicy.Expanding,
            include_detach_button=False)

        vertical_layout = self._panel_details.get_content_widget_layout()
        vertical_layout.setContentsMargins(0, 0, 0, 0)

        from srnd_multi_shot_render_submitter.widgets import details_widget
        self._details_widget = details_widget.MultiShotDetailsWidget(
            self._model,
            debug_mode=self._debug_mode)
        self._details_widget.logMessage.connect(self.add_log_message)

        vertical_layout.addWidget(self._details_widget)

        return self._panel_details


    def _build_job_options_panel(self):
        '''
        Build a panel for Job options.

        Returns:
            panel_job_options (BasePanel): subclass of QDockWidget
        '''
        title_str = 'Job options'
        self._panel_job_options = self.create_panel(
            title_str,
            icon_path=os.path.join(constants.ICONS_DIR_QT, 'tool_s01.png'),
            area=Qt.RightDockWidgetArea,
            horizontal_size_policy=QSizePolicy.Minimum,
            vertical_size_policy=QSizePolicy.Minimum,
            include_detach_button=False)

        vertical_layout = self._panel_job_options.get_content_widget_layout()
        vertical_layout.setContentsMargins(0, 0, 0, 0)

        # Get the JobOptionsWidget and instantiate (or subclass)
        job_options_widget_object = self.get_job_options_widget_object()
        self._job_options_widget = job_options_widget_object()

        vertical_layout.addWidget(self._job_options_widget)

        self.splitDockWidget(
            self._panel_details,
            self._panel_job_options,
            Qt.Vertical)

        # Toggle the visibility of Apply Render Overrides checkbox depending
        # if any plugins are exposed and implemented
        render_overrides_manager = self._model.get_render_overrides_manager()
        render_overrides_plugins_ids = render_overrides_manager.get_render_overrides_plugins_ids()
        widget = self._job_options_widget.get_apply_render_overrides_widget()
        if widget:
            widget.setVisible(bool(render_overrides_plugins_ids))

        return self._panel_job_options


    def _build_footer(self):
        '''
        Build footer widget and all associated widgets.
        Includes the button to start rendering.
        '''
        layout = self.get_content_widget_layout()

        self._widget_footer = QWidget()
        horizontal_layout = QHBoxLayout()
        horizontal_layout.setSpacing(12)
        horizontal_layout.setContentsMargins(8, 8, 8, 8)
        self._widget_footer.setLayout(horizontal_layout)
        layout.addWidget(self._widget_footer)

        self._widget_context_actions = QWidget()
        self._widget_context_actions.setSizePolicy(
            QSizePolicy.Minimum,
            QSizePolicy.Minimum)
        horizontal_layout_context_actions = QHBoxLayout()
        horizontal_layout_context_actions.setSpacing(4)
        horizontal_layout_context_actions.setContentsMargins(0, 0, 0, 0)
        self._widget_context_actions.setLayout(horizontal_layout_context_actions)
        horizontal_layout.addWidget(self._widget_context_actions)

        self._toolButton_duplicate_environments = QToolButton()
        msg = 'Duplicate the selected environments to new rows. '
        msg += '<br><i>Note: Different overrides and frame ranges can be '
        msg += 'applied to multiple instances of environments. '
        msg += '(Rows with same target environment).</i>'
        self._toolButton_duplicate_environments.setToolTip(msg)
        self._toolButton_duplicate_environments.setAutoRaise(True)
        self._toolButton_duplicate_environments.setIconSize(QSize(22, 22))
        icon = QIcon(os.path.join(ICONS_DIR, 'copy_s01.png'))
        self._toolButton_duplicate_environments.setIcon(icon)
        horizontal_layout_context_actions.addWidget(self._toolButton_duplicate_environments)

        self._toolButton_group_shots = QToolButton()
        msg = 'Group the selected environment/s '
        msg += 'or create empty group'
        self._toolButton_group_shots.setToolTip(msg)
        self._toolButton_group_shots.setAutoRaise(True)
        self._toolButton_group_shots.setIconSize(QSize(18, 18))
        icon = QIcon(os.path.join(ICONS_DIR, 'group_s01.png'))
        self._toolButton_group_shots.setIcon(icon)
        horizontal_layout_context_actions.addWidget(self._toolButton_group_shots)

        self._toolButton_delete_environments = QToolButton()
        msg = 'Delete the selected environment/s'
        self._toolButton_delete_environments.setToolTip(msg)
        self._toolButton_delete_environments.setAutoRaise(True)
        self._toolButton_delete_environments.setIconSize(QSize(18, 18))
        icon = QIcon(os.path.join(ICONS_DIR, 'delete_s01.png'))
        self._toolButton_delete_environments.setIcon(icon)
        horizontal_layout_context_actions.addWidget(self._toolButton_delete_environments)

        horizontal_layout_context_actions.addSpacing(4)
        line = srnd_qt.base.utils.get_line(vertical_line=True, height=20)
        horizontal_layout_context_actions.addWidget(line)
        horizontal_layout_context_actions.addSpacing(4)

        # Add overview label about all items in model state (and optional sync)

        self._toolButton_update_overview = QToolButton()
        msg = 'Force the overview label to recompute pass & shot count '
        msg += 'and total number of frames. '
        self._toolButton_update_overview.setToolTip(msg)
        self._toolButton_update_overview.setAutoRaise(True)
        self._toolButton_update_overview.setIconSize(QSize(14, 14))
        icon = QIcon(os.path.join(constants.ICONS_DIR_QT, 'sync.png'))
        self._toolButton_update_overview.setIcon(icon)
        horizontal_layout.addWidget(self._toolButton_update_overview)

        self._toolButton_update_overview.setVisible(
            constants.EXPOSE_UPDATE_OVERVIEW_BUTTON)

        font_italic = QFont()
        font_italic.setFamily(constants.FONT_FAMILY)
        font_italic.setItalic(True)

        self._widget_render_estimate = RenderEstimateWidget(
            self._model,
            parent=self)
        horizontal_layout.addWidget(self._widget_render_estimate)

        horizontal_layout.addSpacing(8)

        msg = 'Proportionately scale all columns at the same time.'
        msg += '<br><i>Note: When you release, the mouse slider returns to the middle, '
        msg += 'So click and drag multiple times to scale as needed.</i>'
        msg += '<br><br><b><i>Note: Right click for menu action to reset all column widths.</i></b>'

        self._slider_column_scaling = QSlider()
        self._slider_column_scaling.setToolTip(msg)
        self._slider_column_scaling.setOrientation(Qt.Horizontal)
        self._slider_column_scaling.setMinimum(-150)
        self._slider_column_scaling.setMaximum(150)
        self._slider_column_scaling.setValue(0)
        self._slider_column_scaling.setSizePolicy(
            QSizePolicy.Minimum,
            QSizePolicy.Fixed)
        self._slider_column_scaling.setMinimumWidth(150)
        horizontal_layout.addWidget(self._slider_column_scaling)

        self._slider_column_scaling.setContextMenuPolicy(Qt.CustomContextMenu)
        self._slider_column_scaling.customContextMenuRequested.connect(
            self._create_context_menu_column_actions)

        horizontal_layout.addSpacing(4)

        self._label_clickable_emblem = clickable_label.ClickableLabel(
            self.WIKI_LINK,
            icon_size=20,
            icon_path=os.path.join(constants.ICONS_DIR_QT, 'help.png'))
        msg = 'Open link:<br>'
        msg += '<b>{}</b>'.format(self.WIKI_LINK)
        msrs_version = utils.get_multi_shot_render_submitter_version()
        host_msrs_version = self._model.get_multi_shot_render_submitter_version()
        msg += '<br><br><b>Paks</b><br>{}'.format(msrs_version)
        msg += '<br>{}'.format(host_msrs_version)
        self._label_clickable_emblem.setToolTip(msg)
        horizontal_layout.addWidget(self._label_clickable_emblem)

        horizontal_layout.addSpacing(8)

        self._pushButton_launch_summary = QPushButton()
        self._pushButton_launch_summary.setStyleSheet('QPushButton {padding: 6px;}')
        msg = 'Launch dialog to show operation summary & validation for '
        msg += 'items about to be submitted.'
        self._pushButton_launch_summary.setToolTip(msg)
        self._pushButton_launch_summary.setIcon(QIcon(self.HOST_APP_ICON))

        horizontal_layout.addWidget(self._pushButton_launch_summary)

        self._update_launch_render_label(show_summary=True)


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
        self._toggle_visible_widget.setDisabled(loading)
        self._widget_menu_bar_header.setDisabled(loading)
        self._widget_footer.setDisabled(loading)
        QApplication.processEvents()


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
        QApplication.processEvents()


    ##########################################################################
    # Submit methods


    def multi_shot_render(
            self,
            selected=False,
            interactive=False,
            current_frame_only=False,
            show_failed_dialog=True,
            **kwargs):
        '''
        Launch the Render validation dialog, to let the user
        see an overview of all render operations about the be performed.

        Args:
            selected (bool): optionally render only item/s selected in MultiShotRenderView
            interactive (bool): optionally interactively render, rather than batch render
            current_frame_only (bool): ignore frame range overrides and only render current project frame
            show_failed_dialog (bool):

        Returns:
            success, msg (tuple):
        '''
        # Reset any UI setup values
        self._log_panel_requires_hiding = False

        # Check whether to progress to Summary & Validation window.
        # Otherwise dialog will popup here and exit.
        can_render, msg = self.validate_can_render()
        if not can_render:
            msg = 'Cannot start render: ' + str(msg)
            self.add_log_message(msg, logging.WARNING)
            return False, msg

        ######################################################################
        # Call render on the view, in case selected indices are required.
        # NOTE: Will pass the selected indices to the model to start rendering.

        # Start Multi Shot Render render (optionally the Summary dialog first)
        render_success, cancelled, render_msg = self._tree_view.multi_shot_render(
            selected=selected,
            interactive=interactive,
            current_frame_only=current_frame_only)

        # Render did not successfully submit
        if not cancelled and (not render_success and render_msg):
            self.logMessage.emit(render_msg, logging.CRITICAL)
            title_str = 'Submission failed.'
            reply = QMessageBox.critical(
                self,
                title_str,
                render_msg,
                QMessageBox.Ok)
            return False, render_msg

        return render_success, render_msg


    def validate_can_render(self):
        '''
        Validate whether render can be started.
        This prevents the user launching the Summary dialog,
        and will immediately popup an warning message.
        Requires reimplementation.

        Returns:
            can_render (bool):
        '''
        # If project has unsaved changed (project is dirty), then
        # ask the user to save, and show save dialog now.
        has_unsaved_changes = self._model.get_project_has_unsaved_changes()

        msg = 'Has unsaved changes: {}. '.format(has_unsaved_changes)
        msg += 'Show save dialog: {}'.format(self._show_save_dialog_on_submit)
        self.add_log_message(msg, logging.WARNING)

        if has_unsaved_changes and self._show_save_dialog_on_submit:
            current_project = self.get_current_project()
            if not current_project:
                current_project = self._model._get_project_from_external_widget()

            msg = 'Current project at validate can render: "{}"'.format(current_project)
            self.add_log_message(msg, logging.INFO)

            from srnd_multi_shot_render_submitter.dialogs import save_reminder_dialog
            dialog = save_reminder_dialog.SaveReminderDialog(
                show_save_and_continue=bool(current_project), # only show this button if have existing project
                host_app_document=self.HOST_APP_DOCUMENT,
                icon_path=self.HOST_APP_ICON,
                parent=self)
            dialog.logMessage.connect(self.add_log_message)

            dialog.exec_()

            result = dialog.result()

            if result == dialog.Rejected:
                msg = 'Cancelled submission'
                return False, msg

            # Update don't show again
            dont_show_again = dialog.get_dont_show_again()
            if dont_show_again:
                msg = 'Updating save reminder do not show again'
                self.add_log_message(msg, logging.INFO)
                self._show_save_dialog_on_submit = False
                self._model.update_preference('show_save_reminder_dialog', False)

            # msg = 'Project altered since the last load'
            # msg += '/save operation, or never saved.'
            # msg += '<br><br><i>Note: Do you want to open the save '
            # msg += 'project dialog, ignore & continue or '
            # msg += 'cancel submission?</i>'
            # result = QMessageBox.question(
            #     self,
            #     'Save project?',
            #     msg,
            #     QMessageBox.Save | QMessageBox.Ignore | QMessageBox.Cancel)

            # Open blocking dialog to choose project to save
            if result == dialog.SaveAs:
                project = self.save_project_as()
                if not project:
                    msg = 'No project saved from save as dialog! Cancelling show summary'
                    return False, msg

            # Save the currently open project
            elif result == dialog.SaveAndContinue:
                if not current_project:
                    msg = 'No current project to save! Cancelling show summary'
                    return False, msg
                success = self._model.save_project_in_host_app(current_project)

        return True, str()


    def setup_ui_for_render(self):
        '''
        Apply any additional ui setup just before submission starts.
        '''
        # Unregister project and render callbacks
        self._callback_save_active_was_active = self.get_callback_save_session_on_project_save()
        self._callback_load_active_was_active = self.get_callback_restore_session_on_project_load()
        self._callback_add_pass_was_active = self.get_callback_add_pass_on_render_node_create()
        self._callback_remove_pass_was_active = self.get_callback_remove_pass_on_render_node_delete()
        self._callback_update_pass_name_was_active = self.get_callback_update_pass_name_on_render_node_rename()
        self.register_callback_project_load(register=False)
        self.register_callback_project_save(register=False)
        self.register_callback_render_node_create(register=False)
        self.register_callback_render_node_delete(register=False)
        self.register_callback_render_node_renamed(register=False)

        # Disable features using timers and threads while loading session
        self._listen_to_jobs_was_enabled = self.get_listen_to_jobs()
        self.set_listen_to_jobs(False)
        self._auto_save_was_enabled = self.get_session_auto_save_enabled()
        self.set_session_auto_save(False)

        self.show_progress_bar(True)

        # Auto show the log viewer when height above threshold
        self._log_panel_requires_hiding = not self._panel_log_viewer.isVisible()
        if self.height() > 700:
            self._panel_log_viewer.setVisible(True)


    def revert_ui_after_render(self):
        '''
        Revert any ui setup just after submission completes.
        '''
        # Register project and render callbacks.
        # Only register callbacks if previously enabled.
        self.register_callback_project_save(
            register=self._callback_save_active_was_active)
        self.register_callback_project_load(
            register=self._callback_load_active_was_active)
        self.register_callback_render_node_create(
            register=self._callback_add_pass_was_active)
        self.register_callback_render_node_delete(
            register=self._callback_remove_pass_was_active)
        self.register_callback_render_node_renamed(
            register=self._callback_update_pass_name_was_active)

        # Revert timers and threads back to previous state
        self.set_listen_to_jobs(self._listen_to_jobs_was_enabled)
        self.set_session_auto_save(self._auto_save_was_enabled)

        self.show_progress_bar(False)

        self._tree_view.horizontalScrollBar().setValue(0)
        self._tree_view.verticalScrollBar().setValue(0)

        # Show the log panel again if required
        if self._log_panel_requires_hiding:
            self._panel_log_viewer.setVisible(False)


##############################################################################


def open_link(link):
    '''
    Open link in web browser

    Args:
        link (str):
    '''
    LOGGER.info('Opening link: "{}"'.format(link))
    from Qt.QtGui import QDesktopServices
    from Qt.QtCore import QUrl
    QDesktopServices().openUrl(QUrl(str(link)))


##############################################################################


def main(**kwargs):
    '''
    Start MultiShotSubmitterWindow as standalone app.
    '''
    import sys

    # Build the GEN command line for Multi Shot Render Submitter UI
    from srnd_multi_shot_render_submitter.command_line import MultiShotRenderCommandLine
    multi_shot_command_line = MultiShotRenderCommandLine()
    parser, options_dict = multi_shot_command_line.build_command_line_interface(
        is_ui_context=True)

    from Qt.QtWidgets import QApplication
    app = QApplication(sys.argv)

    from srnd_qt.ui_framework.styling import palettes
    palettes.style_app_dark(app)

    # Open the submitter UI, using the command line arguments (if any)
    MultiShotSubmitterWindow(
        project=options_dict.get('project'),
        session_file_path=options_dict.get('session'),
        render_environments=options_dict.get('environments') or set(),
        shot_assignments_project=options_dict.get('shot_assignments_project') or os.getenv('FILM'),
        shot_assignments_user=options_dict.get('shot_assignments_user') or USER,
        icon_path=ICON_PATH,
        debug_mode=options_dict.get('debug_mode'))

    sys.exit(app.exec_())


if __name__ == '__main__':
    main()