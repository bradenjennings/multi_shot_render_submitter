

from Qt.QtWidgets import QTreeView, QHeaderView
from Qt.QtCore import Qt, QModelIndex, Signal

from srnd_qt.ui_framework.views import base_tree_view

from srnd_multi_shot_render_submitter.constants import Constants
constants = Constants()


########################################################################################


class LightingInfoView(base_tree_view.BaseTreeView):
    '''
    View to show lighting info details about selected environment and pass for env items.

    Args:
        show_render_categories (bool):
    '''

    logMessage = Signal(str, int)

    def __init__(self, debug_mode=False, parent=None):
        super(LightingInfoView, self).__init__(
            palette=None,
            debug_mode=debug_mode,
            parent=parent)

        self.HOST_APP = constants.HOST_APP
        self.COLUMN_0_WIDTH = 250

        ######################################################################

        self.setUniformRowHeights(True)
        self.setSelectionMode(QTreeView.ExtendedSelection)
        self.setSelectionBehavior(QTreeView.SelectRows)
        self.setItemsExpandable(True)

        # header = self.header()
        # header.setContextMenuPolicy(Qt.CustomContextMenu)
        # header.customContextMenuRequested.connect(
        #     self._create_context_menu_header)


    def sizeHintForColumn(self, column):
        '''
        Reimplement to add some extra padding to size hint.

        Args:
            column (int):
        '''
        size = base_tree_view.BaseTreeView.sizeHintForColumn(self, column)
        size += 30
        return size