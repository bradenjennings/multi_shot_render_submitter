

import datetime
import fileseq
import functools
import logging
import os

from Qt.QtGui import QIcon, QFont
from Qt.QtWidgets import (QWidget, QFrame, QSpinBox, QCheckBox,
    QToolButton, QLineEdit, QLabel, QVBoxLayout, 
    QGridLayout, QHBoxLayout, QSizePolicy)
from Qt.QtCore import Qt, QSize, Signal

import srnd_qt.base.utils
from srnd_qt.ui_framework.widgets import group_box_collapsible

from srnd_multi_shot_render_submitter.constants import Constants
constants = Constants()


##############################################################################


LABEL_RESOLVE_PREVIEW = 'Version Preview'

STYLESHEET_LINEEDIT_DISABLED = '''QLineEdit {
border-style: solid;
border-width: 0px;
color: rgb(200, 200, 200);
background-color: rgb(80, 80, 80);}'''
STYLESHEET_LINEEDIT_DISABLED_KATANA = '''QLineEdit {
border-style: solid;
border-width: 0px;
color: rgb(200, 200, 200);
background-color: rgb(70, 70, 70);}'''

ICONS_DIR = os.path.join(
    os.getenv('SRND_MULTI_SHOT_RENDER_SUBMITTER_ROOT', str()),
    'icons')
STATUS_BADGE_ICONS_DIR = os.path.join(
    ICONS_DIR,
    'details_panel_status_badges')


##############################################################################


