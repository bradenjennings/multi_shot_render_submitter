#!/usr/bin/env python


import copy
import collections
import datetime
import fileseq
import logging
import os
import random
import re
import time
import traceback

from Qt.QtGui import QFont, QIcon
from Qt.QtCore import (Qt, QModelIndex, QSize, Signal)

from srnd_qt.ui_framework.models import base_abstract_item_model

from srnd_multi_shot_render_submitter.constants import Constants
from srnd_multi_shot_render_submitter.models import data_objects
from srnd_multi_shot_render_submitter import factory
from srnd_multi_shot_render_submitter import utils

# Preemptively import athena & Hydra for version preview system (before the UI opens)
import athena
import hydra

##############################################################################

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)

constants = Constants()

TIME_TAKEN_MSG = 'Time Taken To "{}": {} Seconds'

##############################################################################


class MultiShotRenderModel(base_abstract_item_model.BaseAbstractItemModel):
    '''
    A model containing a hierarchy of MSRS data objects which represent
    many output environments, source render nodes, pass for environments and groups.
    Note: This is part of a reusable framework for building applications
    that require a multi shot rendering system.

    Args:
        shot_assignments_project (str): optionally override the project shot assignments
            should be queried and populated from
        shot_assignments_user (str): optionally override the user shot assignments
            should be queried and populated from
        host_app (str):
        constants (Constants): optionally pass a shared instance of Constants module
    '''

    logMessage = Signal(str, int)
    toggleProgressBarVisible = Signal(bool)
    updateLoadingBarFormat = Signal(int, str)
    rescaleColumnsDefaultRequest = Signal(list)
    setColumnWidthRequest = Signal(int, int)

    updateOverviewRequested = Signal()
    updateDetailsPanel = Signal(bool)
    toggleShowFullEnvironments = Signal(bool)

    processingPassForEnv = Signal(QModelIndex, bool, str)
    framesResolveRequest = Signal(QModelIndex)
    versionResolveRequest = Signal(QModelIndex)
    itemsRemoved = Signal(list)
    environmentAdded = Signal(str)
    environmentsAdded = Signal(list)
    requestEnvironmentsThumbnails = Signal(dict)
    environmentsRemoved = Signal(list)
    renderNodeAdded = Signal(str)
    renderNodesRemoved = Signal(list)
    groupAdded = Signal(str)
    environmentHasRenderables = Signal(QModelIndex, bool)
    versionSystemChanged = Signal(str)

    renderSubmitStarted = Signal()
    renderSubmitFinished = Signal()

    aboutToApplyPreferences = Signal()
    applyPreferenceRequest = Signal(str, object)

    def __init__(
            self,
            shot_assignments_project=os.getenv('FILM'),
            shot_assignments_user=os.getenv('USER'),
            render_overrides_env_var='MSRS_RENDER_OVERRIDES',
            version=None,
            *args,
            **kwargs):
        super(MultiShotRenderModel, self).__init__(*args, **kwargs)

        self.HOST_APP = constants.HOST_APP
        self.TOOL_NAME = constants.TOOL_NAME
        self.TOOL_VERSION = version
        self.ORGANIZATION_NAME = 'Weta_Digital'
        # Location for RenderOverridesManager to look for plugins
        self.RENDER_OVERRIDES_ENV_VAR = render_overrides_env_var or 'MSRS_RENDER_OVERRIDES'

        self.SESSION_KEY_MULTI_SHOT_DATA = constants.SESSION_KEY_MULTI_SHOT_DATA
        self.SESSION_KEY_RENDER_NODES = constants.SESSION_KEY_RENDER_NODES
        self.SESSION_KEY_ENVIRONMENTS = constants.SESSION_KEY_ENVIRONMENTS
        self.SESSION_KEY_ENVIRONMENT = constants.SESSION_KEY_ENVIRONMENT
        self.SESSION_KEY_PASSES = constants.SESSION_KEY_PASSES

        self.NORMAL_ROW_HEIGHT = 36
        self.THUMBNAIL_HEIGHT = 46
        self.GROUP_HEIGHT = 30

        ######################################################################

        self._render_items = list()

        # Model config options
        self._update_host_app = True
        self._session_data_is_recalled_after_sync = True
        self._session_data_recalled_from_resource_after_sync = False
        self._sync_only_if_already_in_session = False

        # Global options for next submission
        self._version_global_system = constants.DEFAULT_CG_VERSION_SYSTEM
        self._email_additional_users = list()
        self._global_job_identifier = str()
        self._global_submit_description = str()
        self._show_environment_thumbnails = False
        self._shotsub_thumbnails_static = True
        self._frame_resolve_order_env_first = True

        # Job and dispatch global options
        self._dispatch_deferred = constants.DISPATCH_DEFERRED
        self._snapshot_before_dispatch = constants.SNAPSHOT_BEFORE_DISPATCH
        self._launch_paused = constants.LAUNCH_PAUSED
        self._launch_paused_expires = constants.LAUNCH_PAUSED_EXPIRES
        self._launch_zero_tier = constants.LAUNCH_ZERO_TIER
        self._apply_render_overrides = constants.APPLY_RENDER_OVERRIDES
        self._apply_dependencies = constants.APPLY_DEPEDENCIES
        self._compute_render_estimate = True

        # Listen to previously launched Jobs options
        self._listen_to_jobs = constants.LISTEN_TO_JOBS
        self._listen_to_jobs_frequency = constants.LISTEN_TO_JOBS_FREQUENCY

        # Validation global options
        self._show_summary_dialog = True
        self._send_summary_email_on_submit = True
        self._auto_refresh_from_shotgun = True
        self._cook_more_summary_details = False
        self._validation_auto_start = False
        self._summary_auto_scroll_to_validation = True
        # Cache to store summary header data if multi_shot_render opened via UI and Summary dialog invoked
        self._summary_view_header_data_cache = dict()

        self._show_full_environments = False
        self._sync_rules_active = constants.SYNC_RULES_ACTIVE
        self._sync_rules_include = list()
        self._sync_rules_exclude = list()

        # Tracking members (updated during submission)
        self._project_snapshot_hyref = None
        self._source_project = None
        self._source_project_version = None
        self._email_details_envs_data = list()
        self._last_submitted_uuid_to_plow_ids = dict()
        self._last_submitted_pass_wait_on_applied = dict()
        self._autosave_session_path = None
        self._request_interrupt = False
        self._is_rendering = False
        self._tmp_project_from_external_widget = None
        self._use_logger = True

        self._allocation_project = 0
        self._allocation_project_used = 0
        self._allocation_wall = 0
        self._stats = dict()

        # Other
        self._shot_assignments_project = shot_assignments_project
        self._shot_assignments_user = shot_assignments_user

        self._in_wait_on_interactive_mode = False
        self._is_submitting_in_dispatcher_task = False

        # Setup root abstract data node
        root_node = data_objects.RootMultiShotItem(
            version_global_system=constants.DEFAULT_CG_VERSION_SYSTEM,
            show_full_environments=False)
        self.set_root_node(root_node)
        root_node.logMessage.connect(self.emit_message)

        # Get and instantiate render overrides manager appropiate for this model
        render_overrides_manager_object = self.get_render_overrides_manager_object()
        self._render_overrides_manager = render_overrides_manager_object(
            cached=True,
            from_env_var=self.RENDER_OVERRIDES_ENV_VAR)
        _render_overrides_items_cached = self._render_overrides_manager.get_render_overrides_plugins()
        # msg = 'Instantiated Render Overrides Manager: "{}". '.format(self._render_overrides_manager)
        # msg += 'Has Overrides: "{}"'.format(_render_overrides_items_cached)
        # LOGGER.debug(msg)

        # Get and instantiate the farm job operations object
        scheduler_operations_object = self.get_scheduler_operations_object()
        self._scheduler_operations = scheduler_operations_object(parent=self)
        # msg = 'Instantiated Farm Job Operations: "{}"'.format(self._scheduler_operations)
        # LOGGER.debug(msg)

        # Other signal setup
        self.framesResolveRequest.connect(self.resolve_frames_for_index)

        # Route all messages to shell when in dispatching mode.
        if not self.get_in_host_app_ui():
            self.logMessage.connect(self._log_to_shell)


    ##########################################################################
    # Host app project


    def get_in_host_app(self):
        '''
        Query whether the Multi Shot Render Submitter has
        the desired host application and API available (even if no UI).

        Returns:
            in_host_app (bool):
        '''
        return False


    def get_in_host_app_ui(self):
        '''
        Query whether the Multi Shot Render Submitter is in the host app
        UI context or not, or acting in a standalone manner.
        Requires reimplementation for particular host app.

        Returns:
            in_host_app (bool):
        '''
        return False


    def new_project_in_host_app(self):
        '''
        Create a new project in host application.
        Reimplement this for particular host app.

        Returns:
            success (bool):
        '''
        return False


    def save_project_in_host_app(self, project):
        '''
        Save the current project in host application.
        Reimplement this for particular host app.

        Args:
            project (str):

        Returns:
            success (bool):
        '''
        return False


    def snapshot_host_app_project(self, oz_area=os.getenv('OZ_CONTEXT')):
        '''
        Snapshot the current host app project, which will save
        the project to a new registered product.
        Reimplement this for particular host app and required product type.

        Args:
            oz_area (str): area to make host app project snapshot for

        Returns:
            snapshot_location (str): returns a hyref, or file path of the just
                registered snapshot product.
        '''
        return str()


    def load_project_in_host_app(self, project):
        '''
        Load an existing project in host application.
        Reimplement this for particular host app.

        Args:
            project (str):

        Returns:
            success (bool):
        '''
        return False


    def get_project_has_unsaved_changes(self):
        '''
        Get whether the project has unsaved changes or not.
        Reimplement this for particular host app.

        Returns:
            project_has_unsaved_changes (bool)
        '''
        return False


    def get_project_is_saved_as_asset(self):
        '''
        Get whether the current project is saved as an asset.
        Otherwise False, if saved as file path.
        Reimplement this for particular host app.

        Returns:
            project_is_saved_as_asset (bool)
        '''
        return True


    def browse_for_product_in_host_app(
            self,
            current_asset_hyref=str(),
            start_area=os.getenv('OZ_CONTEXT'),
            title_str='Open GENProject',
            product_types=['GENProject'],
            file_types=['GENProject'],
            context=None,
            save=False):
        '''
        Browse for an existing host app project using the
        HyrefPreviewWidget, popup AreaBrowserDialog.
        Reimplement this for particular host app.

        Args:
            current_asset_hyref (str):
            start_area (str): oz area or hyref
            title_str (str):
            product_types (list): types of resources to pick (or products)
            file_types (list): types of files to pick if using file browser
            context (str):
            save (bool): otherwise load

        Returns:
            result (str): hyref or file path to the project
        '''
        products_settings = dict()
        for product_type in product_types:
            products_settings[product_type] = dict()
            products_settings[product_type]['productContext'] = {
                'productType': [product_type]}

        from srnd_qt.ui_framework.widgets import hyref_preview_widget
        hyref = hyref_preview_widget.HyrefPreviewWidget.browse_for_product(
            start_area=current_asset_hyref or start_area,
            products_settings=products_settings)

        return hyref


    def get_current_project(self):
        '''
        Get the currently open host app project (if any).
        Requires reimplementation for particular host app.

        Returns:
            source_project (str):
        '''
        return str()


    def _get_project_from_external_widget(self):
        '''
        Fallback for standalone host app mode.
        If API doesn't correctly keep track of current project.
        '''
        return self._tmp_project_from_external_widget


    def _set_project_from_external_widget(self, project):
        '''
        Fallback for standalone host app mode.
        If API doesn't correctly keep track of current project.
        '''
        self._tmp_project_from_external_widget = project


    def get_host_app_version(self):
        '''
        Return the version identifier this Multi Shot Render
        Submitter is running in.
        Requires reimplementation for particular host app.

        Returns:
            host_app_version (str):
        '''
        return self.HOST_APP


    def get_all_host_app_render_node_names(self):
        '''
        Return list of all GEN render node full names available in host app.
        Requires reimplementation for particular host app.

        Returns:
            render_nodes (list):
        '''
        return list()


    def get_all_missing_host_app_render_node_names(self):
        '''
        Return list of all GEN render node item full names
        available in host app (not in MSRS model).

        Returns:
            render_nodes (list):
        '''
        item_full_names = self.get_all_host_app_render_node_names()
        current_item_full_names = self.get_render_node_names()
        item_full_names = list(set(item_full_names) - set(current_item_full_names))
        return item_full_names


    def get_multi_shot_render_submitter_version(self):
        '''
        Get the version number of this Multi Shot Render Submitter.
        Requires reimplementation for particular host app.

        Returns:
            host_app_version (str):
        '''
        return None


    def _log_to_shell(self, msg, log_level=logging.NOTSET):
        '''
        Optionally log every message to show during dispatching mode.

        Args:
            msg (str):
            log_level (int):
        '''
        if self._use_logger:
            LOGGER.log(log_level, msg)
        else:
            print(msg)


    ##########################################################################
    # Sync


    def sync_render_nodes(
            self,
            from_selected_nodes=False,
            limit_to=None,
            only_missing=False,
            sync_details=True,
            emit_insertion_signals=False,
            render_nodes=None,
            verify_existing_items=True,
            **kwargs):
        '''
        Sync all Render nodes from host app.
        Requires reimplementation to gather required data, and populate data classes.

        Args:
            from_selected_nodes (bool): optionally only sync / populate from
                selected render nodes
            limit_to (list): optionally provide a list of strings of renderable item names
                to limit which render nodes are populated into MSRS data model.
            only_missing (bool): on sync the render nodes not already in this view.
            sync_details (bool): optionally sync details from node
            emit_insertion_signals (bool): whether to batch update view, or emit signal
                as each row added. Note: batch update requires all editors to reopen.
            render_nodes (list): list of host app render nodes to populate from
            verify_existing_items (bool):

        Returns:
            success_count (int): number of Render nodes successfully synced to data model
        '''
        return 0


    def add_render_nodes(self, item_full_names):
        '''
        Add a column for host app render node / pass name (if not already added).

        Args:
            item_full_names (list):

        Returns:
            success_count (int): number of Render nodes successfully synced to data model
        '''
        success_count = self.sync_render_nodes(
            render_nodes=item_full_names,
            only_missing=True,
            emit_insertion_signals=True)
        if success_count:
            self.updateOverviewRequested.emit()
        return success_count


    def insert_render_pass_for_envs_below_index(
            self,
            render_item,
            column=None,
            sync_details=True,
            emit_insertion_signals=False,
            parent_index=None):
        '''
        Add a unique render pass for env data object for every environment of current model.

        Args:
            render_item (RenderItem):
            column (int): column to insert render pass into MSRS data model
            sync_details (bool): optionally sync details from Katana node
            emit_insertion_signals (bool): whether to batch update view, or emit signal
                as each row added. Note: batch update requires all editors to reopen.
            parent_index (QModelIndex):

        Returns:
            success (bool):
        '''
        if not parent_index:
            parent_index = QModelIndex()
        if column == None:
            column = self.columnCount(parent_index)
        row_count = self.rowCount(parent_index)

        if emit_insertion_signals:
            self.beginInsertColumns(parent_index, column + 1, column + 1)

        # For every existing environment node, it is now necessary to insert
        # a RenderPassForEnvItem  node, to represent this environment / pass combination.
        last_item = None
        for row in range(row_count):
            qmodelindex = self.index(row, 0, parent_index)
            if not qmodelindex.isValid():
                continue
            environment_item = qmodelindex.internalPointer()
            if not environment_item.is_environment_item():
                continue
            pass_env_item_object = self.get_pass_for_env_item_object()

            # These abstract render pass for env data objects are not parented on to
            # environment item to avoid tree view trying to create child row indices.
            # Instead these data objects should be interpreted on every cell.
            pass_env_item = pass_env_item_object(
                queued=True,
                enabled=True,
                source_render_item=render_item,
                debug_mode=self._debug_mode)
            success = environment_item.insert_sibling(
                column,
                pass_env_item)

            if self._debug_mode:
                msg = 'Inserted "{}". '.format(pass_env_item.get_node_type())
                msg += 'Row: {}. Column: {}. Success: {}'.format(row, column, success)
                self.logMessage.emit(msg, logging.DEBUG)
                self.logMessage.emit(repr(pass_env_item), logging.DEBUG)

            pass_env_item.logMessage.connect(self.emit_message)

            pass_env_item.resolve_frames()

            # # Verify order is correct
            # passes = [s.get_source_render_item().get_pass_name() for s in environment_item.siblings()]
            # msg = 'Environment For Row: {}. '.format(row)
            # msg += 'Siblings New Order: {}. '.format(passes)
            # self.logMessage.emit(msg, logging.DEBUG)

            qmodelindex_sibling = qmodelindex.sibling(row, column + 1)
            pass_env_item._update_renderable_count_for_index(
                qmodelindex_sibling,
                renderable_offset=1)

            last_item = pass_env_item

            # NOTE: Every pass for each environment needs to be computed and cached separate
            if constants.EXPOSE_RENDER_ESTIMATE and self._compute_render_estimate:
                self.compute_render_estimates_for_environment(
                    environment_item,
                    pass_for_env_items=[pass_env_item])

        if emit_insertion_signals:
            self.endInsertColumns()

            # Now open all editors along entire column
            qmodelindex = self.index(0, column + 1, parent_index)
            self.openPersisentEditorForColumnRequested.emit(qmodelindex)

        render_item.logMessage.connect(self.emit_message)

        self.renderNodeAdded.emit(render_item.get_node_name())

        return True


    def sync_environments_from_host_app(self, include_current_env=True):
        '''
        Sync all output render environments from host application.
        Requires reimplementation to gather required data, and populate data classes.
        Note: Default implementation just adds the current oz Environment only.

        Args:
            include_current_env (bool): optionally add the current oz Environment
                if no other environments were synced from host app

        Returns:
            success_count (int): number of output render environments synced
        '''
        msg = 'Starting sync output render environments...'
        self.logMessage.emit(msg, logging.INFO)

        success_count = 0

        # Force include current environment off when running without UI
        if not self.get_in_host_app_ui():
           include_current_env = False

        # Always include the current Environment as first Environment
        if include_current_env and self.get_render_items() \
                and not self.get_environment_items():
            result = self.add_environment(oz_area=os.getenv('OZ_CONTEXT'))
            success_count += bool(result)

        return success_count


    def sync_production_data(self, force=False):
        '''
        Sync production data for all environments of session.

        Args:
            force (bool): whether to force update production data
        '''
        if not force:
            if not self._auto_refresh_from_shotgun:
                msg = 'Refresh production data from Shotgun is disabled! '
                msg += 'User should trigger refresh on demand...'
                self.logMessage.emit(msg, logging.WARNING)
                return
        msg = 'Starting sync all production data...'
        self.logMessage.emit(msg, logging.INFO)
        count = 0
        for qmodelindex_env in self.get_environment_items_indices():
            if not qmodelindex_env.isValid():
                continue
            environment_item = qmodelindex_env.internalPointer()
            if not environment_item:
                continue
            count += 1
            environment_item.sync_production_data()
            self.resolve_frames_for_index(
                qmodelindex_env,
                update_overview_requested=False)
        if count:
            self.updateOverviewRequested.emit()
            self.updateDetailsPanel.emit(False)


    def sync_render_nodes_and_environments(
            self,
            hyref=None,
            from_selected_nodes=False,
            limit_to=None,
            only_missing=False,
            keep_session_data=False,
            include_current_env=True,
            emit_insertion_signals=False,
            **kwargs):
        '''
        Sync all environments and render nodes from host app.
        Optionally first open a project to perform sync on.

        Args:
            hyref (str): optional project to first open
            from_selected_nodes (bool): optionally only sync / populate from
                selected render nodes
            limit_to (list): optionally provide a list of strings of renderable item names
                to limit which render nodes are populated into MSRS data model
            only_missing (bool): on sync the render nodes not already in this view.
            keep_session_data (bool): whether to reapply previous session data, after sync
                from host app is called.
            include_current_env (bool): optionally add the current oz Environment
                if no other environments were synced
            emit_insertion_signals (bool): whether to batch update view, or emit signal
                as each row added. Note: batch update requires all editors to reopen.

        Returns:
            success_count (int):
        '''
        limit_to = limit_to or None

        if hyref == str():
            msg = 'Hyref changed to blank string. clearing data model!'
            self.logMessage.emit(msg, logging.WARNING)
            self.clear_data()
            return 0

        # Only reapply session data if requested by argument, and current user preference,
        # and if not syncing from subset of nodes, or only missing.
        session_data = dict()
        recall_after_sync = keep_session_data and self._session_data_is_recalled_after_sync
        recall_after_sync = recall_after_sync and not any([from_selected_nodes, only_missing])
        if recall_after_sync:
            session_data = self.get_session_data() or dict()
            if not session_data:
                msg = 'Failed to serialize any session data before sync '
                msg += 'Was performed. Session will not include any previous '
                msg += 'User overrides!'
                self.logMessage.emit(msg, logging.WARNING)

        hyref = str(hyref or str()) or None

        msg = 'Starting sync render nodes & environments. '
        msg += 'From selected only: {}. '.format(from_selected_nodes)
        msg += 'Only missing: {}. '.format(only_missing)
        msg += 'Limit to: {}. '.format(limit_to)
        msg += 'Keep session data: {}'.format(keep_session_data)
        self.logMessage.emit(msg, logging.INFO)

        # Update progress bar at start
        self.toggleProgressBarVisible.emit(True)
        self.updateLoadingBarFormat.emit(0, msg + ' - %p%')

        within_existing_session = any([from_selected_nodes, only_missing])

        # Clear existing data if not populating from selected nodes or only missing
        if not within_existing_session:
            self.clear_data()

        if session_data:
            self.set_sync_rules_active(bool(session_data.get('sync_rules_active')))
            self.set_sync_rules_include(session_data.get('sync_rules_include', list()))
            self.set_sync_rules_exclude(session_data.get('sync_rules_exclude', list()))

        if hyref:
            msg = 'Loading project before sync: '
            self.logMessage.emit(msg + str(hyref), logging.INFO)

            # Update loading bar
            self.updateLoadingBarFormat.emit(5, msg + ' - %p%')

            # Now load the project
            success = self.load_project_in_host_app(hyref)
            if not success:
                msg = 'Failed to load project before sync called!'
                self.logMessage.emit(msg, logging.CRITICAL)
            # Cache this as the source project
            else:
                self._source_project = hyref

        if self.get_sync_only_if_already_in_session() and not limit_to:
            multi_shot_data = session_data.get(self.SESSION_KEY_MULTI_SHOT_DATA, dict())
            render_nodes_data = multi_shot_data.get(self.SESSION_KEY_RENDER_NODES, dict())
            limit_to = sorted(render_nodes_data.keys())

        if limit_to:
            msg = 'Syncing has been forced to limit populate to: "{}"'.format(limit_to)
            self.logMessage.emit(msg, logging.WARNING)

        render_item_added_count = self.sync_render_nodes(
            from_selected_nodes=from_selected_nodes,
            limit_to=limit_to,
            only_missing=only_missing,
            sync_details=True,
            emit_insertion_signals=emit_insertion_signals)

        self.toggleProgressBarVisible.emit(False)

        self.updateOverviewRequested.emit()

        if not render_item_added_count:
            self.toggleProgressBarVisible.emit(False)
            msg = 'Failed to sync any render nodes from current project!'
            self.logMessage.emit(msg, logging.WARNING)

        # Only sync Environment from from host app, if synced render item/s
        environment_item_added_count = 0
        if render_item_added_count:
            environment_item_added_count = self.sync_environments_from_host_app(
                include_current_env=include_current_env)

        if recall_after_sync and session_data:
            msg = 'Reapplying the previous session data from before sync'
            self.logMessage.emit(msg, logging.DEBUG)
            self.apply_session_data(session_data)

        return int(render_item_added_count + environment_item_added_count)


    def remove_selected_host_app_nodes(self):
        '''
        Remove the selected host app render nodes from the data model and view.

        Returns:
            removed_count (int):
        '''
        columns_to_item = dict()
        for c, render_item in enumerate(self.get_render_items()):
            is_selected = render_item.get_is_selected_in_host_app()
            if is_selected:
                columns_to_item[c + 1] = render_item.get_item_full_name()

        columns = list(columns_to_item.keys())

        msg = 'Starting remove selected host app nodes. '
        msg += 'Columns: "{}"'.format(columns)
        # msg += 'Items: "{}"'.format(columns_to_item.values())
        self.logMessage.emit(msg, logging.INFO)

        if not columns:
            return

        removed_count = self.clear_render_items(columns=columns)
        if removed_count:
            self.updateOverviewRequested.emit()

        return removed_count


    ##########################################################################
    # Environment


    def get_environment_items(self, with_renderable_passes=False):
        '''
        Get all the environment items data objects in this model.
        Optionally get only environment items that have active / renderable passes.

        Args:
            with_renderable_passes (bool): optionally only return environment items
                that has active renderable passes

        Returns:
            environment_items (list):
        '''
        environment_items = list()
        for qmodelindex in self.get_environment_items_indices():
            environment_item = qmodelindex.internalPointer()
            if with_renderable_passes:
                counter = 0
                for pass_env_item in environment_item.get_pass_for_env_items():
                    if pass_env_item.get_active():
                        counter += 1
                        break
                if not counter:
                    continue
            environment_items.append(environment_item)
        return environment_items


    def get_environment_by_name(self, oz_area=os.getenv('OZ_CONTEXT')):
        '''
        Get the first EnvironmentItem by environment name.

        Args:
            oz_area (str):

        Returns:
            environment_item (EnvironmentItem):
        '''
        for environment_item in self.get_environment_items():
            if oz_area == environment_item.get_oz_area():
                return environment_item


    def get_environments_by_name(self, oz_area=os.getenv('OZ_CONTEXT')):
        '''
        Get all the EnvironmentItems by environment name.

        Args:
            oz_area (str):

        Returns:
            environment_items (list): list of EnvironmentItem
        '''
        environment_items = list()
        for environment_item in self.get_environment_items():
            if oz_area == environment_item.get_oz_area():
                environment_items.append(environment_item)
        return environment_items


    def get_environment_item_by_index(self, index):
        '''
        Get a particular EnvironmentItem (or subclass) by index.

        Returns:
            environment_items (list):
        '''
        environment_items = self.get_environment_items()
        if index <= len(environment_items):
            return environment_items[index]


    def get_environment_index_by_identifier(self, identifier):
        '''
        Get a particular QModelIndex by MSRS environment identifier.

        Args:
            identifier (str): MSRS environment identifier (including nth index number)

        Returns:
            qmodelindex (QModelIndex):
        '''
        for qmodelindex in self.get_environment_items_indices():
            if not qmodelindex.isValid():
                continue
            environment_item = qmodelindex.internalPointer()
            if environment_item.get_environment_name_nice() == identifier:
                return qmodelindex


    def get_index_by_identifier(self, identifier):
        '''
        Get a particular QModelIndex by MSRS identifier.

        Args:
            identifier (str): MSRS item identifier (including nth index number)

        Returns:
            qmodelindex (QModelIndex):
        '''
        column_count = self.columnCount(QModelIndex())
        for qmodelindex_env in self.get_environment_items_indices():
            if not qmodelindex_env.isValid():
                continue
            environment_item = qmodelindex_env.internalPointer()
            if environment_item.get_environment_name_nice() == identifier:
                return qmodelindex_env
            for c in range(column_count):
                qmodelindex_pass = qmodelindex_env.sibling(qmodelindex_env.row(), c)
                if not qmodelindex_pass.isValid():
                    continue
                pass_env_item = qmodelindex_pass.internalPointer()
                identifier_pass = pass_env_item.get_identifier(nice_env_name=True)
                if identifier_pass == identifier:
                    return qmodelindex_pass


    def get_index_by_uuid(self, msrs_uuid):
        '''
        Get a particular QModelIndex by MSRS uuid.

        Args:
            msrs_uuid (str):

        Returns:
            qmodelindex (QModelIndex):
        '''
        column_count = self.columnCount(QModelIndex())
        for qmodelindex_env in self.get_environment_items_indices():
            if not qmodelindex_env.isValid():
                continue
            environment_item = qmodelindex_env.internalPointer()
            if environment_item.get_identity_id() == msrs_uuid:
                return qmodelindex_env
            for c in range(column_count):
                qmodelindex_pass = qmodelindex_env.sibling(qmodelindex_env.row(), c)
                if not qmodelindex_pass.isValid():
                    continue
                pass_env_item = qmodelindex_pass.internalPointer()
                if pass_env_item.get_identity_id() == msrs_uuid:
                    return qmodelindex_pass


    def _update_environments_indices(self):
        '''
        Update the cached environments indices.
        '''
        environments_counter = dict()
        for i, environment_item in enumerate(self.get_environment_items()):
            environment = environment_item.get_oz_area()
            if environment not in environments_counter.keys():
                environments_counter[environment] = 0
            environments_counter[environment] += 1
            index = environments_counter[environment]
            environment_item._set_cached_environment_index(index)


    def get_item_environment(self, item, show_full_environments=None):
        '''
        Get the environment of a item.

        Args:
            item (object):
            show_full_environment (bool):

        Returns:
            oz_area (str):
        '''
        if not isinstance(show_full_environments, bool) :
            show_full_environments = self.get_show_full_environments()
        oz_area = None
        if item.is_environment_item():
            if show_full_environments:
                oz_area = str(item.get_oz_area())
            else:
                oz_area = str(item.get_scene_shot_area())
        else:
            environment_item = item.get_environment_item()
            if environment_item:
                if show_full_environments:
                    oz_area = environment_item.get_oz_area()
                else:
                    oz_area = environment_item.get_scene_shot_area()
        return oz_area


    def get_environment_items_indices(self, parent_index=None, depth_limit=2):
        '''
        Get list of main model EnvironmentItem indices.
        Note: EnvironmentItem can only currently be at root of data model or under a group.

        Args:
            parent_index (QModelIndex): optionally only get environment item indices below this QModelIndex
            depth_limit (int): how far to traverse below parent index, to find environment item indices

        Returns:
            environment_items_indices (list):
        '''
        parent_index = parent_index or QModelIndex()
        row_count = self.rowCount(parent_index)
        environment_items_indices = list()
        for row in range(row_count):
            qmodelindex = self.index(row, 0, parent_index)
            if not qmodelindex.isValid():
                continue
            item = qmodelindex.internalPointer()
            # Environment items are normally at the root of the data model
            if item.is_environment_item():
                environment_items_indices.append(qmodelindex)
            # However they can also be in GroupItem
            elif item.is_group_item() and depth_limit > 1:
                row_count_depth2 = self.rowCount(qmodelindex)
                for row_depth2 in range(row_count_depth2):
                    qmodelindex_depth2 = self.index(row_depth2, 0, qmodelindex)
                    if not qmodelindex_depth2.isValid():
                        continue
                    item_depth2 = qmodelindex_depth2.internalPointer()
                    if item_depth2.is_environment_item():
                        environment_items_indices.append(qmodelindex_depth2)
        return environment_items_indices


    def add_environment(
            self,
            oz_area=None,
            passes_states=None,
            in_group_item=None,
            in_group_index=None,
            insertion_row=None,
            sync_production_data=True,
            shot_object=None,
            copy_from=None,
            copy_overrides_from=None,
            prepare_for_display=True,
            validate_environment=True,
            request_thumbnail=True,
            show_dialog=False,
            parent=None):
        '''
        Add a new output environment with optional states per pass, or copy overrides and
        production data from another existing data object (for performance).

        Args:
            oz_area (str): if not specified then a popup dialog will let you pick
            passes_states (dict): optionally pass a mapping of render pass item name to states dict.
                the states keys within the pass map is 'queued', 'enabled'
            in_group_item (GroupItem): optionally specify the parent of the environment item
            in_group_index (QModelIndex): the QModelIndex of the parent group
            insertion_row (int): optionally specify row to insert this environment into parent index
            sync_production_data (bool): whether to sync production data or not,
                before requesting framesResolveRequest.
            shot_object (periscope2.Shot): optionally pass the already queried periscope2
                Shot or Asset object pertianing to this environment
            copy_from (EnvironmentItem): if environment item to copy production data
                from is specified then sync_production_data argument is ignored.
            copy_overrides_from (EnvironmentItem): copy all the overrides from another existing
                environment item
            prepare_for_display (bool): whether to open editors, emit signals for various
                UI updates, and whether to request frames to be resolved
            validate_environment (bool):
            request_thumbnail (bool):
            show_dialog (bool): optionally show any warning dialog or not

        Returns:
            environment_item (EnvironmentItem): if show dialog is True, then the return might be a list
                of environment item
        '''
        oz_area = oz_area or os.getenv('OZ_CONTEXT')
        icon_path = os.path.join(constants.ICONS_DIR_QT, 'add.png')

        # Only validate the production environment if required
        if validate_environment:
            environments = self.get_and_validate_oz_area_to_add(
                oz_area=oz_area,
                icon_path=icon_path,
                show_dialog=show_dialog,
                parent=parent)
            if not environments:
                return list()
            # User picked environments from dialog, so call add_environments N number of times
            if show_dialog and len(environments) > 1:
                return self.add_environments(environments)
            # User picked one environment
            elif environments:
                oz_area = environments[0]

        # Must have an environment string to add
        if not oz_area:
            msg = 'Environment to add is invalid: {}'.format(oz_area)
            self.logMessage.emit(msg, logging.WARNING)
            return

        show_environment_thumbnails = self.get_show_environment_thumbnails()
        render_items = self.get_render_items()

        existing_env_count = len(self.get_environment_items_indices())

        # NOTE: When there are multiple environments already in the model, then make next
        # inserted items inherit states (if every other column has the same states).
        if not passes_states and not copy_overrides_from:
            passes_states = dict()
            for c, render_item in enumerate(render_items):
                item_full_name = render_item.get_item_full_name()
                if existing_env_count >= 1:
                    queued_states, enabled_states = self.get_primary_states_along_column(c + 1)
                    queued = any(queued_states)
                    enabled = any(enabled_states)
                else:
                    queued = True
                    enabled = True
                passes_states[item_full_name] = dict()
                passes_states[item_full_name]['queued'] = queued
                passes_states[item_full_name]['enabled'] = enabled

        parent_index = in_group_index or QModelIndex()
        if insertion_row == None:
            insertion_row = self.rowCount(parent_index)

        msg = 'Adding environment: {}'.format(oz_area)
        # if self._debug_mode:
        #     msg += 'Copy From: "{}". '.format(copy_from)
        #     msg += 'Shot Object: "{}"'.format(shot_object)
        self.logMessage.emit(msg, logging.INFO)

        # msg = 'Using Existing Shot Object: "{}". '.format(shot_object)
        # msg += 'Sync Production Data Is: {}'.format(sync_production_data)
        # self.logMessage.emit(msg, logging.INFO)

        # Optionally emit insertion signal every time node is added.
        if prepare_for_display:
            self.beginInsertRows(
                parent_index,
                insertion_row,
                insertion_row)

        # Create abstract environment node (might be subclass)
        environment_item_object = self.get_environment_item_object()
        environment_item_instance = environment_item_object(
            oz_area=oz_area,
            debug_mode=self._debug_mode,
            insertion_row=insertion_row,
            parent=in_group_item or self._root_node)
        environment_item_instance.logMessage.connect(self.emit_message)

        environment_item_instance.set_frame_resolve_order_env_first(
            self._frame_resolve_order_env_first)

        # Sync production data now (unless disabled from preferences)
        synced_production_data = False
        if (sync_production_data or shot_object) and not copy_from:
            shot_object = environment_item_instance.sync_production_data(
                shot_object=shot_object)
            # Optionally seek and cache the Environment gif path
            if show_environment_thumbnails:
                environment_item_instance.derive_and_cache_shot_thumbnail_path(
                    shot_object=shot_object,
                    animated=not self._shotsub_thumbnails_static)
            synced_production_data = True
        # Optionally copy the existing production data from another environment item
        elif copy_from:
            environment_item_instance.copy_production_data(copy_from)
            synced_production_data = True

        # Optionally copy the existing overrides from another environment item
        if copy_overrides_from:
            overrides_dict = copy_overrides_from.copy_overrides()
            environment_item_instance.paste_overrides(overrides_dict)

        # For every available Render pass name, insert a RenderPassForEnvItem  abstract data node.
        for c, render_item in enumerate(render_items):
            render_item = render_items[c]
            item_full_name = render_item.get_item_full_name()

            queued = True
            enabled = True
            if copy_overrides_from and copy_overrides_from.is_environment_item():
                other_pass_for_env_item = copy_overrides_from.get_pass_for_env_by_full_name(item_full_name)
                if other_pass_for_env_item:
                    queued = other_pass_for_env_item.get_queued()
                    enabled = other_pass_for_env_item.get_enabled()
            else:
                pass_states = passes_states.get(item_full_name) or dict()
                queued = pass_states.get('queued', True)
                enabled = pass_states.get('enabled', True)

                # Is source render item is disabled then this pass should always be initially unqueued
                is_enabled = render_item.get_enabled()
                if not is_enabled:
                    queued = False

            if all([queued, enabled]):
                # Update the cached renderable count on the render item (column header)
                render_item._renderable_count_for_render_node += 1
                # Update the cached renderable count on the render item (column 0 current row)
                environment_item_instance._renderable_count_for_env += 1

            # If other existing render pass for env provided, copy and paste overrides to it (if any)
            overrides_dict = None
            if copy_overrides_from:
                other_pass_for_env_item = copy_overrides_from.get_pass_for_env_by_full_name(
                    item_full_name)
                if other_pass_for_env_item:
                    overrides_dict = other_pass_for_env_item.copy_overrides()

            pass_for_env_item_object = self.get_pass_for_env_item_object()
            # These abstract RenderPassForEnvItem  nodes are not parented on to
            # EnvironmentItem to avoid tree view trying to create child row indices.
            # Instead these abstract classes should be interpreted on every cell.
            pass_for_env_item = pass_for_env_item_object(
                queued=queued,
                enabled=enabled,
                overrides_dict=overrides_dict,
                source_render_item=render_item,
                first_sibling=environment_item_instance,
                debug_mode=self._debug_mode)
            pass_for_env_item.logMessage.connect(self.emit_message)

        if in_group_item:
            for _pass_env_item in environment_item_instance.get_pass_for_env_items():
                _pass_env_item._parent = in_group_item

        qmodelindex = self.index(insertion_row, 0, parent_index)

        # Trigger resolve frames for the first time (if have production data)
        if synced_production_data:
            self.framesResolveRequest.emit(qmodelindex)

        if constants.EXPOSE_RENDER_ESTIMATE and self._compute_render_estimate:
            self.compute_render_estimates_for_environment(
                environment_item_instance)

        if prepare_for_display:
            # Optionally emit insertion signal every time node is added.
            self.endInsertRows()
            # Environments were added so update cached indices
            self._update_environments_indices()
            # Open all editors for row
            self.openPersisentEditorForRowRequested.emit(qmodelindex)
            # Emit signal so splash screen might become visible
            self.environmentAdded.emit(oz_area)

        # Optionally request efficient shotsub thumbnail to be prepared in another thread
        if all([
                request_thumbnail,
                self.get_show_environment_thumbnails(),
                constants.GENERATE_EFFICIENT_THUMBNAILS_IN_THREAD]):
            from Qt.QtWidgets import QApplication
            QApplication.processEvents()
            thumbnail_path = environment_item_instance.get_thumbnail_path()
            if thumbnail_path:
                envs_to_thumbnails_paths = dict()
                envs_to_thumbnails_paths[oz_area] = thumbnail_path
                self.requestEnvironmentsThumbnails.emit(envs_to_thumbnails_paths)

        return environment_item_instance


    def add_environments(
            self,
            environments,
            in_group_item=None,
            in_group_index=None,
            insertion_row=None,
            validate_environment=False,
            batch_add=True,
            skip_existing=False):
        '''
        Add multiple environments to Multi Shot data model.

        Args:
            environments (list): add list of environments
            in_group_item (GroupItem): optionally specify the parent of the environment item
            in_group_index (QModelIndex): the QModelIndex of the parent group
            insertion_row (int): optionally specify row to insert this environment into parent index
            validate_environment (bool): NOTE: already prevalidated in view dropEvent and via Environment dialog
            batch_add (bool): batch add multiple environments together into one insert rows call.
            skip_existing (bool): optionally skip adding another instance of environment already in model

        Returns:
            environment_items (list): list of environment item data objects
        '''
        ts = time.time()

        if not environments:
            environments = list()

        if not environments:
            return list()

        msg = 'Adding environments: {}'.format(environments)
        self.logMessage.emit(msg, logging.INFO)

        self.toggleProgressBarVisible.emit(True)

        parent_index = in_group_index or QModelIndex()
        if insertion_row == None:
            insertion_row = self.rowCount(parent_index)

        if batch_add:
            self.beginInsertRows(
                parent_index,
                insertion_row,
                insertion_row)

        if skip_existing:
            existing_environments = self.get_environments()

        ######################################################################
        # Optionally gather all production data at once

        GET_ALL_PRODUCTION_SHOTS_AT_ONCE = True
        shot_objects_for_envs = dict()
        if GET_ALL_PRODUCTION_SHOTS_AT_ONCE:
            from srnd_multi_shot_render_submitter import production_info
            shot_objects_for_envs = production_info.get_shots_for_environments(
                environments)

        ######################################################################

        environment_items = collections.OrderedDict()
        for i, environment in enumerate(environments):
            if skip_existing:
                if environment in existing_environments:
                    msg = 'Skipping adding same environment: {}'.format(environment)
                    self.logMessage.emit(msg, logging.WARNING)
                    continue

            row = insertion_row + len(environment_items.keys())

            percent = int((float(i) / len(environments)) * 100)
            msg = 'Adding environment: {}'.format(environment)
            # msg += 'Row: "{}"'.format(row)
            # self.logMessage.emit(msg, logging.INFO)
            self.updateLoadingBarFormat.emit(percent, msg + ' - %p%')

            shot_object = shot_objects_for_envs.get(environment)
            environment_item = self.add_environment(
                environment,
                in_group_item=in_group_item,
                in_group_index=in_group_index,
                insertion_row=row,
                sync_production_data=not bool(shot_object),
                shot_object=shot_object, # use the already queried periscope shot (if available)
                show_dialog=False,
                prepare_for_display=not batch_add,
                validate_environment=validate_environment,
                request_thumbnail=False) # defer thumbnail request to later
            if environment_item:
                environment_items[environment] = environment_item

        if batch_add:
            self.endInsertRows()

            # Environments were added so update cached indices
            self._update_environments_indices()

            # Emit signal so splash screen might become visible
            environments = environment_items.keys()
            self.environmentsAdded.emit(environments)

            # Open all editors at once
            for r in range(insertion_row, self.rowCount(parent_index), 1):
                qmodelindex = self.index(r, 0, parent_index)
                self.openPersisentEditorForRowRequested.emit(qmodelindex)

            # Hide the progress bar request
            self.toggleProgressBarVisible.emit(False)

        te = time.time() - ts
        count = len(environment_items.keys())
        msg = 'Add environments took {} seconds for {} items'.format(te, count)
        self.logMessage.emit(msg, logging.INFO)

        # Optionally request efficient shotsub thumbnail to be prepared in another thread
        if all([
                self.get_show_environment_thumbnails(),
                constants.GENERATE_EFFICIENT_THUMBNAILS_IN_THREAD]):
            from Qt.QtWidgets import QApplication
            QApplication.processEvents()
            envs_to_thumbnails_paths = dict()
            for env_item in environment_items.values():
                thumbnail_path = env_item.get_thumbnail_path()
                if thumbnail_path:
                    envs_to_thumbnails_paths[env_item.get_oz_area()] = thumbnail_path
            if envs_to_thumbnails_paths:
                self.requestEnvironmentsThumbnails.emit(envs_to_thumbnails_paths)

        return environment_items


    def add_environments_of_current_sequence(
            self,
            project=None,
            tree=None,
            sequence=None):
        '''
        Add all the environments of current sequence or asset.

        Args
            project (str)::
            tree (str):
            sequence (str):

        Returns:
            environment_items (list): list of environment item data objects
        '''
        project = project or os.getenv('FILM')
        tree = tree or os.getenv('TREE')
        sequence = sequence = os.getenv('SCENE')

        path = '/' + '/'.join([project, tree, sequence])

        from srnd_multi_shot_render_submitter import production_info

        environments = list()
        for code in production_info.get_child_codes(path):
            environment = '/' + '/'.join([project, tree, sequence, code])
            environments.append(environment)

        return self.add_environments(
            environments,
            skip_existing=True)


    def add_environment_for_current_context(self):
        '''
        Add shot for current shells $OZ_CONTEXT.

        Returns:
            environment_item (EnvironmentItem):
        '''
        return self.add_environment(os.getenv("OZ_CONTEXT"))


    ##########################################################################


    def get_in_initial_state(self):
        '''
        Get whether model has render items or environment items.
        NOTE: If has neither then in initial state.

        Returns:
            in_initial_state (bool):
        '''
        has_render_items = bool(self.get_render_items())
        has_environment_items = len(self.get_environment_items())
        return not any([has_render_items, has_environment_items])


    def get_primary_states_along_column(self, column):
        '''
        Formulate a list of queued states and list of enabled states for column.

        Returns:
            queued_states, enabled_states (tuple):
        '''
        queued_states, enabled_states = list(), list()
        for qmodelindex in self.get_environment_items_indices():
            if not qmodelindex.isValid():
                continue
            env_item = qmodelindex.internalPointer()
            pass_env_item = env_item.sibling(column)
            if pass_env_item:
                queued_states.append(pass_env_item.get_queued())
                enabled_states.append(pass_env_item.get_enabled())
        return queued_states, enabled_states


    def add_group(self, group_name='myGroupName'):
        '''
        Create a group at next row of root index.

        Args:
            group_name (str):

        Returns:
            group_item, qmodelindex (tuple): tuple of GroupItem or subclass
                and insertion QModelIndex
        '''
        # NOTE: Get a unique group name that doesnt yet exist
        group_name = utils.get_unique_name(
            group_name,
            existing_names=self.get_group_names())
        parent_index = QModelIndex()
        row_count = self.rowCount(parent_index)
        msg = 'Adding group: "{}". Row: "{}"'.format(group_name, row_count)
        self.logMessage.emit(msg, logging.INFO)
        # Groups are always currently created at root index
        self.beginInsertRows(
            parent_index,
            row_count,
            row_count)
        group_item_object = self.get_group_item_object()
        group_item_instance = group_item_object(
            group_name,
            debug_mode=self._debug_mode,
            parent=self._root_node)
        self.endInsertRows()
        group_item_instance.logMessage.connect(self.emit_message)
        qmodelindex = self.index(row_count, 0, parent_index)
        self.groupAdded.emit(group_name)
        return group_item_instance, qmodelindex


    def get_and_validate_oz_area_to_add(
            self,
            oz_area=None,
            icon_path=None,
            show_dialog=False,
            parent=None):
        '''
        Validate a specified environment, otherwise get environment/s from a
        popup dialog, and validate all of them. Return a list of environments.

        Args:
            oz_area (str): if not specified then a popup dialog will let you pick
            icon_path (str): path for optional icon for popul dialog
            show_dialog (bool): optionally show any warning dialog or not

        Returns:
            environments (list): list of oz area / environments added
        '''
        oz_area = oz_area or os.getenv('OZ_CONTEXT')

        # Convert dev tree to legitmate assets area for product register.
        if oz_area and '/dev/' in oz_area:
            oz_area = utils.convert_dev_tree_to_assets_area(oz_area)
        environments_to_add = list()

        if not oz_area or show_dialog:
            from Qt.QtWidgets import QApplication
            from srnd_multi_shot_render_submitter.dialogs import add_environments_dialog
            add_render_env_dialog = add_environments_dialog.AddEnvironmentsDialog(
                environment=oz_area,
                icon_path=icon_path,
                parent=parent or QApplication.activeWindow())
            # NOTE: Rather than launch blocking environment chooser dialog...
            # if add_render_env_dialog.exec_():
            #     environments_to_add = add_render_env_dialog.get_environments_to_add()
            # Launch as non modal and listen for signal to add requested environment/s
            add_render_env_dialog.addEnvironmentsRequest.connect(
                self.add_environments)
            add_render_env_dialog.show()
            # No environments available when first launching non modal dialog
            return list()
        else:
            environments_to_add = [oz_area]

        # Must have at least one environment to add
        if not environments_to_add:
            msg = 'No environment/s specified to add!'
            self.logMessage.emit(msg, logging.WARNING)
            return list()

        # Validate each oz area / environment
        import oz
        valid_environments = list()
        for environment in environments_to_add:
            if not environment:
                continue
            if not oz.Area.is_valid(environment):
                msg = 'Environment is not valid: "{}". '.format(environment)
                self.logMessage.emit(msg, logging.WARNING)
                continue
            valid_environments.append(environment)

        if not valid_environments:
            msg = 'No valid environments to add!'
            self.logMessage.emit(msg, logging.WARNING)
            return list()

        return valid_environments


    ##########################################################################
    # Session data


    def get_session_data(self, use_submit_note=False):
        '''
        Serialize all EnvironmentItem/s, RenderItem/s and PassForEnvItem/s
        into a subset of the overall session data. This is the core data
        to bring back model to the previous session state.
        Note: Any session data in an external view or Applicaton, should
        be serialized externally.

        Args:
            use_submit_note (str):

        Returns:
            session_data (dict):
        '''
        msg = 'Gathering session data'
        self.logMessage.emit(msg, logging.INFO)

        session_data = dict()

        current_project = self.get_current_project()
        if current_project:
            session_data['project'] = current_project

        ######################################################################
        # Global options available from model to serialize

        session_data['version_global_system'] = self.get_version_global_system()
        render_items = self.get_render_items()
        if render_items:
            current_project_version = render_items[0].get_current_project_version()
            if current_project_version and isinstance(current_project_version, int):
                session_data['source_project_version'] = current_project_version

        session_data['email_additional_users'] = self.get_email_additional_users()
        session_data['additional_job_identifier'] = self.get_global_job_identifier()
        session_data['description_global'] = self.get_global_submit_description()
        session_data['send_summary_email_on_submit'] = self.get_send_summary_email_on_submit()

        session_data['sync_rules_active'] = self.get_sync_rules_active()
        session_data['sync_rules_include'] = self.get_sync_rules_include()
        session_data['sync_rules_exclude'] = self.get_sync_rules_exclude()

        # Job and dispatch global options
        session_data['dispatch_deferred'] = self.get_dispatch_deferred()
        session_data['snapshot_before_dispatch'] = self.get_snapshot_before_dispatch()
        session_data['launch_paused'] = self.get_launch_paused()
        session_data['launch_paused_expires'] = self.get_launch_paused_expires()
        session_data['launch_zero_tier'] = self.get_launch_zero_tier()
        session_data['apply_render_overrides'] = self.get_apply_render_overrides()
        session_data['apply_dependencies'] = self.get_apply_dependencies()

        # Summary and validation options
        # Also store the cached summary view header data (if any)
        if self._summary_view_header_data_cache:
            session_data['summary_view_header_data_cache'] = self._summary_view_header_data_cache or dict()

        session_data['host_app'] = self.HOST_APP

        ######################################################################
        # First collect session data about source render items (on RenderItem/s)

        multi_shot_data = dict()
        multi_shot_data[self.SESSION_KEY_RENDER_NODES] = dict()
        for render_item in self.get_render_items():
            item_full_name = render_item.get_item_full_name()
            if item_full_name in multi_shot_data[self.SESSION_KEY_RENDER_NODES].keys():
                msg = 'Details about render item already added to '
                msg += 'session data. Node name: "{}". '.format(item_full_name)
                self.logMessage.emit(msg, logging.WARNING)
                continue
            render_node_data = render_item.get_session_data() or dict()
            multi_shot_data[self.SESSION_KEY_RENDER_NODES][item_full_name] = render_node_data

        ######################################################################
        # Then collect session data about each EnvironmentItem/s, and child PassForEnvItem/s

        multi_shot_data[self.SESSION_KEY_ENVIRONMENTS] = list()

        for qmodelindex in self.get_environment_items_indices():
            if not qmodelindex.isValid():
                continue
            environment_item = qmodelindex.internalPointer()
            oz_area = str(environment_item.get_oz_area())
            shot_data = environment_item.get_session_data(use_submit_note)
            # Collect details for every RenderItem of this Shot / EnvironmentItem
            for pass_env_item in environment_item.get_pass_for_env_items():
                render_item = pass_env_item.get_source_render_item()
                if not render_item:
                    msg = 'No Associated Render Item For: "{}". '.format(pass_env_item)
                    self.logMessage.emit(msg, logging.WARNING)
                    continue
                full_name = render_item.get_item_full_name()
                if full_name in shot_data[self.SESSION_KEY_PASSES].keys():
                    msg = 'Pass for environment already added to '
                    msg += 'session data. Environment: "{}". '.format(oz_area)
                    msg += 'Node name: "{}". '.format(full_name)
                    self.logMessage.emit(msg, logging.WARNING)
                    continue
                pass_data = pass_env_item.get_session_data(use_submit_note)
                shot_data[self.SESSION_KEY_PASSES][full_name] = pass_data

            # Add entire EnvironmentItem and all child PassForEnvItem/s
            multi_shot_data[self.SESSION_KEY_ENVIRONMENTS].append(shot_data)

        session_data[self.SESSION_KEY_MULTI_SHOT_DATA] = multi_shot_data

        return session_data


    def apply_session_data(self, session_data=None, **kwargs):
        '''
        Apply all per EnvironmentItem, RenderItem, and
        PassForEnvItem details from primary part of session data.

        Args:
            session_data (dict):

        Returns:
            sync_env_count, sync_render_count, sync_pass_count (tuple): number of synced items
        '''
        sync_env_count = 0
        sync_render_count = 0
        sync_pass_count = 0
        session_data = session_data or dict()

        # No session data to apply
        if not session_data:
            return sync_env_count, sync_render_count, sync_pass_count

        # Batch all updates into one update for view
        self.beginResetModel()

        msg = 'Applying session data to model'
        self.logMessage.emit(msg, logging.INFO)

        ######################################################################
        # Apply other model options

        value = session_data.get(
            'version_global_system',
            constants.DEFAULT_CG_VERSION_SYSTEM)
        self.set_version_global_system(value)

        value = session_data.get(
            'dispatch_deferred',
            constants.DISPATCH_DEFERRED)
        self.set_dispatch_deferred(value)

        value = session_data.get(
            'snapshot_before_dispatch',
            constants.SNAPSHOT_BEFORE_DISPATCH)
        self.set_snapshot_before_dispatch(value)

        value = session_data.get(
            'launch_paused',
            constants.LAUNCH_PAUSED)
        self.set_launch_paused(value)

        value = session_data.get(
            'launch_paused_expires',
            constants.LAUNCH_PAUSED_EXPIRES)
        self.set_launch_paused_expires(value)

        value = session_data.get(
            'launch_zero_tier',
            constants.LAUNCH_ZERO_TIER)
        self.set_launch_zero_tier(value)

        value = session_data.get(
            'apply_render_overrides',
            constants.APPLY_RENDER_OVERRIDES)
        self.set_apply_render_overrides(value)

        value = session_data.get(
            'apply_dependencies',
            constants.APPLY_DEPEDENCIES)
        self.set_apply_dependencies(value)

        # Extract the cached summary view header data (if any)
        self._summary_view_header_data_cache = session_data.get(
            'summary_view_header_data_cache', dict())

        value = session_data.get(
            'sync_rules_active',
            constants.SYNC_RULES_ACTIVE)
        self.set_sync_rules_active(value)

        value = session_data.get('sync_rules_include', list())
        self.set_sync_rules_include(value)

        value = session_data.get('sync_rules_exclude', list())
        self.set_sync_rules_exclude(value)

        ######################################################################
        # First apply session data to source Render items / node (on RenderItem/s)

        multi_shot_data = session_data.get(self.SESSION_KEY_MULTI_SHOT_DATA, dict())

        render_nodes_data = multi_shot_data.get(self.SESSION_KEY_RENDER_NODES, dict())
        for render_item in self.get_render_items():
            full_name = render_item.get_item_full_name()
            if full_name not in render_nodes_data.keys():
                msg = 'Render node in synced data doesn\'t '
                msg += 'exist in session data. node name: "{}". '.format(full_name)
                msg += 'Skipping applying any overrides!'
                self.logMessage.emit(msg, logging.WARNING)
                continue
            render_node_data = render_nodes_data[full_name]
            if render_node_data:
                sync_render_count += render_item.apply_session_data(render_node_data)

        ######################################################################
        # Then apply session data to EnvironmentItem/s, and child PassForEnvItem/s

        # Existing environments in synced data from host app.
        # NOTE: The same environment might be appear multiple times.
        oz_areas_list = list(self.get_environments())
        group_items = dict()
        added_env_items = dict()

        shots_data = multi_shot_data.get(self.SESSION_KEY_ENVIRONMENTS, list())
        for shot_data in shots_data:
            oz_area = shot_data.get(self.SESSION_KEY_ENVIRONMENT)
            # Must have valid environment name and data to update model
            if not all([shot_data, oz_area]):
                msg = 'Environment empty name or data: "{}"'.format(oz_area)
                self.logMessage.emit(msg, logging.WARNING)
                continue

            # Get the group section to add this EnvironmentItem into
            group_name = shot_data.get('group_name')
            group_item, qmodelindex_group = None, None
            if group_name:
                result = group_items.get(group_name)
                if result and all([result.get('item'), result.get('index')]) :
                    group_item = result.get('item')
                    qmodelindex_group = result.get('index')
                else:
                    msg = 'Adding new group on apply session data: "{}". '.format(group_name)
                    self.logMessage.emit(msg, logging.INFO)
                    group_item, qmodelindex_group = self.add_group(group_name=group_name)
                    group_items[group_name] = {'item': group_item, 'index': qmodelindex_group}

            # Details about applying data to another instance of environment
            if oz_area in oz_areas_list:
                index = oz_areas_list.index(oz_area)
                msg = 'Applying data to instance of environment: "{}". '.format(oz_area)
                msg += 'At index: "{}"'.format(index)
                self.logMessage.emit(msg, logging.INFO)
                environment_item = self.get_environment_item_by_index(index)
                if not environment_item:
                    msg = 'Failed to get existing environment item: "{}". '.format(oz_area)
                    msg += 'By index: "{}".'.format(index)
                    self.logMessage.emit(msg, logging.WARNING)
                    continue
                # Invalidate this index so subsquent data cannot be applied to same existing env index again
                oz_areas_list[index] = None
            # Otherwise build a new EnvironmentItem if not already synced from host app project
            else:
                sync_required = oz_area not in added_env_items.keys()
                msg = 'Adding new environment on apply session data: "{}". '.format(oz_area)
                self.logMessage.emit(msg, logging.INFO)
                environment_item = self.add_environment(
                    oz_area=oz_area,
                    in_group_item=group_item,
                    in_group_index=qmodelindex_group,
                    sync_production_data=sync_required, # haven't added this environment before, so sync required
                    copy_from=added_env_items.get(oz_area), # copy the production data from this item
                    prepare_for_display=False,
                    validate_environment=sync_required, # haven't added this environment before, so validation required
                    show_dialog=False)
                if not environment_item:
                    continue
                if sync_required:
                    added_env_items[oz_area] = environment_item

            if shot_data:
                # If refresh from shotgun is disabled then load production data from session (if available)
                apply_production_data = not bool(self._auto_refresh_from_shotgun)
                sync_render_count += environment_item.apply_session_data(
                    shot_data,
                    apply_production_data=apply_production_data)

                render_overrides_data = shot_data.get(constants.SESSION_KEY_RENDER_OVERRIDES_DATA)
                if render_overrides_data:
                    environment_item.apply_render_overrides_session_data(render_overrides_data)

            ##################################################################

            passes_data = shot_data.get(self.SESSION_KEY_PASSES, dict())

            # Now load per pass session data
            for full_name in passes_data.keys():
                pass_data = passes_data[full_name]
                if not pass_data:
                    msg = 'No details in pass data to apply '
                    msg += 'To node name: "{}".'.format(full_name)
                    self.logMessage.emit(msg, logging.WARNING)
                    continue

                # Try to get the same RenderPassForEnvItem in synced data.
                pass_env_item = environment_item.get_pass_for_env_by_full_name(full_name)
                if not pass_env_item:
                    msg = 'Failed to get pass for environment item '
                    msg += 'For oz area: "{}". '.format(oz_area)
                    msg += 'And node name: "{}". '.format(full_name)
                    self.logMessage.emit(msg, logging.WARNING)
                    continue

                sync_render_count += pass_env_item.apply_session_data(pass_data)

                render_overrides_data = pass_data.get(constants.SESSION_KEY_RENDER_OVERRIDES_DATA)
                if render_overrides_data:
                    pass_env_item.apply_render_overrides_session_data(render_overrides_data)

        self.endResetModel()

        # Environments were added so update cached indices
        self._update_environments_indices()

        # Recompute all resolve methods, and summary counters
        self.compute_all_summary_counters()

        self.open_all_editors()

        # Auto expand any added groups
        for group_name in group_items.keys():
            qmodelindex = group_items[group_name].get('index')
            if not qmodelindex or not qmodelindex.isValid():
                continue
            self.expandRequested.emit(qmodelindex)

        return sync_env_count, sync_render_count, sync_pass_count


    def open_all_editors(self):
        '''
        Reopen all the editors after reseting model
        '''
        for qmodelindex in self.get_environment_items_indices():
            if not qmodelindex.isValid():
                continue
            self.openPersisentEditorForRowRequested.emit(qmodelindex)
            environment_item = qmodelindex.internalPointer()
            has_renderables = bool(environment_item._get_renderable_count_for_env())
            # NOTE: Update to show environment is renderable hints
            self.environmentHasRenderables.emit(qmodelindex, has_renderables)


    def session_can_be_auto_saved_now(self):
        '''
        Check if it's okay to auto save session data in host app
        at this time.
        Requires reimplementation

        Returns:
            can_auto_save (bool):
        '''
        return True


    def session_save_resource_for_project(
            self,
            project,
            session_data=dict(),
            oz_area=os.getenv('OZ_CONTEXT')):
        '''
        Create or update the session data resource related to the project.
        Note: This is only possible if project is hyref or can resolve to a Hydra Version.

        Args:
            project (str):
            session_data (dict):
            oz_area (str):

        Returns:
            session_path (str): the path to updated session path
        '''
        _msg = 'In Relation To Project: "{}"'.format(project)

        if not session_data:
            msg = 'Session Data Is Empty. So Skipping Save. '
            msg += str(_msg)
            self.logMessage.emit(msg, logging.WARNING)
            return

        # NOTE: If Hydra resource None is returned, a fallback session file
        # path is returned, based on the project file path
        hydra_resource, session_path = self.get_or_create_session_data_resource(
            project,
            oz_area=oz_area)

        # This method only writes session data for a Hydra resource
        if not any([hydra_resource, session_path]):
            msg = 'Failed To Get Hydra Resource Location To Write Session Data! '
            msg += str(_msg)
            self.logMessage.emit(msg, logging.CRITICAL)
            return

        elif not hydra_resource:
            msg = 'Failed To Get Or Create Hydra Resource To Save Session '
            msg += 'Data To. {}'.format(_msg)
            self.logMessage.emit(msg, logging.WARNING)
            return

        # Update session data with actual project
        if project:
            session_data['project'] = project

        from srnd_qt.data import ui_session_data
        ui_session_data.UiSessionData().session_write(
            session_path,
            session_data)
        msg = 'Writing Session Data To: {}. '.format(session_path)
        msg += str(_msg)
        self.logMessage.emit(msg, logging.INFO)

        return session_path


    ##########################################################################


    def get_preferences_schema_location(self):
        '''
        Get the GEN preferences schema location for MSRS.
        NOTE: This does not include the actual values set by user.
        The user preference overrides are written into the same directory as
        QSettings, but instead as a yaml file (not binary cfg file).
        Reimplement this method to return particular schema for host app.

        Returns:
            location (str):
        '''
        CONFIG_DIR = os.path.join(
            os.getenv('SRND_MULTI_SHOT_RENDER_SUBMITTER_ROOT'),
            'config')
        return os.path.join(CONFIG_DIR, 'msrs_preferences.yaml')


    def get_preferences_location(self):
        '''
        Get the preferences location for MSRS.
        NOTE: This is in the same location as QSettings on users local machine.
        NOTE: This is copied from preferences model pref_location method for convenience.

        Returns:
            location (str):
        '''
        pref_dir = os.path.expanduser(
            os.path.join(
                '~',
                '.config',
                self.ORGANIZATION_NAME))
        if not os.path.isdir(pref_dir):
            os.makedirs(pref_dir)
        app_name = self.TOOL_NAME.replace(' ', str())
        location = os.path.join(pref_dir, '{}.yaml'.format(app_name))
        return os.path.expanduser(location)


    def get_preferences_data(self, location=None):
        '''
        Get data from yaml preference file.

        Args:
            location (str): user yaml preference file path

        Returns:
            data (dict):
        '''
        if not location:
            location = self.get_preferences_location()
        if not location or not os.path.isfile(location):
            msg = 'Preference location not valid to get data from: "{}"'.format(location)
            self.logMessage.emit(msg, logging.WARNING)
            return dict()
        import yaml
        from srnd_qt.ui_framework.dialogs.preferences.ordered_dict_yaml_loader import OrderedDictYAMLLoader
        try:
            # data = yaml.load(open(location)) # unordered
            data = yaml.load(open(location), OrderedDictYAMLLoader) # ordered
        except Exception:
            data = dict()
            msg = 'Failed to get preferences data from: "{}". '.format(location)
            msg = 'Full exception: "{}".'.format(traceback.format_exc())
            self.logMessage.emit(msg, logging.WARNING)
        return data


    def open_preferences_dialog(self):
        '''
        Open the preferences dialog in regards to the schema.
        NOTE: Listen for signals of preferences changing as the dialog is open
        and call the respective MSRS object methods, to set and cache the result
        outside the preferences system.
        '''
        msg = 'Opening preferences dialog'
        self.logMessage.emit(msg, logging.INFO)

        # Get the preferences schema data for MSRS
        schema_location = self.get_preferences_schema_location()
        schema_data = self.get_preferences_data(schema_location)
        # Must have valid preferences schema to open dialog
        if not schema_data:
            from Qt.QtWidgets import QMessageBox
            reply = QMessageBox.warning(
                self,
                'Preferences schema data is empty!',
                'Skipping load preferences dialog. No schema data!',
                QMessageBox.Ok)
            return

        app_name = self.TOOL_NAME.replace(' ', str())

        # NOTE: PreferencesDialog will automatically fetch the users
        # latest preference from local config folder.
        from srnd_qt.ui_framework.dialogs.preferences import controller_gui
        preferences = controller_gui.PreferencesDialog(
            schema_dict=schema_data,
            app_name=app_name,
            org_name=self.ORGANIZATION_NAME)

        # Customize the preferences
        dialog = preferences.view
        window_title = self.TOOL_NAME + ' - Preferences'
        dialog.setWindowTitle(window_title)
        dialog.resize(1025, 550)
        stylesheet = 'QTreeWidget { background: rgb(65, 65, 65);'
        stylesheet += 'selection-background-color: rgb(120,120,120);}'
        dialog.navigation_tree.setStyleSheet(stylesheet)
        dialog.navigation_tree.setAlternatingRowColors(False)
        # Remove the white bright brush for categories
        from Qt.QtGui import QColor
        for category_item in dialog.category_items:
            category_item.setBackground(0, QColor(0, 0, 0, 0))

        # Setup preferences callbacks
        preferences.model.pref_changed.connect(self._emit_apply_preference_request)
        preferences.model.restored.connect(self.apply_preferences)

        # # Automatically save preferences every N seconds
        # from Qt.QtCore import QTimer
        # self._preferences_save_timer = QTimer()
        # self._preferences_save_timer.setInterval(preferences.autosave_interval * 1000 * 60)
        # self._preferences_save_timer.timeout.connect(self.save_preferences)
        # self._preferences_save_timer.start()

        dialog.set_section('View')

        dialog.exec_()

        preferences.model.pref_changed.disconnect(self._emit_apply_preference_request)


    def apply_preferences(self):
        '''
        Apply all the users preferences to MSRS objects now.
        '''
        self.aboutToApplyPreferences.emit()

        msg = 'Applying preferences to MSRS objects...'
        self.logMessage.emit(msg, logging.INFO)

        # Get the preferences schema data for MSRS
        schema_location = self.get_preferences_schema_location()
        schema_data = self.get_preferences_data(schema_location)
        app_name = self.TOOL_NAME.replace(' ', str())
        # Prepare preferences model which provides the prefs member containing user values
        from srnd_qt.ui_framework.dialogs.preferences import model
        model = model.Model(
            schema_dict=schema_data,
            app_name=app_name,
            org_name=self.ORGANIZATION_NAME)
        # Invoke apply preference for name and value
        for name in model.prefs.keys():
            value = model.get(name)
            self.applyPreferenceRequest.emit(name, value)


    def update_preference(self, name, value):
        '''
        Update a particular preference and write the results to users preference file.

        Args:
            name, value (tuple):
        '''
        msg = 'Updating preference name: "{}". '.format(name)
        msg += 'Value: "{}"'.format(value)
        self.logMessage.emit(msg, logging.DEBUG)
        schema_location = self.get_preferences_schema_location()
        schema_data = self.get_preferences_data(schema_location)
        app_name = self.TOOL_NAME.replace(' ', str())
        from srnd_qt.ui_framework.dialogs.preferences import model
        model = model.Model(
            schema_dict=schema_data,
            app_name=app_name,
            org_name=self.ORGANIZATION_NAME)
        model.set(name, value)


    def get_preference_value(self, name):
        '''
        Get a preference value for name (if available).

        Args:
            name (str):

        Returns:
            value (object):
        '''
        schema_location = self.get_preferences_schema_location()
        schema_data = self.get_preferences_data(schema_location)
        app_name = self.TOOL_NAME.replace(' ', str())
        from srnd_qt.ui_framework.dialogs.preferences import model
        model = model.Model(
            schema_dict=schema_data,
            app_name=app_name,
            org_name=self.ORGANIZATION_NAME)
        return model.get(name)


    def _emit_apply_preference_request(self, name, value):
        self.applyPreferenceRequest.emit(name, value)


    ##########################################################################
    # Assigned shots


    def populate_assigned_shots(
            self,
            sync_production_data=True,
            current_sequence_only=False):
        '''
        Populate all assigned shots for current user to view.

        Args:
            sync_production_data (bool):
            current_sequence_only (bool):

        Returns:
            environment_items (list): list of environment item data objects
        '''
        project, user = self.get_shot_assignments_from_project_and_user()

        # # TODO: Only for testing. Remove this...
        # project = 'coral2'
        # user = 'robertbyrne'
        # current_sequence = '2028'

        current_sequence = os.getenv('SCENE')

        msg = 'Getting all assigned shots for project: "{}". '.format(project)
        msg += 'User: "{}". '.format(user)
        msg += 'Current sequence only: "{}"'.format(current_sequence_only)
        self.logMessage.emit(msg, logging.INFO)

        # Get assigned shots for project and user
        from srnd_multi_shot_render_submitter import production_info
        shot_codes = production_info.get_shot_codes_for_project_and_user(
            project=project or os.getenv('FILM'),
            user=user or os.getenv('USER'))

        msg = 'Got shot codes: "{}"'.format(shot_codes)
        self.logMessage.emit(msg, logging.INFO)

        # No shots to populate
        if not shot_codes:
            return list()

        environments = list()
        for i, shot_code in enumerate(shot_codes):
            if current_sequence_only:
                is_in_current_sequence = False
                try:
                    # Assuming a fully formulated area is passed here "/aba/shots/004/0010"
                    is_in_current_sequence = shot_code.split('/')[3] == current_sequence
                except IndexError:
                    msg = 'Failed to extract sequence from environment: "{}". '.format(shot_code)
                    self.logMessage.emit(msg, logging.WARNING)
                    continue

                if not is_in_current_sequence:
                    msg = 'Skipping adding environment: "{}". '.format(shot_code)
                    msg += 'Not in current sequence: "{}". '.format(current_sequence)
                    self.logMessage.emit(msg, logging.WARNING)
                    continue
            environments.append(shot_code)

        return self.add_environments(
            environments,
            skip_existing=True)


    def get_shot_assignments_from_project_and_user(self):
        '''
        Get the project and user that shot assignments
        will be queried and populated from.

        Returns:
            project, user (tuple):
        '''
        return self._shot_assignments_project, self._shot_assignments_user


    def set_shot_assignments_from_project_and_user(
            self,
            project=os.getenv('FILM'),
            user=os.getenv('FILM')):
        '''
        Set the project and user that shot assignments
        will be queried and populated from.

        Args:
            project, user (tuple):
        '''
        self._shot_assignments_project = project
        self._shot_assignments_user = user


    ##########################################################################
    # Model config options


    def set_debug_mode(self, debug_mode):
        '''
        Set whether debug mode is enabled on this node and all children.
        Reimplemented method.

        Args:
            debug_mode (str): oz area as single string
        '''
        base_abstract_item_model.BaseAbstractItemModel.set_debug_mode(
            self,
            debug_mode)

        # Set debug mode on root node and all children (RenderItem/s)
        self._root_node.set_debug_mode(debug_mode)

        # Set debug mode on other sibling nodes (RenderPassForEnvItem/s)
        for render_pass_for_env_item in self.get_pass_for_env_items():
            render_pass_for_env_item.set_debug_mode(debug_mode)


    def set_update_host_app(self, update_host_app):
        '''
        Set whether the model is enabled to modify host app data or not.
        Allowing various actions like set node colour, delete node to be performed.

        Args:
            update_host_app (bool):
        '''
        update_host_app = bool(update_host_app)

        msg = 'Setting {} Is Updated On '.format(self.HOST_APP)
        msg += 'Changes To: "{}"'.format(update_host_app)
        self.logMessage.emit(msg, logging.DEBUG)

        self._update_host_app = update_host_app

        # Also propagate modify host app to all render nodes (column headers)
        for render_item in self.get_render_items():
            render_item.set_update_host_app(update_host_app)


    def get_update_host_app(self):
        '''
        Get whether the model is enabled to modify host app data or not.

        Returns:
            update_host_app (bool):
        '''
        return self._update_host_app


    def get_session_data_is_recalled_after_sync(self):
        '''
        Get whether session data is recalled after sync is called.

        Returns:
            value (bool):
        '''
        return self._session_data_is_recalled_after_sync


    def set_session_data_is_recalled_after_sync(self, value):
        '''
        Get whether session data is recalled after sync is called.

        Args:
            value (bool):
        '''
        value = bool(value)
        msg = 'Setting session data is recalled after sync to: {}'.format(value)
        self.logMessage.emit(msg, logging.DEBUG)
        self._session_data_is_recalled_after_sync = value


    def get_session_data_recalled_from_resource_after_sync(self):
        '''
        Get whether session data is recalled after sync is called.

        Returns:
            value (bool):
        '''
        return self._session_data_recalled_from_resource_after_sync


    def set_session_data_recalled_from_resource_after_sync(self, value):
        '''
        Get whether session data is recalled after sync is called.

        Args:
            value (bool):
        '''
        value = bool(value)
        msg = 'Setting session data is recalled from resource after sync: {}'.format(value)
        self.logMessage.emit(msg, logging.DEBUG)
        self._session_data_recalled_from_resource_after_sync = value


    def get_sync_only_if_already_in_session(self):
        '''
        Get whether to sync render nodes only that are in session already.

        Returns:
            value (bool):
        '''
        return self._sync_only_if_already_in_session


    def set_sync_only_if_already_in_session(self, value):
        '''
        Get whether to sync render nodes only that are in session already.

        Args:
            value (bool):
        '''
        value = bool(value)
        msg = 'Setting Sync Only If Already In Session: {}'.format(value)
        self.logMessage.emit(msg, logging.DEBUG)
        self._sync_only_if_already_in_session = value


    ##########################################################################
    # Global options for next submission


    def get_version_global_system(self):
        '''
        Get the global version system like "V+" or "VP+", or
        a particular custom version int.
        Note: This option is on root node to be accesible by data nodes.

        Returns:
            version_global_system (str):
        '''
        return self._root_node.get_version_global_system()


    def set_version_global_system(self, version_global_system):
        '''
        Set any optional global description to describe the next
        Plow Job submission.
        Note: This option is on root node to be accesible by data nodes.

        Args:
            version_global_system (str):
        '''
        _version_global_system = self._root_node.set_version_global_system(
            version_global_system)

        # msg = 'Set Version Global System To: "{}". '.format(version_global_system)
        # self.logMessage.emit(msg, logging.DEBUG)

        if _version_global_system != version_global_system:
            self.versionSystemChanged.emit(str(version_global_system))


    def get_email_additional_users(self):
        '''
        Get any additional users to include in the email showing
        overview of operations, for next submission.

        Returns:
            email_additional_users (list):
        '''
        return self._email_additional_users


    def set_email_additional_users(self, email_additional_users):
        '''
        Set any additional users to include in the email showing
        overview of operations, for next submission.

        Args:
            email_additional_users (list):
        '''
        if self._debug_mode:
            msg = 'Setting Email Additional Users For Next '
            msg += 'Submission To: {}'.format(email_additional_users)
            self.logMessage.emit(msg, logging.DEBUG)

        self._email_additional_users = email_additional_users


    def get_global_job_identifier(self):
        '''
        Get any additional job identifier to add as part of Plow
        Job name, for the next submission.

        Returns:
            additional_job_identifier (str):
        '''
        return self._global_job_identifier


    def set_global_job_identifier(self, value):
        '''
        Set any additional job identifier to add as part of Plow
        Job name, for the next submission.

        Args:
            value (str):
        '''
        value = str(value or str())
        # NOTE: Remove any non alphanumeric characters
        value = re.sub(r'\W+', str(), value)
        if self._debug_mode:
            msg = 'Setting Global Job Identifier To: "{}"'.format(value)
            self.logMessage.emit(msg, logging.DEBUG)
        self._global_job_identifier = value


    def get_global_submit_description(self):
        '''
        Get optional global submit description to describe the next Plow Job submission.

        Returns:
            global_submit_description (str):
        '''
        return self._global_submit_description


    def set_global_submit_description(self, value):
        '''
        Set optional global submit description to describe the next Plow Job submission.

        Returns:
            global_submit_description (str):
        '''
        if self._debug_mode:
            msg = 'Setting Global Submit Description To: "{}"'.format(value)
            self.logMessage.emit(msg, logging.DEBUG)
        self._global_submit_description = str(value or str())


    def get_dispatch_deferred(self):
        '''
        Get whether dispatch deferred (on Plow) is enabled, or
        next submit should happen in current application context.

        Returns:
            dispatch_deferred (bool):
        '''
        return self._dispatch_deferred


    def set_dispatch_deferred(self, dispatch_deferred):
        '''
        Set whether dispatch deferred (on Plow) is enabled, or
        next submit should happen in current application context.

        Args:
            dispatch_deferred (bool):
        '''
        if self._debug_mode:
            msg = 'Setting Dispatch On Plow: "{}"'.format(dispatch_deferred)
            self.logMessage.emit(msg, logging.DEBUG)
        self._dispatch_deferred = dispatch_deferred


    def get_source_project_version(self):
        '''
        For reference purposes get the source project version number.

        Returns:
            source_project_version (bool):
        '''
        return self._source_project_version


    def set_source_project_version(self, source_project_version):
        '''
        For reference purposes set the source project version number.

        Args:
            source_project_version (int):
        '''
        if self._debug_mode:
            msg = 'Setting Source Project Version: "{}"'.format(source_project_version)
            self.logMessage.emit(msg, logging.DEBUG)
        source_project_version = str(source_project_version)
        if source_project_version.isdigit():
            self._source_project_version = int(source_project_version)


    def get_show_environment_thumbnails(self):
        '''
        Get whether shot environments thumbnails are shown in view, via the
        delegate widget RenderPassForEnvWidget.

        Returns:
            show_environment_thumbnails (bool):
        '''
        return self._show_environment_thumbnails


    def set_show_environment_thumbnails(
            self,
            value=True,
            static=None):
        '''
        Set whether shot environments thumbnails are shown in view, via the
        delegate render pass for env widget.

        Args:
            value (bool):
            static (bool):

        Returns:
            thumbnails_request_resize (dict): mapping of environment string to thumbnail file path
        '''
        value = bool(value)
        self._show_environment_thumbnails = value

        if not isinstance(static, bool):
            static = self._shotsub_thumbnails_static
        cached_thumbnail_paths = True
        if static != self._shotsub_thumbnails_static:
            self._shotsub_thumbnails_static = static
            cached_thumbnail_paths = False

        msg = 'Set environment thumbnails: {}. '.format(value)
        msg += 'Static: {}'.format(static)
        self.logMessage.emit(msg, logging.INFO)

        if not self.get_environment_items():
            msg = 'No environment items to toggle thumbnail state for!'
            self.logMessage.emit(msg, logging.WARNING)
            return dict()

        ######################################################################
        # Gather environment names

        environments = set()
        column_count = self.columnCount(QModelIndex())
        for qmodelindex in self.get_environment_items_indices():
            if not qmodelindex.isValid():
                continue
            environment_item = qmodelindex.internalPointer()
            if not environment_item:
                continue
            environments.add(environment_item.get_oz_area())

        ######################################################################
        # Optionally gather all production data at once

        GET_ALL_PRODUCTION_SHOTS_AT_ONCE = True
        shot_objects_for_envs = dict()
        if GET_ALL_PRODUCTION_SHOTS_AT_ONCE:
            from srnd_multi_shot_render_submitter import production_info
            shot_objects_for_envs = production_info.get_shots_for_environments(
                environments)

        ######################################################################

        thumbnails_request_resize = dict()

        column_count = self.columnCount(QModelIndex())
        for qmodelindex in self.get_environment_items_indices():
            if not qmodelindex.isValid():
                continue
            environment_item = qmodelindex.internalPointer()
            if not environment_item:
                continue
            oz_area = environment_item.get_oz_area()
            shot_object = shot_objects_for_envs.get(oz_area)
            if self._show_environment_thumbnails:
                thumbnail_path = environment_item.derive_and_cache_shot_thumbnail_path(
                    shot_object=shot_object,
                    animated=not static,
                    cached=cached_thumbnail_paths)
                # Collect mapping of environment to shot gif path
                if not static and thumbnail_path and os.path.isfile(thumbnail_path):
                    thumbnails_request_resize[oz_area] = str(thumbnail_path)
            # Open (or reopen) editors.
            # NOTE: at this time the QMovie might not exist
            for c in range(0, column_count, 1):
                qmodelindex_column = qmodelindex.sibling(qmodelindex.row(), c)
                self.closePersisentEditorForCellRequested.emit(qmodelindex_column)
                self.openPersisentEditorForCellRequested.emit(qmodelindex_column)
            # Update size hints via data changed
            end_index = qmodelindex.sibling(qmodelindex.row(), column_count)
            self.dataChanged.emit(qmodelindex, end_index)

        return thumbnails_request_resize


    def set_frame_resolve_order_env_first_on_create(self, value):
        '''
        Set whether new environments will use env first or pass
        first frame resolve order.

        Args:
            value (bool):
        '''
        value = bool(value)
        if self._debug_mode:
            msg = 'Setting frame resolve order for new environments to: {}'.format(value)
            self.logMessage.emit(msg, logging.DEBUG)
        self._frame_resolve_order_env_first = value


    def get_frame_resolve_order_env_first_on_create(self):
        '''
        get whether new environments will use env first or pass
        first frame resolve order.

        Returns:
            value (bool):
        '''
        return self._frame_resolve_order_env_first


    def get_snapshot_before_dispatch(self):
        '''
        Get whether to snapshot before dispatch Job is created.

        Returns:
            snapshot_before_dispatch (bool):
        '''
        return self._snapshot_before_dispatch


    def set_snapshot_before_dispatch(self, value):
        '''
        Set whether to snapshot before dispatch Job is created.

        Args:
            value (bool):
        '''
        value = bool(value)
        if self._debug_mode:
            msg = 'Setting Snapshot Before Dispatch: {}'.format(value)
            self.logMessage.emit(msg, logging.DEBUG)
        self._snapshot_before_dispatch = value


    def get_launch_paused(self):
        '''
        Get whether all Jobs to be next submitted will launch paused or not.

        Returns:
            launch_paused (bool):
        '''
        return self._launch_paused


    def set_launch_paused(self, value):
        '''
        Set whether all Jobs to be next submitted will launch paused or not.

        Args:
            value (bool):
        '''
        value = bool(value)
        if self._debug_mode:
            msg = 'Setting Launch Paused: {}'.format(value)
            self.logMessage.emit(msg, logging.DEBUG)
        self._launch_paused = value


    def get_launch_paused_expires(self):
        '''
        Get the number of minutes before the launch paused will expire.

        Returns:
            launch_paused_expires (int):
        '''
        return self._launch_paused_expires


    def set_launch_paused_expires(self, value):
        '''
        Set the number of minutes before the launch paused will expire.

        Args:
            value (int):
        '''
        value = int(value)
        if self._debug_mode:
            msg = 'Setting Launch Paused Expires: {}'.format(value)
            self.logMessage.emit(msg, logging.DEBUG)
        self._launch_paused_expires = value


    def get_launch_zero_tier(self):
        '''
        Get whether all Jobs to be next submitted will launch with zero tier or not.

        Returns:
            launch_zero_tier (bool):
        '''
        return self._launch_zero_tier


    def set_launch_zero_tier(self, value):
        '''
        Set whether all Jobs to be next submitted will launch with zero tier or not.

        Args:
            value (bool):
        '''
        value = bool(value)
        if self._debug_mode:
            msg = 'Setting Launch As Zero Tier: {}'.format(value)
            self.logMessage.emit(msg, logging.DEBUG)
        self._launch_zero_tier = value


    def get_apply_render_overrides(self):
        '''
        Get whether to apply any defined render overrides during submission or not.

        Returns:
            value (bool):
        '''
        return self._apply_render_overrides


    def set_apply_render_overrides(self, value):
        '''
        Set whether to apply any defined render overrides during submission or not.

        Args:
            value (bool):
        '''
        value = bool(value)
        if self._debug_mode:
            msg = 'Setting Apply Render Overrides: {}'.format(value)
            self.logMessage.emit(msg, logging.DEBUG)
        self._apply_render_overrides = value


    def get_apply_dependencies(self):
        '''
        Get whether to apply any defined WAIT On depedencies when launching Job/s or not.

        Returns:
            value (bool):
        '''
        return self._apply_dependencies


    def set_apply_dependencies(self, value):
        '''
        Set whether to apply any defined WAIT On depedencies when launching Job/s or not.

        Args:
            value (bool):
        '''
        value = bool(value)
        if self._debug_mode:
            msg = 'Setting Apply Depedencies: {}'.format(value)
            self.logMessage.emit(msg, logging.DEBUG)
        self._apply_dependencies = value


    def get_compute_render_estimate(self):
        '''
        Get whether to compute and cache render estimates.

        Returns:
            value (bool):
        '''
        return self._compute_render_estimate


    def set_compute_render_estimate(self, value):
        '''
        Set whether to compute and cache render estimates.

        Args:
            value (bool):
        '''
        value = bool(value)
        if self._debug_mode:
            msg = 'Setting Compute Render Estimates: {}'.format(value)
            self.logMessage.emit(msg, logging.DEBUG)
        self._compute_render_estimate = bool(value)


    def get_listen_to_jobs(self):
        '''
        Get whether to listen to previously launched Plow Job/s for render progress updates.

        Returns:
            value (bool):
        '''
        return self._listen_to_jobs


    def set_listen_to_jobs(self, value):
        '''
        Set whether to listen to previously launched Plow Job/s for render progress updates.

        Args:
            value (bool):
        '''
        value = bool(value)
        # if self._debug_mode:
        #     msg = 'Setting Listen To Previously Launched MSRS '
        #     msg += 'Job/s: {}'.format(value)
        self._listen_to_jobs = value


    def get_listen_to_jobs_frequency(self):
        '''
        Get frequency of how often to ping previously launched Plow Job/s for render progress updates.

        Returns:
            value (int):
        '''
        return self._listen_to_jobs_frequency


    def set_listen_to_jobs_frequency(self, value):
        '''
        Set frequency of how often to ping previously launched Plow Job/s for render progress updates.

        Args:
            value (int):
        '''
        try:
            value = int(value)
        except Exception:
            value = constants.LISTEN_TO_JOBS_FREQUENCY_DEFAULT
        if value < constants.LISTEN_TO_JOBS_FREQUENCY_MIN:
            value = constants.LISTEN_TO_JOBS_FREQUENCY_MIN
        # if self._debug_mode:
        #     msg = 'Setting Listen To Previously Launched MSRS '
        #     msg += 'Job/s Frequency: {}'.format(value)
        #     self.logMessage.emit(msg, logging.DEBUG)
        self._listen_to_jobs_frequency = value


    def get_show_summary_dialog(self):
        '''
        Get whether to show the summary dialog before submitting or not.

        Returns:
            auto_start (bool):
        '''
        return self._show_summary_dialog


    def set_show_summary_dialog(self, value):
        '''
        Set whether to show the summary dialog before submitting or not.

        Args:
            value (bool):
        '''
        value = bool(value)
        if self._debug_mode:
            msg = 'Setting show summary dialog: {}'.format(value)
            self.logMessage.emit(msg, logging.DEBUG)
        self._show_summary_dialog = value


    def get_send_summary_email_on_submit(self):
        '''
        Get whether to send summary email on next submission or not.

        Returns:
            send_summary_email_on_submit (bool):
        '''
        return self._send_summary_email_on_submit


    def set_send_summary_email_on_submit(self, value):
        '''
        Set whether to send summary email on next submission or not.

        Args:
            value (bool):
        '''
        value = bool(value)
        if self._debug_mode:
            msg = 'Setting send summary email on next submission: {}'.format(value)
            self.logMessage.emit(msg, logging.DEBUG)
        self._send_summary_email_on_submit = value


    def get_auto_refresh_from_shotgun(self):
        '''
        Get whether to refresh production data when launching summary dialog and in dispatcher task.

        Returns:
            auto_refresh_from_shotgun (bool):
        '''
        return self._auto_refresh_from_shotgun


    def set_auto_refresh_from_shotgun(self, value):
        '''
        Set whether to refresh production data when launching summary dialog and in dispatcher task.

        Args:
            value (bool):
        '''
        value = bool(value)
        if self._debug_mode:
            msg = 'Setting refresh from shotgun on submit: {}'.format(value)
            self.logMessage.emit(msg, logging.DEBUG)
        self._auto_refresh_from_shotgun = value


    def set_cook_more_summary_details(self, value):
        '''
        Set whether to cook more summary details or not.
        NOTE: Might be computationally expensive and user may not care to see more advanced details.

        Args:
            value (bool):
        '''
        value = bool(value)
        if self._debug_mode:
            msg = 'Setting Cook More Summary Details To "{}"'.format(value)
            self.logMessage.emit(msg, logging.DEBUG)
        self._cook_more_summary_details = value


    def get_cook_more_summary_details(self):
        '''
        Get whether to cook more summary details or not.

        Returns:
            value (bool):
        '''
        return self._cook_more_summary_details


    def get_validation_auto_start(self):
        '''
        Get whether to auto start the validation when Summary dialog is opened.

        Returns:
            auto_start (bool):
        '''
        return self._validation_auto_start


    def set_validation_auto_start(self, value):
        '''
        Set whether to auto start the validation when Summary dialog is opened.

        Args:
            value (bool):
        '''
        value = bool(value)
        if self._debug_mode:
            msg = 'Setting Validation Auto Start: {}'.format(value)
            self.logMessage.emit(msg, logging.DEBUG)
        self._validation_auto_start = value


    def get_summary_auto_scroll_to_validation(self):
        '''
        Get whether to auto scroll to validation issue in Summary dialog or not.

        Returns:
            auto_scroll (bool):
        '''
        return self._summary_auto_scroll_to_validation


    def set_summary_auto_scroll_to_validation(self, auto_scroll):
        '''
        Set whether to auto scroll to validation issue in Summary dialog or not.

        Args:
            auto_scroll (bool):
        '''
        if self._debug_mode:
            msg = 'Setting Summary Auto Scroll To Validation: {}'.format(auto_scroll)
            self.logMessage.emit(msg, logging.DEBUG)
        self._summary_auto_scroll_to_validation = auto_scroll


    def set_show_full_environments(self, show_full_environments):
        '''
        Set show full environment or not.
        Note: This option is on root node to be accesible by data nodes.

        Args:
            show_full_environments (bool):
        '''
        self._root_node.set_show_full_environments(show_full_environments)
        for qmodelindex in self.get_environment_items_indices():
            if not qmodelindex.isValid():
                continue
            self.dataChanged.emit(qmodelindex, qmodelindex)


    def get_show_full_environments(self):
        '''
        Get show full environment or not.
        Note: This option is on root node to be accesible by data nodes.

        Returns:
            show_full_environments (bool):
        '''
        return self._root_node.get_show_full_environments()


    def toggle_show_full_environments(self, show_full_environments=None):
        '''
        Toggle show full environment or not.

        Args:
            show_full_environments (bool):
        '''
        show_full_environments = not self.get_show_full_environments()

        if self._debug_mode:
            msg = 'Toggling Environment Full '
            msg += 'Name Visible: {}'.format(show_full_environments)
            self.logMessage.emit(msg, logging.DEBUG)

        self.set_show_full_environments(show_full_environments)
        self.toggleShowFullEnvironments.emit(show_full_environments)


    ##########################################################################
    # Sync rules options


    def get_sync_rules_active(self):
        '''
        Get whether all sync rules should be considered for next Sync operation or not.

        Returns:
            value (bool):
        '''
        return self._sync_rules_active


    def set_sync_rules_active(self, value):
        '''
        Set whether all sync rules should be considered for next Sync operation or not.

        Args:
            value (bool):
        '''
        value = bool(value)
        if self._debug_mode:
            msg = 'Setting Sync Rules Active To: {}'.format(value)
            self.logMessage.emit(msg, logging.DEBUG)
        self._sync_rules_active = value


    def get_sync_rules_include(self, remove_comments=False):
        '''
        Get list of Sync include rules.
        Note: This may optionally include sync rules which are commented out.

        Args:
            remove_comments (bool): optionally remove comments from sync rules

        Returns:
            rules (list):
        '''
        rules_verified = list()
        for rule in self._sync_rules_include:
            if not rule:
                continue
            rule = str(rule)
            if remove_comments and rule.startswith('#'):
                continue
            rules_verified.append(rule)
        return rules_verified


    def set_sync_rules_include(self, value):
        '''
        Set list of sync include rules.
        Note: This may include sync rules which are commented out.

        Args:
            value (list):
        '''
        if self._debug_mode:
            msg = 'Setting Sync Include Rules To: {}'.format(value)
            self.logMessage.emit(msg, logging.DEBUG)
        self._sync_rules_include = value


    def get_sync_rules_exclude(self, remove_comments=False):
        '''
        Get list of Sync exclude rules.
        Note: This may optionally exclude sync rules which are commented out.

        Args:
            remove_comments (bool): optionally remove comments from sync rules

        Returns:
            rules (list):
        '''
        rules_verified = list()
        for rule in self._sync_rules_exclude:
            if not rule:
                continue
            rule = str(rule)
            if remove_comments and rule.startswith('#'):
                continue
            rules_verified.append(rule)
        return rules_verified


    def set_sync_rules_exclude(self, value):
        '''
        Set list of sync exclude rules.
        Note: This may exclude sync rules which are commented out.

        Args:
            value (list):
        '''
        if self._debug_mode:
            msg = 'Setting Sync Exclude Rules To: {}'.format(value)
            self.logMessage.emit(msg, logging.DEBUG)
        self._sync_rules_exclude = value


    def filter_render_nodes_by_rules(self, render_node_names=None):
        '''
        Filter the render nodes by rules.

        Args:
            render_node_names (list):

        Returns:
            render_node_names_filtered (list):
        '''
        # Sync rules is disabled so return render node list as is
        if not self._sync_rules_active:
            return render_node_names
        # No sync rules so return render node list as is
        sync_rules_include = self.get_sync_rules_include(remove_comments=True)
        sync_rules_exclude = self.get_sync_rules_exclude(remove_comments=True)
        if not any([sync_rules_include, sync_rules_exclude]):
            msg = 'No Include Or Exclude Rules To Filter Render Nodes: "{}"'.format(render_node_names)
            self.logMessage.emit(msg, logging.WARNING)
            return render_node_names
        # No render nodes to filter
        if not render_node_names:
            return list()
        msg = 'Filtering Render Nodes: "{}". '.format(render_node_names)
        msg += 'Using Include Rules: "{}". '.format(sync_rules_include)
        msg += 'Using Exclude Rules: "{}"'.format(sync_rules_exclude)
        self.logMessage.emit(msg, logging.WARNING)

        includes_found = set()
        for render_node_name in render_node_names:
            for sync_rule in sync_rules_include:
                result = re.findall(sync_rule, render_node_name, flags=re.IGNORECASE)
                if result:
                    includes_found.add(render_node_name)
                    break
        msg = 'Render Nodes Found By Include Rules: "{}". '.format(includes_found)
        self.logMessage.emit(msg, logging.WARNING)

        excludes_found = set()
        for render_node_name in render_node_names:
            for sync_rule in sync_rules_exclude:
                result = re.findall(sync_rule, render_node_name, flags=re.IGNORECASE)
                if result:
                    excludes_found.add(render_node_name)
                    break
        msg = 'Render Nodes Found By Exclude Rules: "{}". '.format(excludes_found)
        self.logMessage.emit(msg, logging.WARNING)

        render_node_names_filtered = set()
        if all([includes_found, excludes_found]):
            render_node_names_filtered = includes_found.difference(excludes_found)
        elif includes_found:
            render_node_names_filtered = includes_found
        elif excludes_found:
            render_node_names_filtered = set(render_node_names).difference(excludes_found)

        msg = 'Filtered Render Nodes: "{}"'.format(render_node_names_filtered)
        self.logMessage.emit(msg, logging.WARNING)

        return render_node_names_filtered


    ##########################################################################
    # Tracking members (updated during submission)


    def get_project_snapshot(self):
        '''
        Get the last host app project snapshot performed
        during submission (if any).

        Args:
            as_hyref (str): optionally return project as file path or hyref

        Returns:
            project_snapshot_hyref (str):
        '''
        return self._project_snapshot_hyref


    def get_source_project(self):
        '''
        Get the last source project before submission started (if any).
        Note: This is cached just before snapshot project.

        Returns:
            source_project (str):
        '''
        return self._source_project


    def get_autosave_session_path(self):
        '''
        Get the autosave session path performed during the last submission.
        Note: This is cached just after snapshot project and saving json product.

        Returns:
            autosave_session_path (str):
        '''
        return self._autosave_session_path


    def request_interrupt(self):
        '''
        Request renders to halt.
        Will continue to send email regarding Environments that did submit.

        Returns:
            request_interrupt (bool):
        '''
        self._request_interrupt = True


    def get_is_rendering(self):
        '''
        Is the model currenting rendering specified items or not.

        Returns:
            is_rendering (bool):
        '''
        return self._is_rendering


    def check_override_is_editable(self, override_id):
        '''
        Check if override id has an edit mode.

        Args:
            override_id (str):

        Returns:
            has_edit_mode (bool):
        '''
        return override_id in [
            constants.OVERRIDE_FRAMES_CUSTOM,
            constants.OVERRIDE_FRAMES_NOT_CUSTOM,
            constants.OVERRIDE_FRAMES_XCUSTOM,
            constants.OVERRIDE_FRAMES_NOT_XCUSTOM,
            constants.OVERRIDE_NOTE,
            constants.OVERRIDE_JOB_IDENTIFIER,
            constants.OVERRIDE_WAIT,
            'Version']


    ##########################################################################
    # Render manager and overrides


    def get_render_overrides_manager(self):
        '''
        Get the already instantiated render overrides manager of this model.

        Returns:
            render_overrides_manager (RenderOverridesManager):
        '''
        return self._render_overrides_manager


    ##########################################################################
    # Scheduler


    def get_scheduler_operations(self):
        '''
        Get the already instantiated scheduler operations object of this model.

        Returns:
            scheduler_operations (SchedulerOperations):
        '''
        return self._scheduler_operations


    ##########################################################################
    # Get subclassed object types appropiate for model (via factory)
    # TODO: The interface could change to class methods later.


    def get_group_item_object(self):
        '''
        Get an GroupItem (or subclass) appropiate for this model.
        Returns uninstantiated object.

        Returns:
            group_item (GroupItem):
        '''
        return factory.MultiShotFactory.get_group_item_object()


    def get_environment_item_object(self):
        '''
        Get environment item object appropiate for this model in uninstantiated state.
        Returns uninstantiated object.

        Returns:
            environment_item (EnvironmentItem):
        '''
        return factory.MultiShotFactory.get_environment_item_object()


    def get_render_item_object(self):
        '''
        Get render item object appropiate for this model in uninstantiated state.
        Returns uninstantiated object.

        Returns:
            render_item (RenderItem):
        '''
        return factory.MultiShotFactory.get_render_item_object()


    def get_pass_for_env_item_object(self):
        '''
        Get render pass for env object appropiate for this model in uninstantiated state.
        Returns uninstantiated object.

        Returns:
            pass_for_env_item (RenderPassForEnvItem):
        '''
        return factory.MultiShotFactory.get_pass_for_env_item_object()


    def get_summary_model_object(self):
        '''
        Get summary model object appropiate for this model in uninstantiated state.

        Returns:
            summary_model (SummaryModel):
        '''
        return factory.MultiShotFactory.get_summary_model_object()


    def get_render_overrides_manager_object(self):
        '''
        Get render overrides item manager object appropiate for this model in uninstantiated state.

        Returns:
            render_overrides_manager (RenderOverridesManager):
        '''
        return factory.MultiShotFactory.get_render_overrides_manager_object()


    def get_scheduler_operations_object(self):
        '''
        Get uninstantiated scheduler operations object.

        Returns:
            scheduler_operations_object (SchedulerOperations):
        '''
        return factory.MultiShotFactory.get_scheduler_operations_object()


    ##########################################################################


    def get_render_items(self):
        '''
        Get all render item data objects

        Returns:
            render_items (list):
        '''
        return self._render_items


    def get_render_node_names(self):
        '''
        Get the full node names of all render nodes in model.

        Returns:
            render_node_names (list):
        '''
        return [item.get_item_full_name() for item in self.get_render_items()]


    def get_column_of_render_node(self, item_full_name):
        '''
        Get the index of render node in model from full node name.

        Returns:
            column_index (int):
        '''
        if item_full_name in self.get_render_node_names():
            return self.get_render_node_names().index(item_full_name) + 1
        else:
            return -1


    def get_render_item_by_name(self, item_full_name):
        '''
        Get a particular RenderItem abstract data node by host app full node name.

        Args:
            item_full_name (str):

        Returns:
            render_item (RenderItem):
        '''
        for render_item in self.get_render_items():
            if render_item.get_item_full_name() == item_full_name:
                return render_item


    def get_render_item_for_column(self, column):
        '''
        Get a RenderItem for a particular column.

        Args:
            column (int):

        Returns:
            render_item (RenderItem): or subclass
        '''
        column = column - 1
        if column < 0:
            return
        try:
            return self.get_render_items()[column]
        except IndexError:
            return


    def get_environments(
            self,
            with_renderable_passes=False,
            include_index=False,
            include_job_identifier=False):
        '''
        Get all output render oz environments as list of strings currently in model.

        Args:
            with_renderable_passes (bool): optionally only return environment items
                that has active renderable passes
            include_index (bool): optionally end the environment with dash then index number.
                Note: The same environment can exist multiple times in the model.
            include_job_identifier (bool): this option takes priority over include_index.

        Returns:
            environments (list): list of environments.
                Note: the same environment might appear multiple times
        '''
        environments = set()
        environments_counter = dict()
        for environment_item in self.get_environment_items():
            environment = environment_item.get_oz_area()
            if not environment:
                continue

            if any([include_index, include_job_identifier]):
                # Keep track of index of item
                if environment not in environments_counter.keys():
                    environments_counter[environment] = 0
                environments_counter[environment] += 1
                # Add index to environment string
                env_index = environments_counter[environment]
                job_identifier = environment_item.get_job_identifier()
                if include_job_identifier and job_identifier:
                    environment += '-' + str(job_identifier)
                elif include_index:
                    environment += '-' + str(env_index)

            # Option limit to Shot Environments with at least one renderable pass
            if with_renderable_passes:
                for pass_env_item in environment_item.get_pass_for_env_items():
                    if pass_env_item.get_active():
                        environments.add(environment)
                        break
            else:
                environments.add(environment)

        return list(environments)


    def get_group_items_indices(self):
        '''
        Get list of main model GroupItem indices.

        Returns:
            group_items_indices (list):
        '''
        parent_index = QModelIndex()
        row_count = self.rowCount(parent_index)
        group_items_indices = list()
        for row in range(row_count):
            qmodelindex = self.index(row, 0, parent_index)
            if not qmodelindex.isValid():
                continue
            item = qmodelindex.internalPointer()
            if item.is_group_item():
                group_items_indices.append(qmodelindex)
        return group_items_indices


    def get_group_items(self):
        '''
        Get all data nodes that are GroupItem (or subclass).

        Returns:
            group_items (list):
        '''
        group_items = list()
        for qmodelindex in self.get_group_items_indices():
            group_item = qmodelindex.internalPointer()
            group_items.append(group_item)
        return group_items


    def get_group_names(self):
        '''
        Get list of all group names currently in the model.

        Returns:
            group_names (list):
        '''
        group_names = list()
        for group_item in self.get_group_items():
            group_name = group_item.get_group_name()
            if group_name:
                group_names.append(group_name)
        return group_names


    def get_pass_for_env_items(self):
        '''
        Get all the render pass for env items in the entire model.

        Returns:
            pass_for_env_items (list):
        '''
        pass_for_env_items = list()
        for qmodelindex in self.get_pass_for_env_items_indices():
            if not qmodelindex.isValid():
                continue
            pass_for_env_item = qmodelindex.internalPointer()
            pass_for_env_items.append(pass_for_env_item)
        return pass_for_env_items


    def get_identifiers(self, nice_env_name=False):
        '''
        Get all the identifiers of render pass for env items in the entire model.

        Args:
            joiner (str):
            nice_env_name (bool):

        Returns:
            identifiers (list):
        '''
        identifiers = list()
        for pass_env_item in self.get_pass_for_env_items():
            identifier = pass_env_item.get_identifier(nice_env_name=nice_env_name)
            identifiers.append(identifier)
        return identifiers


    def get_counts_for_shot_and_pass_selection(
            self,
            shots_selected,
            shots_passes_selected):
        '''
        Get counts in passes and frames from selected shots and passes.

        Args:
            shots_selected (list):
            shots_passes_selected (list):

        Returns:
            results (dict):
        '''
        results = dict()
        results['enabled_pass_count'] = 0
        results['queued_pass_count'] = 0
        results['enabled_frame_count'] = 0
        results['queued_frame_count'] = 0

        # Gather and store selected details of passes
        pass_for_env_ids = set()
        for pass_env_item in shots_passes_selected:
            active = pass_env_item.get_active()
            results['enabled_frame_count'] += pass_env_item.get_resolved_frames_count_enabled()
            if active:
                results['queued_frame_count'] += pass_env_item.get_resolved_frames_count_queued()
            results['enabled_pass_count'] += int(pass_env_item.get_enabled())
            results['queued_pass_count'] += int(active)
            pass_for_env_ids.add(id(pass_env_item))

        # Gather and store selected details of shots
        for environment_item in shots_selected:
            for pass_env_item in environment_item.get_pass_for_env_items():
                if id(pass_env_item) in pass_for_env_ids:
                    continue
                active = pass_env_item.get_active()
                enabled = pass_env_item.get_enabled()
                results['enabled_frame_count'] += pass_env_item.get_resolved_frames_count_enabled()
                if active:
                    results['queued_frame_count'] += pass_env_item.get_resolved_frames_count_queued()
                results['enabled_pass_count'] += int(enabled)
                results['queued_pass_count'] += int(active)

        return results


    def get_pass_for_env_items_being_dispatched(self):
        '''
        Get only the render pass for env items currently being dispatched in the entire model.

        Returns:
            pass_for_env_items (list):
        '''
        pass_for_env_items = list()
        for qmodelindex in self.get_pass_for_env_items_indices():
            if not qmodelindex.isValid():
                continue
            pass_for_env_item = qmodelindex.internalPointer()
            if pass_for_env_item.get_is_being_dispatched():
                pass_for_env_items.append(pass_for_env_item)
        return pass_for_env_items


    def get_identifiers_being_dispatched(self, nice_env_name=False):
        '''
        Get only the identifiers of render pass for env items currently being dispatched in the entire model.

        Args:
            joiner (str):
            nice_env_name (bool):

        Returns:
            identifiers (list):
        '''
        identifiers = list()
        for pass_env_item in self.get_pass_for_env_items_being_dispatched():
            identifier = pass_env_item.get_identifier(nice_env_name=nice_env_name)
            identifiers.append(identifier)
        return identifiers


    def get_pass_for_env_items_indices(self, env_indices=None, column=None):
        '''
        Get a list of QModelIndex for abstract data classes of
        RenderPassForEnvItem (or subclasses), which acts as cells
        in the model (for all columns except 1).

        Args:
            env_indices (list): list of EnvironmentItem QModexlIndex
            column (list): optionally only get pass for env items along a particular column.
                Note: Column number specified less than one is ignored.

        Returns:
            pass_for_env_items_indices (list):
        '''
        if not env_indices:
            env_indices = list()
        if isinstance(column, int) and column >= 1:
            columns = [column]
        else:
            columns = range(1, self.columnCount(QModelIndex()))
        pass_for_env_items_indices = list()
        for env_index in env_indices or self.get_environment_items_indices():
            row = env_index.row()
            qmodelindex_parent = env_index.parent()
            for c in columns:
                qmodelindex = self.index(row, c, qmodelindex_parent)
                if not qmodelindex.isValid():
                    continue
                pass_for_env_items_indices.append(qmodelindex)
        return pass_for_env_items_indices


    def get_item_from_uuid(
            self,
            uuid,
            environment_items=None,
            pass_env_items=None,
            must_be_active=False):
        '''
        Get a Multi Shot item by UUID.

        Args:
            uuid (str): the UUID to find
            environment_items (list): optionally only check a subset of environment items
            pass_env_items (list): optionally only check a subset of render pass for environment items
            must_be_active (bool): optionally don't return matching item if inactive

        Returns:
            item (BaseMultiShotItem): can return various Multi Shot item types
        '''
        environment_items = environment_items or self.get_environment_items()
        for env_item in environment_items:
            if env_item.get_identity_id() == str(uuid):
                return env_item
        pass_env_items = pass_env_items or self.get_pass_for_env_items()
        for pass_env_item in pass_env_items:
            if must_be_active and not pass_env_item.get_active():
                continue
            if pass_env_item.get_identity_id() == str(uuid):
                return pass_env_item
        # TODO: Currently checking for RenderItem by UUID isn't required but should be added also


    def get_wait_on_targets(self, item):
        '''
        Get WAIT on target items for render pass for env items or environment items.

        Args:
            item (RenderPassForEnvItem): or environment item

        Returns:
            items (list): list of render pass for env items or environment items
        '''
        if not item:
            return list()
        if not any([item.is_environment_item(), item.is_pass_for_env_item()]):
            return list()
        items = list()
        for wait_on in item.get_wait_on():
            item = self.get_item_from_uuid(wait_on)
            if item:
                items.append(item)
        return items


    def get_wait_on_identifiers(self, item):
        '''
        Get WAIT On as human readable identifiers, rather than UUIDs.

        Args:
            item (RenderPassForEnv): or environment item

        Returns:
            identifiers (list): list of human readable WAIT on identifiers
        '''
        wait_on_targets = self.get_wait_on_targets(item) or list()
        identifiers = list()
        for wait_on_target in wait_on_targets:
            if wait_on_target.is_environment_item():
                identifier = wait_on_target.get_environment_name_nice()
            elif wait_on_target.is_pass_for_env_item():
                identifier = wait_on_target.get_identifier(nice_env_name=True)
            identifiers.append(identifier)
        return identifiers


    def get_wait_on_plow_ids_display_string(self, item):
        '''
        Get WAIT On as human readable identifiers, rather than UUIDs.

        Args:
            item (RenderPassForEnv): or environment item

        Returns:
            identifiers (list): list of human readable WAIT on identifiers
        '''
        wait_on_plow_ids = item.get_wait_on_plow_ids()
        if not wait_on_plow_ids:
            return list()
        display_values = list()
        scheduler_operations = self.get_scheduler_operations()
        for values in wait_on_plow_ids:
            if not values:
                continue
            job = scheduler_operations.get_job(values[0])
            if len(values) == 1:
                display_values.append(job.name)
            elif len(values) == 2:
                layer = scheduler_operations.get_layer_for_job(job, values[1])
                if layer:
                    display_value = '{} {}'.format(job.name, layer.name)
                    display_values.append(display_value)
                else:
                    tasks = scheduler_operations.get_tasks_for_job(job, values[1])
                    if tasks:
                        display_value = '{} {}'.format(job.name, tasks[0].name)
                        display_values.append(display_value)
        return ', '.join(display_values)


    def get_item_from_identifier(
            self,
            identifier,
            environment_items=None,
            pass_env_items=None,
            must_be_active=False):
        '''
        Get a Multi Shot item by human readable Identifier.

        Args:
            identifier (str): the human readable identifier to find
            environment_items (list): optionally only check a subset of environment items
            pass_env_items (list): optionally only check a subset of render pass for environment items
            must_be_active (bool): optionally don't return matching item if inactive

        Returns:
            item (BaseMultiShotItem): can return various Multi Shot item types
        '''
        environment_items = environment_items or self.get_environment_items()
        for env_item in environment_items:
            found_match, _identifier = self.check_identifier_matches_item(identifier, env_item)
            if found_match:
                return env_item
        pass_env_items = pass_env_items or self.get_pass_for_env_items()
        for pass_env_item in pass_env_items:
            if must_be_active and not pass_env_item.get_active():
                continue
            found_match, _identifier = self.check_identifier_matches_item(identifier, pass_env_item)
            if found_match:
                return pass_env_item
        # NOTE: RenderItem currently do not have or need identifiers


    def convert_uuids_to_identifiers(self, uuids):
        '''
        Convert a list of Multi Shot UUIDs to human readable Identifiers.

        Args:
            uuids (list):

        Returns:
            identifiers (list):
        '''
        if not uuids:
            uuids = list()
        identifiers = list()
        for uuid in uuids:
            item = self.get_item_from_uuid(uuid)
            if not item:
                continue
            if item.is_environment_item():
                identifier = item.get_environment_name_nice()
            else:
                identifier = item.get_identifier(nice_env_name=True)
            identifiers.append(identifier)
        return identifiers


    def convert_identifiers_to_uuids(self, identifiers):
        '''
        Convert a list of Multi Shot UUIDs to human readable Identifiers.

        Args:
            identifiers (list):

        Returns:
            uuids (list):
        '''
        if not identifiers:
            identifiers = list()
        uuids = list()
        for identifier in identifiers:
            item = self.get_item_from_identifier(identifier)
            if not item:
                continue
            uuid = item.get_identity_id()
            uuids.append(uuid)
        return uuids


    def check_identifier_matches_item(self, identifier, item):
        '''
        Validate a human readable identifier matches a single Multi Shot item.

        Args:
            identifier (str):
            item (BaseMultiShotItem): item can be multiple Multi Shot item types

        Returns:
            found_match, identifier (tuple):
        '''
        if item.is_pass_for_env_item():
            env_item = item.get_environment_item()
            render_item = item.get_source_render_item()
            item_full_name = render_item.get_item_full_name()
        else:
            env_item = item
            item_full_name = None
        env = env_item.get_oz_area()
        env_index = env_item._get_cached_environment_index()
        job_identifier = env_item.get_job_identifier()

        found_match = False

        # Check for direct string match
        _identifier = item.get_identifier()
        if _identifier == identifier:
            found_match = True

        # Check for simple environment match
        if not found_match:
            _identifier = env
            found_match = _identifier == identifier

        # Check for match to environment identifier (with job identifier or index)
        if not found_match:
            _identifier = env + '-' + str(env_index)
            found_match = _identifier == identifier
        if not found_match and job_identifier:
            _identifier = env + '-' + str(job_identifier)
            found_match = _identifier == identifier

        # Check for match to pass for env identifier
        if item_full_name:
            if not found_match:
                _identifier = env + '-' + str(env_index) + constants.IDENTIFIER_JOINER + item_full_name
                found_match = _identifier == identifier
            if not found_match and job_identifier:
                _identifier = env + '-' + str(job_identifier) + constants.IDENTIFIER_JOINER + item_full_name
                found_match = _identifier == identifier
            # if not found_match:
            #     _identifier = env + constants.IDENTIFIER_JOINER + item_full_name
            #     found_match = _identifier == identifier

        return found_match, _identifier


    ##########################################################################
    # Resolve methods (at model level)


    def resolve_all(
            self,
            pass_for_env_items=None,
            current_frame_only=False,
            update_progress_bar=False,
            cache_values=False,
            collapse_version_overrides=False):
        '''
        Resolve all frames, and versions, and get the highest for VP+, and
        apply to Pass for Env items set to VP+.
        NOTE: This currently only happens when multi_shot_render is called.

        Args:
            pass_for_env_items (list): list of specific PassForEnvItem (or subclasses) to render
            current_frame_only (bool): ignore frame range overrides and only render current project frame
            update_progress_bar (bool):
            cache_values (bool): whether to store the resolved cg version as private
                member on each render pass for env or not.
            collapse_version_overrides (bool): whether to collapse dynamic version overrides to explicit

        Returns:
            success (bool):
        '''
        if update_progress_bar:
            current_percent = 0
            progress_msg = 'Resolving Overrides & Preparing To '
            progress_msg += 'Open Summary - %p%'
            self.updateLoadingBarFormat.emit(current_percent, progress_msg)

        # Resync production data, before resolving frames (if any passes enabled)
        environment_items = self.get_environment_items()
        env_count = len(environment_items)
        synced_render_items = set()
        for i, environment_item in enumerate(environment_items):
            # First check if any renderable items for row
            pass_for_env_items_row = environment_item.get_pass_for_env_items()
            renderable_pass_for_env_items = list()
            for pass_env_item in pass_for_env_items_row:
                # Skip counting unqueued or disabled items
                if not pass_env_item.get_active():
                    continue
                # Optionally only resolve subset of pass for environments
                if pass_for_env_items and pass_env_item not in pass_for_env_items:
                    continue
                renderable_pass_for_env_items.append(pass_env_item)

                # Do non fast sync on source render item only if required and on demand.
                render_item = pass_env_item.get_source_render_item()
                if render_item not in synced_render_items:
                    fast = not self.get_cook_more_summary_details()
                    render_item.sync_render_details(fast=fast)
                    synced_render_items.add(render_item)

            # No renderable passes for Environment / graph state
            if not renderable_pass_for_env_items:
                continue

            # Cache the currrent production data as previous (for summary)
            environment_item.cache_production_data_as_previous()

            # Has renderable passes so Sync production data
            if self._auto_refresh_from_shotgun:
                environment_item.sync_production_data()

            # Cache the production data changed details (for summary)
            environment_item.cache_production_data_changed()

            # Optionally update progress bar
            if update_progress_bar:
                percent = int(float(i) / env_count) + current_percent
                self.updateLoadingBarFormat.emit(percent, progress_msg)
                current_percent = int(percent)

            # Now go back any resolve required frames and versions
            next_version_numbers = [1]
            for pass_env_item in renderable_pass_for_env_items:
                pass_env_item.resolve_frames(
                    current_frame_only=current_frame_only)
                pass_env_item.resolve_version(
                    source_project_version=self._source_project_version,
                    cache_values=True,
                    collapse_version_overrides=collapse_version_overrides)
                resolved_version_number = pass_env_item.get_resolved_version_number()
                if resolved_version_number:
                    next_version_numbers.append(resolved_version_number)

            max_version = max(next_version_numbers)
            msg = 'Computed next max shot version: {}.'.format(max_version)
            msg += 'Queued render passes set to VP+ will use this version to render to. '
            self.logMessage.emit(msg, logging.INFO)

            for pass_env_item in renderable_pass_for_env_items:
                if pass_env_item.get_resolved_version_system() == constants.CG_VERSION_SYSTEM_PASSES_NEXT:
                    pass_env_item.set_resolved_version_number(max_version)
                    identifier = pass_env_item.get_identifier()
                    msg = 'Set pass: "{}". '.format(identifier)
                    msg += 'To resolved version: "{}". '.format(max_version)
                    self.logMessage.emit(msg, logging.DEBUG)

        return True


    def get_pass_count_all_queued(self, pass_for_env_items=None):
        '''
        Get the total number of RenderPassForEnvItem/s that
        currently enabled and queued.

        Args:
            pass_for_env_items (list): list of specific PassForEnvItem (or subclasses) to operate on

        Returns:
            pass_count_all_queued (int):
        '''
        pass_count_all_queued = 0
        for render_item in self.get_render_items():
            pass_count_all_queued += render_item._get_renderable_count_for_render_node()
        return pass_count_all_queued


    def resolve_frames_for_index(
            self,
            qmodelindex,
            update_overview_requested=True):
        '''
        Resolve the frames for the given qmodelindex, and cache the result.
        Optionally emit updateOverviewRequested.

        Args:
            qmodelindex (QModelIndex):
            update_overview_requested (bool):
        '''
        if not qmodelindex.isValid():
            return False

        item = qmodelindex.internalPointer()
        if item.is_group_item():
            return False

        # Resolve the frames for current column or all columns
        if qmodelindex.column() == 0:
            # Resolve for every column
            pass_for_env_items = item.get_pass_for_env_items()
            for i, pass_for_env_item in enumerate(pass_for_env_items):
                # Resolve frames and cache value
                pass_for_env_item.resolve_frames()
        else:
            # Resolve frames and cache value
            item.resolve_frames()

        if update_overview_requested:
            self.updateOverviewRequested.emit()

        return True


    def get_shot_count_with_queued(self, pass_for_env_items=None):
        '''
        Get the total number of Shot EnvironmentItem/s that
        currently enabled and queued.

        Args:
            pass_for_env_items (list): list of specific PassForEnvItem (or subclasses) to operate on

        Returns:
            shot_count_with_queued (int):
        '''
        # if pass_for_env_items:
        #     pass_for_env_items = set(pass_for_env_items)

        shot_count_with_queued = 0
        for environment_item in self.get_environment_items():
            # # If pass for env item mask is available, then check at least one item is in current Environment
            # if pass_for_env_items:
            #     _pass_for_env_items = environment_item.get_pass_for_env_items() or list()
            #     result = set(_pass_for_env_items).intersection(pass_for_env_items)
            #     if not result:
            #         continue
            shot_count_with_queued += int(bool(environment_item._get_renderable_count_for_env()))
        return shot_count_with_queued


    def formulate_label_only_render_estimate(
            self,
            pass_for_env_items=None,
            pass_count_all_queued=None,
            shot_count_with_queued=None,
            frame_count_all_queued=None):
        '''
        Formulate full render overview with render estimate as string.
        NOTE: The returned value is only intended to be used with QLabel as simple text.
        NOTE: By default the RenderEstimateWidget instead paints a graph, and calls
        RenderEstimateWidget.update_estimate instead.

        Args:
            pass_for_env_items (list): list of specific PassForEnvItem
                (or subclasses) to get values for
            pass_count_all_queued (int):
            shot_count_with_queued (int):
            frame_count_all_queued (int):

        Returns:
            result (tuple): result is tuple of (
                overview_str,
                pass_count_all_queued,
                shot_count_with_queued,
                frame_count_all_queued)
        '''
        # Add overview details
        if pass_count_all_queued == None:
            pass_count_all_queued = self.get_pass_count_all_queued()

        if shot_count_with_queued == None:
            shot_count_with_queued = self.get_shot_count_with_queued()

        if frame_count_all_queued == None:
            frame_count_all_queued = self.get_frame_count_all_queued(pass_for_env_items)

        msg_parts = list()
        if pass_count_all_queued:
            msg = '{} passes'.format(pass_count_all_queued)
            msg_parts.append(msg)

        if shot_count_with_queued:
            msg = '{} shots'.format(shot_count_with_queued)
            msg_parts.append(msg)

        if frame_count_all_queued:
            msg = '{} frames'.format(frame_count_all_queued)
            msg_parts.append(msg)

        msg = ', '.join(msg_parts)

        if constants.EXPOSE_RENDER_ESTIMATE and self._compute_render_estimate:
            # Add the render estimate
            render_estimate = self._formulate_render_estimate_text(pass_for_env_items)
            if render_estimate:
                msg += '\n' + render_estimate

        return (
            msg,
            pass_count_all_queued,
            shot_count_with_queued,
            frame_count_all_queued)


    def compute_all_summary_counters(self):
        '''
        Throw away any cached summary details, like renderable count for render item,
        and environment item, and also resolve all frames for each render pass for env.

        Returns:
            success (bool):
        '''
        environment_items = self.get_environment_items()
        env_count = len(environment_items)
        msg = 'Computing all summary counters for {} environments...'.format(env_count)
        self.logMessage.emit(msg, logging.INFO)
        # Clear cached renderable counts for all environments and passes
        for environment_item in environment_items:
            environment_item._renderable_count_for_env = 0
            for pass_env_item in environment_item.get_pass_for_env_items():
                render_item = pass_env_item.get_source_render_item()
                render_item._renderable_count_for_render_node = 0
        # Update renderable counts
        for environment_item in environment_items:
            for pass_env_item in environment_item.get_pass_for_env_items():
                if not pass_env_item.get_active():
                    continue
                render_item = pass_env_item.get_source_render_item()
                render_item._renderable_count_for_render_node += 1
                environment_item._renderable_count_for_env += 1
                pass_env_item.resolve_frames()
        # Request overview to be updated
        self.updateOverviewRequested.emit()


    def get_frame_count_all_queued(self, pass_for_env_items=None):
        '''
        Get the total number of resolved frame range each
        RenderPassForEnvItem/s currently has.

        Args:
            pass_for_env_items (list): list of specific PassForEnvItem
                (or subclasses) to get values for

        Returns:
            frame_count_all_queued (int):
        '''
        pass_for_env_items = pass_for_env_items or self.get_pass_for_env_items()
        frame_count = 0
        for pass_env_item in pass_for_env_items:
            if not pass_env_item.get_active():
                continue
            frame_count += pass_env_item.get_resolved_frames_count_queued()
        return frame_count


    def compute_render_estimates_for_environments(
            self,
            compute=True,
            environment_items=None,
            force=False):
        '''
        Compute render estimates for all or specified environments.

        Args:
            compute (bool):
            environment_items (list):
            force (bool): force (bool): optionally skip getting estimate if already cached
        '''
        environment_items = environment_items or self.get_environment_items()

        msg = 'Toggling Compute Render Estimates To: {}. '.format(compute)
        msg += 'Force Update: {}'.format(force)
        self.logMessage.emit(msg, logging.WARNING)

        self.set_compute_render_estimate(compute)

        if compute:
            start_time = time.time()

            # Update a progress bar for each environment because might be expensive
            msg = 'Computing Render Estimates For All Passes Of Environments...'
            self.logMessage.emit(msg, logging.INFO)
            self.updateLoadingBarFormat.emit(0, msg + ' - %p%')
            self.toggleProgressBarVisible.emit(True)
            count = len(environment_items)
            for i, environment_item in enumerate(environment_items):
                percent = int((float(i) / count) * 100)
                self.updateLoadingBarFormat.emit(percent, msg + ' - %p%')
                oz_area = environment_item.get_oz_area()
                self.compute_render_estimates_for_environment(
                    environment_item,
                    force=force)

            self.toggleProgressBarVisible.emit(False)

            te = int(time.time() - start_time)
            msg = 'Time Taken To Compute All Render Estimates. '
            self.logMessage.emit(TIME_TAKEN_MSG.format(msg, te), logging.DEBUG)

        # Now update overview from model
        self.updateOverviewRequested.emit()


    def compute_render_estimates_for_environment(
            self,
            environment_item,
            pass_for_env_items=None,
            force=False):
        '''
        Compute render estimates for single environment.
        Compute and cache estimated average time to render a single frame of each
        pass of this environment (or the specified passes),
        NOTE: Results are cached on each target render pass for env item.

        Args:
            environment_item (EnvironmentItem):
            pass_for_env_items (list): list of pass for env items to compute estimate for.
                if not provided then compute for all passes of environment.
            force (bool): optionally skip getting estimate if already cached
        '''
        pass_for_env_items = pass_for_env_items or environment_item.get_pass_for_env_items()
        if not pass_for_env_items:
            return

        try:
            import plow
        except ImportError:
            return

        start_time = time.time()

        # Get areas of passes with underscores
        areas = set()
        for pass_env_item in pass_for_env_items:
            identifier = pass_env_item.get_identifier()
            # Optionally skip getting estimate if already cached
            if not force and pass_env_item.get_render_estimate_average_frame():
                if self._debug_mode:
                    msg = 'Skipping Compute Render Estimate For Pass Already Cached: "{}". '.format(identifier)
                    msg += 'Areas: "{}". '.format(areas)
                    self.logMessage.emit(msg, logging.DEBUG)
                continue
            # NOTE: We want to get all the estimates even for disabled items,
            # so when user toggles disabled item back on, there is no delay, the
            # cached values can be retrieved.
            # if not pass_env_item.get_active():
            #     continue
            environment_item = pass_env_item.get_environment_item()
            area = environment_item.get_oz_area().strip('/').replace('/', '_')
            areas.add(area)

        if not areas:
            return

        pass_count = len(pass_for_env_items)
        msg = 'Computing render estimate for pass count: "{}". '.format(pass_count)
        msg += 'Areas: "{}". '.format(areas)
        self.logMessage.emit(msg, logging.DEBUG)

        # Cache Plow jobs for areas
        # for_host = '_.*{}.*'.format(constants.HOST_APP[1:])
        for area in areas:
            if self._stats.has_key(area):
                continue
            self._stats[area] = dict()
            # regex = area + for_host
            jobs = plow.get_jobs(
                # regex=regex,
                state=[plow.JobState.FINISHED], # plow.JobState.RUNNING
                attr={'film_tree_scene_shot': area}) # this attribute name is valid for shots or assets render
            # Grab the latest completed layer for each layer name
            for job in jobs:
                # Must have host name in stats key (katana or clarisse)
                if not constants.HOST_APP.lower() in job.statsKey.lower():
                    continue
                for layer in job.get_layers():
                    include_layer = False
                    # # Only include interesting Layers with particular service key.
                    # # NOTE: The service key might not necessarily be a render task...
                    # if not include_layer:
                    #     include_layer = layer.service in constants.HOST_APP_SERVICE_KEYS
                    # Katana and Clarisse have the task type Layer attribute to
                    # quickly check if render type (as opposed to post task etc)
                    if not include_layer:
                        task_type = layer.attrs.get('task_type')
                        if task_type:
                            include_layer = task_type == 'render'
                    # # Fallback to checking service key for host app name.
                    # # NOTE: The service key might not necessarily be a render task...
                    # if not include_layer:
                    #     include_layer = constants.HOST_APP.lower() in layer.service.lower()
                    if not include_layer:
                        continue
                    layer_stats = layer.stats
                    # Ignore Plow Layers that finish so quickly, something must have gone wrong...
                    seconds = layer_stats.totalClockTime / 1000.0
                    if seconds < 20:
                        continue
                    # Caching Plow Layer object for each area and layer name (if task type is render).
                    if layer.name not in self._stats[area]:
                        self._stats[area][layer.name] = layer
                    # if there are 2 layers with the same job/layer keys, store the latest run.
                    elif layer.stopTime > self._stats[area][layer.name].stopTime:
                        self._stats[area][layer.name] = layer

        # NOTE: Normally this is called once for each environment (so there will one 1 area typically).
        for area in areas:
            layers = self._stats.get(area)
            if not layers:
                continue
            for layer_name in layers.keys():
                layer = layers[layer_name]

                # Clarisse and Katana also provide the pass name Layer attribute
                # which is cleaner and requires no parsing.
                pass_name = layer.attrs.get('pass_name') or layer.name

                # NOTE: For Clarisse pass name is currently full item path, this should be changed to
                # item name only. Instead store item_full_name as different attribute.
                # Clarisse item path: "project://scene/context/Image.MyPassA"
                # NOTE: For Katana or most apps you can't put a dot character in a node / pass name.
                if '.' in pass_name:
                    pass_name = pass_name.split('.')[-1]
                # Get the matching MSRS pass for env item for Layer name
                found_pass_env_item = None
                for pass_env_item in pass_for_env_items:
                    # if not pass_env_item.get_active():
                    #     continue
                    render_item = pass_env_item.get_source_render_item()
                    if render_item.get_node_name() == pass_name:
                        found_pass_env_item = pass_env_item
                        break
                if not found_pass_env_item:
                    continue
                # Also check if service keys match from cached Plow Layer....
                # Only interested in Layers with particular service key.
                service_keys_match = layer.service in constants.HOST_APP_SERVICE_KEYS
                # Fallback to checking service key for host app name.
                # NOTE: Cached Plow layers have already been filtered to render tasks.
                if not service_keys_match:
                    service_keys_match = constants.HOST_APP.lower() in layer.service.lower()
                if not service_keys_match:
                    continue
                layer_stats = layer.stats
                # total_time = layer_stats.totalCoreTime
                # if not total_time:
                #     continue
                # task_count = len(layer.get_tasks())
                # if not task_count:
                #     continue
                # # Get the average time per task
                # average_time = total_time / float(task_count)
                # Prediction starts as the previous run's total core time
                if constants.PREFER_ESTIMATE_CORE_HOURS:
                    average_time = layer_stats.avgCoreTime # layer_stats.totalCoreTime
                else:
                    average_time = layer_stats.avgClockTime # layer_stats.totalClockTime
                if not average_time:
                    continue
                # msg = 'job id: "{}"'.format(job.id)
                # msg += '\nlayer id: "{}"'.format(layer.id)
                # msg += '\ntask count: "{}"'.format(task_count)
                # msg += '\ntotal time: "{}"'.format(total_time)
                # msg += '\naverage time: "{}"'.format(average_time)
                # msg += '\nseconds: "{}"'.format(seconds)
                # self.logMessage.emit(msg, logging.DEBUG)
                found_pass_env_item.set_render_estimate_average_frame(average_time)

        te = int(time.time() - start_time)
        msg = 'Time Taken To Compute Render Estimate '
        msg += 'For {} Passes: "{}". '.format(te, pass_count)
        self.logMessage.emit(
            constants.TIME_TAKEN_MSG.format(msg, te),
            logging.DEBUG)


    def _formulate_render_estimate_text(self, pass_for_env_items=None):
        '''
        Formulate render estimate string about pass for env items using last cached estimate values.
        NOTE: By default the RenderEstimateWidget instead paints a graph, and calls
        RenderEstimateWidget.update_estimate instead.

        Args:
            pass_for_env_items (list): list of pass for env items to formulate estimate for.
                if not provided then formulate for all passes of environment.

        Returns:
            render_estimate (str):
        '''
        pass_for_env_items = pass_for_env_items or self.get_pass_for_env_items()
        if not pass_for_env_items:
            return str()

        hours = 0
        est_passes = 0
        unknown = 0
        for pass_env_item in pass_for_env_items:
            if not pass_env_item.get_active():
                continue
            estimate = pass_env_item.get_render_estimate_average_frame()
            frame_count = pass_env_item.get_resolved_frames_count_queued()
            if estimate:
                hours += self.get_core_hours_from_estimate(estimate, frame_count)
                est_passes += 1
            else:
                unknown += 1

        # TODO: More information - asset count?  (get more sophisticated in some way - need to talk to Jackie Schwer)

        hours_rounded = round(hours, 2)

        if constants.PREFER_ESTIMATE_CORE_HOURS:
            label = 'core-hours'
        else:
            label = 'hours'

        render_estimate = '{} passes were estimated {} {}. '.format(
            est_passes,
            hours_rounded,
            label)

        # Get and cache allocation details
        if not self._allocation_project:
            self._allocation_project, self._allocation_project_used = self.get_allocation()

        if hours and self._allocation_project:
            percent = hours / float(self._allocation_project)
            render_estimate += '\n{:.1%} total show '.format(percent)
            render_estimate += 'allocation over night.'
        if unknown:
            render_estimate += '\n{} passes were not estimated.'.format(unknown)

        return render_estimate


    def get_core_hours_from_estimate(self, estimate_per_frame, frame_count=1):
        '''
        Get estimated render hours per frame multiplied by frame count.

        Args:
            estimate_per_frame (float): estimate of average render time per frame.
            frame_count (int):

        Returns:
            hours (float):
        '''
        estimate_total = estimate_per_frame * frame_count
        seconds = estimate_total / 1000.0
        minutes = seconds / 60.0
        hours = minutes / 60.0
        # hours_rounded = round(hours, 2)
        return hours


    def get_allocation(self, project=None, cached=True):
        '''
        Get and cache render wall allocation for single project.

        Args:
            project (str):
            cached (bool): whether to use last cached value (if any):

        Returns:
            allocation, allocation_used (tuple):
        '''
        if not self._allocation_project or not cached:
            pass_for_env_items = self.get_pass_for_env_items()
            if pass_for_env_items:
                pass_for_env_item = pass_for_env_items[0]
                env_item = pass_for_env_item.get_environment_item()
                context = env_item.get_context()
                project = context.get('FILM') or os.getenv('FILM')
            else:
                project = os.getenv('FILM')
            self._allocation_project = 0
            self._allocation_project_used = 0
            try:
                import plow
                project = plow.get_project(project) # plow.Project()
                # TODO: How long is "over night"?
                night_time_hours = 12                             # lets say 12 hours, crazy cg supes say 8.
                for quoto in project.get_quotas():                    # plow.Project.Quota()
                    cores = quoto.size                                # this is in Cores.
                    cores_running = quoto.running
                    self._allocation_project += cores * night_time_hours  # convert to core-hours by choosing a number of rendering hours
                    if cores_running:
                        self._allocation_project_used += cores_running * night_time_hours
            except Exception:
                pass
        return self._allocation_project, self._allocation_project_used


    def get_allocation_wall(self, cached=True):
        '''
        Get and cache entire render wall allocation.

        Args:
            cached (bool): whether to use last cached value (if any):

        Returns:
            allocation (float):
        '''
        if not self._allocation_wall or not cached:
            self._allocation_wall = 0
            try:
                import plow
                night_time_hours = 12
                for quoto in plow.cluster.get_quotas():
                    cores = quoto.size
                    cores_running = quoto.running
                    self._allocation_wall += cores * night_time_hours
            except Exception:
                pass
        return self._allocation_wall


    ##########################################################################
    # Collect email details


    def get_email_global_details(self):
        '''
        Collect all the global email details during submission.

        Returns:
            email_details (list):
        '''
        email_details = list()

        source_project = self.get_source_project()
        detail_item = ('Source Project', str(source_project))
        email_details.append(detail_item)

        session_path = self.get_autosave_session_path()
        detail_item = ('Auto Save Session Path', str(session_path))
        email_details.append(detail_item)

        global_job_identifier = self.get_global_job_identifier()
        if global_job_identifier:
            detail_item = ('Additional Job Identifier', str(global_job_identifier))
            email_details.append(detail_item)

        description_global = self.get_global_submit_description()
        if description_global:
            detail_item = ('Overall Submission Description', str(description_global))
            email_details.append(detail_item)

        version_global_system = self.get_version_global_system()
        detail_item = ('Version System Global', str(version_global_system))
        email_details.append(detail_item)

        label_str = '{} Version'.format(self.HOST_APP.title())
        host_app_version = self.get_host_app_version()
        detail_item = (label_str, str(host_app_version))
        email_details.append(detail_item)

        multi_shot_submitter_version = self.get_multi_shot_render_submitter_version()
        label_str = '{} Version'.format(self.TOOL_NAME)
        detail_item = (label_str, str(multi_shot_submitter_version))
        email_details.append(detail_item)

        # Also show version of base multi shot render submitter pak
        if 'GEN' not in self.TOOL_NAME:
            label_str = 'Multi Shot Render Submitter Version'.format(self.TOOL_NAME)
            version = utils.get_multi_shot_render_submitter_version()
            detail_item = (label_str, str(version))
            email_details.append(detail_item)

        return email_details


    def get_email_environment_details(self, environment_item):
        '''
        Collect all Environment email details.

        Args:
            environment_item (EnvironmentItem): or subclass

        Returns:
            attr_list (list):
        '''
        attr_list = list()

        identity_id = environment_item.get_environment_name_nice(
            prefer_jid=False) # prefer to use env index, to insure is unique target)
        detail_item = ('MSRS Environment Identifier', identity_id)
        attr_list.append(detail_item)

        identity_id = environment_item.get_identity_id()
        detail_item = ('MSRS Environment UUID', identity_id)
        attr_list.append(detail_item)

        shot_status = environment_item.get_editorial_shot_status()
        detail_item = ('Editorial Shot Status', shot_status)
        attr_list.append(detail_item)

        production_range_source = environment_item.get_production_range_source()

        cut_range = environment_item.get_cut_range()
        label_active = str()
        if 'Cut' in production_range_source:
            label_active = ' (active)'
        detail_item = ('Cut Range{}'.format(label_active), cut_range)
        attr_list.append(detail_item)

        delivery_range = environment_item.get_delivery_range()
        label_active = str()
        if 'Delivery' in production_range_source:
            label_active = ' (active)'
        detail_item = ('Delivery Range{}'.format(label_active), delivery_range)
        attr_list.append(detail_item)

        frame_range = environment_item.get_frame_range()
        label_active = str()
        if 'FrameRange' in production_range_source:
            label_active = ' (active)'
        detail_item = ('Frame Range{}'.format(label_active), frame_range)
        attr_list.append(detail_item)

        due_date = environment_item.get_due_date()
        detail_item = ('Due Date', due_date)
        attr_list.append(detail_item)

        ######################################################################
        # Show Environment / Shot overrides

        _attr_list = self.get_email_override_base_item_details(environment_item)
        attr_list.extend(_attr_list)

        job_identifier = environment_item.get_job_identifier()
        if job_identifier:
            detail_item = ('Optional Job Identifier', job_identifier)
            attr_list.append(detail_item)

        wait_on = environment_item.get_wait_on()
        if wait_on:
            _identifiers = self.get_wait_on_identifiers(environment_item)
            detail_item = ('Shot WAIT On', _identifiers)
            attr_list.append(detail_item)

        wait_on_plow_ids = environment_item.get_wait_on_plow_ids()
        has_wait_on_plow_ids = bool(wait_on_plow_ids)
        if has_wait_on_plow_ids:
            attr_list.append(('Shot WAIT On Plow Ids', wait_on_plow_ids))

        note_override = environment_item.get_note_override_submission()
        if note_override:
            detail_item = ('Shot Submission Note', note_override)
            attr_list.append(detail_item)

        post_tasks = environment_item.get_post_tasks()
        if post_tasks:
            detail_item = ('Post Task/s', post_tasks)
            attr_list.append(detail_item)

            koba_shotsub = environment_item.get_koba_shotsub()
            if koba_shotsub:
                detail_item = ('Koba Shotsub', bool(koba_shotsub))
                attr_list.append(detail_item)

        return attr_list


    def get_email_override_base_item_details(self, item):
        '''
        Get email details from item that inherits from OverrideBaseItem.

        Args:
            override_base_item (OverrideBaseItem): render pass for env or environment item subclass

        Returns:
            attr_list (list):
        '''
        if item.is_environment_item():
            label = 'Shot'
        else:
            label = 'Pass'

        attr_list = list()

        version_override = item.get_version_override()
        if version_override:
            detail_item = (label + ' Version Override', version_override)
            attr_list.append(detail_item)

        frame_range_override = item.get_frame_range_override()
        if frame_range_override:
            detail_item = (label + ' Frame Override', frame_range_override)
            attr_list.append(detail_item)

        frame_rule_important = item.get_frames_rule_important()
        if frame_rule_important:
            detail_item = (label + ' Important Frame Override', frame_rule_important)
            attr_list.append(detail_item)

        frame_rule_fml = item.get_frames_rule_fml()
        if frame_rule_fml:
            detail_item = (label + ' FML Frame Override', frame_rule_fml)
            attr_list.append(detail_item)

        frames_rule_x10 = item.get_frames_rule_x10()
        if frames_rule_x10:
            detail_item = (label + ' X10 Frame Override', frames_rule_x10)
            attr_list.append(detail_item)

        frames_rule_x1 = item.get_frames_rule_x1()
        if frames_rule_x1:
            detail_item = (label + ' X1 Frame Override', frames_rule_x1)
            attr_list.append(detail_item)

        frames_rule_xn = item.get_frames_rule_xn()
        if frames_rule_xn:
            detail_item = (label + ' xN Frame Override', frames_rule_xn)
            attr_list.append(detail_item)

        not_frame_range_override = item.get_not_frame_range_override()
        if not_frame_range_override:
            detail_item = (label + ' NOT Frame Range Override', not_frame_range_override)
            attr_list.append(detail_item)

        frame_rule_not_important = item.get_not_frames_rule_important()
        if frame_rule_not_important:
            detail_item = (label + ' NOT Important Frame Override', frame_rule_not_important)
            attr_list.append(detail_item)

        frame_rule_not_fml = item.get_not_frames_rule_fml()
        if frame_rule_not_fml:
            detail_item = (label + ' NOT FML Frame Override', frame_rule_not_fml)
            attr_list.append(detail_item)

        frame_rule_not_x10 = item.get_not_frames_rule_x10()
        if frame_rule_not_x10:
            detail_item = (label + ' NOT X10 Frame Override', frame_rule_not_x10)
            attr_list.append(detail_item)

        frame_rule_not_xn = item.get_not_frames_rule_xn()
        if frame_rule_not_xn:
            detail_item = (label + ' NOT xN Frame Override', frame_rule_not_xn)
            attr_list.append(detail_item)

        render_overrides_attr_list = self.get_email_render_overrides_details(item)
        if render_overrides_attr_list:
            attr_list.extend(render_overrides_attr_list)

        return attr_list


    def get_email_pass_for_env_details(self, pass_env_item):
        '''
        Collect all Pass for Env email details.

        Args:
            pass_env_item (PassForEnvItem): or subclass

        Returns:
            attr_list (list):
        '''
        render_item = pass_env_item.get_source_render_item()
        item_full_name = render_item.get_item_full_name()
        pass_name = render_item.get_pass_name()
        environment_item = pass_env_item.get_environment_item()
        oz_area = environment_item.get_oz_area()

        attr_list = list()

        attr_list.append(('Pass Name', str(pass_name)))

        identity_id = pass_env_item.get_identifier(
            nice_env_name=True,
            prefer_jid=False) # prefer to use env index, to insure is unique target)
        detail_item = ('MSRS Pass Identifier', identity_id)
        attr_list.append(detail_item)

        identity_id = pass_env_item.get_identity_id()
        detail_item = ('MSRS Pass UUID', identity_id)
        attr_list.append(detail_item)

        resolved_frames = pass_env_item.get_resolved_frames_queued()
        attr_list.append(('Resolved Frames', str(resolved_frames)))

        version_number = str(pass_env_item.get_resolved_version_number())
        version_system = str(pass_env_item.get_resolved_version_system())

        label_str = str(version_number)
        attr_list.append(('Resolved Version', label_str))

        ######################################################################
        # Show Pass overrides

        _attr_list = self.get_email_override_base_item_details(pass_env_item)
        attr_list.extend(_attr_list)

        wait_on = pass_env_item.get_wait_on()
        if wait_on:
            _identifiers = self.get_wait_on_identifiers(pass_env_item)
            detail_item = ('Pass WAIT On', _identifiers)
            attr_list.append(detail_item)

        wait_on_plow_ids = pass_env_item.get_wait_on_plow_ids()
        has_wait_on_plow_ids = bool(wait_on_plow_ids)
        if has_wait_on_plow_ids:
            attr_list.append(('Pass WAIT On Plow Ids', wait_on_plow_ids))

        note_override = pass_env_item.get_note_override_submission()
        if note_override:
            detail_item = ('Pass Submission Note', note_override)
            attr_list.append(detail_item)

        post_tasks = pass_env_item.get_post_tasks()
        if post_tasks:
            detail_item = ('Post Task/s', post_tasks)
            attr_list.append(detail_item)

        return attr_list


    def get_email_render_overrides_details(self, item):
        '''
        Gather render overrides details for auto email about render pass for env or environment item.
        TODO: May want to later only show the resolved value according to env and pass.

        Args:
            override_base_item (OverrideBaseItem): render pass for env or environment item subclass

        Returns:
            render_overrides_attr_list (list): a list of tuples with details about render overrides
                to be added to auto email
        '''
        if not any([item.is_environment_item(), item.is_pass_for_env_item()]):
            return list()
        render_overrides_attr_list = list()
        render_overrides_items = item.get_render_overrides_items()
        for override_id in render_overrides_items.keys():
            render_override_item = render_overrides_items[override_id]
            override_label = render_override_item.get_override_label()
            override_value = render_override_item.get_value()
            render_overrides_attr_list.append((override_label, override_value))
        return render_overrides_attr_list


    ##########################################################################
    # Render from entire data model


    def multi_shot_render(
            self,
            pass_for_env_items=None,
            interactive=False,
            current_frame_only=False,
            global_jbx_bucket=None,
            show_summary_dialog=None,
            parent=None,
            **kwargs):
        '''
        Render all the enabled and queued Render nodes for all target
        environments, by iterating over of abstract data nodes that
        wrap the Render nodes for each environment and call render.
        Otherwise pass in a subset of the abstract data nodes, to render
        only these. Typically these would be derived from a views
        selection model, and getting QModelIndex internal pointer to data node.
        Note: This high level method shouldn't need to be reimplemented
        for particular host application, instead reimplement the host app specific
        EnvironmentItem.render_passes_for_env method.

        Args:
            pass_for_env_items (list): optionally render only render the specified render pass for env
            interactive (bool): optionally interactively render, rather than batch render
            current_frame_only (bool): ignore frame range overrides and only render current project frame
            global_jbx_bucket (str):
            show_summary_dialog (bool): optionally provide override boolean, otherwise default is to use
                show summary dialog state of this model

        Returns:
            success, cancelled, msg (tuple):
        '''

        parent = parent or self
        if not isinstance(show_summary_dialog, bool):
            show_summary_dialog = self.get_show_summary_dialog()

        is_dispatching = self._dispatch_deferred and not interactive

        self.renderSubmitStarted.emit()

        # Collapse version overrides when dispatcher task is running remotely.
        collapse_version_overrides = False
        if self._is_submitting_in_dispatcher_task:
            collapse_version_overrides = True
        # Otherwise if generating jobs locally or interactive collapse the version overrides now
        elif not is_dispatching:
            collapse_version_overrides = True

        # NOTE: Cache all passes cg version overrides.
        # Since resolve_all will flatten all dynamic version overrides to explicit cg overrides.
        cg_ver_cache = dict()
        if collapse_version_overrides:
            cg_ver_cache = self._cache_cg_version_overrides(pass_for_env_items) or dict()
            msg = 'Will temporarily collapse dynamic version '
            msg += 'overrides to explicit during submission...'
            self.logMessage.emit(msg, logging.WARNING)
        else:
            msg = 'Keeping any dynamic version overrides as is for now...'
            self.logMessage.emit(msg, logging.WARNING)

        resolve_start_time = time.time()

        # Resolve all core override values and cache, such as frames and versions
        success = self.resolve_all(
            pass_for_env_items,
            current_frame_only=current_frame_only,
            cache_values=True,
            collapse_version_overrides=collapse_version_overrides,
            update_progress_bar=True)

        te = int(time.time() - resolve_start_time)
        msg = 'Time Taken To Resolve All. '
        self.logMessage.emit(TIME_TAKEN_MSG.format(msg, te), logging.DEBUG)

        # Count all the frames to check there is renderables and other conditions
        if not current_frame_only:
            frame_count = self.get_frame_count_all_queued(pass_for_env_items)
            # Must have some frames to render
            if not frame_count:
                if cg_ver_cache:
                    self._revert_cg_version_overrides(cg_ver_cache)
                self.renderSubmitFinished.emit()
                msg = 'No frames to render, or no queued and enabled items!'
                self.logMessage.emit(msg, logging.CRITICAL)
                return False, False, msg
            # Check interactive render is okay to proceed depending on inputs.
            # TODO: Is this still required for FarmTools2?
            if interactive:
                can_render_interactive, msg = self.check_can_render_interactive(
                    frame_count=frame_count)
                if not can_render_interactive:
                    if cg_ver_cache:
                        self._revert_cg_version_overrides(cg_ver_cache)
                    self.renderSubmitFinished.emit()
                    return False, False, msg
        else:
            msg = 'Submitting only for current project frame...'
            self.logMessage.emit(msg, logging.WARNING)

        ######################################################################

        # The following caching steps run on provided subset of render pass for env or all
        _pass_for_env_items = pass_for_env_items
        if not _pass_for_env_items:
            _pass_for_env_items = self.get_pass_for_env_items()

        # Validate and cache wait on for all items in session.
        # NOTE: This runs during initial user submission. Not when running in the dispatcher Job on Plow.
        wait_on_cache = dict()
        if not self._is_submitting_in_dispatcher_task and not interactive:
            wait_on_cache = self._cache_wait_on(_pass_for_env_items) # selected or all pass for env items

        # Clear any previous submission Plow Job and Layer ids, and set is dispatching state.
        # NOTE: This runs during initial user submission. Not when running in the dispatcher Job on Plow.
        plow_ids_cache = dict()
        if not self._is_submitting_in_dispatcher_task and not interactive:
            plow_ids_cache = self._cache_plow_ids()
            # All the pass for env items to be dispatched
            for pass_env_item in _pass_for_env_items:
                if is_dispatching and pass_env_item.get_active():
                    pass_env_item.set_is_being_dispatched(True)

        ######################################################################
        # Optionally launch Summary & validation dialog.

        if show_summary_dialog and not self._is_submitting_in_dispatcher_task:
            msg = 'Launching output summary & validation dialog...'
            self.logMessage.emit(msg, logging.WARNING)
            self.updateLoadingBarFormat.emit(0, msg + ' - %p%')

            window = self.get_summary_and_validation_window(
                pass_for_env_items=pass_for_env_items,
                interactive=interactive,
                debug_mode=self._debug_mode,
                parent=parent)
            summary_view = window.get_summary_view()

            # Apply any cached summary view header data
            if self._summary_view_header_data_cache:
                summary_view.apply_header_data(
                    self._summary_view_header_data_cache,
                    apply_visibility=True)

            # NOTE: This window is set to be Application blocking like a dialog
            window.show()

            # Get values that might have changed.
            # NOTE: All the other options are updated on model directly.
            is_dispatching = self._dispatch_deferred and not interactive

            result = window.get_was_accepted()

            # Update cache of summary view header data
            self._summary_view_header_data_cache = summary_view.get_column_data() or dict()

            from Qt.QtWidgets import QDialog
            if result == QDialog.Rejected:
                if cg_ver_cache:
                    self._revert_cg_version_overrides(cg_ver_cache)
                if wait_on_cache:
                    self._revert_wait_on(wait_on_cache)
                if plow_ids_cache:
                    self._revert_plow_ids(plow_ids_cache)
                cancelled = True
                msg = 'User cancelled summary & validation dialog'
                self.logMessage.emit(msg, logging.WARNING)
                self.renderSubmitFinished.emit()
                return False, cancelled, msg

        ######################################################################
        # Run pre render and collect session data

        render_start_time = time.time()

        # Run any pre render setup on model and target items
        pre_render_success, pre_render_msg = self.pre_render()
        if not pre_render_success:
            if cg_ver_cache:
                self._revert_cg_version_overrides(cg_ver_cache)
            if wait_on_cache:
                self._revert_wait_on(wait_on_cache)
            if plow_ids_cache:
                self._revert_plow_ids(plow_ids_cache)
            msg = 'Pre render failed!\n'
            msg += str(pre_render_msg)
            self.logMessage.emit(msg, logging.CRITICAL)
            self.renderSubmitFinished.emit()
            return False, False, pre_render_msg

        ######################################################################
        # Create a global JunkBox bucket id to use for centralized dispatch details

        if not global_jbx_bucket:
            from srnd_multi_shot_render_submitter import junkbox
            jbx = junkbox.JunkBox()
            global_jbx_bucket = jbx.get_bucket_id_random()

        ######################################################################

        # Get all important session data and save it
        session_data = self.get_session_data(use_submit_note=is_dispatching)
        if not session_data:
            if cg_ver_cache:
                self._revert_cg_version_overrides(cg_ver_cache)
            if wait_on_cache:
                self._revert_wait_on(wait_on_cache)
            if plow_ids_cache:
                self._revert_plow_ids(plow_ids_cache)
            msg = 'Failed to serialize any session data '
            msg += 'before render started!'
            self.logMessage.emit(msg, logging.CRITICAL)
            self.renderSubmitFinished.emit()
            return False, False, msg

        ######################################################################
        # Optionally snapshot or get current source project

        oz_area_submission = os.getenv('OZ_CONTEXT')

        # Snapshot the project now if deferring submit to later
        if is_dispatching and self._snapshot_before_dispatch:
            source_project, warning_messages = self.snapshot_host_app_project(
                oz_area=oz_area_submission)
            if not source_project:
                msg = 'Failed to snapshot the current project to dispatch from! '
                msg += '<br><i>Note: Please check you have the required permissions!</i>'
                msg += '<br><br>Error:<br><i>'
                if warning_messages:
                    msg += '<br>'.join(warning_messages)
                msg += '</i>'
                self.logMessage.emit(msg, logging.CRITICAL)
                self.renderSubmitFinished.emit()
                return False, False, msg
            msg = 'Snapshot project result: "{}". '.format(source_project)
            self.logMessage.emit(msg, logging.INFO)
        # Get the current project from host app, or external widget (or last source project)
        else:
            # Get current project from host app API, or external UI widget (if any).
            source_project = self.get_current_project() or self._get_project_from_external_widget()
            # Use previous source project (if API doesn't return current project),
            # and no external project widget to get project from.
            if not source_project:
                source_project = self._source_project

            if source_project:
                msg = 'Using existing project: "{}". '.format(source_project)
                msg += 'Snapshot project not required or requested.'
                self.logMessage.emit(msg, logging.INFO)

        # Update the session resource in relation to project
        if self.get_in_host_app_ui() and source_project:
            self.session_save_resource_for_project(
                source_project,
                session_data,
                oz_area=oz_area_submission)

        # Cache the current project (to add to email details etc), and update session data
        self._source_project = source_project
        if self._source_project:
            session_data['project'] = self._source_project

        ######################################################################
        # Save time stamped session data for current submission

        session_path = str(self.get_session_auto_save_location() or str())
        self._autosave_session_path = session_path

        # Write current session data
        if session_path:
            msg = 'Writing session data to: "{}"'.format(session_path)
            self.logMessage.emit(msg, logging.INFO)
            from srnd_qt.data import ui_session_data
            ui_session_data.UiSessionData().session_write(
                session_path,
                session_data)

        ######################################################################

        # If deferred dispatch is enabled then the rest of submission will happen in a Job on Plow
        if is_dispatching:
            result = self._multi_shot_dispatch(pass_for_env_items)
            if cg_ver_cache:
                self._revert_cg_version_overrides(cg_ver_cache)
            if wait_on_cache:
                self._revert_wait_on(wait_on_cache)
            if plow_ids_cache:
                self._revert_plow_ids(plow_ids_cache)
            return result

        ######################################################################
        # Submit each Environment and required passes in current app context

        job_count = 0
        renderable_pass_count = 0
        shots_to_render = set()
        envs_hashes_of_pass_versions = list()

        pass_count_progress = 0
        pass_count_progress_all = len(self.get_pass_for_env_items_indices())

        # NOTE: jinja for HTML templates supports OrderedDict.
        email_details = collections.OrderedDict()
        email_details['globals'] = collections.OrderedDict()
        email_details['envs_data'] = list()

        for env_qmodelindex in self.get_environment_items_indices():
            if not env_qmodelindex.isValid():
                continue
            env_item = env_qmodelindex.internalPointer()

            # Get all the pass for env items for this environment item
            pass_for_env_items_indices = self.get_pass_for_env_items_indices(
                env_indices=[env_qmodelindex])
            if not pass_for_env_items_indices:
                continue

            # Check if request interrupt previously triggered before continue
            oz_area = env_item.get_oz_area()
            if self._request_interrupt:
                msg = 'Skipping submission of environment: "{}".'.format(oz_area)
                self.logMessage.emit(msg, logging.WARNING)
                continue

            # Count number of passes to render, emit signals to paint progress, and update loading bar
            # NOTE: UI updates via signals which is ignored in standalone mode.
            # NOTE: Only counting passes is required here.
            environment_start_time = time.time()
            scene_shot_area = env_item.get_scene_shot_area()
            submit_msg = 'Submitting shot: {}'.format(scene_shot_area)
            pass_to_render_count = 0
            for i, pass_qmodelindex in enumerate(pass_for_env_items_indices):
                if not pass_qmodelindex.isValid():
                    continue
                pass_env_item = pass_qmodelindex.internalPointer()
                # Updating the loading bar (if any)
                percent = int((float(pass_count_progress) / pass_count_progress_all) * 100)
                self.updateLoadingBarFormat.emit(percent, submit_msg + ' - %p%')
                pass_count_progress += 1
                # Rendering has been limited to particular data items.
                if pass_for_env_items and pass_env_item not in pass_for_env_items:
                    continue
                # Item must be enabled and queued to be renderable
                if not pass_env_item.get_active():
                    continue
                identifier = pass_env_item.get_identifier()
                # Must have some queued frames to render
                if not pass_env_item.get_resolved_frames_count_queued():
                    msg = 'No queued frames skipping render '
                    msg += 'of: "{}".'.format(identifier)
                    self.logMessage.emit(msg, logging.WARNING)
                    continue
                # Environment has another pass to render
                pass_to_render_count += 1
                # Paint red preview of passes for environment being submitted, and update loading bar
                self.processingPassForEnv.emit(
                    pass_qmodelindex,
                    True,
                    str())

            # Must have passes to render from current target environment
            if not pass_to_render_count:
                if self._debug_mode:
                    msg = 'No renderable passes for environment: "{}". '.format(oz_area)
                    msg += 'Will skip environment render!'
                    self.logMessage.emit(msg, logging.WARNING)
                continue

            # Perform any environment updates, this might be expensive...
            # NOTE: If this method has no or needs no implementation it should return True
            success = env_item.update_environment_in_host_app(
                session_path=self._autosave_session_path)
            if not success:
                msg = 'Setup failed for environment: "{}". '.format(oz_area)
                msg += 'Will skip environment render!'
                self.logMessage.emit(msg, logging.WARNING)
                continue

            # Setup each render pass and apply any overrides
            passes_for_envs_to_render = collections.OrderedDict()
            applied_overrides_for_pass = collections.OrderedDict()
            for i, pass_qmodelindex in enumerate(pass_for_env_items_indices):
                if not pass_qmodelindex.isValid():
                    continue
                pass_env_item = pass_qmodelindex.internalPointer()
                if pass_for_env_items and pass_env_item not in pass_for_env_items:
                    continue
                if not pass_env_item.get_active():
                    continue
                # No resolved frames so skip
                if not pass_env_item.get_resolved_frames_count_queued():
                    continue
                # It is known at this point this render node must be renderable,
                # so force the node to enabled to indicate this (for snapshot scene).
                # NOTE: Some host app will anot render disabled nodes.
                previous_state_dict = dict()
                render_item = pass_env_item.get_source_render_item()
                render_node_was_enabled = render_item.get_enabled()
                if not render_node_was_enabled:
                    render_item.set_enabled(True)
                previous_state_dict['render_node_was_enabled'] = render_node_was_enabled
                passes_for_envs_to_render[pass_env_item] = previous_state_dict

            # No pass for environments to render
            if not passes_for_envs_to_render:
                continue

            # Cache all the render overrides for environment and passes thereof
            render_overrides_cache = dict()
            if self._apply_render_overrides:
                render_overrides_cache = self._cache_render_override_items(
                    env_item,
                    pass_env_items=passes_for_envs_to_render.keys())

            # Setup each render pass ready for ready
            for pass_env_item in passes_for_envs_to_render.keys():
                # Perform any setup on Render node in host app..
                # NOTE: This might not have any interesting implementation, in which case it returns True
                success, msg = pass_env_item.setup_render_pass_for_env(
                    update_environment=False)
                if not success:
                    msg = 'Failed to setup render pass for env: '
                    msg += '"{}" '.format(identifier)
                    self.logMessage.emit(msg, logging.WARNING)
                    continue
                # Apply any render overrides in host app scene
                has_render_overrides = pass_env_item.has_render_overrides(include_from_env=True)
                if self._apply_render_overrides and has_render_overrides:
                    # Apply pass render overrides (including inherited from environment)
                    _applied_overrides = pass_env_item.apply_render_overrides() or dict()
                    if _applied_overrides:
                        # Cache mapping of override id to items which will later be reverted...
                        applied_overrides_for_pass[pass_env_item] = _applied_overrides

            # Also show red outline at environment item level
            self.processingPassForEnv.emit(
                env_qmodelindex,
                True,
                submit_msg)

            submit_long_msg = 'Setting environment & submitting '
            submit_long_msg += 'oz area: {}'.format(oz_area)
            self.logMessage.emit(submit_long_msg, logging.WARNING)

            # Updating the loading bar (if any)
            percent = int((float(pass_count_progress) / pass_count_progress_all) * 100)
            self.updateLoadingBarFormat.emit(percent, submit_msg + ' - %p%')

            pass_count = len(passes_for_envs_to_render.keys())

            # Formulate job name for this Environment, and all included passes
            job_name = self.get_environment_job_name(
                env_item,
                global_job_identifier=self.get_global_job_identifier(),
                pass_count=pass_count)

            # Use pass note if rendering only one pass of environment
            notes = list()
            if pass_count == 1:
                _pass_env_item = passes_for_envs_to_render.keys()[0]
                note = _pass_env_item.get_note_override_submission()
                if not note:
                    note = _pass_env_item.get_note_override() or str()
                if note:
                    notes.append(note)
            # Add shot note
            shot_note = env_item.get_note_override_submission() or env_item.get_note_override() or str()
            if shot_note and shot_note not in notes:
                notes.append(shot_note)
            # Add global note
            global_note = self.get_global_submit_description()
            if global_note and global_note not in notes:
                notes.append(global_note)
            notes = '\n'.join(notes)

            # Check if target environment item can reuse an existing snapshot
            # or not by looking in hash data dict.
            snapshot, pass_for_env_hash_data = self.get_snapshot_from_hash_data(
                env_item, # the environment item to get hash data for
                passes_for_envs_to_render.keys(), # the passes to consider to get hash data for environment
                envs_hashes_of_pass_versions) or None  # this environments passes hash data

            # Render all the passes together in one job
            oz_area = env_item.get_oz_area()
            try:
                success, collected_details_dict = self.render_passes_for_environment(
                    env_item,
                    oz_area=oz_area,
                    pass_env_items=passes_for_envs_to_render.keys(),
                    snapshot=snapshot,
                    job_name=job_name,
                    global_job_identifier=self.get_global_job_identifier(),
                    interactive=interactive,
                    local=False,
                    current_frame_only=current_frame_only,
                    launch_paused=self._launch_paused,
                    launch_zero_tier=self._launch_zero_tier,
                    session_path=self._autosave_session_path,
                    note=notes,
                    update_environment=False)
            except Exception:
                msg = 'Failed to submit environment: "{}". '.format(env_item.get_identifier())
                msg += 'Full exception: "{}"'.format(traceback.format_exc())
                self.logMessage.emit(msg, logging.CRITICAL)
                success = False
                collected_details_dict = dict()

            # NOTE: Revert any previously applied render overrides
            if self._apply_render_overrides:
                # Revert the render overrides which were previously successfully applied to each pass
                for pass_env_item in applied_overrides_for_pass.keys():
                    _applied_overrides = applied_overrides_for_pass.get(pass_env_item)
                    if _applied_overrides:
                        pass_env_item.revert_render_overrides(
                            override_id_to_items=_applied_overrides)
                # Revert the render override items to previous state
                self._revert_render_override_items(
                    env_item,
                    pass_env_items=passes_for_envs_to_render.keys(),
                    render_overrides_cache=render_overrides_cache)

            environment_submit_time = int(time.time() - environment_start_time)
            msg = 'Environment took {} seconds to submit'.format(environment_submit_time)
            self.logMessage.emit(msg, logging.WARNING)

            # Update painting of red outline for each pass when submitting from UI
            if not is_dispatching:
                self._paint_submission_progress(
                    pass_for_env_items,
                    pass_for_env_items_indices)

            if success:
                _snapshot_hyref = env_item.get_snapshot_hyref()
                # NOTE: Fallback for old way snapshot hyref was stored in collected details
                if not _snapshot_hyref:
                    _snapshot_hyref = collected_details_dict.get('project_snapshot_hyref')
                self._project_snapshot_hyref = _snapshot_hyref
                if self._project_snapshot_hyref:
                    _session_data = copy.deepcopy(session_data)
                    _session_data['project'] = self._project_snapshot_hyref
                    self.session_save_resource_for_project(
                        self._project_snapshot_hyref,
                        session_data=_session_data)
                job_count += 1
                shots_to_render.add(str(oz_area))
                renderable_pass_count += len(passes_for_envs_to_render.keys())

                # Add the environments hash data for pass versions to tracking list
                if _snapshot_hyref:
                    data = dict()
                    data['environment'] = oz_area
                    data['hash_data'] = pass_for_env_hash_data
                    data['snapshot'] = _snapshot_hyref
                    envs_hashes_of_pass_versions.append(data)
                    msg = 'Caching current environment hash data: "{}"'.format(data)
                    self.logMessage.emit(msg, logging.CRITICAL)

                ##############################################################

                # Get Plow Job id from first pass of submitted environment.
                # NOTE: All passes have same Plow Job id by design currently.
                plow_job_id = passes_for_envs_to_render.keys()[0].get_plow_job_id_last()
                if not plow_job_id:
                    # Otherwise extract Plow Job id from collected details
                    plow_job_id = collected_details_dict.get('plow_job_id')

                if plow_job_id:
                    plow_layer_ids = collected_details_dict.get('plow_layer_ids', dict())
                    # plow_task_ids = collected_details_dict.get('plow_task_ids', dict())
                    for pass_env_item in passes_for_envs_to_render.keys():
                        pass_env_item.set_plow_job_id_last(plow_job_id)
                        identity_id = pass_env_item.get_identity_id()

                        if identity_id not in self._last_submitted_uuid_to_plow_ids.keys():
                            self._last_submitted_uuid_to_plow_ids[identity_id] = dict()
                        self._last_submitted_uuid_to_plow_ids[identity_id]['job_id'] = plow_job_id

                        time_stamp = utils.get_time_stamp(include_time_of_day=True)
                        self._last_submitted_uuid_to_plow_ids[identity_id]['time'] = time_stamp

                        _render_item = pass_env_item.get_source_render_item()
                        _identifier = _render_item.get_item_full_name()

                        _plow_layer_id = plow_layer_ids.get(_identifier)
                        if _plow_layer_id:
                            pass_env_item.set_plow_layer_id_last(_plow_layer_id)
                            self._last_submitted_uuid_to_plow_ids[identity_id]['layer_id'] = _plow_layer_id

                    # If Job already PAUSED and launch expire time available, set it now
                    launch_paused_expires = self.get_launch_paused_expires()
                    if launch_paused_expires:
                        _job = self._scheduler_operations.get_job(plow_job_id)
                        if _job and _job.paused:
                            msg = 'Setting job: "{}". '.format(plow_job_id)
                            msg += 'Launch expire time to: "{}"'.format(launch_paused_expires)
                            self.logMessage.emit(msg, logging.WARNING)
                            # NOTE: Job was already paused when launching Kenobi graph.
                            # In order for the PAUSED clamp to have the correct origValue, when
                            # expire time runs out, the Job needs to be unpaused, then paused again.
                            # NOTE: The origValue of PAUSED clamp is not currently settable by design.
                            _job.pause(False)
                            _job.pause(True, expires=launch_paused_expires)

                if self._last_submitted_uuid_to_plow_ids:
                    self._update_uuid_to_plow_ids_in_junkbox(global_jbx_bucket)

                if self._is_submitting_in_dispatcher_task and plow_job_id:
                    self.add_launched_plow_ids_to_dispatcher_job(plow_job_id)

                # Optionally WAIT on explicit Plow Job and Task Idss
                # if env_item.get_all_wait_on_plow_ids():
                self.apply_wait_on_plow_ids(passes_for_envs_to_render.keys())

                # Optionally apply WAIT on other multi shot items
                if self._apply_dependencies and self._last_submitted_uuid_to_plow_ids:
                    self.apply_wait_to_all_render_passes(
                        env_item, # environment item to apply WAIT On, and to all child pass for env items
                        passes_for_envs_to_render.keys(), # current pass for env items just submitted
                        global_jbx_bucket=global_jbx_bucket)
                # Unpause the entire environment Job, if have no pass to Plow id depedencies
                elif plow_job_id and not self._launch_paused:
                    self._scheduler_operations.job_pause(
                        plow_job_id,
                        pause=False,
                        name=env_item.get_environment_name_nice())

                ##############################################################
                # Collect Multi Shot email details
                # TODO: This can be improved and made into a discrete method...

                env_data = collections.OrderedDict()
                env_data['environment'] = oz_area
                env_data['passes'] = collections.OrderedDict()
                env_data['attrs'] = self.get_email_environment_details(env_item)
                env_data['snapshot_project'] = _snapshot_hyref
                email_details['envs_data'].append(env_data)
                # Index to update with additional submission info
                index = len(email_details['envs_data']) - 1

                for pass_env_item in sorted(passes_for_envs_to_render.keys()):
                    render_item = pass_env_item.get_source_render_item()
                    # Apply previous state to render node
                    previous_state_dict = passes_for_envs_to_render[pass_env_item]
                    if previous_state_dict:
                        render_node_was_enabled = previous_state_dict.get('render_node_was_enabled')
                        if isinstance(render_node_was_enabled, bool):
                            render_item.set_enabled(render_node_was_enabled)
                    # Collect each environment and pass email details
                    attr_list = self.get_email_pass_for_env_details(pass_env_item)
                    if not attr_list:
                        continue
                    item_full_name = render_item.get_item_full_name()
                    if item_full_name not in email_details['envs_data'][index]['passes'].keys():
                        email_details['envs_data'][index]['passes'][item_full_name] = dict()
                    email_details['envs_data'][index]['passes'][item_full_name]['attrs'] = attr_list

                # Add additional per pass details such as cg hyref to email details
                for category_label, attr_name in [
                        # ('Plow Task Ids', 'plow_task_ids'),
                        ('Plow Layer Id', 'plow_layer_ids'),
                        ('Cg Hyref', 'cg_hyrefs'),
                        ('Cg Deep Hyref', 'cg_deep_hyrefs')]:
                    info_for_item_dict = collected_details_dict.get(attr_name, dict())
                    for full_name in info_for_item_dict.keys():
                        detail_item = (category_label, info_for_item_dict[full_name])
                        if full_name in email_details['envs_data'][index]['passes']:
                            email_details['envs_data'][index]['passes'][full_name]['attrs'].append(detail_item)

                # Add additional global email details
                time_stamp = utils.get_time_stamp(include_time_of_day=True)
                detail_item = ('Completed Submission Time', str(time_stamp))
                email_details['envs_data'][index]['attrs'].insert(0, detail_item)
                # detail_item = ('Time Taken To Submit (Seconds)', environment_submit_time)
                detail_item = (
                    'Total Time To Generate Job (Excludes Project Load)',
                    str(datetime.timedelta(seconds=environment_submit_time)))
                email_details['envs_data'][index]['attrs'].insert(0, detail_item)
                detail_item = ('Plow Job Id', str(plow_job_id))
                email_details['envs_data'][index]['attrs'].insert(0, detail_item)
                label_str = '{} Snapshot Hyref'.format(self.HOST_APP.title())
                detail_item = (label_str, str(self._project_snapshot_hyref))
                email_details['envs_data'][index]['attrs'].insert(0, detail_item)
            else:
                self._project_snapshot_hyref = None

            # Run any post render / tear down for Environment (if any)
            post_env_render_success, msg = env_item.post_environment_render()

            self.processingPassForEnv.emit(
                env_qmodelindex,
                False,
                str())

        shot_count = len(shots_to_render)

        ######################################################################
        # Any final Job configuration, then submit

        msg = 'Submitting constructed job...'
        self.logMessage.emit(msg, logging.INFO)

        render_time_end = int(time.time() - render_start_time)
        msg = 'Overall render submit complete in {} seconds'.format(render_time_end)
        self.logMessage.emit(msg, logging.INFO)

        # Add instrumentation for Job submission.
        msg = 'Submitted Renders'
        utils.log_with_winstrumentation(
            self.TOOL_NAME,
            function_key=msg,
            host_app=self.HOST_APP)

        ######################################################################
        # Optionally send an email from user who submitted and list of recipients

        # Cache the email details if being routed into dispatcher system
        self._email_details_envs_data = email_details['envs_data']

        if self._send_summary_email_on_submit:
            msg = 'Sending overview of operation email'
            self.logMessage.emit(msg, logging.INFO)

            email_time_start = time.time()

            email_details['globals'] = self.get_email_global_details() or list()
            time_stamp = utils.get_time_stamp(include_time_of_day=True)
            detail_item = ('Completed All Submissions Time ', str(time_stamp))
            email_details['globals'].append(detail_item)
            # detail_item = ('Total Submission Time (sec)', str(render_time_end))
            # email_details['globals'].append(detail_item)
            detail_item = (
                'Total Submission Time',
                str(datetime.timedelta(seconds=render_time_end)))
            email_details['globals'].append(detail_item)

            main_title = 'Submitted {} {} Render '.format(
                renderable_pass_count,
                self.HOST_APP.title())
            main_title += 'Passes For {} Environment/s. '.format(shot_count)
            summary_title = '{} - Global Options'.format(self.TOOL_NAME)

            html = utils.generate_html(
                self.TOOL_NAME,
                self.get_multi_shot_render_submitter_version(),
                main_title,
                summary_title,
                '{}_multi_shot_submission_v2'.format(self.HOST_APP.lower()),
                attributes=email_details)
            if html:
                tool_name_camel_case = self.TOOL_NAME.title().replace(' ', str())
                subject = '[ToolTracking][{}] '.format(tool_name_camel_case)
                subject += str(main_title)
                cc = self.get_email_additional_users() or list()
                cc.extend(constants.ADMIN_USERS)
                utils.send_email(cc, subject, html)

            email_end_time = int(time.time() - email_time_start)
            msg = 'Formulated and sent email'
            self.logMessage.emit(
                TIME_TAKEN_MSG.format(msg, email_end_time),
                logging.WARNING)

        ######################################################################

        if not self._is_submitting_in_dispatcher_task:
            if cg_ver_cache:
                self._revert_cg_version_overrides(cg_ver_cache)
            if wait_on_cache:
                self._revert_wait_on(wait_on_cache)
            if plow_ids_cache:
                self._revert_plow_ids(plow_ids_cache, skip_if_already_set=True)

        # Run any post render operation on model data, or other object cleanup
        post_render_success, post_render_msg = self.post_render()
        if not post_render_success:
            msg = 'Post render failed!\n'
            msg += str(post_render_msg)
            self.logMessage.emit(msg, logging.CRITICAL)
            # NOTE: Carry on anyway, since render did actually submit

        self.renderSubmitFinished.emit()

        return True, False, msg


    def _multi_shot_dispatch(self, pass_for_env_items=None):
        '''
        Dispatch all or the specific pass for env items by building a Plow job
        which contains a Task for each Environment. Each task will load up a host
        app and resolve all core and render overrides , and do a snapshot etc.
        NOTE: This is currently only intended to be called via multi_shot_render method.

        Args:
            pass_for_env_items (list): optionally render only render the specified RenderPassForEnv items

        Returns:
            success, cancelled, msg (tuple):
        '''
        # Update cached environment indices, the dispatcher uses env index to target items by identifier string
        self._update_environments_indices()

        # Can now revert is being dispatched indicator for all items.
        # Note: If was being dispatched this is now included in session data.
        for pass_env_item in self.get_pass_for_env_items():
            pass_env_item.set_is_being_dispatched(False)

        from srnd_multi_shot_render_submitter.dispatcher.abstract_multi_shot_dispatcher import \
            AbstractMultiShotDispatcher
        # Get the dispatcher plugin required for host app (if any)
        dispatcher = AbstractMultiShotDispatcher.get_dispatcher_instance_for_host_app(
            self.HOST_APP,
            debug_mode=self._debug_mode)

        if not dispatcher:
            msg = 'No Multi Shot Dispatcher Available For Requested '
            msg += 'Host App: "{}". '.format(self.HOST_APP)
            msg += 'You Could Try To Turn Off Dispatch On Plow For Now!'
            self.logMessage.emit(msg, logging.WARNING)
            return False, False, msg

        # Filter dispatch to all environments that have passes queued and enabled for output.
        if not pass_for_env_items:
            environments = self.get_environments(
                with_renderable_passes=True,
                include_index=False, # same environment should be dispatched in the same proc
                include_job_identifier=False)
            dispatcher.set_environments_override(environments)

        dispatcher.set_global_job_identifier(self.get_global_job_identifier())

        # Set project file path
        project_file_path, msg = utils.get_hyref_default_location(
            self._source_project) or self._source_project
        dispatcher.set_project(project_file_path)

        # Let the dispatcher know about all the required Environment/s and passes to submit
        dispatcher.set_session_location(self._autosave_session_path)

        # Collect a subset of renderables from selection to pass to dispatcher
        environments = set()
        items_to_set_dispatch_job_id = set()
        if pass_for_env_items:
            pass_for_env_identifiers = set()
            # Traverse over all environments looking for matching pass for env items
            environments_counter = dict()
            for env_item in self.get_environment_items():
                env = env_item.get_oz_area()
                if env not in environments_counter.keys():
                    environments_counter[env] = 0
                environments_counter[env] += 1
                for pass_env_item in env_item.get_pass_for_env_items():
                    if not pass_env_item in pass_for_env_items:
                        continue
                    if pass_env_item.get_active():
                        environments.add(env_item.get_oz_area()) # submit all environments together in same proc
                        pass_for_env_identifiers.add(pass_env_item.get_identifier(
                            nice_env_name=True,
                            prefer_jid=False)) # prefer to use env index, to insure is unique target
                        items_to_set_dispatch_job_id.add(env_item)
                        items_to_set_dispatch_job_id.add(pass_env_item)

            msg = 'Collected Pass For Env Identifiers To '
            msg += 'Render: "{}"'.format(pass_for_env_identifiers)
            self.logMessage.emit(msg, logging.CRITICAL)
            dispatcher.set_pass_for_env_identifiers_override(list(pass_for_env_identifiers))
        else:
            environments = set(self.get_environments(with_renderable_passes=True) or list())
            environment_items = self.get_environment_items(with_renderable_passes=True) or list()
            for env_item in environment_items:
                items_to_set_dispatch_job_id.add(env_item)
                for pass_env_item in env_item.get_pass_for_env_items(active_only=True):
                    items_to_set_dispatch_job_id.add(pass_env_item)

        # The environments of render pass for env to dispatch
        if environments:
            msg = 'Collected Environments To Dispatch: "{}"'.format(environments)
            self.logMessage.emit(msg, logging.CRITICAL)
            dispatcher.set_environments_override(list(environments))

        # Now resolve the project from session data, and Environments
        # to render after setting the renderable identifiers.
        dispatcher.validate_and_resolve_targets_in_session_data()

        note_global = self.get_global_submit_description()
        dispatcher.set_global_note_override(note_global)

        msg = 'Dispatch Deferred Is Enabled. '
        msg += 'All Environment/s Will Be Submitted In Separate '
        msg += 'Tasks On Plow.'
        self.logMessage.emit(msg, logging.WARNING)

        email_global_details = self.get_email_global_details() or list()
        dispatcher.set_email_global_details(email_global_details)

        dispatcher.set_multi_shot_render_submitter_version(
            self.get_multi_shot_render_submitter_version())
        dispatcher.set_host_app_version(self.get_host_app_version())
        dispatcher.set_auto_refresh_from_shotgun(
            self._auto_refresh_from_shotgun)

        # Build and submit the Kenobi nodes required for dispatcher job
        success, result_msg = dispatcher.create_dispatcher_job(submit=True)

        dispatcher_plow_job_id = None
        if success:
            dispatcher_plow_job_id = dispatcher.get_plow_job_id_last_dispatched()

        msg = 'Create Dispatch Job Result: "{}". '.format(success)
        msg += 'Message: "{}". '.format(result_msg)
        msg += 'Plow Job Id: "{}"'.format(dispatcher_plow_job_id)
        self.logMessage.emit(msg, logging.DEBUG)

        # Cache the dispatcher Plow Job id on each target environment item
        if items_to_set_dispatch_job_id and dispatcher_plow_job_id:
            for item in items_to_set_dispatch_job_id:
                item.set_dispatcher_plow_job_id(dispatcher_plow_job_id)

        self.renderSubmitFinished.emit()
        return success, False, msg


    def get_snapshot_from_hash_data(
            self,
            environment_item,
            pass_for_env_items,
            _envs_hashes_of_pass_versions):
        '''
        Check if target environment item can reuse an existing snapshot or not
        by comparing pass for env hash data to all existing data and finding match.

        Args:
            environment_item (EnvironmentItem): the environment item to get hash data for
            pass_for_env_items (list): the passes to consider to get hash data for environment
            _envs_hashes_of_pass_versions (list): all hash data for all environment submissions

        Returns:
            snapshot, pass_for_env_hash_data (tuple): location to project snapshot that can be reused (if any)
        '''
        environment = environment_item.get_oz_area()
        # Collect hash data for environment and included passes to render
        pass_for_env_hash_data = environment_item.get_hash_pass_versions(
            pass_env_items=pass_for_env_items)
        msg = 'Current Environment Hash Data: "{}"'.format(pass_for_env_hash_data)
        self.logMessage.emit(msg, logging.CRITICAL)
        # Check if hashed environment data matches another previous Job submission.
        # If so can reuse the scene snapshot to ensure it was generated at same time.
        snapshot = None
        for data in _envs_hashes_of_pass_versions:
            _environment = data.get('environment')
            if _environment != environment:
                continue
            _previous_hash_data = data.get('hash_data')
            match_count = 0
            for _pass_env_item in pass_for_env_items:
                _render_item = _pass_env_item.get_source_render_item()
                _item_full_name = _render_item.get_item_full_name()
                _hash_data = _previous_hash_data.get(_item_full_name)
                if _hash_data and _hash_data == pass_for_env_hash_data.get(_item_full_name):
                    match_count += 1
            if match_count == len(pass_for_env_items):
                snapshot = data.get('snapshot')
                break
        if snapshot:
            msg = 'Reusing Snapshot "{}" For Env "{}", '.format(snapshot, environment)
            msg += 'From Previous Same Environment Submission. '
            msg += 'As All Pass MSRS Hash Data Matches!'
            self.logMessage.emit(msg, logging.CRITICAL)
        return snapshot, pass_for_env_hash_data


    def render_passes_for_environment(self, env_item, *args, **kwargs):
        '''
        A wrapper around Environment render passes for env method.
        NOTE: Allows host app specific Multi Shot implementations to pass additional arguments.

        Args:
            env_item (EnvironmentItem):
        '''
        return env_item.render_passes_for_environment(*args, **kwargs)


    def check_can_render_interactive(self, frame_count=1, show_dialog=True):
        '''
        Check whether it is okay to proceed with interactive render.
        Requires reimplementation for particular host app.

        Args:
            frame_count (int):
            show_dialog (bool): whether to show popup dialog with warnings.

        Returns:
            can_render_interactive, msg (tuple): by default returns True and empy message
        '''
        return True, str()


    def pre_render(self):
        '''
        Optionally implement any pre render operations, to run just
        before rendering from entire data model.

        Returns:
            success, msg (bool):
        '''
        start_time = time.time()

        # Clear tracking members (will be updated during submission)
        self._project_snapshot_hyref = None
        self._email_details_envs_data = list()
        self._last_submitted_uuid_to_plow_ids = dict()
        self._last_submitted_pass_wait_on_applied = dict()
        # Keep this cached at render startup, and update on render submit
        # self._source_project = None
        self._autosave_session_path = None
        self._request_interrupt = False
        self._is_rendering = True

        # Validate all render override are valid
        self.validate_all_render_overrides()

        time_end = int(time.time() - start_time)
        msg = 'Completed Pre Render In {} Seconds'.format(time_end)
        self.logMessage.emit(msg, logging.DEBUG)

        return True, msg


    def post_render(self):
        '''
        Optionally implement any post render operations, to run just
        after rendering from entire data model.

        Returns:
            success, msg (bool):
        '''
        self._is_rendering = False

        start_time = time.time()

        msg = 'Post Render Has No Implemented Operations To Perform'
        self.logMessage.emit(msg, logging.WARNING)

        time_end = int(time.time() - start_time)
        msg = 'Completed Post Render In {} Seconds'.format(time_end)
        self.logMessage.emit(msg, logging.DEBUG)

        return True, msg


    def add_launched_plow_ids_to_dispatcher_job(self, render_plow_job_id):
        '''
        Add the generated Plow job id to the dispatcher Job attribute.

        Args:
            render_plow_job_id (str):

        Returns:
            success (bool):
        '''
        msg = 'Adding Launched Plow Ids To Dispatcher Job: "{}"'.format(render_plow_job_id)
        self.logMessage.emit(msg, logging.INFO)
        if not render_plow_job_id:
            return False
        dispatcher_plow_job_id = os.getenv('PLOW_JOB_ID')
        if not dispatcher_plow_job_id:
            msg = 'No "PLOW_JOB_ID" Environment Variable In Current Context!'
            self.logMessage.emit(msg, logging.WARNING)
            return False
        job = self._scheduler_operations.get_job(dispatcher_plow_job_id)
        if not job:
            msg = 'Failed To Get Job From Plow Job Id: "{}"'.format(dispatcher_plow_job_id)
            self.logMessage.emit(msg, logging.WARNING)
            return False
        attrs = job.attrs
        dispatched_plow_job_ids = attrs.get('dispatched_plow_job_ids', str())
        dispatched_plow_job_ids = set(dispatched_plow_job_ids.split(','))
        dispatched_plow_job_ids.add(render_plow_job_id)
        dispatched_plow_job_ids = list(dispatched_plow_job_ids)
        additional_attrs = dict()
        additional_attrs['dispatched_plow_job_ids'] = ','.join(dispatched_plow_job_ids)
        job.update_attrs(additional_attrs)
        return True


    ##########################################################################
    # Caching and reverting overrides during render submission


    def _cache_cg_version_overrides(self, pass_for_env_items=None):
        '''
        Cache all the current cg pass overrides of current model data object values.

        Args:
            pass_for_env_items (list):

        Returns:
            cg_version_overrides_cache (dict):
        '''
        pass_for_env_items = pass_for_env_items or self.get_pass_for_env_items()
        cg_version_overrides_cache = dict()
        for pass_env_item in pass_for_env_items:
            identity_id = pass_env_item.get_identity_id()
            version_override = pass_env_item.get_version_override()
            cg_version_overrides_cache[identity_id] = version_override
        if self._debug_mode and cg_version_overrides_cache:
            msg = 'Cg Version Overrides Cache: "{}"'.format(cg_version_overrides_cache)
            self.logMessage.emit(msg, logging.WARNING)
        return cg_version_overrides_cache


    def _revert_cg_version_overrides(
            self,
            cg_version_overrides_cache,
            pass_for_env_items=None):
        '''
        Revert pass for env items to previous cg version override state

        Args:
            cg_version_overrides_cache (dict): mapping of UUID to previous version state
            pass_for_env_items (list):
        '''
        if not cg_version_overrides_cache:
            cg_version_overrides_cache = dict()
        pass_for_env_items = pass_for_env_items or self.get_pass_for_env_items()
        for pass_env_item in pass_for_env_items:
            identity_id = pass_env_item.get_identity_id()
            if not cg_version_overrides_cache.has_key(identity_id):
                continue
            identifier = pass_env_item.get_identifier(nice_env_name=True)
            version_override = cg_version_overrides_cache.get(identity_id)
            version_override = version_override or None
            if self._debug_mode:
                msg = 'Reverting Cg Version Override For Identifier: "{}". '.format(identifier)
                msg += 'MSRS UUID: "{}". '.format(identity_id)
                msg += 'Reverting To: "{}"'.format(version_override)
                self.logMessage.emit(msg, logging.WARNING)
            pass_env_item.set_version_override(version_override)


    def _cache_wait_on(self, target_pass_for_env_items=None):
        '''
        Cache all the MSRS WAIT on states to list of mapping of identity id to WAIT on.
        Also bake and clear WAIT on states on to items ready for submission, depending
        on target items.

        Args:
            target_pass_for_env_items (list):

        Returns:
            wait_on_cache (list):
        '''
        scheduler_operations = self.get_scheduler_operations()

        wait_on_cache = dict()
        # Cache and resolve all pass for env WAIT on...
        for pass_env_item in self.get_pass_for_env_items():
            environment_item = pass_env_item.get_environment_item()
            identity_id_env = environment_item.get_identity_id()
            # Force any explicit Plow ids are available, otherwise removed from session.
            current_wait_on_plow_ids = pass_env_item.get_wait_on_plow_ids()
            validated_wait_on_plow_ids = scheduler_operations.validate_plow_ids(
                current_wait_on_plow_ids)
            pass_env_item.set_wait_on_plow_ids(validated_wait_on_plow_ids)
            # Validate and store subset of WAIT on (to available pass items for selection)
            identity_id = pass_env_item.get_identity_id()
            wait_on = pass_env_item.get_wait_on()
            # Remove invalid ids that shouldn't be set anyway
            if identity_id in wait_on:
                wait_on.remove(identity_id)
            if identity_id_env in wait_on:
                wait_on.remove(identity_id_env)
            # Cache the WAIT on for pass for env
            wait_on_cache[identity_id] = wait_on
            # Check if this item is in target pass for env items.
            # NOTE: Its not currently possible to not have any target items
            # with current submitter design at this point...
            is_target = True
            if target_pass_for_env_items:
                is_target = pass_env_item in target_pass_for_env_items
            # If items not active then clear WAIT on
            if not pass_env_item.get_active() or not is_target:
                wait_on = list()
            # If item active then validate source and target WAIT on
            else:
                wait_on = self.validate_wait_on_multi_shot_uuids(
                    wait_on,
                    pass_for_env_items=target_pass_for_env_items,
                    source_uuid=pass_env_item.get_identity_id())
            pass_env_item.set_wait_on(wait_on)
            # Also validate and cache the WAIT on for environment
            if identity_id_env not in wait_on_cache.keys():
                wait_on_env = environment_item.get_wait_on()
                wait_on_cache[identity_id_env] = wait_on_env
                # Remove invalid ids that shouldn't be set anyway
                if identity_id_env in wait_on_env:
                    wait_on_env.remove(identity_id_env)
                wait_on_env = self.validate_wait_on_multi_shot_uuids(
                    wait_on_env,
                    pass_for_env_items=target_pass_for_env_items,
                    source_uuid=environment_item.get_identity_id())
                environment_item.set_wait_on(wait_on_env)
        if self._debug_mode:
            msg = 'WAIT On Cache: "{}"'.format(wait_on_cache)
            self.logMessage.emit(msg, logging.WARNING)
        return wait_on_cache


    def _revert_wait_on(
            self,
            wait_on_cache,
            pass_for_env_items=None):
        '''
        Revert WAIT on for pass for env items, using an UUID to WAIT on list mapping.

        Args:
            wait_on_cache (dict): mapping of UUIDs to previous wait on list
            pass_for_env_items (list):
        '''
        if not wait_on_cache:
            wait_on_cache = dict()
        pass_for_env_items = pass_for_env_items or self.get_pass_for_env_items()
        if not all([wait_on_cache, pass_for_env_items]):
            return
        environment_id_reverted = list()
        for pass_env_item in pass_for_env_items:
            identifier = pass_env_item.get_identifier(nice_env_name=True)
            identity_id = pass_env_item.get_identity_id()
            wait_on = wait_on_cache.get(identity_id)
            if wait_on != None:
                wait_on = wait_on or list()
                if self._debug_mode:
                    msg = 'Reverting WAIT On List For Pass Identifier: "{}". '.format(identifier)
                    msg += 'MSRS UUID: "{}". '.format(identity_id)
                    msg += 'Reverting To: "{}"'.format(wait_on)
                    self.logMessage.emit(msg, logging.WARNING)
                pass_env_item.set_wait_on(wait_on)

            # Also revert the WAIT on for environment
            environment_item = pass_env_item.get_environment_item()
            identity_id_env = environment_item.get_identity_id()
            if identity_id_env not in wait_on_cache.keys():
                continue
            if identity_id_env in environment_id_reverted:
                continue
            identifier_env = environment_item.get_environment_name_nice()
            wait_on_env = wait_on_cache.get(identity_id_env)
            if wait_on_env != None:
                wait_on_env = wait_on_env or list()
                if self._debug_mode:
                    msg = 'Reverting WAIT On List For Env Identifier: "{}". '.format(identifier_env)
                    msg += 'MSRS UUID: "{}". '.format(identity_id_env)
                    msg += 'Reverting To: "{}"'.format(wait_on_env)
                    self.logMessage.emit(msg, logging.WARNING)
                environment_item.set_wait_on(wait_on_env)
                environment_id_reverted.append(identity_id_env)


    def _cache_plow_ids(self, pass_for_env_items=None):
        '''
        Cache Plow ids to dictionary and clear current model data object values.

        Args:
            pass_for_env_items (list):

        Returns:
            plow_ids_cache (dict):
        '''
        if not pass_for_env_items:
            pass_for_env_items = list()

        pass_for_env_items = pass_for_env_items or self.get_pass_for_env_items()

        plow_ids_cache = dict()
        # Clear any only Plow Job and Task ids, and set is dispatching status for all
        for pass_env_item in pass_for_env_items:
            identity_id = pass_env_item.get_identity_id()
            # Clear item is being dispatched status
            pass_env_item.set_is_being_dispatched(False)
            # Cache the previous Plow ids and cache them
            job_id = pass_env_item.get_plow_job_id_last()
            layer_id = pass_env_item.get_plow_layer_id_last()
            task_ids = pass_env_item.get_plow_task_ids_last()
            if any([job_id, layer_id, task_ids]):
                plow_ids_cache[identity_id] = dict()
                if job_id:
                    plow_ids_cache[identity_id]['job_id'] = job_id
                if layer_id:
                    plow_ids_cache[identity_id]['layer_id'] = layer_id
                if task_ids:
                    plow_ids_cache[identity_id]['task_ids'] = task_ids
            # Clear the Plow ids
            pass_env_item.set_plow_job_id_last(None)
            pass_env_item.set_plow_layer_id_last(None)
            pass_env_item.set_plow_task_ids_last(None)

        if self._debug_mode and plow_ids_cache:
            msg = 'Plow Ids Cache: "{}"'.format(plow_ids_cache)
            self.logMessage.emit(msg, logging.WARNING)

        return plow_ids_cache


    def _revert_plow_ids(
            self,
            plow_ids_cache,
            pass_for_env_items=None,
            skip_if_already_set=False):
        '''
        Revert Plow Job and Task ids for pass for env items, using an UUID to Plow ids mapping.

        Args:
            plow_ids_cache (dict): mapping of UUID to previous Plow ids info
            pass_for_env_items (list):
            skip_if_already_set (bool): optionally only apply Plow cached ids, if the pass for env
                item doesn't already have an existing value.
        '''
        if not plow_ids_cache:
            plow_ids_cache = dict()
        pass_for_env_items = pass_for_env_items or self.get_pass_for_env_items()
        for pass_env_item in pass_for_env_items:
            identity_id = pass_env_item.get_identity_id()
            id_info = plow_ids_cache.get(identity_id)
            if not id_info:
                continue
            job_id = id_info.get('job_id')
            layer_id = id_info.get('layer_id')
            task_ids = id_info.get('task_ids')
            if skip_if_already_set:
                if not pass_env_item.get_plow_job_id_last():
                    pass_env_item.set_plow_job_id_last(job_id)
                if not pass_env_item.get_plow_layer_id_last():
                    pass_env_item.set_plow_layer_id_last(layer_id)
                if not pass_env_item.get_plow_task_ids_last():
                    pass_env_item.set_plow_task_ids_last(task_ids)
            else:
                pass_env_item.set_plow_job_id_last(job_id)
                pass_env_item.set_plow_layer_id_last(layer_id)
                pass_env_item.set_plow_task_ids_last(task_ids)


    def _cache_render_override_items(
            self,
            env_item,
            pass_env_items=None):
        '''
        Get cached mapping of render overrides for environment and passes there of.

        Args:
            env_item (EnvironmentItem):
            pass_env_items (list):

        Returns:
            render_overrides_cache (dict):
        '''
        pass_env_items = pass_env_items or self.get_pass_for_env_items()
        render_overrides_cache = dict()
        env_identifier = env_item.get_identifier()
        env_render_overrides = env_item.get_render_overrides_items()
        if env_render_overrides:
            env_render_overrides = copy.deepcopy(env_render_overrides)
        render_overrides_cache[env_identifier] = env_render_overrides
        for pass_env_item in pass_env_items:
            pass_identifier = pass_env_item.get_identifier()
            pass_render_overrides = pass_env_item.get_render_overrides_items(
                include_from_env=False)
            if pass_render_overrides:
                pass_render_overrides = copy.deepcopy(pass_render_overrides)
            render_overrides_cache[pass_identifier] = pass_render_overrides
        if self._debug_mode and render_overrides_cache:
            msg = 'Render Overrides Cache: "{}". '.format(render_overrides_cache)
            msg += 'Environment: "{}"'.format(env_identifier)
            self.logMessage.emit(msg, logging.WARNING)
        return render_overrides_cache


    def _revert_render_override_items(
            self,
            env_item,
            pass_env_items=None,
            render_overrides_cache=None):
        '''
        Revert render overrides for environment and passes there of from cached mapping.

        Args:
            env_item (EnvironmentItem):
            pass_env_items (list):
            render_overrides_cache (dict):
        '''
        if not render_overrides_cache:
            render_overrides_cache = dict()
        pass_env_items = pass_env_items or self.get_pass_for_env_items()
        env_identifier = env_item.get_identifier()
        env_render_overrides = render_overrides_cache.get(env_identifier, dict())
        env_item.set_render_overrides_items(env_render_overrides)
        for pass_env_item in pass_env_items:
            pass_identifier = pass_env_item.get_identifier()
            pass_render_overrides = render_overrides_cache.get(pass_identifier, dict())
            pass_env_item.set_render_overrides_items(pass_render_overrides)


    ##########################################################################
    # Emitting signals for associated view (if any)


    def _paint_submission_progress(
            self,
            pass_for_env_items,
            pass_for_env_items_indices):
        '''
        Paint render hints when submitting from UI.

        Args:
            pass_for_env_items (list): list of pass for env items
            pass_for_env_items_indices (list): list of QModelIndices
        '''
        for i, pass_qmodelindex in enumerate(pass_for_env_items_indices):
            if not pass_qmodelindex.isValid():
                continue
            pass_env_item = pass_qmodelindex.internalPointer()
            if pass_for_env_items and pass_env_item not in pass_for_env_items:
                continue
            if not pass_env_item.get_active():
                continue
            self.processingPassForEnv.emit(
                pass_qmodelindex,
                False,
                str())


    ##########################################################################
    # WAIT on. Dependencies setup


    def get_item_wait_on_target_indices(self, qmodelindex):
        '''
        Get all the target indices for all the WAIT on of item.

        Args:
            qmodelindex (QModelIndex): the index to gather dependent QModelIndices for
        '''
        if not qmodelindex.isValid():
            return list()
        item = qmodelindex.internalPointer()
        if not item.get_wait_on():
            return list()
        column_count = self.columnCount(QModelIndex())
        columns = range(1, column_count, 1)
        wait_on_list = item.get_wait_on()
        qmodelindices = set()
        for env_qmodelindex in self.get_environment_items_indices():
            if not env_qmodelindex.isValid() or env_qmodelindex == qmodelindex:
                continue
            env_item = env_qmodelindex.internalPointer()
            found_match = env_item.get_identity_id() in wait_on_list
            if found_match:
                # msg = 'Env: "{}". '.format(env_item.get_environment_name_nice())
                # msg += 'Matches WAIT On: "{}"'.format(wait_on_list)
                # self.logMessage.emit(msg, logging.CRITICAL)
                qmodelindices.add(env_qmodelindex)
                #continue
            for c in columns:
                qmodelindex_column = env_qmodelindex.sibling(env_qmodelindex.row(), c)
                if not qmodelindex_column.isValid() or qmodelindex_column == qmodelindex:
                    continue
                pass_env_item = qmodelindex_column.internalPointer()
                found_match = pass_env_item.get_identity_id() in wait_on_list
                if found_match:
                    # msg = 'Pass For Env: "{}". '.format(pass_env_item.get_identifier())
                    # msg += 'Matches WAIT On: "{}"'.format(wait_on_list)
                    # self.logMessage.emit(msg, logging.CRITICAL)
                    qmodelindices.add(qmodelindex_column)
        return list(qmodelindices)


    def apply_wait_to_all_render_passes(
            self,
            target_env_item,
            current_pass_for_env_items,
            global_jbx_bucket=None):
        '''
        First gather Plow ids for relevant items, and then apply WAIT on to Plow
        Job/s and Task/s in relation to either all pass for env items being dispatched
        or all (active items only).

        Args:
            current_pass_for_env_items (list): current pass for env items just submitted
            is_being_dispatched (bool): whether the task currently running was submitted using
                dispatch on Plow option.

        Returns:
            applied_wait_count (int):
        '''
        if not current_pass_for_env_items or not target_env_item:
            return 0

        is_being_dispatched = self._is_submitting_in_dispatcher_task
        env_nice_name = target_env_item.get_environment_name_nice(prefer_jid=True)

        msg = 'Apply WAIT For Environment Item: "{}"'.format(env_nice_name)
        self.logMessage.emit(msg, logging.INFO)
        msg = 'Was Submitted In Dispatch Mode: "{}"'.format(is_being_dispatched)
        self.logMessage.emit(msg, logging.INFO)

        current_pass_for_env_items = current_pass_for_env_items or target_env_item.get_pass_for_env_items()
        wait_on_all_for_env = target_env_item.get_all_wait_on()

        # When running dispatched collect Plow ids from other WAIT on targets.
        # NOTE: These other targets are being dispatched in separate procs.
        ATTEMPT_COUNT = 100
        SLEEP_TIME = 10
        if is_being_dispatched:
            msg = 'Is Being Dispatched. So Will WAIT For Other Ids To Become Available...'
            self.logMessage.emit(msg, logging.CRITICAL)
            # Looking at every other possible pass for env item
            for environment_item in self.get_environment_items():
                identifier_env = environment_item.get_environment_name_nice()
                identity_id_env = environment_item.get_identity_id()

                # Don't need to WAIT on this environment being dispatched.
                # Or WAIT on another environment with same oz area, since all same environments
                # are currently dispatched together.
                if environment_item == target_env_item or \
                        environment_item.get_identifier() == target_env_item.get_identifier():
                    continue

                env_items_cancelled = self.get_environment_items_cancelled_for_dispatch()
                if environment_item in env_items_cancelled:
                    msg = 'Environment Has Been Cancelled For Dispatch: "{}". '.format(identifier_env)
                    msg += 'Skip WAIT For Dependent Plow Ids!'
                    self.logMessage.emit(msg, logging.WARNING)
                    continue

                for pass_env_item in environment_item.get_pass_for_env_items():
                    identifier = pass_env_item.get_identifier(nice_env_name=True)
                    # Only pass for env items being dispatched
                    if not pass_env_item.get_is_being_dispatched():
                        # msg = 'Is Being Dispatched. But Pass Not Is Dispatched: "{}"'.format(identifier)
                        # self.logMessage.emit(msg, logging.WARNING)
                        continue
                    # Skip current pass for env targets
                    if pass_env_item in current_pass_for_env_items:
                        # msg = 'Is Being Dispatched. Pass Is In Current Submission: "{}"'.format(identifier)
                        # self.logMessage.emit(msg, logging.WARNING)
                        continue
                    identity_id = pass_env_item.get_identity_id()
                    if identity_id not in wait_on_all_for_env and identity_id_env not in wait_on_all_for_env:
                        msg = 'Is Being Dispatched. But Identity Not Required For WAIT On: "{}"'.format(identifier)
                        self.logMessage.emit(msg, logging.WARNING)
                        continue
                    # Attempt to get Plow ids of this other item, and keep trying...
                    for attempt_count in range(ATTEMPT_COUNT):
                        # Get the latest shared Plow ids results from JunkBox bucket
                        uuid_to_plow_ids, pass_wait_on_applied = self._get_wait_on_applied_from_junkbox(
                            global_jbx_bucket)
                        plow_job_id = uuid_to_plow_ids.get(identity_id, dict()).get('job_id')
                        plow_layer_id = uuid_to_plow_ids.get(identity_id, dict()).get('layer_id')
                        # plow_task_ids = uuid_to_plow_ids.get(identity_id, dict()).get('task_ids')
                        # This pass hasn't yet been dispatched (so WAIT for it)
                        if not plow_job_id:
                            msg = 'Waiting For Target To Be Dispatched: "{}". '.format(identifier)
                            msg += 'MSRS UUID: "{}". '.format(identity_id)
                            msg += 'Attempt Count: "{}"'.format(attempt_count)
                            self.logMessage.emit(msg, logging.WARNING)
                            time.sleep(SLEEP_TIME)
                            continue
                        # Apply Plow ids which might be from other dispatcher tasks
                        msg = 'Collected Plow Job Id From Other Dispatcher Task: "{}". '.format(plow_job_id)
                        msg += 'Layer Id: "{}". '.format(plow_layer_id)
                        # msg += 'Task Id: "{}"'.format(plow_task_ids)
                        self.logMessage.emit(msg, logging.WARNING)
                        pass_env_item.set_plow_job_id_last(plow_job_id)
                        pass_env_item.set_plow_layer_id_last(plow_layer_id)
                        # pass_env_item.set_plow_task_ids_last(plow_task_ids)
                        break

        # Get the latest shared Plow ids results from JunkBox bucket
        if is_being_dispatched:
            _uuid_to_plow_ids, pass_wait_on_applied = self._get_wait_on_applied_from_junkbox(
                global_jbx_bucket)
        else:
            _uuid_to_plow_ids, pass_wait_on_applied = (
                self._last_submitted_uuid_to_plow_ids,
                self._last_submitted_pass_wait_on_applied)

        # Apply WAIT on for all target render pass for env
        # NOTE: As environments may be submitted out of order, always run this check to apply WAIT on.
        plow_job_id = None
        applied_to_passes = list()
        applied_wait_count = 0
        for pass_env_item in self.get_pass_for_env_items():
            if is_being_dispatched and not pass_env_item.get_is_being_dispatched():
                continue
            wait_on_source_target_applied = self.apply_wait_on(pass_env_item)
            if not wait_on_source_target_applied:
                continue
            applied_wait_count += 1
            identifier = pass_env_item.get_identifier(nice_env_name=True)
            identity_id = pass_env_item.get_identity_id()
            msg = 'Successfully Applied WAIT On: "{}". '.format(wait_on_source_target_applied)
            msg += 'To: "{}". '.format(identifier)
            self.logMessage.emit(msg, logging.INFO)
            time_stamp = utils.get_time_stamp(include_time_of_day=True)
            # Store indication that this WAIT on has now been applied for later cache in JunkBox.
            for source_uuid, target_uuid in wait_on_source_target_applied:
                if source_uuid not in self._last_submitted_pass_wait_on_applied.keys():
                    self._last_submitted_pass_wait_on_applied[source_uuid] = dict()
                if target_uuid not in self._last_submitted_pass_wait_on_applied[source_uuid].keys():
                    self._last_submitted_pass_wait_on_applied[source_uuid][target_uuid] = time_stamp
            # Update the JunkBox bucket with details of depends just applied
            self._update_wait_on_applied_in_junkbox(global_jbx_bucket)

        # # NOTE: Before checking to unpause Jobs, add slight delay to make sure JunkBox is up to date
        # if applied_wait_count:
        #     time.sleep(2)

        # NOTE: It's only possible to cancel an environment when dispatching on Plow
        env_items_cancelled = list()
        if is_being_dispatched:
            env_items_cancelled = self.get_environment_items_cancelled_for_dispatch()

        # Unpause Job/s if no more WAIT on to apply.
        # NOTE: As environments may be submitted out of order, always run this check for every env.
        for environment_item in self.get_environment_items():
            identity_id_env = environment_item.get_identity_id()
            # Get the latest shared Plow ids results from JunkBox bucket
            if is_being_dispatched:
                _uuid_to_plow_ids, pass_wait_on_applied = self._get_wait_on_applied_from_junkbox(
                    global_jbx_bucket)
            else:
                _uuid_to_plow_ids, pass_wait_on_applied = (
                    self._last_submitted_uuid_to_plow_ids,
                    self._last_submitted_pass_wait_on_applied)

            env_nice_name = environment_item.get_environment_name_nice(prefer_jid=True)
            msg = 'Checking Environment To Unpause Job: "{}"'.format(env_nice_name)
            self.logMessage.emit(msg, logging.WARNING)
            plow_job_id = None
            applied_to_passes = list()

            for pass_env_item in environment_item.get_pass_for_env_items():

                # NOTE: All passes are submitted in same Job by design currently
                _plow_job_id = pass_env_item.get_plow_job_id_last()
                if _plow_job_id:
                    plow_job_id = _plow_job_id
                if is_being_dispatched and not pass_env_item.get_is_being_dispatched():
                    continue
                if not any([pass_env_item.get_wait_on(), environment_item.get_wait_on()]):
                    continue

                # Get WAIT on set for combination of pass for environment and environment
                identity_id = pass_env_item.get_identity_id()
                wait_on_set = set(pass_env_item.get_wait_on())
                msg = '\n\nWAIT ON SET: "{}"'.format(wait_on_set)
                if environment_item not in env_items_cancelled:
                    wait_on_set_env = set(environment_item.get_wait_on() or list())
                    msg += '\nWAIT ON SET ENV: "{}"'.format(wait_on_set_env)
                    if wait_on_set_env:
                        wait_on_set = wait_on_set.union(wait_on_set_env)

                # Verify all environments of pass for env items hasnt been cancelled
                wait_on_set_verified = set()
                for _wait_on in wait_on_set:
                    _item = self.get_item_from_uuid(_wait_on)
                    if not _item:
                        continue
                    if _item.is_pass_for_env_item():
                        _item = _item.get_environment_item()
                    if _item not in env_items_cancelled:
                        wait_on_set_verified.add(_wait_on)
                wait_on_set = set(wait_on_set_verified)

                # Check for WAIT On that has been applied to this pass
                wait_on_applied_to_this_pass = set()
                for key in pass_wait_on_applied.keys():
                    if key in [identity_id, identity_id_env]:
                        for _wait_on in pass_wait_on_applied[key].keys():
                            if _wait_on in wait_on_set:
                                wait_on_applied_to_this_pass.add(_wait_on)

                all_wait_on_applied = bool(wait_on_set.intersection(wait_on_applied_to_this_pass) == wait_on_set)
                applied_to_passes.append(all_wait_on_applied)
                if self._debug_mode:
                    msg += '\nWAIT ON SET COMBINED: "{}"'.format(wait_on_set)
                    msg += '\nWAIT ON APPLIED TO THIS PASS: "{}"'.format(wait_on_applied_to_this_pass)
                    msg += '\nALL WAIT ON APPLED: "{}"'.format(all_wait_on_applied)
                    self.logMessage.emit(msg, logging.DEBUG)

            if plow_job_id and all(applied_to_passes) and not self._launch_paused:
                msg = 'No More WAIT On To Apply To: "{}". '.format(env_nice_name)
                msg += 'Unpausing Job: "{}"'.format(plow_job_id)
                self.logMessage.emit(msg, logging.WARNING)
                self._scheduler_operations.job_pause(
                    plow_job_id,
                    pause=False,
                    name=env_nice_name)
            else:
                msg = 'Environment Still Has WAIT On: "{}". '.format(env_nice_name)
                msg += 'Applied To Passes: "{}". '.format(applied_to_passes)
                msg += 'Plow Job Id: "{}". '.format(plow_job_id)
                self.logMessage.emit(msg, logging.WARNING)

        return applied_wait_count


    def apply_wait_on(self, pass_env_item, pass_env_items=None):
        '''
        Apply dependencies between single pass and all other already submitted passes.
        Note: Create Job on Job or Task on Task dependencies.

        Args:
            pass_env_item (RenderPassForEnv): the render pass for env to apply WAIT to
            pass_env_items (list): all other already submitted render pass for
                env to consider to make dependencies with

        Returns:
            wait_on_source_target (list):
        '''
        if not pass_env_item.is_pass_for_env_item():
            msg = 'Can Only Apply WAIT To Render Pass For Environment Items! '
            self.logMessage.emit(msg, logging.WARNING)
            return dict()
        if not pass_env_items:
            pass_env_items = self.get_pass_for_env_items()

        env_item = pass_env_item.get_environment_item()

        identifier = pass_env_item.get_identifier(nice_env_name=True)
        pass_uuid = pass_env_item.get_identity_id()

        wait_on_source_target = dict()
        wait_on_set = pass_env_item.get_wait_on() or list()
        if wait_on_set:
            wait_on_source_target[pass_uuid] = wait_on_set
        wait_on_set_env = env_item.get_wait_on() or list()
        if wait_on_set_env:
            wait_on_source_target[env_item.get_identity_id()] = wait_on_set_env

        # This pass has nothing to WAIT on
        if not wait_on_source_target:
            return dict()

        # This pass must already be submitted to Plow to apply dependency to another Job or Task
        plow_job_id_last = pass_env_item.get_plow_job_id_last()
        plow_layer_id_last = pass_env_item.get_plow_layer_id_last()
        plow_task_ids_last = pass_env_item.get_plow_task_ids_last()
        if not plow_job_id_last:
            if self._debug_mode:
                msg = 'Cannot Apply WAIT On Because No Other Plow Job Id: "{}"'.format(identifier)
                self.logMessage.emit(msg, logging.WARNING)
            return dict()

        msg = 'Applying WAIT To: "{}". '.format(identifier)
        msg += 'This Item Should WAIT On: "{}"'.format(wait_on_source_target)
        self.logMessage.emit(msg, logging.INFO)

        # Get the Plow Job and Task objects for this pass for env.
        # NOTE: To create WAIT on this pass must be already submitted.
        job = self._scheduler_operations.get_job(plow_job_id_last, name=identifier)
        if not job:
            # msg = 'Failed To Get Job Object For Plow Id: "{}". '.format(plow_job_id_last)
            # msg += 'Identifier: "{}"'.format(identifier)
            return dict()

        layer = list()
        if plow_layer_id_last:
            layer = self._scheduler_operations.get_layer_for_job(
                job,
                plow_layer_id_last,
                name=identifier)

        tasks = list()
        if plow_task_ids_last:
            tasks = self._scheduler_operations.get_tasks_for_job(
                job,
                plow_task_ids_last,
                name=identifier)

        # Iterate over user WAIT on list and try to find match to this pass for env item
        wait_on_source_target_applied = list()
        for i, source_uuid in enumerate(wait_on_source_target.keys()):
            source_item = self.get_item_from_uuid(source_uuid, pass_env_items=pass_env_items)
            msg = 'Found Source Item With MSRS UUID: "{}". '.format(source_uuid)
            msg += 'Identifier: "{}". '.format(source_item.get_identifier())
            msg += 'UUID: "{}". '.format(source_item.get_identity_id())
            msg += 'Count: "{}"'.format(i)
            self.logMessage.emit(msg, logging.WARNING)

            target_uuids = wait_on_source_target[source_uuid]
            for x, target_uuid in enumerate(target_uuids):
                target_item = self.get_item_from_uuid(target_uuid, pass_env_items=pass_env_items)
                msg = 'Found WAIT On Target Item With MSRS UUID: "{}". '.format(target_uuid)
                msg += 'Identifier: "{}". '.format(target_item.get_identifier())
                msg += 'UUID: "{}". '.format(target_item.get_identity_id())
                msg += 'Count: "{}"'.format(x)
                self.logMessage.emit(msg, logging.WARNING)
                if not target_item:
                    continue

                _plow_job_id_last, _plow_layer_id_last, _plow_task_ids_last = None, None, list()
                if isinstance(target_item, data_objects.EnvironmentItem):
                    for _pass_env_item in target_item.get_pass_for_env_items():
                        # Get first valid Plow Job id for passes
                        if _pass_env_item.get_plow_job_id_last():
                            _plow_job_id_last = _pass_env_item.get_plow_job_id_last()
                            _identifier = _pass_env_item.get_identifier()
                            break
                else:
                    _identifier = target_item.get_identifier()
                    _plow_job_id_last = target_item.get_plow_job_id_last()
                    _plow_layer_id_last = target_item.get_plow_layer_id_last()
                    _plow_task_ids_last = target_item.get_plow_task_ids_last()
                if not _plow_job_id_last:
                    msg = 'Failed To Get Other Plow Job Id: "{}"'.format(_plow_job_id_last)
                    self.logMessage.emit(msg, logging.WARNING)
                    continue

                # Get the other Plow Job and Task objects, that have already been submitted
                other_job = self._scheduler_operations.get_job(_plow_job_id_last, name=_identifier)
                if not other_job:
                    msg = 'Failed To Get Other Plow Job Object: "{}"'.format(_plow_job_id_last)
                    self.logMessage.emit(msg, logging.WARNING)
                    continue

                other_layer = list()
                if _plow_layer_id_last:
                    other_layer = self._scheduler_operations.get_layer_for_job(
                        other_job,
                        _plow_layer_id_last,
                        name=identifier)
                    if not other_layer:
                        msg = 'Failed To Get Other Plow Layer Object: "{}"'.format(other_layer)
                        self.logMessage.emit(msg, logging.WARNING)

                other_tasks = list()
                if _plow_task_ids_last:
                    other_tasks = self._scheduler_operations.get_tasks_for_job(
                        other_job,
                        _plow_task_ids_last,
                        name=_identifier)
                    if not other_tasks:
                        msg = 'Failed To Get Other Plow Tasks Objects: "{}"'.format(_plow_task_ids_last)
                        self.logMessage.emit(msg, logging.WARNING)

                if target_item.is_environment_item() and all([job, other_job]):
                    if source_item and source_item.is_pass_for_env_item() and layer:
                        success = self._scheduler_operations.create_layer_on_job_layers_depend(layer, other_job)
                        if success:
                            wait_on_source_target_applied.append((source_uuid, target_uuid))
                    elif source_item and source_item.is_pass_for_env_item() and tasks:
                        success = self._scheduler_operations.create_tasks_on_job_layers_depend(tasks, other_job)
                        if success:
                            wait_on_source_target_applied.append((source_uuid, target_uuid))
                    else:
                        success = self._scheduler_operations.create_job_on_job_depend(job, other_job)
                        if success:
                            wait_on_source_target_applied.append((source_uuid, target_uuid))

                elif target_item.is_pass_for_env_item() and all([layer, other_layer]):
                    success = self._scheduler_operations.create_layer_on_layer_depends(layer, other_layer)
                    if success:
                        wait_on_source_target_applied.append((source_uuid, target_uuid))

                elif target_item.is_pass_for_env_item() and all([tasks, other_tasks]):
                    success = self._scheduler_operations.create_tasks_on_tasks_depend(tasks, other_tasks)
                    if success:
                        wait_on_source_target_applied.append((source_uuid, target_uuid))

        return wait_on_source_target_applied


    def get_environment_items_cancelled_for_dispatch(self):
        '''
        Get any environment items that have been cancelled across all dispatcher tasks of this Job.

        Returns:
            cancelled_environment_items (list): list of EnvironmentItem
        '''
        if self._debug_mode:
            msg = 'Checking For Cancelled Dispatch Environments...'
            self.logMessage.emit(msg, logging.WARNING)
        job_id = os.getenv('PLOW_JOB_ID')
        if not job_id:
            # msg = 'No "PLOW_JOB_ID" To Check For Cancelled Dispatch Environments!'
            # self.logMessage.emit(msg, logging.WARNING)
            return list()
        job = self._scheduler_operations.get_job(job_id)
        if not job:
            # msg = 'Failed To Get Job To Check For Cancelled Dispatch Environments! '
            # msg += 'From Job Id: "{}"'.format(job_id)
            # self.logMessage.emit(msg, logging.WARNING)
            return list()
        import plow
        task_states = [plow.TaskState.EATEN, plow.TaskState.DEAD] # plow.TaskState.SUSPEND
        cancelled_environment_items = set()
        for task in job.get_tasks(state=task_states):
            # msg = 'Checking For Cancelled Dispatch Environment For Task: "{}"'.format(task.name)
            # self.logMessage.emit(msg, logging.WARNING)
            layer = task.get_layer()
            attrs = layer.attrs or dict()
            environments_to_dispatch = attrs.get('environments_to_dispatch', str())
            environments_to_dispatch = environments_to_dispatch.split(',')
            # msg = 'Layer Has Environments To Dispatch: "{}"'.format(environments_to_dispatch)
            # self.logMessage.emit(msg, logging.WARNING)
            for env_identifier in environments_to_dispatch:
                environment_item = self.get_item_from_identifier(env_identifier)
                # msg = 'Environment Item For Identifier: "{}"'.format(environment_item)
                # self.logMessage.emit(msg, logging.WARNING)
                if environment_item:
                    cancelled_environment_items.add(environment_item)
        return list(cancelled_environment_items)


    def _get_wait_on_applied_from_junkbox(self, global_jbx_bucket, jbx=None):
        '''
        Get latest mapping of pass for env identifiers to Plow Task Ids for
        a global JunkBox id. Which is shared across all dispatcher tasks.

        Args:
            global_jbx_bucket (str):

        Returns:
            uuid_to_plow_ids, pass_wait_on_applied (tuple): two dictionaries
        '''
        msg = 'Getting Latest Pass Identifier To Plow Task Ids '
        msg += 'From JunkBox Bucket: "{}"'.format(global_jbx_bucket)
        LOGGER.info(msg)

        from srnd_multi_shot_render_submitter import junkbox
        jbx = jbx or junkbox.JunkBox()

        PASS_TO_TASK_IDS_KEY = 'uuid_to_plow_ids'
        PASS_WAIT_ON_APPLIED_KEY = 'pass_wait_on_applied'

        uuid_to_plow_ids = jbx.get_junkbox_data(
            global_jbx_bucket,
            PASS_TO_TASK_IDS_KEY)
        pass_wait_on_applied = jbx.get_junkbox_data(
            global_jbx_bucket,
            PASS_WAIT_ON_APPLIED_KEY)
        if not uuid_to_plow_ids:
            uuid_to_plow_ids = dict()
        if not pass_wait_on_applied:
            pass_wait_on_applied = dict()

        if self._debug_mode:
            msg = 'Got From JunkBox Id: "{}". '.format(global_jbx_bucket)
            msg += 'MSRS UUIDs To Plow Ids: "{}"'.format(uuid_to_plow_ids)
            LOGGER.info(msg)

            msg = 'Got From JunkBox Id: "{}". '.format(global_jbx_bucket)
            msg += 'MSRS UUIDs To Plow Ids WAIT On Already Applied: "{}"'.format(pass_wait_on_applied)
            LOGGER.info(msg)

        return uuid_to_plow_ids, pass_wait_on_applied


    def _update_uuid_to_plow_ids_in_junkbox(self, global_jbx_bucket, jbx=None):
        '''
        Update UUIDs to Plow ids applied in JunkBox.

        Args:
            global_jbx_bucket (str):
        '''
        from srnd_multi_shot_render_submitter import junkbox
        jbx = jbx or junkbox.JunkBox()
        PASS_TO_TASK_IDS_KEY = 'uuid_to_plow_ids'
        current_data = self._get_last_submitted_uuid_to_plow_ids()
        if not current_data:
            return
        previous_data = jbx.get_junkbox_data(global_jbx_bucket, PASS_TO_TASK_IDS_KEY)
        if not previous_data:
            previous_data = dict()
        current_data.update(previous_data)
        jbx.put_junkbox_data(global_jbx_bucket, PASS_TO_TASK_IDS_KEY, current_data)
        msg = 'Updated JunkBox Id: "{}". '.format(global_jbx_bucket)
        msg += 'MSRS UUIDs To Plow Ids: "{}"'.format(current_data)
        self.logMessage.emit(msg, logging.DEBUG)


    def _update_wait_on_applied_in_junkbox(self, global_jbx_bucket, jbx=None):
        '''
        Update WAIT On applied in JunkBox.

        Args:
            global_jbx_bucket (str):
        '''
        from srnd_multi_shot_render_submitter import junkbox
        jbx = jbx or junkbox.JunkBox()
        PASS_WAIT_ON_APPLIED_KEY = 'pass_wait_on_applied'
        current_data = self._get_last_submitted_pass_wait_on_applied()
        if not current_data:
            return
        # msg = 'CURRENT DATA: "{}"'.format(current_data)
        # self.logMessage.emit(msg, logging.DEBUG)
        previous_data = jbx.get_junkbox_data(global_jbx_bucket, PASS_WAIT_ON_APPLIED_KEY)
        if not previous_data:
            previous_data = dict()
        # msg = 'PREVIOUS DATA: "{}"'.format(previous_data)
        # self.logMessage.emit(msg, logging.DEBUG)
        # Merge the dicts
        # current_data.update(previous_data)
        new_data = dict()
        for key, value in previous_data.iteritems():
            new_data[key] = value
            value = current_data.get(key)
            if value:
                new_data[key].update(value)
        for key, value in current_data.iteritems():
            if key not in new_data.keys():
                new_data[key] = value
        # msg = 'NEW DATA: "{}"'.format(new_data)
        # self.logMessage.emit(msg, logging.DEBUG)
        jbx.put_junkbox_data(global_jbx_bucket, PASS_WAIT_ON_APPLIED_KEY, new_data)
        msg = 'Updated JunkBox Id: "{}". '.format(global_jbx_bucket)
        msg += 'MSRS UUIDs To Plow Ids WAIT On Already Applied: "{}". '.format(new_data)
        self.logMessage.emit(msg, logging.DEBUG)


    def apply_wait_on_plow_ids(self, pass_for_env_items):
        '''
        Apply WAIT on to existing Plow Job/s and Task/s to environment
        and render pass for env items.

        Args:
            pass_for_env_items (list):

        Returns:
            wait_on_applied_count (int):
        '''
        if not pass_for_env_items:
            pass_for_env_items = list()

        plow_job_to_job_ids = list()
        plow_ids_to_ids = list()
        for pass_env_item in pass_for_env_items:
            environment_item = pass_env_item.get_environment_item()
            plow_job_id = pass_env_item.get_plow_job_id_last()
            # The item to WAIT on explicit Plow Job id, must have a Plow id itself
            if not plow_job_id:
                continue
            plow_layer_or_task_id = pass_env_item.get_plow_layer_id_last()
            if not plow_layer_or_task_id:
                plow_layer_or_task_id = pass_env_item.get_plow_task_ids_last()
            wait_on_plow_ids = list(pass_env_item.get_wait_on_plow_ids() or list())
            # This pass should be also dependening on all Environment depends
            wait_on_plow_ids.extend(list(environment_item.get_wait_on_plow_ids() or list()))
            if not wait_on_plow_ids:
                continue
            for wait_on in wait_on_plow_ids:
                if not wait_on:
                    continue
                plow_job_id_other = str(wait_on[0])
                if len(wait_on) == 1:
                    value = [plow_job_id, plow_job_id_other]
                    plow_job_to_job_ids.append(value)
                elif len(wait_on) > 1 and plow_layer_or_task_id:
                    plow_other_layer_or_task_id = str(wait_on[1])
                    value = [
                        plow_job_id,
                        plow_layer_or_task_id,
                        plow_job_id_other,
                        plow_other_layer_or_task_id]
                    plow_ids_to_ids.append(value)

        wait_on_applied_count = 0

        # Create Job on Job depends
        for plow_job_id, plow_job_id_other in plow_job_to_job_ids:
            job = self._scheduler_operations.get_job(plow_job_id)
            if not job:
                continue
            job_other = self._scheduler_operations.get_job(plow_job_id_other)
            if not job_other:
                continue
            success = self._scheduler_operations.create_job_on_job_depend(job, job_other)
            wait_on_applied_count += int(success)

        # Create Layer on Layer or Task on Task depends
        for plow_job_id, plow_layer_or_task_id, plow_job_id_other, plow_other_layer_or_task_id in plow_ids_to_ids:
            # Must have source and target Job
            job = self._scheduler_operations.get_job(plow_job_id)
            if not job:
                continue
            job_other = self._scheduler_operations.get_job(plow_job_id_other)
            if not job_other:
                continue

            success = False

            layer = self._scheduler_operations.get_layer_for_job(job, plow_layer_or_task_id)
            # Create depends from submitted Multi Shot items Layer to...
            if layer:
                layer_other = self._scheduler_operations.get_layer_for_job(job_other, plow_other_layer_or_task_id)
                # Create depends from submitted Multi Shot items Layer to other explicit Layer by id
                if layer_other:
                    success = self._scheduler_operations.create_layer_on_layer_depends(layer, layer_other)
                # Create depends from submitted Multi Shot items Layer to other explicit Task by id
                else:
                    tasks = self._scheduler_operations.get_tasks_for_job(job_other, plow_other_layer_or_task_id)
                    if not tasks:
                        continue
                    success = self._scheduler_operations.create_layer_on_layer_depends(layer, tasks)
            # Create depends from submitted Multi Shot items Task to...
            else:
                # Multi Shot source item does not have Layer or Tasks object
                tasks = self._scheduler_operations.get_tasks_for_job(job, plow_layer_or_task_id)
                if not tasks:
                    continue
                # Create depends from submitted Multi Shot items Tasks to other explicit Layer by id
                layer_other = self._scheduler_operations.get_layer_for_job(job_other, plow_other_layer_or_task_id)
                if layer_other:
                    success = self._scheduler_operations.create_tasks_on_job_layers_depend(tasks, layer_other)
                # Create depends from submitted Multi Shot items Tasks to other explicit Task by id
                else:
                    task_other = self._scheduler_operations.get_tasks_for_job(job_other, plow_other_layer_or_task_id)
                    if not task_other:
                        continue
                    success = self._scheduler_operations.create_tasks_on_tasks_depend(tasks, [task_other])

            wait_on_applied_count += int(success)

        # Add delay before Job is possibly unpaused
        if wait_on_applied_count:
            time.sleep(3)

        return wait_on_applied_count


    def _check_wait_on_matches_pass_for_env(self, wait_on, pass_env_item):
        '''
        Check WAIT on string matches the pass for env identifier or environment.
        TODO: This will be replaced later with more generic method elsewhere.

        Args:
            wait_on (str): the environment name with optional job identifier or index, or the full
                identifier name to pass for environment.
            pass_env_item (RenderPassForEnvItem): the pass for env item to see if WAIT on matches.
        '''
        env_item = pass_env_item.get_environment_item()
        render_item = pass_env_item.get_source_render_item()
        oz_area = env_item.get_oz_area()

        # First try to find match for simple environment
        matches = wait_on == oz_area
        if matches:
            return True, 'environment'

        # Otherwise environment and job identifier
        job_identifier = env_item.get_job_identifier()
        if job_identifier:
            env_nice_name_with_jid = env_item.get_environment_name_nice(prefer_jid=True)
            matches = wait_on == env_nice_name_with_jid
            if matches:
                return True, 'environment'

        # Otherwise environment and env index
        env_nice_name_with_index = env_item.get_environment_name_nice(prefer_jid=False)
        matches = wait_on == env_nice_name_with_index
        if matches:
            return True, 'environment'

        # Otherwise find match with full identifier
        item_full_name = render_item.get_item_full_name()
        identifier = oz_area + constants.IDENTIFIER_JOINER + item_full_name
        if wait_on == identifier:
            return True, 'pass'

        # Otherwise find match with full identifier including job identifier
        if job_identifier:
            identifier = env_nice_name_with_jid + constants.IDENTIFIER_JOINER
            identifier += item_full_name
            if wait_on == identifier:
                return True, 'pass'

        # Otherwise find match with full identifier including env index
        identifier = env_nice_name_with_index + constants.IDENTIFIER_JOINER
        identifier += item_full_name
        if wait_on == identifier:
            return True, 'pass'

        return False, None


    def validate_wait_on_multi_shot_uuids(
            self,
            uuids,
            pass_for_env_items=None,
            must_be_active=True,
            only_is_being_dispatched=False,
            source_uuid=None):
        '''
        Validate a list of WAIT on to multi shot items can be found in the model.

        Args:
            UUIDs (list): list of UUIDs to validate are in model
            pass_for_env_items (list): optional subset of render pass for env items to validate
            must_be_active (bool): optionally only return validated wait on identifiers, which
                are actually active and enabled.
            only_is_being_dispatched (bool): if list of explicit pass_for_env_items
                is not being provided, then instead of checking against all pass for env
                items, only check against those being dispatched
            source_uuid (str): optionally provide the source uuid, which will be excluded from
                validated results.

        Returns:
            validated_uuids (list):
        '''
        if not uuids:
            return list()

        msg = 'Validating UUIDs: "{}"'.format(uuids)
        self.logMessage.emit(msg, logging.WARNING)

        if not pass_for_env_items:
            if only_is_being_dispatched:
                pass_for_env_items = self.get_pass_for_env_items_being_dispatched()
            else:
                pass_for_env_items = self.get_pass_for_env_items()

        validated_uuids = set()

        # Check for UUID match in render pass for env items, and add validated pass UUID
        for pass_env_item in pass_for_env_items:
            if must_be_active and not pass_env_item.get_active():
                continue
            uuid = pass_env_item.get_identity_id()
            if uuid in uuids:
                validated_uuids.add(uuid)
            env_item = pass_env_item.get_environment_item()
            uuid = env_item.get_identity_id()
            if uuid in uuids:
                validated_uuids.add(uuid)

        # NOTE: Making a dependency to self is not valid
        if source_uuid:
            if source_uuid in validated_uuids:
                validated_uuids.remove(source_uuid)

        return list(validated_uuids)


    def validate_all_render_overrides(self):
        '''
        Validate all render overrides values in entire model.

        Returns:
            changed_count (int): if any render overrides items were removed during validation
        '''
        msg = 'Validating All Render Overrides In MSRS Data Model...'
        self.logMessage.emit(msg, logging.WARNING)
        changed_count = 0
        for qmodelindex_env in self.get_environment_items_indices():
            environment_item = qmodelindex_env.internalPointer()
            _changed_count = environment_item.validate_render_overrides()
            if _changed_count:
                changed_count += _changed_count
                self.dataChanged.emit(qmodelindex_env, qmodelindex_env)
            for qmodelindex_pass in self.get_pass_for_env_items_indices(
                    env_indices=[qmodelindex_env]):
                pass_env_item = qmodelindex_pass.internalPointer()
                _changed_count = pass_env_item.validate_render_overrides()
                if _changed_count:
                    changed_count += _changed_count
                    self.dataChanged.emit(qmodelindex_pass, qmodelindex_pass)
        return changed_count


    ##########################################################################


    def get_environment_job_name(
            self,
            environment_item,
            global_job_identifier=None,
            pass_count=1):
        '''
        Get a job name for a particular environment.

        Args:
            environment_item (EnvironmentItem): or subclass
            global_job_identifier (str): an optional identifier to add into every generated Job name
            pass_count (int):

        Returns:
            job_name (str):
        '''
        job_name_parts = ['{}MSRS'.format(self.HOST_APP.title())]

        # Optional global job identifier
        global_job_identifier = self.get_global_job_identifier()
        if global_job_identifier:
            job_name_parts.append(str(global_job_identifier))

        # Optionaly unique job identifier per environment
        job_identifier = environment_item.get_job_identifier()
        if job_identifier:
            job_name_parts.append(str(job_identifier))

        if pass_count > 1:
            job_name_parts.append('{}Passes'.format(pass_count))

        job_name = '_'.join(job_name_parts)
        job_name = job_name.replace('"', str()).replace("'", str())

        msg = 'Proposed Render Job Name Is: "{}"'.format(job_name)
        self.logMessage.emit(msg, logging.WARNING)

        return job_name


    def get_summary_and_validation_window(
            self,
            pass_for_env_items=None,
            interactive=False,
            debug_mode=False,
            parent=None):
        '''
        Get and build the summary and validation window, appropiate for host app.
        Reimplement this to return a subclassed summary window and / or optionally
        with a custom validation system.

        Args:
            pass_for_env_items (bool): list of specific pass for env items to render
            interactive (bool): indicate to the summary window an interactive otherwise
                batch render is being done
            debug_mode (bool):
            parent (QWidget): parent the window to specified QWidget or other subclass

        Returns:
            window (SummaryAndValidationWindow):
        '''
        time_start = time.time()

        from srnd_multi_shot_render_submitter.dialogs import summary_and_validation_window
        window = summary_and_validation_window.SummaryAndValidationWindow(
            self, # the source model to extend
            summary_model_object=self.get_summary_model_object(), # pass the possibly subclassed summary model
            pass_for_env_items=pass_for_env_items,
            interactive=interactive,
            validation_auto_start=self._validation_auto_start,
            auto_scroll=self._summary_auto_scroll_to_validation,
            build=False,
            version=self.TOOL_VERSION,
            debug_mode=debug_mode,
            parent=parent)
        window.logMessage.connect(self.emit_message)

        # TODO: Could remove specifying the validation system, and let subclassed versions of this method
        # provide the correct validation system object. Right now validation system base isn't abstract
        # so can be used as placeholder anyway.
        from srnd_multi_shot_render_submitter.validation import validation_system_base
        validation_system_object = validation_system_base.ValidationSystemBase
        window.build_child_widgets(validation_system_object=validation_system_object)

        te = int(time.time() - time_start)
        msg = 'Time to instantiate summary & validation dialog. '
        self.logMessage.emit(TIME_TAKEN_MSG.format(msg, te), logging.DEBUG)

        return window


    def _get_email_details_for_envs(self):
        '''
        Get the last collected email details for submission (if any).

        Returns:
            email_details_envs (list):
        '''
        return self._email_details_envs_data


    def _get_last_submitted_uuid_to_plow_ids(self):
        '''
        Get mapping of last submitted pass for env identifier to Plow Task id.
        Note: This is written to global JunkBox id when each environment finishes submit.

        Returns:
            last_submitted_uuid_to_plow_ids (dict): key is pass for env identifier
        '''
        return self._last_submitted_uuid_to_plow_ids


    def _get_last_submitted_pass_wait_on_applied(self):
        '''
        Get mapping of last submitted pass for env identifier to WAIT on already applied.
        Note: This is written to global JunkBox id when each environment finishes submit.

        Returns:
            last_submitted_pass_wait_on_applied (dict): key is pass for env identifier
        '''
        return self._last_submitted_pass_wait_on_applied


    ##########################################################################
    # Dispatch methods


    def render_from_command_line(self, args_to_parse):
        '''
        Render in the currrent application context from this model
        using the incoming command line arguments.
        Note: This is normally invoked from the shell, inside a Job on Plow
        and via Katana script mode executing this module, which instantiates
        this model, and then calls this method with arguments.

        Args:
            args (list):

        Returns:
            success, msg (bool):

        Raises:
            AttributeError: when command line arguments are invalid, or
                cannot be used to instantiate model in expected way
        '''
        import sys

        msg = 'Render From Command Line Args: "{}". '.format(args_to_parse)
        LOGGER.info(msg)

        # Build the GEN command line for Multi Shot Render Submitter UI
        from srnd_multi_shot_render_submitter.command_line import MultiShotRenderCommandLine
        multi_shot_command_line = MultiShotRenderCommandLine()
        parser, options_dict = multi_shot_command_line.build_command_line_interface(
            args_to_parse=args_to_parse,
            force_args=self.get_in_host_app(),
            is_ui_context=False)

        project = options_dict.get('project')
        session = options_dict.get('session')
        environments_override = options_dict.get('environments')
        identifiers_override = options_dict.get('pass_for_env_identifiers_override')
        render_nodes_override = options_dict.get('render_nodes_override')
        global_shotsub_override = options_dict.get('global_shotsub_override')
        global_note_override = options_dict.get('global_note_override')
        global_job_identifier = options_dict.get('global_job_identifier')
        auto_refresh_from_shotgun = options_dict.get('auto_refresh_from_shotgun', True)

        overrides_dict = dict()

        # Extract overrides if user specified additional per item overrides
        # from command line (and when --dispatch isn't specified).
        # This collects all the per item overrides into the expected overrides dict format.
        if options_dict:
            from srnd_multi_shot_render_submitter.dispatcher.abstract_multi_shot_dispatcher import \
                AbstractMultiShotDispatcher
            overrides_dict = AbstractMultiShotDispatcher.resolve_per_render_node_overrides(options_dict) or dict()

        jbx_bucket = str(options_dict.get('jbx_bucket') or str()).replace('"', str())
        global_jbx_bucket = str(options_dict.get('global_jbx_bucket') or str()).replace('"', str())

        from srnd_multi_shot_render_submitter import junkbox
        jbx = junkbox.JunkBox()

        # Extract any overrides stored in the JunkBox id.
        # NOTE: In --dispatch mode the extra user overrides args are written into JunkBox
        # to avoiding passing exccess argument around.
        if jbx_bucket:
            _overrides_dict = jbx.get_junkbox_data(jbx_bucket, 'overrides_dict') or dict()
            if _overrides_dict:
                overrides_dict = _overrides_dict
                msg = 'Extracted Overrides Dict From JunkBox: "{}". '.format(overrides_dict)
                LOGGER.debug(msg)

        # Extract only the dispatcher results stored from JunkBox.
        uuid_to_plow_ids, pass_wait_on_applied = dict(), dict()
        if global_jbx_bucket:
            uuid_to_plow_ids, pass_wait_on_applied = self._get_wait_on_applied_from_junkbox(
                global_jbx_bucket)

        session_data = dict()
        limit_to = list()
        if session:
            from srnd_multi_shot_render_submitter import utils
            success, session_data = utils.extract_session_data(session)
            if not success:
                msg = 'Failed To Extract Session Data From: "{}". '.format(session)
                LOGGER.warning(msg)
                raise AttributeError(msg)
            # If project override not provided then derive it from session data.
            if not project:
                project = session_data.get('project')
            # Extract the list of renderable names to act as limit of sync
            multi_shot_data = session_data.get(constants.SESSION_KEY_MULTI_SHOT_DATA, dict())
            render_nodes_data = multi_shot_data.get(constants.SESSION_KEY_RENDER_NODES, dict())
            limit_to = sorted(render_nodes_data.keys())

        if not project:
            msg = 'No Project Specified To Load!'
            LOGGER.warning(msg)
            raise AttributeError(msg)

        debug_mode = options_dict.get('debug_mode', False)
        self.set_debug_mode(debug_mode)
        msg = 'Log Verbosity Level In Debug Mode: {}'.format(debug_mode)
        LOGGER.info(msg)

        self.set_auto_refresh_from_shotgun(auto_refresh_from_shotgun)

        msg = 'Synching Render Nodes & Envrionments'
        LOGGER.info(msg)

        # Sync all render nodes and environments (first open the project)
        self.set_session_data_is_recalled_after_sync(False)

        self.sync_render_nodes_and_environments(
            hyref=project,
            limit_to=limit_to) # limit sync to render nodes in session data

        source_project_version = session_data.get('source_project_version')
        self.set_source_project_version(source_project_version)

        render_items = self.get_render_items()
        renderable_count = len(render_items)
        msg = 'Synched {} Renderable Nodes From Host App. '.format(renderable_count)
        LOGGER.info(msg)

        if session_data:
            self.apply_session_data(session_data)

        environment_items = self.get_environments()
        environment_count = len(environment_items)
        msg = 'Environments In Current Session: "{}". '.format(environment_count)
        LOGGER.info(msg)

        # Override renderable state, by setting queued and enabled states
        if any([
                environments_override,
                identifiers_override,
                render_nodes_override,
                overrides_dict,
                isinstance(global_shotsub_override, bool),
                uuid_to_plow_ids]):
            self.override_renderable_items_for_dispatching(
                environments_override=environments_override,
                pass_for_env_identifiers=identifiers_override,
                render_nodes_override=render_nodes_override,
                overrides_dict=overrides_dict,
                uuid_to_plow_ids=uuid_to_plow_ids,
                global_shotsub_override=global_shotsub_override)

        if global_note_override:
            self.set_global_submit_description(global_note_override)

        if global_job_identifier:
            self.set_global_job_identifier(global_job_identifier)

        # NOTE: This is now the deferred task running on Plow.
        # So run the task now in current host app context.
        self.set_dispatch_deferred(False)

        msg = 'About To Start Render...'
        LOGGER.info(msg)

        self._is_submitting_in_dispatcher_task = True

        self.set_send_summary_email_on_submit(False)

        # Do render submission of subset of environment
        success, cancelled, msg = self.multi_shot_render(
            show_summary_dialog=False,
            global_jbx_bucket=global_jbx_bucket)

        msg = 'Success: "{}". Message: "{}"'.format(success, msg)
        LOGGER.info(msg)

        # Cache the results of this dispatching task in JunkBox bucket
        if jbx_bucket:
            email_details_envs = self._get_email_details_for_envs()
            success = jbx.put_junkbox_data(
                jbx_bucket,
                jbx.DISPATCHER_JUNKBOX_KEY,
                email_details_envs)

        return success, msg


    def override_renderable_items_for_dispatching(
            self,
            environments_override=None,
            pass_for_env_identifiers=None,
            render_nodes_override=None,
            overrides_dict=None,
            uuid_to_plow_ids=None,
            global_shotsub_override=None):
        '''
        Override the renderable state of every pass, depending
        on the provided arguments of this method.
        Note: This is currently intended to use by the dispatcher system
        to set various items to renderable based on a list of strings.

        Args:
            environments_override (list): Environment/s to render from. This option
                doesn't change the queued and enabled states of passes.
            pass_for_env_identifiers (list): Optionally override which passes are
                queued and enabled for rendering. If provided then passes that do no
                appear in this list are disabled.
            render_nodes_override (list):
            overrides_dict (dict):
            uuid_to_plow_ids (dict): mapping of already submitted pass for env identifiers,
                mapped to Plow Task id
            global_shotsub_override (bool):

        Returns:
            overridden_pass_count (int):
        '''
        if not environments_override:
            environments_override = list()
        if not pass_for_env_identifiers:
            pass_for_env_identifiers = list()
        if not render_nodes_override:
            render_nodes_override = list()
        if not overrides_dict:
            overrides_dict = dict()

        msg = '\n\nOVERRIDDING RENDERABLE ITEMS FOR DISPATCH\n'

        msg += '\nenvironments_override - "{}". '.format(environments_override)
        msg += 'Type: "{}"'.format(type(environments_override))

        msg += '\npass_for_env_identifiers - "{}". '.format(pass_for_env_identifiers)
        msg += 'Type: "{}"'.format(type(pass_for_env_identifiers))

        msg += '\nrender_nodes_override - "{}". '.format(render_nodes_override)
        msg += 'Type: "{}"'.format(type(render_nodes_override))

        msg += '\noverrides_dict - "{}". '.format(overrides_dict)
        msg += 'Type: "{}"'.format(type(overrides_dict))
        msg += '\n\n'

        msg += '\nglobal_shotsub_override - "{}". '.format(global_shotsub_override)
        msg += 'Type: "{}"'.format(type(global_shotsub_override))
        msg += '\n\n'

        self.logMessage.emit(msg, logging.INFO)

        # Add any missing environments to dispatch from.
        # NOTE: All the environments from session data will be available in the model already.
        # NOTE: Any environments override that includes index or identifier
        # is to target existing session data only.
        # NOTE: Only environments which do not specify index or job identifier can be added here.
        # NOTE: Therefore only one of each extra environment can be added.
        if environments_override:
            existing_environments = self.get_environments()

            msg = 'Adding Any Missing Environments When Preparing '
            msg += 'Environments Override To Dispatch: "{}". '.format(environments_override)
            self.logMessage.emit(msg, logging.INFO)

            msg = 'Existing Environments Already Synced: "{}". '.format(existing_environments)
            self.logMessage.emit(msg, logging.INFO)

            import oz
            for environment in environments_override:
                environment = str(environment)
                env_only = str(environment)
                # Strip optional index and job identifier
                if '-' in environment:
                    env_only = environment.split('-')[0]
                # Validate the oz area exists
                if not oz.Area.is_valid(env_only):
                    msg = 'Environment Is Not Valid: "{}". '.format(env_only)
                    self.logMessage.emit(msg, logging.WARNING)
                    continue
                # Check if environment with optional index and job identifier not already added
                if env_only in existing_environments:
                    msg = 'Environment Already In Synced Data: "{}". '.format(env_only)
                    msg += 'Skipping Adding Anothr Instance!'
                    self.logMessage.emit(msg, logging.WARNING)
                    continue
                # Add environment (ignoring index and job identifier)
                self.add_environment(oz_area=env_only)

        # Traverse over all EnvironmentItem and RenderPassForEnvItem, and toggle
        # queued and enabled states depending on dispatcher options, such as
        # environments, identifiers and render node overrides.
        environments_counter = dict()
        for environment_item in self.get_environment_items():
            env = environment_item.get_oz_area()

            # Count the Nth version of this environment
            if env not in environments_counter.keys():
                environments_counter[env] = 0
            environments_counter[env] += 1
            env_index = environments_counter[env]

            # Propose the environment with index and job identifier
            env_with_index = env + '-' + str(env_index)
            env_with_identifier = None
            job_identifier = environment_item.get_job_identifier() or str()
            if job_identifier:
                env_with_identifier = env + '-' + str(job_identifier)

            # Get and apply the overrides only for this environment item (if any)
            if overrides_dict and isinstance(overrides_dict, dict):
                env_identifier_long = str(env)
                _overrides_dict = overrides_dict.get(env_identifier_long)
                if not _overrides_dict:
                    env_identifier_long = str(env_with_index)
                    _overrides_dict = overrides_dict.get(env_identifier_long)
                    if not _overrides_dict and env_with_identifier:
                        env_identifier_long = str(env_with_identifier)
                        _overrides_dict = overrides_dict.get(env_identifier_long)
                if _overrides_dict:
                    overrides_applied = environment_item.paste_overrides(_overrides_dict)
                    if overrides_applied:
                        msg = 'Successfully Applied Overrides Count: {}. '.format(overrides_applied)
                        msg += 'To: "{}". '.format(env_identifier_long)
                        msg += 'From Data: "{}"'.format(_overrides_dict)
                        LOGGER.info(msg)

            # Resolve which RenderPassForEnv need dispatching, and apply any queued and enabled overrides
            for pass_env_item in environment_item.get_pass_for_env_items():
                render_item = pass_env_item.get_source_render_item()
                item_full_name = render_item.get_item_full_name()
                identifier = pass_env_item.get_identifier()
                identity_id = pass_env_item.get_identity_id()

                # Check this render item is in user specified overrides
                in_render_nodes_override = False
                if render_nodes_override:
                    in_render_nodes_override = item_full_name in render_nodes_override

                # Check this pass for env item is in user specified overrides
                in_identifier_overrides = False
                if pass_for_env_identifiers:
                    # Check if user specified identifier matches this item identifier exacetly
                    in_identifier_overrides = identifier in pass_for_env_identifiers
                    # Otherwise add the index of Nth version of this environment to identifier
                    # and check if in user specified pass for env identifiers.
                    if not in_identifier_overrides:
                        identifier_nice_name = env + '-' + str(env_index) + constants.IDENTIFIER_JOINER + item_full_name
                        in_identifier_overrides = identifier_nice_name in pass_for_env_identifiers
                    # Otherwise add the job identifier to the Nth version of this environment to
                    # identifier and check if in user specified pass for env identifiers.
                    if not in_identifier_overrides and job_identifier:
                        identifier_nice_name = env + '-' + str(job_identifier) + constants.IDENTIFIER_JOINER + item_full_name
                        in_identifier_overrides = identifier_nice_name in pass_for_env_identifiers

                # If have existing Plow ids dispatched in other tasks, apply it now
                if uuid_to_plow_ids:
                    plow_ids = uuid_to_plow_ids.get(identity_id)
                    if plow_ids:
                        plow_job_id = plow_ids.get('job_id')
                        if plow_job_id:
                            pass_env_item.set_plow_job_id_last(plow_job_id)
                        plow_layer_id = plow_ids.get('layer_id')
                        if plow_layer_id:
                            pass_env_item.set_plow_layer_id_last(plow_layer_id)

                # # Optionally override all post tasks to Shotsub enabled or disabled
                # # TODO: global shotsub override via command line needs some more thought...
                # if isinstance(global_shotsub_override, bool):
                #     post_tasks = pass_env_item.get_post_tasks()
                #     if global_shotsub_override:
                #         post_task_details = dict()
                #         post_task_details['name'] = 'stats'
                #         post_task_details['type'] = 'shotsub'
                #         post_tasks.append(post_task_details)
                #     msg = 'Overridding Item: "{}" '.format(identifier)
                #     msg += 'Shotsub Post Task/s To: "{}". '.format(post_tasks)
                #     LOGGER.info(msg)
                #     pass_env_item.set_post_tasks(post_tasks)

                # Resolve whether need to actually override the RenderPassForEnvItem options.
                override_renderable = None
                # If environments override specified, then dispatch only items
                if environments_override:
                    if any([
                            env in environments_override, # the environment is targeted to dispatch
                            env_with_index in environments_override, # the environment with index is targeted to dispatch
                            env_with_identifier in environments_override]): # the environment with job identifier targeted to dispatch
                        # Must also have some render nodes or pass for env identifiers to dispatch
                        if any([render_nodes_override, pass_for_env_identifiers]):
                            override_renderable = any([
                                in_render_nodes_override,
                                in_identifier_overrides])
                    # This target environment not specified to be dispatched
                    else:
                        override_renderable = False
                # Otherse just check all render nodes to dispatch or pass for env identifiers
                else:
                    if any([render_nodes_override, pass_for_env_identifiers]):
                        override_renderable = any([
                            in_render_nodes_override,
                            in_identifier_overrides])

                # Get and apply the overrides only for this render pass for env (if any)
                if overrides_dict and isinstance(overrides_dict, dict):
                    # Get the overrides only for this item
                    pass_identifier_long = env + constants.IDENTIFIER_JOINER + item_full_name
                    _overrides_dict = overrides_dict.get(pass_identifier_long)
                    if not _overrides_dict:
                        pass_identifier_long = env + '-' + str(env_index) + constants.IDENTIFIER_JOINER + item_full_name
                        _overrides_dict = overrides_dict.get(pass_identifier_long)
                        if not _overrides_dict:
                            pass_identifier_long = env + '-' + str(job_identifier) + constants.IDENTIFIER_JOINER + item_full_name
                            _overrides_dict = overrides_dict.get(pass_identifier_long)
                    if _overrides_dict:
                        # Apply overrides to this RenderPassForEnvItem
                        overrides_applied = pass_env_item.paste_overrides(_overrides_dict)
                        if overrides_applied:
                            msg = 'Successfully Applied Overrides Count: {}. '.format(overrides_applied)
                            msg += 'To: "{}". '.format(pass_identifier_long)
                            msg += 'From Data: "{}"'.format(_overrides_dict)
                            LOGGER.info(msg)

                # Toggling queued and enabled states not required for this render pass for env item
                if not isinstance(override_renderable, bool):
                    msg = 'Identifier: "{}". '.format(identifier)
                    msg += 'Is Dispatching: "{}"'.format(pass_env_item.get_is_being_dispatched())
                    LOGGER.info(msg)
                    continue

                # Toggle the queued and enabled state (if required)
                if self._debug_mode:
                    msg = 'Overridding Pass For Env: "{}" '.format(identifier)
                    msg += 'To: "{}". To Prepare For Dispatching. '.format(override_renderable)
                    LOGGER.info(msg)
                pass_env_item.set_enabled(override_renderable)
                pass_env_item.set_queued(override_renderable)


    ##########################################################################
    # multishotRenderSubmitter session data resource


    def get_or_create_session_data_resource(
            self,
            project_hyref,
            oz_area=os.getenv('OZ_CONTEXT'),
            include_user=True):
        '''
        Get an existing multiShotRenderSubmitter resource or
        create for the specified project. Also copy the previous resource
        json file across to the new resource.

        Args:
            project_hyref (str):
            oz_area (str):
            include_user (bool):

        Returns:
            hydra_resource, session_path (tuple): hydra.Resource and
                session location string
        '''
        if not project_hyref:
            return None, str()

        resource_name = self.get_session_data_product_type()
        user = os.getenv('USER')
        resource_name_user = None
        if include_user and user:
            resource_name_user = resource_name + '_' + user

        # Cast project hyref to string (might be QString)
        project_hyref = str(project_hyref)

        # If file path is specified, try to get the related hyref (if any)
        is_file = os.path.isfile(project_hyref)
        if not project_hyref.startswith(('hyref://', 'urn:')) and is_file:
            project_hyref = utils.get_hyref_for_location(project_hyref)

            # Return a file path for multi shot render submitter session
            # based on project file path (if not registered in Hydra).
            if project_hyref and os.path.isfile(project_hyref):
                path_components = project_hyref.split('.')
                path_components.pop()
                path_components[0] += '_{}'.format(resource_name)
                # Add user name to snapshot file name
                if include_user:
                    path_components[0] += '_{}'.format(user)
                path_components.append(self.get_session_data_file_format())
                session_path = '.'.join(path_components)
                return None, session_path

        import hydra
        try:
            hydra_hyref = hydra.Hyref(project_hyref)
            hydra_object = hydra_hyref.getObject()
        except hydra.HydraRefException as error:
            return None, str()

        if isinstance(hydra_object, hydra.Tag):
            hydra_object = hydra_object.getVersion()

        hydra_version = None
        if isinstance(hydra_object, hydra.Resource):
            hydra_version = hydra_object.getParentVersion()
        elif isinstance(hydra_object, hydra.Product):
            if hydra_object.hasTag('published'):
                hydra_version = hydra_object.getVersionByTag('published')
            elif hydra_object.hasTag('latest'):
                hydra_version = hydra_object.getVersionByTag('latest')
        elif isinstance(hydra_object, hydra.Version):
            hydra_version = hydra_object

        if not hydra_version:
            return None, str()

        try:
            parent_product = hydra_version.getParentProduct()
            product_name = parent_product.name
            facets = parent_product.facets or dict()
            project = facets.get('project')[0]
            tree = facets.get('tree')[0]
            scene = facets.get('scene', facets.get('asset'))[0]
            shot = facets.get('shot', facets.get('variant'))[0]
            environment = '/' + '/'.join([project, tree, scene, shot])
            msg = 'Derived Environment For Session Data Resource '
            msg += 'From Project Hydra Object: "{}".'.format(environment)
            self.logMessage.emit(msg, logging.DEBUG)
        except Exception as error:
            msg = 'Could not derive environment from project hydra object. '
            msg += 'Which would have defined where to put session data resource. '
            msg += 'Will instead use environment: "{}". '.format(environment)
            # msg += 'Error: "{}". '.format(error)
            self.logMessage.emit(msg, logging.WARNING)
            return None, str()

        extra_attr = self.get_session_data_extra_attrs()

        # First check if project Product Version has user specific MSRS session
        hydra_resource = None
        hydra_resource_user = None
        if include_user and resource_name_user:
            if hydra_version.hasResource(resource_name_user):
                hydra_resource = hydra_version.getResource(resource_name_user)
                hydra_resource_user = hydra_resource
        # Then check project Product Version has MSRS session (not user).
        # NOTE: Older sessions weren't user specific.
        if not hydra_resource:
            if hydra_version.hasResource(resource_name):
                hydra_resource = hydra_version.getResource(resource_name)
        if hydra_resource:
            hydra_resource.updateAttrs(extra_attr)

        # If still haven't found the MSRS resource for project Product Version,
        # then traverse backwards through product versions until find one.
        if not hydra_resource_user:
            last_session_location = None
            hydra_product = hydra_version.getParentProduct()
            hydra_versions = hydra_product.getVersions(order=hydra.Order.Descending)
            hydra_versions.pop()
            for _hydra_version in hydra_versions:
                _hydra_resource = None
                # First check if project Product Version has user specific MSRS session
                if include_user and resource_name_user:
                    if _hydra_version.hasResource(resource_name_user):
                        _hydra_resource = _hydra_version.getResource(resource_name_user)
                # Then check project Product Version has MSRS session (not user).
                # NOTE: Older sessions weren't user specific.
                if not _hydra_resource:
                    if _hydra_version.hasResource(resource_name):
                        _hydra_resource = _hydra_version.getResource(resource_name)
                # Found last MSRS session resource which should be migrated to this project version.
                if _hydra_resource:
                    hydra_resource = _hydra_resource
                    last_session_location = hydra_resource.location
                    msg = 'Found Last Session Data Resource: "{}". '.format(last_session_location)
                    self.logMessage.emit(msg, logging.WARNING)
                    break

            # propose location to write next multiShotRenderSubmitter session data resource
            resource_location = self.get_session_data_resource_file_path(
                environment,
                product_name,
                version=hydra_version.number,
                include_user=include_user)

            # Now create the multiShotRenderSubmitter session data resource for this project version
            hydra_resource = hydra_version.createResource(
                resource_name_user or resource_name,
                resource_location,
                isDefault=False,
                expectCreate=False,
                attrs=extra_attr)

            # Copy old multiShotRenderSubmitter session data resource, into new resource
            if last_session_location and os.path.isfile(last_session_location):
                msg = 'Copying Old multiShotRenderSubmitter '
                msg += 'Session Data From: "{}". '.format(last_session_location)
                msg += 'To: "{}"'.format(resource_location)
                self.logMessage.emit(msg, logging.WARNING)
                import wetaos
                try:
                    wetaos.Path(last_session_location).copy(resource_location, force=True)
                except wetaos.WetaOSError as error:
                    msg = 'Failed To Copy Old multiShotRenderSubmitter '
                    msg += 'Session Data From: "{}". '.format(last_session_location)
                    msg += 'To: "{}". '.format(resource_location)
                    msg += 'Full Exception: "{}".'.format(traceback.format_exc())
                    self.logMessage.emit(msg, logging.CRITICAL)

        if not hydra_resource:
            return None, str()

        return hydra_resource, hydra_resource.location


    def get_session_data_extra_attrs(
            self,
            shots_to_render=list(),
            passes_to_render=list()):
        '''
        Get any extra session data attributes to add as meta data.

        Args:
            shots_to_render (list):
            passes_to_render (list):

        Returns:
            extra_attrs (dict):
        '''
        extra_attrs = dict()
        extra_attrs['Description'] = str(self.get_global_submit_description() or str())
        extra_attrs['AdditionalJobIdentifier'] = str(self.get_global_job_identifier() or str())
        if shots_to_render:
            extra_attrs['ShotsToRender'] = ','.join(sorted(list(shots_to_render)))
        if passes_to_render:
            extra_attrs['PassesToRender'] = ','.join(sorted(list(passes_to_render)))
        return extra_attrs


    def link_session_data_to_cg_products(
            self,
            session_data_hydra_object,
            hyrefs_to_cg_products,
            link_name=None):
        '''
        Setup linking required from session data to each registered Cg Product.
        Subclasses may reimplement this for different linking system.

        Args:
            session_data_hydra_object (hydra.Resource): Hydra object or hyref string
            hyrefs_to_cg_products (list): list of hyref strings

        Returns:
            link_count_added (int):
        '''
        import hydra

        if isinstance(session_data_hydra_object, str):
            session_data_hydra_object = hydra.Hyref(session_data_hydra_object).getObject()
        elif isinstance(session_data_hydra_object, hydra.Hyref):
            session_data_hydra_object = session_data_hydra_object.getObject()

        session_data_hydra_version = None
        if isinstance(session_data_hydra_object, hydra.Resource):
            session_data_hydra_version = session_data_hydra_object.getParentVersion()
        elif isinstance(session_data_hydra_object, hydra.Version):
            session_data_hydra_version = session_data_hydra_object
        elif isinstance(session_data_hydra_object, hydra.Product):
            session_data_hydra_version = session_data_hydra_object.getLatestVersion()

        if not session_data_hydra_version:
            return 0

        tool_name_camel_case = self.TOOL_NAME.title().replace(' ', str())
        link_name = link_name or tool_name_camel_case

        link_count_added = 0
        for hyref in hyrefs_to_cg_products:
            # Get the target cg Hyref
            try:
                cg_hydra_version = hydra.Hyref(hyref).getVersion()
            except (hydra.HydraRefException, AttributeError), error:
                msg = 'Failed To Get Hydra Version To Setup Linking. '
                msg += 'Hyref: {}. '.format(hyref)
                msg += 'Error: {}'.format(error)
                self.logMessage.emit(msg, logging.WARNING)
                continue

            # Add link from session data to cg Product Version
            try:
                link = session_data_hydra_version.createLink(
                    cg_hydra_version,
                    hydra.LinkType.Output,
                    name=link_name)
                if link:
                    link_count_added += 1
            except Exception, error:
                msg = 'Failed To Create Link!'
                self.logMessage.emit(msg, logging.WARNING)

        return link_count_added


    def get_session_data_resource_file_path(
            self,
            oz_area,
            product_name,
            file_format=None,
            version=None,
            include_user=True):
        '''
        Get a path for resource to point for given product name, and oz area.
        Subclasses might reimplement this for different functionality.

        Args:
            product_name (str): for example 'LightRigAgnostic'
            file_format (str): if left as None then uses current class attribute
            version (int): version number of resource file path to get. if left as None, then
                the next version is calculated based on existing version folders at
                proposed folder path.
            oz_area (str): if left as None then uses current class attribute
            include_user (bool):

        Returns:
            file_path (str):
        '''
        # Must have oz area and product name to output data file
        if not oz_area or not product_name:
            return

        # The root directory to store json depends on host app, but
        # ProductType is shared.
        product_type = self.get_session_data_product_type()
        ROOT_DIRECTORY = self.HOST_APP.title() + product_type[0].title() + product_type[1:]

        # Path to put all product version/s
        folder_path = os.path.join(
            oz_area,
            'shots',
            self.HOST_APP.lower(),
            ROOT_DIRECTORY,
            product_name)

        # Get next version from folder path if not provided
        if version == None:
            version = utils.get_next_cg_version_from_folder(folder_path) or 1
        version_str = 'v' + str(version).zfill(2)

        folder_version_path = os.path.join(folder_path, version_str)

        # Make folder path if not already existing
        if not os.path.isdir(folder_version_path):
            try:
                os.makedirs(folder_version_path)
            except OSError, error:
                msg = 'Failed To Make Directory: {}. '.format(folder_version_path)
                msg += 'Error: {}. '.format(error)
                self.logMessage.emit(msg, logging.CRITICAL)
                return

        # Get the suggested file format by this class
        if not file_format:
            file_format = self.get_session_data_file_format()

        # Get the file name (currently just based on product name)
        name = self.get_session_data_product_type()
        user = os.getenv('USER')
        area = oz_area.replace('/', '_').lstrip('_')
        if include_user and user:
            file_name = '_'.join([name, area, product_name, user])
        else:
            file_name = '_'.join([name, area, product_name])
        if version_str:
            file_name += '_{}'.format(version_str)
        file_name += '.' + str(file_format)

        return os.path.join(folder_version_path, file_name)


    def get_session_data_product_type(self):
        '''
        This is the GEN product type for all multiShotRenderSubmitter
        implementations for different host applications.
        Internal Product attributes reveal which host app this
        product was produced for.

        Returns:
            session_data_product_type (str):
        '''
        return 'multiShotRenderSubmitter'


    def get_session_data_file_format(cls):
        '''
        This is the GEN session data product type for all
        multiShotRenderSubmitter implementations for different host applications.

        Returns:
            session_data_file_format (str):
        '''
        return 'json'


    def get_session_auto_save_location(
            self,
            session_folder=None,
            oz_area=os.getenv('OZ_CONTEXT'),
            user_name=os.getenv('USER')):
        '''
        Get a path to store an auto save session which is unique
        for a particular combination of tool name, user name and
        time stamp (to second).
        Reimplement this if auto saved session needs to
        go somewhere in particular for host app.
        Note: This location must be accessible by the render wall, since
        this method is called at submission time.

        Args:
            app_name (str):
            session_folder (str): or provided automatically
            oz_area (str): if session folder not specified, then write
                session auto save file to this particular oz area
            user_name (str): session auto save file name will include the
                user who submitted the job. to make sure unique at submit time.

        Returns:
            session_path (str):
        '''
        file_prefix = self.TOOL_NAME.replace(' ', '_').lower()

        session_folder = session_folder or os.path.join(
            oz_area,
            'temp',
            'render',
            file_prefix)

        import wetaos

        if not wetaos.Path(session_folder).exists:
            try:
                wetaos.Path(session_folder).allocate()
            except OSError as error:
                msg = 'Failed To Make Directory: {}. '.format(session_folder)
                msg += 'Error: {}. '.format(error)
                self.logMessage.emit(msg, logging.WARNING)
                return False

        import srnd_qt.base.utils
        time_stamp = srnd_qt.base.utils.get_time_stamp(include_seconds=True)

        file_end = '.{}'.format(self.get_session_data_file_format())
        session_file_name = '_'.join([file_prefix, user_name, time_stamp]) + file_end

        session_path = os.path.join(session_folder, session_file_name)

        return session_path


    ##########################################################################
    # Core model


    def columnCount(self, parent_index):
        '''
        Return column count of given qmodelindex.
        Reimplemented method.

        Args:
            parent_index (QtCore.QModelIndex):

        Returns:
            column_count (int):
        '''
        return len(self.get_render_items()) + 1


    def data(self, qmodelindex, role):
        '''
        Data of the model for different roles.

        Args:
            qmodelindex (QtCore.QModelIndex):
            role (Qt.ItemDataRole):

        Returns:
            data (object): data for qmodelindex and role
        '''
        if not qmodelindex.isValid():
           return

        item = qmodelindex.internalPointer()
        c = qmodelindex.column()

        # GroupItem data roles
        if item.is_group_item():
            if role == Qt.ToolTipRole:
                msg = 'Group name: <b>"{}"</b>'.format(item.get_group_name())
                msg += '<br>Environment count: <b>"{}"</b>'.format(item.child_count())
                return msg
            if c == 0:
                if role in [Qt.DisplayRole, Qt.EditRole]:
                    return item.get_group_name()
                elif role == Qt.SizeHintRole:
                    return QSize(0, self.GROUP_HEIGHT)
                elif role == Qt.FontRole:
                    font = QFont()
                    font.setFamily(constants.FONT_FAMILY)
                    font.setBold(True)
                    font.setPixelSize(13)
                    return font
                elif role == Qt.DecorationRole:
                    return QIcon(item.get_icon_path())

        if c == 0 and role == Qt.ToolTipRole and not self._in_wait_on_interactive_mode:
            oz_area = item.get_oz_area()
            msg = 'Render environment: <b>{}</b>. ' .format(oz_area)
            msg += '<br>MSRS UUID: <b>{}</b>. ' .format(item.get_identity_id())
            msg += '<br>Renderable pass count: <b>{}</b>. '.format(
                item._get_renderable_count_for_env())
            msg += '<br>Environment index (nth version): <b>{}</b>. '.format(
                item._get_cached_environment_index())
            # msg += '<br>Environment Context: <b>{}</b>. '.format(item.get_context())

            production_range_source = item.get_production_range_source()
            label_active = str()
            if 'Cut' in production_range_source:
                label_active = ' (active)'
            msg += '<br>Cut range{}: <b>{}</b>. '.format(label_active, item.get_cut_range())

            label_active = str()
            if 'Delivery' in production_range_source:
                label_active = ' (active)'
            msg += '<br>Delivery range{}: <b>{}</b>. '.format(label_active, item.get_delivery_range())

            label_active = str()
            if 'FrameRange' in production_range_source:
                label_active = ' (active)'
            msg += '<br>Frame range{}: <b>{}</b>. '.format(label_active, item.get_frame_range())

            msg += '<br>Editorial shot status: <b>{}</b>. '.format(item.get_editorial_shot_status())
            msg += '<br>Last production data refresh: <b>{}</b>. '.format(
                item.get_production_data_last_refreshed_since_now())

            tooltip = item.get_overrides_tooltip()
            if tooltip:
                msg += '<br>' + tooltip

            msg += '<br><b>NOTE: DOUBLE CLICK TO SELECT ALL PASSES</b>'
            return msg

        elif c >= 1 and role == Qt.ToolTipRole and not self._in_wait_on_interactive_mode:
            queued =  item.get_queued()
            enabled = item.get_enabled()
            environment_item = item.get_environment_item()
            oz_area = environment_item.get_oz_area()
            render_item = item.get_source_render_item()
            render_node_name = render_item.get_node_name()
            item_full_name = render_item.get_item_full_name()
            pass_name = render_item.get_pass_name()
            msg = 'Node name: <b>{}</b>. ' .format(render_node_name)
            msg += '<br>Pass name: <b>{}</b>. ' .format(pass_name)
            msg += '<br>MSRS UUID: <b>{}</b>. ' .format(item.get_identity_id())
            if item_full_name != render_node_name:
                msg += '<br>Full item name: <b>{}</b>. ' .format(item_full_name)
            msg += '<br>Render environment: <b>{}</b>. ' .format(oz_area)
            msg += '<br>Queued: <b>{}</b>. '.format(queued)
            msg += 'Enabled: <b>{}</b>. '.format(enabled)
            estimate = item.get_render_estimate_average_frame()
            if constants.EXPOSE_RENDER_ESTIMATE and estimate:
                value = str(datetime.timedelta(seconds=int(estimate / 1000.0)))
                msg += '<br>Estimate core hours per frame: <b>{}</b>. '.format(value)
            tooltip, range_issue = item.get_frame_range_tooltip()
            if tooltip:
                msg += '<br>' + tooltip
            tooltip = item.get_overrides_tooltip()
            if tooltip:
                msg += tooltip
            return msg


    def headerData(self, section, orientation, role=Qt.DisplayRole):
        '''
        Header data for different roles and orientations.

        Args:
            section (int): column to get headerData for
            orientation (Qt.Orientation):
            role (Qt.ItemDataRole):

        Returns:
            data (object):
        '''
        if role == Qt.DisplayRole:
            if section > 0:
                try:
                    render_item = self.get_render_items()[section - 1]
                    return str(render_item.get_node_name())
                except IndexError:
                    return

        elif role == Qt.ToolTipRole:
            if section > 0:
                render_item = self.get_render_items()[section - 1]
                item_full_name = render_item.get_item_full_name()
                pass_name = render_item.get_pass_name()
                msg = 'Render node: <b>{}</b>'.format(item_full_name)
                msg += '<br>Pass name: <b>{}</b>'.format(pass_name)
                msg += '<br>MSRS UUID: <b>{}</b>'.format(render_item.get_identity_id())
                msg += '<br>Render item frame range: <b>{}</b>'.format(render_item.get_frames())
                explicit_version = render_item.get_explicit_version()
                msg += '<br>Render item explicit version: <b>{}</b>'.format(explicit_version)
                enabled = render_item.get_enabled()
                if not enabled:
                    msg += '<br>Enabled: <b>{}</b>'.format(enabled)
                renderable_count = render_item._get_renderable_count_for_render_node()
                msg += '<br>Renderable count: <b>{}</b>'.format(renderable_count)
                # node_colour = render_item.get_node_colour()
                # if node_colour:
                #     msg += '<br>Node Colour: <b>{}</b>'.format(node_colour)
                aov_names = render_item.get_aov_names()
                if aov_names:
                    msg += '<br>AOV names: <b>{}</b>'.format(aov_names)
                render_category = render_item.get_render_category()
                if render_category:
                    msg += '<br>Render category: <b>{}</b>'.format(render_category)
                other_attrs = dict(render_item.get_other_attrs() or dict())
                if other_attrs:
                    msg += '<br>Other attrs: <b>{}</b>'.format(other_attrs)

                msg += '<br><br><b>NOTE: DOUBLE CLICK TO SELECT ALL PASSES OF COLUMN</b>'
                return msg

        elif role == Qt.FontRole:
            font = QFont()
            font.setFamily(constants.FONT_FAMILY)
            if section == 0:
                font.setPixelSize(11)
                font.setBold(True)
            else:
                qmodelindex = self.index(0, section, QModelIndex())
                try:
                    render_item = self.get_render_items()[section - 1]
                except:
                    render_item = None
                if render_item and render_item._cached_width:
                    if render_item._cached_width <= 60:
                        width = 8
                    elif render_item._cached_width <= 90:
                        width = 9
                    elif render_item._cached_width <= 200:
                        width = 10
                        font.setBold(True)
                    elif render_item._cached_width <= 300:
                        width = 11
                        font.setBold(True)
                    else:
                        width = 12
                        font.setBold(True)
                    font.setPixelSize(width)
                else:
                    font.setPixelSize(11)
                    font.setBold(True)

            return font


    def setData(self, qmodelindex, value, role=Qt.EditRole):
        '''
        Data of the model for different roles.

        Args:
            qmodelindex (QtCore.QModelIndex):
            role (Qt.ItemDataRole):
        '''
        if not qmodelindex.isValid():
           return False

        item = qmodelindex.internalPointer()
        c = qmodelindex.column()

        if item.is_group_item() and role == Qt.EditRole:
            if hasattr(value, 'toString'):
                value = value.toString()
            # NOTE: Get a unique group name that doesnt yet exist
            value = utils.get_unique_name(
                value,
                existing_names=self.get_group_names())
            item.set_group_name(value)
            self.dataChanged.emit(qmodelindex, qmodelindex)
            return True

        return base_abstract_item_model.BaseAbstractItemModel.setData(
            self,
            qmodelindex,
            role)


    def flags(self, index):
        '''
        Flags for different columns.
        Reimplemented from super method.

        Args:
            index (QModelIndex):

        Returns:
            flags (int):
        '''
        flags = int()
        flags |= Qt.ItemIsEnabled
        flags |= Qt.ItemIsSelectable

        c = index.column()
        if not index.isValid():
            flags |= Qt.ItemIsDropEnabled
            return flags

        item = index.internalPointer()
        if item.is_group_item():
            flags |= Qt.ItemIsEditable
            flags |= Qt.ItemIsDragEnabled
            flags |= Qt.ItemIsDropEnabled
        else:
            if item.is_environment_item():
                flags |= Qt.ItemIsDragEnabled
        return flags


    def supportedDropActions(self):
        '''
        Tell the model which drop actions are supported.

        Returns:
            drop_action (int): int from hex from combined Qt.DropActions flags.
        '''
        return Qt.MoveAction


    def mimeData(self, indexes):
        '''
        Reimplementing mimeData to collect all Environments in selection.

        Args:
            indexes (QtCore.QModelIndexList): the indexes to be dragged

        Returns:
            mime_data (QtCore.QMimeData):
        '''
        string_list = list()
        for qmodelindex in indexes:
            if not qmodelindex.isValid():
                continue
            item = qmodelindex.internalPointer()
            if item.is_environment_item():
                string_list.append(item.get_oz_area())

        if string_list:
            from Qt.QtCore import QMimeData
            # NOTE: This gathered text mime data should not be used for dropping into MSRS main view.
            # Instead this is only used to drop environments into external applications.
            # MSRS instead rearranges items directly when dragging and dropping instead of using mime data.
            mime_data = QMimeData()
            mime_data.setText('\n'.join(string_list))
            mime_data.from_msrs = True

            return mime_data

        return base_abstract_item_model.BaseAbstractItemModel.mimeData(self, indexes)


    def clear_data(self):
        '''
        Clear the data model.
        '''
        msg = 'Clearing The Model!'
        self.logMessage.emit(msg, logging.DEBUG)

        # Reset cached values
        self._summary_view_header_data_cache = dict()

        # clear render items first (columns)
        column_count = self.columnCount(QModelIndex())
        self.beginRemoveColumns(
            QModelIndex(),
            0,
            column_count)
        self._render_items = list()
        self.endRemoveColumns()

        # Clear the primary children of models root node
        base_abstract_item_model.BaseAbstractItemModel.clear_data(self)

        # Reset additional options on model
        if isinstance(self._root_node, data_objects.RootMultiShotItem):
            self.set_version_global_system(constants.DEFAULT_CG_VERSION_SYSTEM)


    def render_item_about_to_be_removed(self, render_item):
        '''
        A RenderItem (or subclass) is about to be removed
        from model. So run any additional required cleanup.
        Requires reimplementation.

        Args:
            render_item (RenderItem): or subclass

        Returns:
            success (bool):
        '''
        return True


    def clear_render_items(self, columns=None):
        '''
        Clear render item/s from column/s.

        Args:
            columns (list):

        Returns:
            removed_count (int):
        '''
        if not columns:
            columns = range(1, self.columnCount(QModelIndex()))

        msg = 'Clear Column/s Render Items: "{}"'.format(columns)
        self.logMessage.emit(msg, logging.WARNING)

        removed_item_names = list()
        for column in reversed(sorted(columns)):
            if column == 0:
                continue

            ##################################################################
            # Remove ungrouped EnvironmentItem/s and RenderPassForEnv

            self._remove_render_items_under_qmodelindex(
                column,
                QModelIndex(), # get ungrouped environment items
                depth_limit=1) # do not traverse to grouped environment items

            ##################################################################
            # Remove grouped EnvironmentItem/s

            group_indices = self.get_group_items_indices()
            for group_qmodelindex in group_indices:
                self._remove_render_items_under_qmodelindex(
                    column,
                    group_qmodelindex)

            ##################################################################
            # Remove RenderItem from master list

            render_item = self._render_items.pop(column - 1)
            self.render_item_about_to_be_removed(render_item)
            item_full_name = render_item.get_item_full_name()
            removed_item_names.append(item_full_name)

            msg = 'Removed Render Item: "{}". '.format(item_full_name)
            self.logMessage.emit(msg, logging.WARNING)
            if self._debug_mode:
                self.logMessage.emit(str(render_item), logging.DEBUG)

        msg = 'Finished Removing Render Items: "{}"'.format(removed_item_names)
        self.logMessage.emit(msg, logging.WARNING)

        self.renderNodesRemoved.emit(removed_item_names)

        return len(removed_item_names)


    def _remove_render_items_under_qmodelindex(
            self,
            column,
            parent_index=None,
            depth_limit=2):
        '''
        Clear render item/s from column/s.

        Args:
            columns (list):
            parent_index (QModelIndex):
            depth_limit (int): how far to traverse below parent index, to find environment item indices

        Returns:
            removed (int):
        '''
        if not parent_index:
            parent_index = QModelIndex()

        removed_count = 0

        self.beginRemoveColumns(
            parent_index,
            column,
            column)

        for qmodelindex in self.get_environment_items_indices(
                    parent_index=parent_index,
                    depth_limit=depth_limit):
            if not qmodelindex.isValid():
                continue
            environment_item = qmodelindex.internalPointer()

            pass_env_item = environment_item.sibling(column)
            identifier = pass_env_item.get_identifier(nice_env_name=True)

            msg = 'Removing Pass For Env Item: "{}". '.format(identifier)
            msg += 'For Column: "{}"'.format(column)
            self.logMessage.emit(msg, logging.WARNING)

            # Take away the cached renderable count, equal to entire column cached renderables
            _render_item = pass_env_item.get_source_render_item()
            item_full_name = _render_item.get_item_full_name()

            # Update the cached renderable count for Environment item, depending if column
            # render pass for env was active or not
            modified_active_count = int(pass_env_item.get_active() or 0)
            environment_item._renderable_count_for_env -= modified_active_count
            if environment_item._renderable_count_for_env < 0:
                environment_item._renderable_count_for_env = 0
            has_renderables = bool(environment_item._renderable_count_for_env)

            # Remove the render pass for env for column (sibling of Environment item)
            node_type = pass_env_item.get_node_type()
            pass_env_item._source_render_item = None
            success = environment_item.remove_sibling(column)
            if self._debug_mode:
                msg = 'Removed "{}" for pass name: "{}". '.format(node_type, item_full_name)
                msg += 'Row: {}. Column: {}. Success: {}'.format(qmodelindex.row(), column, success)
                self.logMessage.emit(msg, logging.WARNING)

            # NOTE: Update to show environment is renderable hints
            self.environmentHasRenderables.emit(
                qmodelindex,
                has_renderables)

        self.endRemoveColumns()
        removed_count += 1

        return removed_count