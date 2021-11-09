

import datetime
import fileseq
import os

from Qt.QtGui import QFont, QColor, QIcon
from Qt.QtCore import (Qt, QModelIndex, Signal, QSize)

from srnd_qt.ui_framework.models import base_abstract_item_model
from srnd_multi_shot_render_submitter.constants import Constants
constants = Constants()


########################################################################################


class SummaryModel(base_abstract_item_model.BaseAbstractItemModel):
    '''
    A model to show a summary of all Multi Shot Render operations
    about to be submitted. Extends an existing Multi Shot model.
    Reimplement this model for a particular host app (if required).

    Args:
        model (MultiShotRenderModel): the main MSRS model
        view (MultiShotRenderView): the main MSRS view
        shot_assignments_project (str): optionally override the project shot assignments
            should be queried and populated from
        shot_assignments_user (str): optionally override the user shot assignments
            should be queried and populated from
    '''

    logMessage = Signal(str, int)

    def __init__(
            self,
            model,
            view,
            *args,
            **kwargs):
        super(SummaryModel, self).__init__(*args, **kwargs)

        self.HOST_APP = constants.HOST_APP

        self.NORMAL_ROW_HEIGHT = 26
        self.COLUMN_OF_NAME = 0
        self.COLUMN_OF_VALIDATION = 1
        self.COLUMN_OF_JOB_ID = 2
        self.COLUMN_OF_VERSION = 3
        self.COLUMN_OF_RENDER_CATEGORY = 4
        self.COLUMN_OF_RENDER_ESTIMATE = 5
        self.COLUMN_OF_WAIT_ON_IDENTIFIERS = 6
        self.COLUMN_OF_WAIT_ON_PLOW_IDS = 7
        self.COLUMN_OF_PRODUCTION_FRAMES = 8
        self.COLUMN_OF_FRAME_RANGE = 9
        self.COLUMN_OF_FRAMES = 10
        self.COLUMN_OF_POST_TASK = 11
        self.COLUMN_OF_KOBA_SHOTSUB = 12
        self.COLUMN_OF_SUBMISSION_NOTE = 13

        self.COLUMNS_REQUIRE_DELEGATES = [
            self.COLUMN_OF_VALIDATION,
            self.COLUMN_OF_POST_TASK,
            self.COLUMN_OF_SUBMISSION_NOTE]

        self._headers = [
            'Pass',
            'Validation',
            'Job identifier',
            'Version preview',
            'Category',
            'Render estimate',
            'Depend on identifiers',
            'Depend on Plow ids',
            'Production frames',
            'Frame range',
            'Frames',
            'Post task/s',
            'Koba shotsub',
            'Shotsub description']

        self._source_model = model
        self._source_view = view

        self.set_root_node(model.get_root_node())


    def find_environment_item(self, oz_area):
        '''
        Find a particular EnvironmentItem by environment name.

        Args:
            oz_area (str):

        Returns:
            environment_item, qmodelindex (tuple):
        '''
        for qmodelindex in self._source_model.get_environment_items_indices():
            if not qmodelindex.isValid():
                continue
            env_item = qmodelindex.internalPointer()
            if not env_item or not env_item.is_environment_item():
                continue
            if oz_area != env_item.get_oz_area():
                continue
            return env_item, qmodelindex
        return None, QModelIndex()


    def data(self, index, role):
        '''
        Data of the model for different roles.

        Args:
            index (QtCore.QModelIndex):
            role (Qt.ItemDataRole):

        Returns:
            data (object): data for index and role
        '''
        if not index.isValid():
           return

        item = index.internalPointer()
        if not item:
            return

        c = index.column()
        is_environment_item = item.is_environment_item()

        if role == Qt.FontRole:
            font = QFont()
            if c == self.COLUMN_OF_NAME:
                if is_environment_item:
                    font.setPointSize(10)
                    font.setBold(True)
                else:
                    font.setPointSize(9)
                    font.setBold(True)
            elif c == self.COLUMN_OF_JOB_ID:
                font.setPointSize(10)
                font.setBold(True)
            else:
                font.setPointSize(9)
            return font

        elif role == Qt.SizeHintRole:
            return QSize(0, self.NORMAL_ROW_HEIGHT)

        is_group_item = item.is_group_item()
        is_pass_for_env_item = item.is_pass_for_env_item()

        if c == self.COLUMN_OF_NAME:
            if is_environment_item:
                oz_area = item.get_oz_area()
                if role == Qt.DisplayRole:
                    if self._source_model.get_show_full_environments():
                        title = oz_area
                    else:
                        title = item.get_scene_shot_area()
                    job_identifier = item.get_job_identifier()
                    env_index = item._get_cached_environment_index()
                    if job_identifier:
                        title += ' ({})'.format(job_identifier)
                    elif env_index:
                        title += ' ({})'.format(env_index)
                    return title
                elif role == Qt.ForegroundRole:
                    colour = [c * 1.2 for c in self._source_view.get_environment_colour()]
                    colour = [255 if c > 255 else c for c in colour]
                    return QColor(*colour)
                elif role == Qt.ToolTipRole:
                    job_identifier = item.get_job_identifier()
                    env_index = item._get_cached_environment_index()
                    msg = 'Oz Area: <b>{}</b>'.format(oz_area)
                    msg += '<br>Group name: <b>{}</b>'.format(item.get_group_name())
                    msg += '<br>Job identifier: <b>{}</b>'.format(job_identifier)
                    msg += '<br>Environment index (nth version of same): <b>{}</b>'.format(env_index)
                    return msg
                return

            elif is_group_item:
                if role == Qt.DisplayRole:
                    return item.get_group_name()
                elif role == Qt.ToolTipRole:
                    msg = 'Group Name: <b>"{}"</b>'.format(item.get_group_name())
                    msg += '<br>Environment Count: <b>"{}"</b>'.format(item.child_count())
                    return msg
                elif role == Qt.ForegroundRole:
                    colour = [c * 1.2 for c in self._source_view.get_environment_colour()]
                    colour = [255 if c > 255 else c for c in colour]
                    return QColor(*colour)
                return

            elif is_pass_for_env_item:
                render_item = item.get_source_render_item()
                if role == Qt.DisplayRole:
                    if not render_item:
                        return
                    return render_item.get_node_name()
                elif role == Qt.ForegroundRole:
                    return QColor(225, 225, 225)
                elif role == Qt.ToolTipRole:
                    render_item = item.get_source_render_item()
                    render_node_name = render_item.get_node_name()
                    item_full_name = render_item.get_item_full_name()
                    pass_name = render_item.get_pass_name()
                    msg = 'Node name: <b>{}</b>. ' .format(render_node_name)
                    if item_full_name != render_node_name:
                        msg += 'Full item name: <b>{}</b>. ' .format(item_full_name)
                    msg += '<br>Pass name: <b>{}</b>. ' .format(pass_name)
                    aov_names = render_item.get_aov_names()
                    if aov_names:
                        msg += '<br>AOV names: <b>{}</b>. ' .format(aov_names)
                    render_category = render_item.get_render_category()
                    if render_category:
                        msg += '<br>Render category: <b>{}</b>. ' .format(render_category)
                    return msg
                return

        if c > 0 and is_pass_for_env_item:

            if c == self.COLUMN_OF_VERSION:
                if role in [Qt.DisplayRole, Qt.ToolTipRole]:
                    version_system = str(item.get_resolved_version_system() or str())
                    version_number = item.get_resolved_version_number()
                    version_label_str = str()
                    if version_system and version_system.startswith('V'):
                        version_label_str = '{} ({})'.format(version_system, version_number)
                    else:
                        version_label_str = 'v' + str(version_number)
                    if role == Qt.ToolTipRole and item.get_resolved_version_already_registered():
                        version_label_str += ' (<b>Cg Version Already Registered</b>)'
                    return version_label_str
                elif role == Qt.ForegroundRole:
                    if item.get_resolved_version_already_registered():
                        return QColor(255, 0, 0)
                elif role == Qt.DecorationRole:
                    if item.get_resolved_version_already_registered():
                        return QIcon(os.path.join(constants.ICONS_DIR, 'warning.png'))

            elif c == self.COLUMN_OF_RENDER_CATEGORY:
                if role in [Qt.DisplayRole, Qt.ToolTipRole]:
                    render_item = item.get_source_render_item()
                    return render_item.get_render_category()

            elif c == self.COLUMN_OF_RENDER_ESTIMATE:
                if role in [Qt.DisplayRole, Qt.ToolTipRole]:
                    estimate = item.get_render_estimate_average_frame()
                    if constants.EXPOSE_RENDER_ESTIMATE and estimate:
                        core_hours = item.get_render_estimate_core_hours() # all active frames
                        return str(core_hours) + ' core (h)'
                        # return str(datetime.timedelta(seconds=int(estimate / 1000.0))) # one frame    

            elif c == self.COLUMN_OF_FRAME_RANGE:
                if role == Qt.DisplayRole:
                    environment_item = item.get_environment_item()
                    if environment_item and environment_item.get_split_frame_ranges():
                        split_frame_ranges_list = environment_item.get_split_frame_to_job_type() or list()
                        return str(split_frame_ranges_list)
                    else:
                        return str(item.get_resolved_frames_queued())
                elif role in [Qt.ForegroundRole, Qt.ToolTipRole]:
                    tooltip, range_issue = item.get_frame_range_tooltip()
                    if role == Qt.ForegroundRole:
                        if range_issue:
                            return QColor(255, 0, 0)
                    elif role == Qt.ToolTipRole:
                        environment_item = item.get_environment_item()
                        if environment_item.get_split_frame_ranges():
                            tooltip += '<br>Split Frame Job Is Enabled'
                        return tooltip
                elif role == Qt.DecorationRole:
                    environment_item = item.get_environment_item()
                    if environment_item.get_split_frame_ranges():
                        return QIcon(os.path.join(constants.ICONS_DIR, 'split_20x20_s01.png'))

            elif c == self.COLUMN_OF_FRAMES and role == Qt.DisplayRole:
                return str(item.get_resolved_frames_count_queued())

        # Show the resolved job identifier (global and per environment combined)
        elif is_environment_item:
            if c == self.COLUMN_OF_JOB_ID:
                if role == Qt.DisplayRole:
                    optional_job_identifier = str()
                    global_job_identifier = self._source_model.get_global_job_identifier()
                    if global_job_identifier:
                        optional_job_identifier = str(global_job_identifier)
                    job_identifier = item.get_job_identifier()
                    if job_identifier:
                        if optional_job_identifier:
                            optional_job_identifier = '_'.join([
                                optional_job_identifier, 
                                job_identifier])
                        else:
                            optional_job_identifier = str(job_identifier)
                    return str(optional_job_identifier)
                elif role == Qt.ForegroundRole:
                    return QColor(*self._source_view.get_job_override_colour())                                   
        
            elif c == self.COLUMN_OF_PRODUCTION_FRAMES:
                if role == Qt.DisplayRole:
                    return item.get_production_frame_range() or str()
                elif role == Qt.ToolTipRole:
                    frame_range = item.get_production_frame_range()
                    value = item.get_production_range_source()
                    msg = 'Production frame range: <b>{}"</b>'.format(frame_range)
                    msg += '<br>Source: <b>{}</b>'.format(value)
                    if item.get_production_data_changed():
                        previous_value = item.get_previous_production_frame_range()
                        msg += '<br><br><b><font color=#FF0000>'
                        msg += 'WARNING: Production frame range just changed!</font></b>'
                        msg += '<br>Previous value: <b>{}"</b>'.format(previous_value)
                    elif not self._source_model.get_auto_refresh_from_shotgun():
                        # value = item.get_production_data_last_refreshed()
                        value = item.get_production_data_last_refreshed_since_now()
                        msg += '<br><br><b><font color=#FF0000>'
                        msg += 'WARNING: Production frames auto refresh is disabled</font></b>'
                        msg += '<br>Last refreshed production data: <b>{}"</b>'.format(value)                        
                    return msg
                elif role == Qt.ForegroundRole:
                    if item.get_production_data_changed():
                        return QColor(255, 255, 0)
                    elif not self._source_model.get_auto_refresh_from_shotgun():
                        return QColor(255, 255, 0)                        
                elif role == Qt.DecorationRole:
                    if item.get_production_data_changed():
                        return QIcon(os.path.join(constants.ICONS_DIR, 'warning.png'))    
                    elif not self._source_model.get_auto_refresh_from_shotgun():
                        return QIcon(os.path.join(constants.ICONS_DIR, 'warning.png'))    

        if not is_group_item and role in [Qt.DisplayRole, Qt.ToolTipRole]:
            if c == self.COLUMN_OF_WAIT_ON_IDENTIFIERS:
                identifiers = self._source_model.get_wait_on_identifiers(item)
                if identifiers:
                    return ', '.join(identifiers)

            elif c == self.COLUMN_OF_WAIT_ON_PLOW_IDS:
                return self._source_model.get_wait_on_plow_ids_display_string(item)

        # Fallback roles
        if role == Qt.ForegroundRole:
            return QColor(200, 200, 200)


    ##########################################################################
    # Core model


    def rowCount(self, parent_index):
        '''
        Number of rows under parent index.
        Reimplemented to make sibling columns act as row.

        Args:
            parent_index (QModelIndex):

        Returns:
            row_count (int):
        '''
        if not parent_index.isValid():
            parent_node = self._root_node
        else:
            parent_node = parent_index.internalPointer()
        if not parent_node.is_sibling() and parent_node.has_siblings():
            return parent_node.sibling_count()
        else:
            return parent_node.child_count()


    def hasChildren(self, parent_index):
        '''
        Does this abstract data node have any children.
        Reimplemented to make sibling columns act as row.

        Args:
            parent_index (QModelIndex):
        '''
        if not parent_index.isValid():
            return True
        item = parent_index.internalPointer()
        if item.is_environment_item() and item.has_siblings():
            return True
        return item.has_children()


    def parent(self, qmodelindex):
        '''
        Get parent QModelIndex of existing qmodelindex.
        Reimplemented to make sibling columns act as row.

        Args:
            qmodelindex (QModelIndex):

        Returns:
            qmodelindex (QModelIndex):
        '''
        if not qmodelindex.isValid():
            return QModelIndex()
        node = self.get_node(qmodelindex)
        parent_node = None
        if node:
            if node.is_sibling():
                parent_node = node.get_first_sibling()
            else:
                parent_node = node.parent()
        # If qmodelindex has no parent, return root qmodelindex
        if not parent_node or parent_node == self._root_node:
            return QModelIndex()
        try:
            return self.createIndex(parent_node.row(), 0, parent_node)
        except:
            return QModelIndex()


    def index(self, row, column, parent=QModelIndex()):
        '''
        Get a QModelIndex for row / column and with parent.
        Reimplemented to make sibling columns act as row.

        Args:
            row (int):
            column (int):
            parent (QModelIndex):

        Returns:
            index (QModelIndex):
        '''
        parent_node = self.get_node(parent)
        if parent_node.has_siblings():
            child_item = parent_node.sibling(row, offset_column=0)
        else:
            child_item = parent_node.child(row)
        if child_item:
            return self.createIndex(row, column, child_item)
        else:
            return QModelIndex()


    def flags(self, index):
        '''
        Flags for different columns.

        Args:
            index (QtCore.QModelIndex):

        Returns:
            flags (int):
        '''
        c = index.column()

        flags = int()
        flags |= Qt.ItemIsEnabled

        if not index.isValid():
            return flags

        item = index.internalPointer()

        if c < self.COLUMN_OF_POST_TASK:
            flags |= Qt.ItemIsSelectable

        # if c == self.COLUMN_OF_SUBMISSION_NOTE:
        #     flags |= Qt.ItemIsEditable

        return flags