class MultiShotDetailsWidget(QFrame):
    '''
    Widget to show resolved values of interest, and overrides for MSRS items.
    Badges can optionally be shown for overrides which allow the user 
    to easily remove the override in context of this panel, or invoke the 
    edit mode of the override, therefore opening the respective UI for editing.
    Badges are also shown for inherited overrides from the environment, and
    allow the user to easily override the value at the pass level, by setting
    a new override at this level

    Args:
        model (MultiShotRenderModel):
        show_overrides (bool):
        show_override_badges (bool):
        show_inherited_overrides (bool):
        expose_override_badges (bool):
        debug_mode (bool):
    '''

    logMessage = Signal(str, int)
    updateDetailsPanel = Signal(bool)
    updateDetailsPanelComplete = Signal()
    removeOverrideRequest = Signal(str, str)
    editOverrideRequest = Signal(str, str)

    def __init__(
            self,
            model,
            show_overrides=True,
            show_override_badges=True,
            show_inherited_overrides=True,
            expose_override_badges=True,
            debug_mode=False,
            parent=None):
        super(MultiShotDetailsWidget, self).__init__(parent=parent)

        self.setObjectName('DetailsPanel')

        self._source_model = model
        self._debug_mode = debug_mode
        self._show_overrides = bool(show_overrides)
        self._show_override_badges = bool(show_override_badges)
        self._show_inherited_overrides = bool(show_inherited_overrides)
        self._expose_override_badges = bool(expose_override_badges)
        self._auto_resolve_versions = False
        self._version_system_global = constants.DEFAULT_CG_VERSION_SYSTEM

        self._group_boxes_sections = dict()
        self._cached_states = dict()

        self.SHOW_MAX_ITEMS_DEFAULT = 4

        self._vertical_layout_main = QVBoxLayout()
        self._vertical_layout_main.setContentsMargins(4, 4, 4, 4)
        self._vertical_layout_main.setSpacing(4)
        self.setLayout(self._vertical_layout_main)
        self.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding)

        ######################################################################

        from srnd_qt.ui_framework import search_line_edit
        self._lineEdit_filter = search_line_edit.SearchLineEdit(
            include_options_menu=False)
        msg = 'Filter the details panel with string search'
        self._lineEdit_filter.setToolTip(msg)
        self._lineEdit_filter.setFixedHeight(25)
        self._lineEdit_filter.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Fixed)
        self._vertical_layout_main.addWidget(self._lineEdit_filter)

        ######################################################################

        self._build_selection_summary_widget()

        self._widget_details = QWidget()
        self._vertical_layout_details = QVBoxLayout()
        self._vertical_layout_details.setSpacing(4)
        self._vertical_layout_details.setContentsMargins(0, 0, 0, 0)
        self._widget_details.setLayout(self._vertical_layout_details)
        self._vertical_layout_main.addWidget(self._widget_details)
        self._widget_details.setVisible(False)

        self._vertical_layout_main.addStretch(100)

        # TODO: Later improve global styling system and reimplement
        # in srnd_katana_render_submitter repo
        if constants.IN_KATANA_UI_MODE:
            self.setStyleSheet(constants.STYLESHEET_FRAME_DETAILS_PANEL)
        else:
            self.setStyleSheet(constants.STYLESHEET_FRAME_DETAILS_PANEL_NO_BORDER)

        self.populate(         
            resolve_versions=False,
            only_when_visible=False)

        self._wire_events()


    def _wire_events(self):
        '''
        Main UI events to connect
        '''
        self._lineEdit_filter.searchRequest.connect(
            lambda x: self.filter_by_string(x))


    ##########################################################################


    def set_debug_mode(self, debug_mode):
        '''
        Set whether debug mode is enabled on this node and all children.

        Args:
            debug_mode (str): oz area as single string
        '''
        self._debug_mode = bool(debug_mode)


    def set_show_overrides(self, show=True):
        '''
        Set whether to show overrides or not.
        Otherwise only some resolved values are shown.

        Args:
            show (bool):
        '''
        show = bool(show)
        changed = show != self._show_overrides
        self._show_overrides = show
        if changed:
            if self._debug_mode:
                msg = 'Set show overrides: {}'.format(show)
                self.logMessage.emit(msg, logging.DEBUG)                   
            self._emit_update_details_panel()


    def set_show_override_badges(self, show=True):
        '''
        Set whether to show override badges or not and trigger populate.

        Args:
            show (bool):
        '''
        show = bool(show)
        changed = show != self._show_override_badges
        self._show_override_badges = show
        if changed:
            if self._debug_mode:
                msg = 'Set show override badges: {}'.format(show)
                self.logMessage.emit(msg, logging.DEBUG)                   
            self._emit_update_details_panel()
    

    def set_show_inherited_overrides(self, show=True):
        '''
        Set whether to show overrides inherited from environment at the render pass level.

        Args:
            show (bool):
        '''
        show = bool(show)
        changed = show != self._show_inherited_overrides
        self._show_inherited_overrides = show
        if changed:
            if self._debug_mode:
                msg = 'Set show inherited overrides: {}'.format(show)
                self.logMessage.emit(msg, logging.DEBUG)                   
            self._emit_update_details_panel()


    def set_show_selection_summary(self, show=True):
        '''
        Set whether to show selection summary within this details widget,

        Args:
            show (bool):
        '''
        show = bool(show)
        if self._debug_mode:
            msg = 'Set show selection summary: {}'.format(show)
            self.logMessage.emit(msg, logging.DEBUG)        
        self._widget_selection_summary.setVisible(show)


    def set_max_widget_count(self, count=4):
        '''
        Set whether to show override badges or not and trigger populate.

        Args:
            show (bool):
            update_details (bool):
        '''
        count = int(count)
        if self._debug_mode:
            msg = 'Set details max widget count: {}'.format(count)
            self.logMessage.emit(msg, logging.DEBUG)
        self._max_widget_count = count


    def get_expose_override_badges(self):
        '''
        Get whether to expose override badges or not.

        Returns:
            exposed (bool):
        '''
        return self._expose_override_badges


    def set_expose_override_badges(self, expose=True):
        '''
        Set whether to expose override badges or not.

        Args:
            expose (bool):
        '''
        expose = bool(expose)
        self._expose_override_badges = expose


    def get_show_override_badges(self):
        '''
        Get whether override badges or shown not.

        Returns:
            show (bool):
        '''
        return self._show_override_badges


    def get_show_inherited_overrides(self):
        '''
        Get whether to show overrides inherited from environment at the render pass level.

        Returns:
            show (bool):
        '''
        return self._show_inherited_overrides


    def get_auto_resolve_versions(self):
        '''
        Get whether auto resolve versions is enabled.

        Returns:
            auto_resolve_versions (bool):
        '''
        return self._auto_resolve_versions


    def set_auto_resolve_versions(self, auto_resolve_versions):
        '''
        Set whether auto resolve versions is enabled.

        Args:
            auto_resolve_versions (bool):
        '''
        if auto_resolve_versions == self._auto_resolve_versions:
            return

        self._auto_resolve_versions = auto_resolve_versions

        self.updateDetailsPanel.emit(self._auto_resolve_versions)


    def get_version_global_system(self):
        '''
        Get the global version system like "V+" or "VP+", or a custom version.

        Returns:
            version_global_system (str):
        '''
        return self._version_system_global


    def set_version_global_system(self, version_global_system):
        '''
        Get the global version system like "V+" or "VP+", or a custom version.

        Args:
            version_global_system (str):
        '''
        self._version_system_global = version_global_system


    def get_search_widget(self):
        '''
        Get the search filter widget.

        Returns:
            line_edit_filter (SearchLineEdit):
        '''
        return self._lineEdit_filter


    def get_content_widget_layout(self):
        '''
        Get this MultiShotDetailsWidget main layout.

        Returns:
            horizontal_layout (QVBoxLayout):
        '''
        return self._vertical_layout_main


    def clear_cached_states(self):
        '''
        Clear any cached states such as expand and collapsed of each section of this widget.
        '''
        self._cached_states = dict()


    ##########################################################################
    # Filter existing widgets


    def filter_by_string(self, filter_str):
        '''
        Filter all the widget fields and labels by value.

        Args:
            filter_str (QtCore.QString): filter by search string
        '''
        filter_str = str(filter_str or str()).lower()
        for group_box in self._widgets_fields_to_filter.keys():
            visible_count = 0
            for widget in self._widgets_fields_to_filter[group_box].keys():
                _widgets = self._widgets_fields_to_filter[group_box][widget]
                if not _widgets:
                    continue
                label = _widgets[0]
                found_hit = True
                if label:
                    found_hit = filter_str in str(label.text()).lower()
                if not found_hit and isinstance(widget, QLineEdit):
                    found_hit = filter_str in str(widget.text()).lower()
                visible_count += int(found_hit)
                widget.setVisible(found_hit)
                for _widget in _widgets:
                    _widget.setVisible(found_hit)
            group_box.setVisible(bool(visible_count))


    ##########################################################################
    # Dynamically build widgets on demand


    def _build_selection_summary_widget(self):
        '''
        Build selection summary widget to show details for selected MSRS items.
        '''
        from srnd_multi_shot_render_submitter.widgets import selection_summary_widget
        self._widget_selection_summary = selection_summary_widget.SelectionSummaryWidget(parent=self)
        self._vertical_layout_main.addWidget(self._widget_selection_summary)


    def get_selection_summary_widget(self):
        '''
        Get the selection summary widget of this lighting info widget.

        Returns:
            widget_selection_summary (SelectionSummaryWidget):
        '''
        return self._widget_selection_summary


    def populate(
            self,
            shots_selected=None,
            shots_passes_selected=None,
            resolve_versions=False,
            only_when_visible=True):
        '''
        Populate the details panel for selected passes and environments.
        NOTE: The selection summary section is peristent, while other
        widgets are dynamically destroyed and built depending on selection.

        Args:
            shots_selected (list): list of environment item
            shots_passes_selected (list): list of render pass for env items
            resolve_versions (bool): optionally force resolve versions to run.
                otherwise will use the internal auto_resolve_version member state.
            only_when_visible (bool):
        '''
        # Optimization if details widget / panel not visible, do not update
        if only_when_visible and not self.isVisible():
            msg = 'Skipping update details widget. '
            msg += 'Because not visible!'
            self.logMessage.emit(msg, logging.DEBUG)
            return

        if not shots_selected:
            shots_selected = list()
        if not shots_passes_selected:
            shots_passes_selected = list()
            
        # msg = 'Shots selected: "{}"'.format(shots_selected)
        # self.logMessage.emit(msg, logging.DEBUG)
        # msg = 'Shots passes selected: "{}"'.format(shots_passes_selected)
        # self.logMessage.emit(msg, logging.DEBUG)
        
        show_full_environments = self._source_model.get_show_full_environments()

        self.clear_details()

        # self._shot_environments_ids = set() # shot environment ids added so far
        # self._shot_environments = set() # shot environments added so far
        self._pass_for_env_ids = set() # pass ids added so far
        self._resolved_versions_for_ids = dict() # keeps track of all versions for env
        self._group_boxes_sections = dict() # mapping of msrs UUIDs to group box sections
        self._widgets_fields_to_filter = dict() # mapping of group box sections to fields, to label
        self._widget_count = 0 # number of sections added so far

        selected = set(shots_selected).union(set(shots_passes_selected))
        total_selection_count = len(selected)
        self._widget_details.setVisible(bool(total_selection_count))

        # Gather all selected string identifiers (human readable), and UUIDs
        self._widget_selection_summary.get_and_cache_identifiers_for_selection(selected)  

        # msg = 'Populating details widget from: "{}"'.format(selected)
        # self.logMessage.emit(msg, logging.DEBUG)

        # First collect details of Shot / Environment objects and add widget/s
        for i, env_item in enumerate(shots_selected):
            oz_area_id = id(env_item)
            oz_area = env_item.get_oz_area()
            # if oz_area_id in self._shot_environments_ids:
            #     continue

            # # Add a Environment / Shot info section (production data)
            # if oz_area not in self._shot_environments:
            success, group_box = self.add_shot_info_section(
                env_item,
                show_full_environments=show_full_environments)

            # Also add Environment / Shot overrides
            success, group_box = self.add_shot_overrides_section(
                env_item,
                show_full_environments=show_full_environments,
                resolve_versions=resolve_versions)

            # # Now show a section for every included pass
            # for pass_env_item in env_item.get_pass_for_env_items():
            #     # if pass_env_item.get_enabled():
            #     success, group_box = self.add_pass_for_env_section(
            #         pass_env_item,
            #         resolve_versions=resolve_versions)

        # Now collect details of per pass for environment objects and add widget/s
        for i, pass_env_item in enumerate(shots_passes_selected):
            success, group_box = self.add_pass_for_env_section(
                pass_env_item,
                resolve_versions=resolve_versions)

        # Update the version numbers of the widgets set to VP+, to max version
        if self._resolved_versions_for_ids:
            for env_id in self._resolved_versions_for_ids.keys():
                version_numbers = self._resolved_versions_for_ids[env_id].get('version_numbers', [1])
                if not version_numbers:
                    continue
                max_version = max(version_numbers)
                widgets = self._resolved_versions_for_ids[env_id].get('pass_version_widgets', list())
                for widget in widgets:
                    widget.setText('v' + str(max_version))

        ######################################################################
        # Update selection summary

        search_str = str(self._lineEdit_filter.text())
        if search_str:
            self.filter_by_string(search_str)
        
        # Update panel details now built
        self.updateDetailsPanelComplete.emit()


    def clear_details(self):
        '''
        Clear all the details from this details panel.
        '''
        srnd_qt.base.utils.clear_layout(self._vertical_layout_details)


    def add_shot_info_section(
            self,
            env_item,
            show_full_environments=False):
        '''
        Add a section to show Environment / Shot info
        for the given EnviromnmentItem.

        Args:
            env_item (EnvironmentItem):
            show_full_environments (bool):

        Returns:
            success, group_box (tuple): bool status and GroupBoxCollapsible
        '''
        # Do not show a widget when max widget count reached, or not enabled
        if self._widget_count >= self._max_widget_count:
            return False, None

        oz_area = env_item.get_oz_area()
        env_id = id(env_item)
        env_identity_id = env_item.get_identity_id()

        # # Do not show a widget, if already added Environment
        # if env_id in self._shot_environments_ids:
        #     return False, None
        # self._shot_environments_ids.add(env_id)

        # self._shot_environments.add(oz_area)

        if not show_full_environments:
            oz_area = env_item.get_scene_shot_area()
        title_str = 'Shot Info: <b>{}</b>'.format(oz_area)

        details_to_add = list()

        editorial_shot_status = env_item.get_editorial_shot_status()
        production_range_source = env_item.get_production_range_source()
        cut_range = env_item.get_cut_range()
        delivery_range = env_item.get_delivery_range()
        frame_range = env_item.get_frame_range()
        important_frames = env_item.get_important_frames()

        if editorial_shot_status:
            details = dict()
            details['info_type'] = 'Status'
            details['value'] = editorial_shot_status
            details_to_add.append(details)

        if cut_range:
            label = 'Cut range'
            if 'Cut' in production_range_source:
                label = '<b>{}</b>'.format(label)
            details = dict()
            details['info_type'] = label
            details['value'] = cut_range
            details_to_add.append(details)

        if delivery_range:
            label = 'Delivery range'
            if 'Delivery' in production_range_source:
                label = '<b>{}</b>'.format(label)
            details = dict()
            details['info_type'] = label
            details['value'] = delivery_range
            details_to_add.append(details)

        if frame_range:
            label = 'Frame range'
            if 'FrameRange' in production_range_source:
                label = '<b>{}</b>'.format(label)
            details = dict()
            details['info_type'] = label
            details['value'] = frame_range
            details_to_add.append(details)

        if important_frames:
            label = 'Important frames'
            if 'Important' in production_range_source:
                label = '<b>{}</b>'.format(label)
            details = dict()
            details['info_type'] = label
            details['value'] = str(important_frames)
            details_to_add.append(details)

        due_date = env_item.get_due_date()
        if due_date:
            details = dict()
            details['info_type'] = 'Due date'
            details['value'] = env_item.get_due_date()
            details_to_add.append(details)

        datetime_str = env_item.get_production_data_last_refreshed_since_now()
        if datetime_str:
            details = dict()
            details['info_type'] = 'Last production data refresh'
            details['value'] = datetime_str
            details_to_add.append(details)

        section_type = 'shot_info'

        # Get or choose collapsed
        collapsed = None
        details_section_id = env_identity_id + '_' + section_type
        if details_section_id in self._cached_states:
            collapsed = self._cached_states[details_section_id].get('collapsed')
        if collapsed == None:
            collapsed = self._widget_count >= int(self._max_widget_count / 2.0)
        self._cached_states[details_section_id] = dict()
        self._cached_states[details_section_id]['collapsed'] = collapsed

        group_box, _widgets_to_update = self._add_details_section(
            title_str,
            details_to_add,
            section_type=section_type,
            collapsed=collapsed,
            msrs_uuid=env_identity_id)

        return True, group_box


    def add_shot_overrides_section(
            self,
            env_item,
            show_full_environments=False,
            resolve_versions=False):
        '''
        Add a section to show Environment / Shot overrides
        for the given EnviromnmentItem.

        Args:
            env_item (EnvironmentItem):
            show_full_environments (bool):
            resolve_versions (bool):

        Returns:
            success, group_box (tuple): bool status and GroupBoxCollapsible
        '''
        enabled = env_item.get_enabled()
        env_id = id(env_item)
        env_identity_id = env_item.get_identity_id()

        if self._widget_count >= self._max_widget_count or not enabled:
            return False, None

        if show_full_environments:
            oz_area = env_item.get_oz_area()
        else:
            oz_area = env_item.get_scene_shot_area()

        details_to_add = list()

        ######################################################################
        # Resolve the highest version for entire environment.
        # NOTE: Use any pre cached versions for pass for environments.

        new_id = env_id not in self._resolved_versions_for_ids
        if new_id:
            self._resolved_versions_for_ids[env_id] = dict()
            self._resolved_versions_for_ids[env_id]['version_numbers'] = list()
            self._resolved_versions_for_ids[env_id]['pass_version_widgets'] = list()

        auto_resolve_versions = self.get_auto_resolve_versions()
        do_resolve_version = enabled and new_id
        do_resolve_version = do_resolve_version and (auto_resolve_versions or resolve_versions)
        resolved_version_number, version_numbers = (None, list())
        if do_resolve_version:
            if self._debug_mode:
                msg = 'Resolving Version For Environment: "{}".'.format(oz_area)
                self.logMessage.emit(msg, logging.DEBUG)
            # Resolve or get the pre resolved per pass version
            for _pass_env_item in env_item.get_pass_for_env_items():
                identifier = _pass_env_item.get_identifier()
                version_number = _pass_env_item.resolve_version(
                    cache_values=False,
                    collapse_version_overrides=False)
                self._resolved_versions_for_ids[env_id]['version_numbers'].append(version_number)
                if self._debug_mode:
                    msg = 'Resolving Version For Identifier (From Env): "{}". '.format(identifier)
                    msg += 'Version: "{}"'.format(version_number)
                    self.logMessage.emit(msg, logging.DEBUG)
                if version_number:
                    version_numbers.append(version_number)
        elif not new_id:
            version_numbers = self._resolved_versions_for_ids[env_id].get('version_numbers')
        if version_numbers:
            resolved_version_number = max(version_numbers)

        ######################################################################

        version_override = env_item.get_version_override()
        if do_resolve_version and resolved_version_number:
            details = dict()
            details['info_type'] = 'Max Version Preview'
            details['value'] = 'v' + str(resolved_version_number)
            details_to_add.append(details)

        ######################################################################
        # Get and add all frame override details for environment item
        
        if self._show_overrides:
            _details_to_add, _ids_added = self.get_frame_overrides_details_for_item(env_item)
            if _details_to_add:
                details_to_add.extend(_details_to_add)

            ######################################################################
            # Get and add all other overrides details for environment item

            _details_to_add, _ids_added = self.get_other_overrides_details_for_item(env_item)
            if _details_to_add:
                details_to_add.extend(_details_to_add)

            ######################################################################

            job_identifier = env_item.get_job_identifier()
            if job_identifier:
                details = dict()
                details['info_type'] = 'Job Identifier'
                details['value'] = job_identifier
                details['override_id'] = constants.OVERRIDE_JOB_IDENTIFIER
                details_to_add.append(details)

            koba_shotsub = env_item.get_koba_shotsub()
            if koba_shotsub:
                details = dict()
                details['info_type'] = 'Koba Shotsub'
                details['value'] = koba_shotsub
                details_to_add.append(details)

        ######################################################################
        # Get and add all render overrides details for environment item
        
        _details_to_add, _ids_added = self.get_render_override_section_details(env_item)
        if _details_to_add:
            details_to_add.extend(_details_to_add)

        ######################################################################

        dispatcher_plow_job_id = env_item.get_dispatcher_plow_job_id()
        if dispatcher_plow_job_id:
            details = dict()
            details['info_type'] = 'Last Dispatcher Plow Job Id'
            details['value'] = dispatcher_plow_job_id
            details_to_add.append(details)

        ######################################################################
       
        # if not details_to_add:
        #     return False, None

        title_str = 'Shot Overrides: <b>{}</b>'.format(oz_area)
        env_index = env_item._get_cached_environment_index()
        job_identifier = env_item.get_job_identifier()
        if job_identifier:
            title_str += ' <i>({})</i>'.format(job_identifier)
        elif env_index:
            title_str += ' <i>({})</i>'.format(env_index)

        section_type = 'environment'

        # Get or choose collapsed
        collapsed = None
        details_section_id = env_identity_id + '_' + section_type
        if details_section_id in self._cached_states:
            collapsed = self._cached_states[details_section_id].get('collapsed')
        if collapsed == None:
            collapsed = self._widget_count >= int(self._max_widget_count / 2.0)
        self._cached_states[details_section_id] = dict()
        self._cached_states[details_section_id]['collapsed'] = collapsed

        group_box, _widgets_to_update = self._add_details_section(
            title_str,
            details_to_add,
            collapsed=collapsed,
            section_type=section_type,
            msrs_uuid=env_identity_id)

        return True, group_box


    def add_pass_for_env_section(
            self,
            pass_env_item,
            resolve_versions=False,
            show_full_environments=None):
        '''
        Add a section to show pass overrides for the given PassForEnvItem.

        Args:
            pass_env_item (PassForEnvItem):
            resolve_versions (bool): optionally force resolve versions to run.
                otherwise will use the internal auto_resolve_version member state.
            show_full_environments (bool):

        Returns:
            success, group_box (tuple): bool status and GroupBoxCollapsible
        '''
        env_item = pass_env_item.get_environment_item()
        render_item = pass_env_item.get_source_render_item()
        if not any([env_item, render_item]):
            msg = 'Failed to show details for: {}'.format(pass_env_item)
            self.logMessage.emit(msg, logging.CRITICAL)
            return False, None

        active = pass_env_item.get_active()
        enabled = pass_env_item.get_enabled()
        resolved_frames = pass_env_item.get_resolved_frames_queued()

        oz_area = env_item.get_oz_area()
        split_frame_ranges = env_item.get_split_frame_ranges()
        env_id = id(env_item)
        pass_id = id(pass_env_item)
        pass_identity_id = pass_env_item.get_identity_id()
        identifier = pass_env_item.get_identifier()

        if env_id not in self._resolved_versions_for_ids:
            self._resolved_versions_for_ids[env_id] = dict()
            self._resolved_versions_for_ids[env_id]['version_numbers'] = list()
            self._resolved_versions_for_ids[env_id]['pass_version_widgets'] = list()

        new_pass_id = pass_id not in self._pass_for_env_ids
        self._pass_for_env_ids.add(pass_id)

        # Update the resolved version system (if not already resolved)
        auto_resolve_versions = self.get_auto_resolve_versions()
        do_resolve_version = enabled and new_pass_id
        do_resolve_version = do_resolve_version and (auto_resolve_versions or resolve_versions)
        resolved_version_number, version_numbers = (None, list())
        if do_resolve_version:
            version_number = pass_env_item.resolve_version(
                cache_values=False,
                collapse_version_overrides=False)
            self._resolved_versions_for_ids[env_id]['version_numbers'].append(version_number)
            if self._debug_mode:
                msg = 'Resolving Version For Identifier: "{}". '.format(identifier)
                msg += 'Version: "{}"'.format(version_number)
                self.logMessage.emit(msg, logging.DEBUG)
            resolved_version_number = version_number
        else:
            version_numbers = self._resolved_versions_for_ids[env_id].get(
                'version_numbers')
        if version_numbers:
            resolved_version_number = max(version_numbers)

        # Do not show a widget when max widget count reached, or not enabled
        if self._widget_count >= self._max_widget_count or not enabled:
            return False, None

        # Do not show a widget, if already added from selected Environments
        if not new_pass_id:
            return False, None

        root_item = env_item.get_root_item()

        # If show full environments not specified, get it now from root item
        if show_full_environments == None:
            show_full_environments = root_item.get_show_full_environments()

        pass_name = render_item.get_pass_name()
        item_full_name = render_item.get_item_full_name()
        if show_full_environments:
            env_label = env_item.get_oz_area()
        else:
            env_label = env_item.get_scene_shot_area()
        pass_title_str = '{} - <b>{}</b>'.format(env_label, pass_name)

        details_to_add = list()
        resolved_version_system = str(pass_env_item.get_resolved_version_system())

        ######################################################################

        details = dict()
        details['info_type'] = 'Resolved frames'
        details['value'] = str(resolved_frames)
        details_to_add.append(details)

        if do_resolve_version and resolved_version_number:
            details = dict()
            details['info_type'] = LABEL_RESOLVE_PREVIEW
            details['value'] = 'v' + str(resolved_version_number)
            details_to_add.append(details)

        estimate = pass_env_item.get_render_estimate_average_frame()
        if constants.EXPOSE_RENDER_ESTIMATE and estimate:
            details = dict()
            if constants.PREFER_ESTIMATE_CORE_HOURS:
                details['info_type'] = 'Estimate core hours per frame'
            else:
                details['info_type'] = 'Estimate hours per frame'
            # details['value'] = str(pass_env_item.get_render_estimate_core_hours()) # all active frames
            details['value'] = str(datetime.timedelta(seconds=int(estimate / 1000.0))) # one frame
            details_to_add.append(details)

        ######################################################################

        # Get and add all frame override details for pass for env item
        if self._show_overrides:
            _details_to_add, _ids_added_frames = self.get_frame_overrides_details_for_item(pass_env_item)
            if _details_to_add:
                details_to_add.extend(_details_to_add)

            ######################################################################

            # Get and add all other overrides details for pass for env item
            _details_to_add, _ids_added_other = self.get_other_overrides_details_for_item(pass_env_item)
            if _details_to_add:
                details_to_add.extend(_details_to_add)

            ######################################################################

            # Get and add all render overrides details for pass for env item
            _details_to_add, _ids_added_render_overrides = self.get_render_override_section_details(pass_env_item)
            if _details_to_add:
                details_to_add.extend(_details_to_add)

        ######################################################################

        plow_job_id_last = pass_env_item.get_plow_job_id_last()
        if plow_job_id_last:
            details = dict()
            details['info_type'] = 'Last plow job id'
            details['value'] = plow_job_id_last
            details_to_add.append(details)

        plow_layer_id_last = pass_env_item.get_plow_layer_id_last()
        if plow_layer_id_last:
            details = dict()
            details['info_type'] = 'Last plow layer id'
            details['value'] = plow_layer_id_last
            details_to_add.append(details)

        plow_task_ids_last = pass_env_item.get_plow_task_ids_last()
        if plow_task_ids_last:
            details = dict()
            details['info_type'] = 'Last plow task ids'
            details['value'] = plow_task_ids_last
            details_to_add.append(details)

        dispatcher_plow_job_id = pass_env_item.get_dispatcher_plow_job_id()
        if dispatcher_plow_job_id:
            details = dict()
            details['info_type'] = 'Last dispatcher plow job id'
            details['value'] = dispatcher_plow_job_id
            details_to_add.append(details)

        if item_full_name != render_item.get_node_name():
            details = dict()
            details['info_type'] = 'Full name'
            details['value'] = item_full_name
            details['tooltip'] = item_full_name
            details_to_add.append(details)

        ######################################################################
        # Show inherited overrides

        if self._show_inherited_overrides:
            # Get and add all frame override details inherited from environment
            _details_to_add, _ids_added = self.get_frame_overrides_details_for_item(
                env_item,
                prefix='Inherited',
                inherited=True,
                exclude_ids=_ids_added_frames)
            if _details_to_add:
                details_to_add.extend(_details_to_add)

            # Get and add all other overrides details inherited from environment
            _details_to_add, _ids_added = self.get_other_overrides_details_for_item(
                env_item,
                prefix='Inherited',
                inherited=True,
                exclude_ids=_ids_added_other)
            if _details_to_add:
                details_to_add.extend(_details_to_add)

            # Get and add all render overrides details inherited from environment
            _details_to_add, _ids_added = self.get_render_override_section_details(
                env_item,
                prefix='Inherited',
                inherited=True,
                exclude_ids=_ids_added_render_overrides)
            if _details_to_add:
                details_to_add.extend(_details_to_add)

        ######################################################################

        # if not details_to_add:
        #     return False, None

        section_type = 'pass'

        # Get or choose collapsed
        collapsed = None
        details_section_id = pass_identity_id + '_' + section_type
        if details_section_id in self._cached_states:
            collapsed = self._cached_states[details_section_id].get('collapsed')
        if collapsed == None:
            collapsed = self._widget_count >= int(self._max_widget_count / 2.0)
        self._cached_states[details_section_id] = dict()
        self._cached_states[details_section_id]['collapsed'] = collapsed

        group_box_pass_overrides, _widgets_to_update = self._add_details_section(
            pass_title_str,
            details_to_add,
            collapsed=collapsed,
            section_type=section_type,
            msrs_uuid=pass_identity_id)

        if do_resolve_version and resolved_version_system == constants.CG_VERSION_SYSTEM_PASSES_NEXT:
            self._resolved_versions_for_ids[env_id]['pass_version_widgets'].extend(
                _widgets_to_update)

        ##################################################################

        # # Add an environment info section for production data
        # if oz_area not in self._shot_environments:
        #     self.add_shot_info_section(
        #         env_item,
        #         show_full_environments=show_full_environments)

        return True, group_box_pass_overrides


    ##########################################################################
    # Gather overrides into lists of dict to build widgets for


    def get_frame_overrides_details_for_item(
            self,
            item,
            prefix=None,
            inherited=False,
            exclude_ids=None):
        '''
        Gather frame override details for item.

        Args:
            item (OverrideBaseItem): render pass for env or environment item
            prefix (str):
            inherited (bool):
            exclude_ids (list):

        Returns:
            return details_to_add, ids_added
        '''
        if not prefix:
            prefix = str()
        else:
            prefix += ' '
        ids_added = list()
        if not exclude_ids:
            exclude_ids = list()
        details_to_add = list()

        override_id = constants.OVERRIDE_FRAMES_CUSTOM
        frame_range_override = item.get_frame_range_override()
        if frame_range_override and not override_id in exclude_ids:
            details = dict()
            details['info_type'] = '{}Custom Frames'.format(prefix)
            details['value'] = frame_range_override
            details['override_id'] = override_id
            details_to_add.append(details)
            ids_added.append(override_id)

        override_id = constants.OVERRIDE_FRAMES_FML
        fml = item.get_frames_rule_fml()
        if fml and not override_id in exclude_ids:
            details = dict()
            details['info_type'] = '{}FML'.format(prefix)
            details['value'] = True
            details['override_id'] = override_id
            details_to_add.append(details)
            ids_added.append(override_id)

        override_id = constants.OVERRIDE_FRAMES_X1
        x1 = item.get_frames_rule_x1()
        if x1 and not override_id in exclude_ids:
            details = dict()
            details['info_type'] = '{}x1'.format(prefix)
            details['value'] = True
            details['override_id'] = override_id
            details_to_add.append(details)
            ids_added.append(override_id)

        override_id = constants.OVERRIDE_FRAMES_X10
        x10 = item.get_frames_rule_x10()
        if x10 and not override_id in exclude_ids:
            details = dict()
            details['info_type'] = '{}x10'.format(prefix)
            details['value'] = True
            details['override_id'] = override_id
            details_to_add.append(details)
            ids_added.append(override_id)

        override_id = constants.OVERRIDE_FRAMES_XCUSTOM
        xn = item.get_frames_rule_xn()
        if xn and not override_id in exclude_ids:
            details = dict()
            details['info_type'] = '{}xN'.format(prefix)
            details['value'] = xn
            details['override_id'] = override_id
            details_to_add.append(details)
            ids_added.append(override_id)

        override_id = constants.OVERRIDE_FRAMES_IMPORTANT
        important_frames = item.get_frames_rule_important()
        if important_frames and not override_id in exclude_ids:
            details = dict()
            details['info_type'] = '{}Important Frames'.format(prefix)
            details['value'] = important_frames
            details['override_id'] = override_id
            details_to_add.append(details)
            ids_added.append(override_id)

        ######################################################################

        override_id = constants.OVERRIDE_FRAMES_NOT_CUSTOM
        not_frame_range_override = item.get_not_frame_range_override()
        if not_frame_range_override and not override_id in exclude_ids:
            details = dict()
            details['info_type'] = '{}Custom NOT Frames'.format(prefix)
            details['value'] = not_frame_range_override
            details['override_id'] = override_id
            details_to_add.append(details)
            ids_added.append(override_id)

        override_id = constants.OVERRIDE_FRAMES_NOT_FML
        not_fml = item.get_not_frames_rule_fml()
        if not_fml and not override_id in exclude_ids:
            details = dict()
            details['info_type'] = '{}NOT FML'.format(prefix)
            details['value'] = True
            details['override_id'] = override_id
            details_to_add.append(details)
            ids_added.append(override_id)

        override_id = constants.OVERRIDE_FRAMES_NOT_X10
        not_x10 = item.get_not_frames_rule_x10()
        if not_x10 and not override_id in exclude_ids:
            details = dict()
            details['info_type'] = '{}NOT x10'.format(prefix)
            details['value'] = True
            details['override_id'] = override_id
            details_to_add.append(details)
            ids_added.append(override_id)

        override_id = constants.OVERRIDE_FRAMES_NOT_XCUSTOM
        not_xn = item.get_not_frames_rule_xn()
        if not_xn and not override_id in exclude_ids:
            details = dict()
            details['info_type'] = '{}NOT xN'.format(prefix)
            details['value'] = not_xn
            details['override_id'] = override_id
            details_to_add.append(details)
            ids_added.append(override_id)

        override_id = constants.OVERRIDE_FRAMES_NOT_IMPORTANT
        not_important_frames = item.get_not_frames_rule_important()
        if not_important_frames and not override_id in exclude_ids:
            details = dict()
            details['info_type'] = '{}Not Important Frames'.format(prefix)
            details['value'] = not_important_frames
            details['override_id'] = override_id
            details_to_add.append(details)
            ids_added.append(override_id)
        
        # Do not show split frame job as inherited 
        if item.is_environment_item() and not inherited:
            split_frame_ranges = item.get_split_frame_ranges()
            if split_frame_ranges and not override_id in exclude_ids:
                # split_frame_ranges_list = env_item.get_split_frame_to_job_type_list()
                details = dict()
                details['info_type'] = 'Split Frame Job'
                details['value'] = split_frame_ranges
                details['override_id'] = constants.OVERRIDE_SPLIT_FRAME_RANGES
                details_to_add.append(details)

        # Mark all details as inherited
        if inherited:
            for details in details_to_add:
                details['inherited'] = True

        return details_to_add, ids_added


    def get_other_overrides_details_for_item(
            self,
            item,
            prefix=None,
            inherited=False,
            exclude_ids=None):
        '''
        Gather other override details for item.

        Args:
            item (OverrideBaseItem): render pass for env or environment item
            prefix (str):
            inherited (bool):
            exclude_ids (list):

        Returns:
            details_to_add, ids_added (tuple):
        '''
        if not prefix:
            prefix = str()
        else:
            prefix += ' '
        ids_added = list()
        if not exclude_ids:
            exclude_ids = list()
        details_to_add = list()

        override_id = 'Version'
        version_override = item.get_version_override()
        if version_override and not override_id in exclude_ids:
            details = dict()
            details['info_type'] = '{}Version Override'.format(prefix)
            details['value'] = version_override
            details['override_id'] = override_id
            details_to_add.append(details)
            ids_added.append(override_id)

        override_id = constants.OVERRIDE_NOTE
        note_override = item.get_note_override()
        if note_override and not override_id in exclude_ids:
            details = dict()
            details['info_type'] = '{}Note'.format(prefix)
            details['value'] = note_override
            details['override_id'] = override_id
            details_to_add.append(details)
            ids_added.append(override_id)

        override_id = constants.OVERRIDE_WAIT
        wait_on = item.get_wait_on()
        if wait_on and not override_id in exclude_ids and not inherited:
            _identifiers = self._source_model.get_wait_on_identifiers(item)
            _identifiers = ' '.join(_identifiers)
            details = dict()
            details['info_type'] = '{}Depends On'.format(prefix)
            details['value'] = _identifiers
            details['override_id'] = override_id
            details_to_add.append(details)
            ids_added.append(override_id)

        display_values = self._source_model.get_wait_on_plow_ids_display_string(item)
        if display_values and not override_id in exclude_ids:
            details = dict()
            details['info_type'] = '{}Depends On Plow'.format(prefix)
            details['value'] = str(display_values)
            details['override_id'] = override_id
            details_to_add.append(details)
            ids_added.append(override_id)

        post_tasks = item.get_post_tasks()
        if post_tasks and not inherited:
            details = dict()
            details['info_type'] = '{}Post Task/s'.format(prefix)
            # NOTE: list of OrderedDict with unicode key /values looks messy for 
            # display purposes, so cast to clean dict.
            post_tasks_clean = list()
            # Display value for post tasks is simplified
            post_tasks_display = list()
            for post_task in post_tasks:
                _post_task = dict()
                name = post_task.get('name')
                post_tasks_display.append(str(name))
                # _type = post_task.get('type')
                # if name and _type:
                #     post_tasks_display[str(_type)] = str(name)
                for key, value in post_task.iteritems():
                    _post_task[str(key)] = str(value)
                post_tasks_clean.append(_post_task)
            details['value'] = ', '.join(post_tasks_display)
            details['tooltip'] = str(post_tasks_clean)
            # details['value'] = str(post_tasks_display)
            details_to_add.append(details)

        # Mark all details as inherited
        if inherited:
            for details in details_to_add:
                details['inherited'] = True

        return details_to_add, ids_added


    def get_render_override_section_details(
            self,
            item,
            prefix=None,
            inherited=False,
            exclude_ids=None):
        '''
        Gather render overrides details list from render pass for env or environment item.

        Args:
            override_base_item (OverrideBaseItem): render pass for env or environment item subclass
            prefix (str):
            inherited (bool):
            exclude_ids (list):

        Returns:
            details_to_add, ids_added (tuple):
        '''
        if not any([item.is_environment_item(), item.is_pass_for_env_item()]):
            return list(), list()

        if not prefix:
            prefix = str()
        else:
            prefix += ' '
        ids_added = list()
        if not exclude_ids:
            exclude_ids = list()
        details_to_add = list()

        render_overrides_items = item.get_render_overrides_items()
        for override_id in render_overrides_items.keys():
            if override_id in exclude_ids:
                continue
            render_override_item = render_overrides_items[override_id]
            override_type = render_override_item.get_override_type()
            override_value = render_override_item.get_value()
            override_category = render_override_item.get_override_category()
            override_label = render_override_item.get_override_label()
            override_acronym = render_override_item.get_override_acronym()
            override_description = render_override_item.get_override_description()
            author = render_override_item.get_author()
            author_department = render_override_item.get_author_department()
            tooltip = 'Render Override: "<b>{}</b>"'.format(override_label)
            tooltip += '<br>Type: "<b>{}</b>"'.format(override_type)
            tooltip += '<br>Value: "<b>{}</b>"'.format(override_value)
            tooltip += '<br>Id: "<b>{}</b>"'.format(override_id)
            if override_category:
                tooltip += '<br>Category: "<b>{}</b>"'.format(override_category)
            if override_acronym:
                tooltip += '<br>Acronym: "<b>{}</b>"'.format(override_acronym)
            if author:
                tooltip += '<br>Author: "<b>{}</b>"'.format(author)
            if author_department:
                tooltip += '<br>Author Department: "<b>{}</b>"'.format(author_department)
            if override_description:
                tooltip += '<br>Override Description:<br>"<b>{}</b>"'.format(override_description)
            details = dict()
            details['info_type'] = '{}{}'.format(prefix, override_label)
            # NOTE: In case value is OrderedDict instead of dict, show it as dict
            if isinstance(override_value, dict):
                override_value = dict(override_value)
            details['value'] = override_value
            details['tooltip'] = tooltip
            details['override_id'] = override_id
            details_to_add.append(details)
            ids_added.append(override_id)

        # Mark all details as inherited
        if inherited:
            for details in details_to_add:
                details['inherited'] = True

        return details_to_add, ids_added


    ##########################################################################


    def _add_details_section(
            self,
            title_str,
            details_to_add,
            collapsed=False,
            section_type='details',
            msrs_uuid=None):
        '''
        Add a details section to this details widget.

        Args:
            title_str (str):
            details_to_add (list):
            collapsed (bool):
            section_type (str):
            msrs_uuid (str):

        Returns:
            group_box, widgets_to_update (tuple):
        '''
        grid_layout = QGridLayout()

        group_box = group_box_collapsible.GroupBoxCollapsible(
            title_str=title_str,
            collapsed=collapsed,
            closeable=False,
            layout=grid_layout,
            content_margin=4,
            auto_expand_parent=False)
        group_box.details_section_id = str()
        if all([msrs_uuid, section_type]):
            group_box.details_section_id = msrs_uuid + '_' + section_type

        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_layout.setSpacing(2)

        line_edit_widget = group_box.get_title_widget()
        font = line_edit_widget.font()
        font.setFamily(constants.FONT_FAMILY)
        font.setPointSize(8)
        font.setBold(False)
        line_edit_widget.setFont(font)

        # TODO: Later improve global styling system and reimplement
        # in srnd_katana_render_submitter repo
        if constants.IN_KATANA_UI_MODE:
            group_box.set_header_style(
                group_box_collapsible.STYLESHEET_GROUP_BOX_HEADER_70)
            group_box.set_group_box_style(
                constants.STYLESHEET_GROUPBOX_DETAILS_PANEL_BORDER)
        else:
            group_box.set_dark_stylesheet()

        self._vertical_layout_details.addWidget(group_box)

        self._widgets_fields_to_filter[group_box] = dict()

        widgets_to_update = list()
        for i in range(0, len(details_to_add), 1):
            info_type = details_to_add[i].get('info_type')
            if not info_type:
                continue
            value = details_to_add[i].get('value')
            tooltip = details_to_add[i].get('tooltip') or str(value)
            override_id = details_to_add[i].get('override_id')
            inherited = details_to_add[i].get('inherited', False)

            column = 0

            toolButton_status_badge = None
            if self._show_override_badges and self._expose_override_badges:
                if all([section_type, override_id, msrs_uuid]):
                    toolButton_status_badge = QToolButton()
                    msg = 'Click to open menu to remove this override. '
                    msg += '<br><i>Label: <b>{}</b></i>'.format(info_type)
                    msg += '<br><i>Override id: <b>{}</b></i>'.format(override_id)
                    msg += '<br><i>Value: <b>{}</b></i>'.format(value)
                    msg += '<br><i>Is inherited: <b>{}</b></i>'.format(inherited)
                    toolButton_status_badge.setToolTip(msg)
                    toolButton_status_badge.setAutoRaise(True)
                    toolButton_status_badge.setIconSize(QSize(18, 18))
                    toolButton_status_badge.setFixedSize(18, 18)
                    if section_type == 'environment' or inherited:
                        if inherited:
                            icon = QIcon(os.path.join(
                                STATUS_BADGE_ICONS_DIR,
                                'msrs_detail_panel_environment_inherited_s01.png'))
                        else:
                            icon = QIcon(os.path.join(
                                STATUS_BADGE_ICONS_DIR,
                                'msrs_detail_panel_environment_s01.png'))
                    else:
                        if inherited:
                            icon = QIcon(os.path.join(
                                STATUS_BADGE_ICONS_DIR,
                                'msrs_detail_panel_pass_inherited_s01.png'))
                        else:
                            icon = QIcon(os.path.join(
                                STATUS_BADGE_ICONS_DIR,
                                'msrs_detail_panel_pass_s01.png'))
                    toolButton_status_badge.setIcon(icon)
                    grid_layout.addWidget(toolButton_status_badge, i, column)
                    column += 1
                    toolButton_status_badge.setContextMenuPolicy(Qt.CustomContextMenu)

                    method_to_call = functools.partial(
                        self._create_context_menu_status_badge,
                        section_type=section_type,
                        inherited=bool(inherited),
                        override_id=str(override_id),
                        msrs_uuid=str(msrs_uuid))
                    toolButton_status_badge.customContextMenuRequested.connect(method_to_call)
                    toolButton_status_badge.clicked.connect(method_to_call)
                # Add placeholder widget to keep other columns inline with status badges
                elif section_type:
                    grid_layout.addWidget(QWidget(), i, column)
                    column += 1

            label_info_type = QLabel(info_type)
            label_info_type.setTextInteractionFlags(Qt.TextSelectableByMouse)
            label_info_type.setFont(constants.PANEL_FONT_REGULAR)
            if tooltip:
                label_info_type.setToolTip(tooltip)
            grid_layout.addWidget(label_info_type, i, column)
            column += 1
            
            _value = str(value)
            # Prefer not to show simple True boolean value, instead show empty string
            if isinstance(value, bool) and value:
                _value = str()

            widget = QLineEdit(_value)
            if tooltip:
                widget.setToolTip(tooltip)
            widget.setFixedHeight(18)
            widget.setReadOnly(True)
            if constants.IN_KATANA_UI_MODE:
                widget.setStyleSheet(STYLESHEET_LINEEDIT_DISABLED_KATANA)
            else:
                widget.setStyleSheet(STYLESHEET_LINEEDIT_DISABLED)
            widget.setCursorPosition(0)
            grid_layout.addWidget(widget, i, column)
            column += 1

            # Update list of widgets to update later with highest version
            if info_type == LABEL_RESOLVE_PREVIEW:
                widgets_to_update.append(widget)
            widgets = [label_info_type]
            if toolButton_status_badge:
                widgets.append(toolButton_status_badge)
            self._widgets_fields_to_filter[group_box][widget] = widgets

        self._widget_count += 1

        if msrs_uuid:
            self._group_boxes_sections[msrs_uuid] = group_box
            group_box.toggled.connect(self._update_section_cached_states)

        return group_box, widgets_to_update


    def _update_section_cached_states(self, visible):
        '''
        Update cache details for single section such as collapsed and expanded states.
        '''
        group_box = self.sender()
        if not group_box or not hasattr(group_box, 'details_section_id'):
            return
        details_section_id = group_box.details_section_id
        cached_states = dict()
        cached_states[details_section_id] = dict()
        cached_states[details_section_id]['collapsed'] = visible
        self._cached_states.update(cached_states)
        # msg = 'Updated Sections Cached States From: "{}"'.format(cached_states)
        # self.logMessage.emit(msg, logging.INFO)


    def _create_context_menu_status_badge(
            self,
            pos=None,
            show=True,
            section_type=None,
            inherited=False,
            override_id=None,
            msrs_uuid=None):
        '''
        Build a QMenu for status badges.

        Args:
            pos (QPoint):
            show (bool): show the menu after populating or not
            section_type (str):
            inherited (bool):
            override_id (str):
            msrs_uuid (str):

        Returns:
            menu (QtGui.QMenu):
        '''
        from Qt.QtWidgets import QMenu
        import srnd_qt.base.utils

        menu = QMenu('Status Badges Menu', self)

        font_italic = QFont()
        font_italic.setFamily(constants.FONT_FAMILY)
        font_italic.setItalic(True)

        action = srnd_qt.base.utils.context_menu_add_menu_item(
            self,
            'Modify Override')
        action.setFont(font_italic)
        menu.addAction(action)

        render_overrides_manager = self._source_model.get_render_overrides_manager()
        render_overrides_plugins_ids = render_overrides_manager.get_render_overrides_plugins_ids()
        is_render_override = override_id in render_overrides_plugins_ids

        if section_type == 'environment':
            if is_render_override:
                label = '{} environment render override'
            else:
                label = '{} environment override'
        else:
            if is_render_override:
                label = '{} pass render override'
            else:
                label = '{} pass override'

        if inherited:
            action = srnd_qt.base.utils.context_menu_add_menu_item(
                self,
                'Set Override At Pass Level')
            method_to_call = functools.partial(
                self._emit_edit_override,
                str(override_id),
                str(msrs_uuid))
            action.triggered.connect(method_to_call)
            menu.addAction(action)
        else:
            # Remove override action
            _label = label.format('Remove')
            action = srnd_qt.base.utils.context_menu_add_menu_item(
                self,
                _label,
                icon_path=os.path.join(ICONS_DIR, 'delete_s01.png'))
            method_to_call = functools.partial(
                self._emit_remove_override,
                str(override_id),
                str(msrs_uuid))
            action.triggered.connect(method_to_call)
            menu.addAction(action)

            # Edit override action
            can_edit = bool(is_render_override)
            if not can_edit:
                can_edit = self._source_model.check_override_is_editable(override_id)
            if can_edit:
                _label = label.format('Edit')
                action = srnd_qt.base.utils.context_menu_add_menu_item(
                    self, 
                    _label,
                    icon_path=os.path.join(ICONS_DIR, 'edit_s01.png'))
                method_to_call = functools.partial(
                    self._emit_edit_override,
                    str(override_id),
                    str(msrs_uuid))
                action.triggered.connect(method_to_call)
                menu.addAction(action)

        if show:
            from Qt.QtGui import QCursor
            menu.exec_(QCursor.pos())

        return menu


    ##########################################################################


    def sizeHint(self):
        '''
        Return the size this widget should be.
        '''
        return QSize(constants.DETAILS_EDITOR_WIDTH, 850)


    def _emit_update_details_panel(self):
        '''
        Emit a message requesting this panel itself to be rebuilt
        based on external selection.
        '''
        self.updateDetailsPanel.emit(False)


    def _emit_remove_override(self, override_id, msrs_uuid):
        '''
        Emit a message requesting for an override to be removed from status badge.

        Args:
            override_id (str):
            msrs_uuid (str):
        '''
        override_id = str(override_id)
        msrs_uuid = str(msrs_uuid)
        self.removeOverrideRequest.emit(override_id, msrs_uuid)


    def _emit_edit_override(self, override_id, msrs_uuid):
        '''
        Emit a message requesting for an override edit mode to be invoked.

        Args:
            override_id (str):
            msrs_uuid (str):
        '''
        override_id = str(override_id)
        msrs_uuid = str(msrs_uuid)
        self.editOverrideRequest.emit(override_id, msrs_uuid)


    def _visibility_changed(self):
        '''
        When visibility toggled back on trigger the panel to rebuild from external selection.
        '''
        if self.isVisible():
            self._emit_update_details_panel()