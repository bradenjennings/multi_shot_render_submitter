

import logging
import os

from Qt.QtWidgets import QWidget, QFrame, QHeaderView, \
    QVBoxLayout, QSizePolicy # QTreeWidget, QTreeWidgetItem,
from Qt.QtCore import Qt, QSize, Signal, QModelIndex

import srnd_qt.base.utils
from srnd_qt.ui_framework.widgets import group_box_collapsible

from srnd_multi_shot_render_submitter.constants import Constants
constants = Constants()

LIGHTING_INFO_COLUMNS = ['Name', 'Frame Range', 'Cut', 'Status', 'Due']


##############################################################################


class MultiShotLightingInfoWidget(QFrame):
    '''
    Widget to show lighting info details about selected environment and pass for env items.

    Args:
        model (MultiShotRenderModel): the main MSRS model
        view (MultiShotRenderView): the main MSRS view
        debug_mode (bool):
    '''

    logMessage = Signal(str, int)
    updateLightingInfoPanel = Signal()
    updateLightingInfoPanelComplete = Signal()

    def __init__(
            self,
            model,
            view,
            debug_mode=False,
            parent=None):
        super(MultiShotLightingInfoWidget, self).__init__(parent=parent)

        self.setObjectName('LightingInfoPanel')

        self._source_model = model
        self._source_view = view

        self._debug_mode = bool(debug_mode)

        self._vertical_layout_main = QVBoxLayout()
        self._vertical_layout_main.setContentsMargins(4, 4, 4, 4)
        self._vertical_layout_main.setSpacing(4)
        self.setLayout(self._vertical_layout_main)
        self.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding)
        self.setMinimumHeight(200)

        ######################################################################

        # TODO: Later improve global styling system and reimplement
        # in srnd_katana_render_submitter repo
        if constants.IN_KATANA_UI_MODE:
            self.setStyleSheet(constants.STYLESHEET_FRAME_DETAILS_PANEL)
        else:
            self.setStyleSheet(constants.STYLESHEET_FRAME_DETAILS_PANEL_NO_BORDER)

        self._build_tree_view()
        self._build_selection_summary_widget()

        self.populate()


    ##########################################################################


    def _build_tree_view(self):
        '''
        Build the lighting info tree view and model.

        Returns:
            tree_view (QtGui.QTreeView):
        '''
        from srnd_multi_shot_render_submitter.views import lighting_info_view
        self._tree_view_lighting_info = lighting_info_view.LightingInfoView(
            debug_mode=self._debug_mode,
            parent=self)
        self._tree_view_lighting_info.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding)
        self._vertical_layout_main.addWidget(self._tree_view_lighting_info)

        from srnd_multi_shot_render_submitter.models import lighting_info_model
        self._model_lighting_info = lighting_info_model.LightingInfoModel(
            self._source_model,
            self._source_view,
            debug_mode=self._debug_mode)
        self._tree_view_lighting_info.setModel(self._model_lighting_info)

        # self._model_lighting_info.logMessage.connect(self._emit_log_message)
        self._tree_view_lighting_info.logMessage.connect(self._emit_log_message)

        return self._tree_view_lighting_info


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
            visible_render_node_names=None,
            only_when_visible=True):
        '''
        Populate the details panel for selected passes and environments.

        Args:
            shots_selected (list): list of environment item
            shots_passes_selected (list): list of render pass for env items
            only_when_visible (bool):
        '''
        # Optimization if lighting info widget / panel not visible, do not update
        if only_when_visible and not self.isVisible():
            msg = 'Skipping update lighting info widget. '
            msg += 'Because not visible!'
            self.logMessage.emit(msg, logging.DEBUG)
            return

        if not shots_selected:
            shots_selected = list()
        if not shots_passes_selected:
            shots_passes_selected = list()
        if not visible_render_node_names:
            visible_render_node_names = list()

        # msg = 'Shots selected: "{}"'.format(shots_selected)
        # self.logMessage.emit(msg, logging.DEBUG)
        # msg = 'Shots passes selected: "{}"'.format(shots_passes_selected)
        # self.logMessage.emit(msg, logging.DEBUG)

        show_full_environments = self._source_model.get_show_full_environments()

        self.clear_details()

        selected = set()
        if shots_selected:
            selected = selected.union(shots_selected)
        if shots_passes_selected:
            selected = selected.union(shots_passes_selected)

        # Gather all selected string identifiers (human readable), and UUIDs
        self._widget_selection_summary.get_and_cache_identifiers_for_selection(selected)

        # msg = 'Populating lighting info widget from: "{}"'.format(selected)
        # self.logMessage.emit(msg, logging.DEBUG)

        self._model_lighting_info.populate(
            shots_selected,
            shots_passes_selected,
            visible_render_node_names=visible_render_node_names)

        ######################################################################
        # Update selection summary

        self._tree_view_lighting_info.expandAll()

        column_count = self._model_lighting_info.columnCount(QModelIndex())
        for c in range(column_count):
            self._tree_view_lighting_info.resizeColumnToContents(c)

        # Update panel lighting info now built
        self.updateLightingInfoPanelComplete.emit()


    ##########################################################################


    def set_debug_mode(self, debug_mode):
        '''
        Set whether debug mode is enabled on this node and all children.

        Args:
            debug_mode (str): oz area as single string
        '''
        debug_mode = bool(debug_mode)
        self._debug_mode = debug_mode
        self._tree_view_lighting_info.set_debug_mode(debug_mode)
        # self._model_lighting_info.set_debug_mode(debug_mode)


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


    def get_content_widget_layout(self):
        '''
        Get this RenderShotsDetailsWidget main layout.

        Returns:
            horizontal_layout (QVBoxLayout):
        '''
        return self._vertical_layout_main


    def get_lighting_info_tree_view(self):
        '''
        Get the lighting info tree widget.
        '''
        return self._tree_view_lighting_info


    ##########################################################################


    def clear_details(self):
        '''
        Clear all the info within the tree view of this lighting info panel.
        '''
        self._model_lighting_info.clear_data()


    def sizeHint(self):
        '''
        Return the size this widget should be.
        '''
        return QSize(constants.LIGHTING_INFO_EDITOR_WIDTH, 350)


    def _emit_log_message(self, message, status):
        '''
        Emit the current hyref as logMessage signal upstream.
        '''
        self.logMessage.emit(message, status)


    def _emit_update_panel(self):
        '''
        Emit a message requesting this panel itself to be rebuilt based on external selection.
        '''
        self.updateLightingInfoPanel.emit()


    def _visibility_changed(self):
        '''
        When visibility toggled back on trigger the panel to rebuild frome external selection.
        '''
        if self.isVisible():
            self._emit_update_panel()