

import datetime
import logging

from Qt.QtGui import QFont, QColor
from Qt.QtCore import Qt, QModelIndex, Signal, QSize

from srnd_qt.ui_framework.models import base_abstract_item_model
from srnd_multi_shot_render_submitter.constants import Constants
constants = Constants()


########################################################################################


class LightingInfoModel(base_abstract_item_model.BaseAbstractItemModel):
    '''
    Model to show lighting info details about selected environment and pass for env items.

    Args:
        model (MultiShotRenderModel): the main MSRS model
        view (MultiShotRenderView): the main MSRS view
        debug_mode (bool):
    '''

    logMessage = Signal(str, int)

    def __init__(
            self, 
            model,
            view,
            debug_mode=False,
            parent=None):
        super(LightingInfoModel, self).__init__(
            debug_mode=debug_mode,
            parent=parent)

        self._source_model = model
        self._source_view = view

        self.HOST_APP = constants.HOST_APP
        self.COLUMN_OF_NAME = 0
        self.COLUMN_OF_RESOLVED_FRAMES = 1
        self.COLUMN_OF_CUT_RANGE = 2
        self.COLUMN_OF_STATUS = 3
        self.COLUMN_OF_DUE_DATE = 4
        self.COLUMN_OF_RENDER_ESTIMATE = 5

        self.NORMAL_ROW_HEIGHT = 24

        self._headers = [
            'Name',
            'Resolved frames',
            'Cut range',
            'Status',
            'Due',
            'Render Estimate']
        

    ##########################################################################


    def set_debug_mode(self, debug_mode):
        '''
        Set whether debug mode is enabled on this node and all children.

        Args:
            debug_mode (str): oz area as single string
        '''
        self._debug_mode = bool(debug_mode)


    def populate(
            self, 
            shots_selected, 
            shots_passes_selected=None,
            visible_render_node_names=None):
        '''
        Populate this lighting info model for selected passes and environments.

        Args:
            shots_selected (list): list of environment item
            shots_passes_selected (list): list of render pass for env items  
            visible_render_node_names (list):
        '''
        # if self._debug_mode:
        #     msg = 'Populating lighting info model. '
        #     msg += 'Shots selected: {}. '.format(len(shots_selected))
        #     msg += 'Passes selected: {}. '.format(len(shots_passes_selected))
        #     msg += 'Visible render node names: {}'.format(visible_render_node_names)
        #     self.logMessage.emit(msg, logging.DEBUG)

        # Collect selected passes where shot not selected
        passes_of_shots_to_add = dict()
        for pass_env_item in shots_passes_selected:
            environment_item = pass_env_item.get_environment_item()
            if environment_item in shots_selected:
                continue
            if environment_item not in passes_of_shots_to_add.keys():
                passes_of_shots_to_add[environment_item] = list()
            passes_of_shots_to_add[environment_item].append(pass_env_item)

        # Add all selected shots
        pass_for_env_ids = set()
        for environment_item in shots_selected:
            pass_for_env_items = list()
            for pass_env_item in shots_passes_selected:           
                if pass_env_item.get_environment_item() == environment_item:
                    pass_for_env_ids.add(id(pass_env_item))
                    pass_for_env_items.append(pass_env_item)
            self.add_shot_info_section(
                environment_item, 
                pass_for_env_items,
                visible_render_node_names=visible_render_node_names)
        
        # Add all selected passes (where shot was not selected)
        for environment_item in passes_of_shots_to_add.keys():
            pass_for_env_items = passes_of_shots_to_add[environment_item]
            self.add_shot_info_section(
                environment_item, 
                pass_for_env_items,
                visible_render_node_names=visible_render_node_names)


    def add_shot_info_section(
            self, 
            environment_item, 
            pass_for_env_items=None,
            visible_render_node_names=None):
        '''
        Add shot info section for environment and all passes there of to 
        this lighting info model.

        Args:
            environment_item (EnvironmentItem):
            pass_for_env_items (list):
            visible_render_node_names (list):
        '''
        area = environment_item.get_oz_area()
        pass_for_env_items = pass_for_env_items or environment_item.get_pass_for_env_items()
        pass_count = len(pass_for_env_items)
        # if self._debug_mode:
        #     msg = 'Adding environment to lighting info model: "{}". '.format(area)
        #     msg += 'Pass Count: {}'.format(pass_count)
        #     self.logMessage.emit(msg, logging.DEBUG) 
         
        # NOTE: New data objects are built based on the currently selected items,
        # This allows the structure of the data to be reconfigured as needed for this model.

        # NOTE: Build environment data object copy for this model (using session data for now).
        # TODO: Implement __copy__ and __deepcopy__ to be more direct.
        id_before = id(environment_item)
        environment_item_object = self._source_model.get_environment_item_object()
        session_data = environment_item.get_session_data()
        environment_item_copy = environment_item_object(oz_area=environment_item.get_oz_area())
        environment_item_copy.copy_production_data(environment_item)
        environment_item_copy.apply_session_data(session_data)
        environment_item_copy._environment_index_cached = environment_item._environment_index_cached

        # msg = 'Id before: {}. After: {}'.format(id_before, id(environment_item_copy))
        # self.logMessage.emit(msg, logging.DEBUG) 

        # This panel is repopulated all at once, so its better and more direct to update all indices at once.
        self.beginResetModel()

        # Add environment at root of this model
        root_item = self.get_root_node()
        root_item.add_child(environment_item_copy) 

        pass_env_item_object = self._source_model.get_pass_for_env_item_object()

        # Add passes directly below eahc model.
        for i, pass_env_item in enumerate(pass_for_env_items):
            render_item = pass_env_item.get_source_render_item()

            if visible_render_node_names:
                if render_item.get_node_name() not in visible_render_node_names:
                    continue                 

            # NOTE: Build pass for env data object copy for this model (using session data for now).
            # TODO: Implement __copy__ and __deepcopy__ to be more direct.
            session_data = pass_env_item.get_session_data()
            pass_env_item_copy = pass_env_item_object(
                queued=True,
                enabled=True,
                source_render_item=render_item,
                debug_mode=self._debug_mode)
            environment_item_copy.add_child(pass_env_item_copy)                
            pass_env_item_copy.apply_session_data(session_data)
            pass_env_item_copy.copy_resolved_values(pass_env_item)         

        self.endResetModel()


    ##########################################################################
    # Core model


    def data(self, index, role):
        '''
        Data of the model for different roles.
        NOTE: Very similar to SummaryModel....

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
            elif c == self.COLUMN_OF_DUE_DATE:
                font.setPointSize(9)
                font.setBold(True)
            else:
                font.setPointSize(9)
            return font

        # elif role == Qt.SizeHintRole:
        #     return QSize(0, self.NORMAL_ROW_HEIGHT)

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
                    # if self._source_view:
                    colour = [c * 1.2 for c in self._source_view.get_environment_colour()]
                    colour = [255 if c > 255 else c for c in colour]
                    return QColor(*colour)                        
                    # else:
                    #     return QColor(150, 255, 150)            
                elif role == Qt.ToolTipRole:
                    job_identifier = item.get_job_identifier()
                    env_index = item._get_cached_environment_index()
                    msg = 'Oz Area: <b>{}</b>'.format(oz_area)
                    msg += '<br>Job identifier: <b>{}</b>'.format(job_identifier)
                    msg += '<br>Environment index (nth version of same): <b>{}</b>'.format(env_index)
                    return msg
                return     
            elif is_pass_for_env_item:
                render_item = item.get_source_render_item()
                if role == Qt.DisplayRole:
                    if not render_item:
                        return
                    return render_item.get_node_name()
                elif role == Qt.ToolTipRole:
                    render_node_name = render_item.get_node_name()
                    item_full_name = render_item.get_item_full_name()
                    pass_name = render_item.get_pass_name()
                    msg = 'Node name: <b>{}</b>. ' .format(render_node_name)
                    if item_full_name != render_node_name:
                        msg += '<br>Full item name: <b>{}</b>. ' .format(item_full_name)                    
                    return msg
                elif role == Qt.ForegroundRole:
                    return QColor(225, 225, 225)                
        
        elif role == Qt.DisplayRole:
            if is_pass_for_env_item:
                if c == self.COLUMN_OF_RESOLVED_FRAMES and item.get_active():  
                    return item.get_resolved_frames_queued()
                elif c == self.COLUMN_OF_RENDER_ESTIMATE:  
                    estimate = item.get_render_estimate_average_frame()
                    if constants.EXPOSE_RENDER_ESTIMATE and estimate:
                        core_hours = item.get_render_estimate_core_hours() # all active frames
                        return str(core_hours) + ' core (h)'
                        # return str(datetime.timedelta(seconds=int(estimate / 1000.0))) # one frame                       
            elif is_environment_item:  
                if c == self.COLUMN_OF_CUT_RANGE:
                    return item.get_cut_range() or str()                 
                elif c == self.COLUMN_OF_STATUS:  
                    return item.get_editorial_shot_status()                  
                elif c == self.COLUMN_OF_DUE_DATE:  
                    return item.get_due_date()                                   