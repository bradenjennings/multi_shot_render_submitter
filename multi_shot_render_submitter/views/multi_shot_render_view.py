

import collections
import fileseq
import functools
import logging
import os
import time
import traceback

from Qt.QtWidgets import (QApplication, QDialog, QTreeView,
    QHeaderView, QMessageBox, QSizePolicy)
from Qt.QtGui import (QCursor, QIcon, QPixmap, QColor, QPen,
    QFont, QFontMetrics, QPainter, QRegExpValidator, QMovie)
from Qt.QtCore import (Qt, QModelIndex, Signal, QSize, QRect,
    QPoint, QItemSelection, QItemSelectionModel, 
    QItemSelectionRange, QRegExp)

import srnd_qt.base.utils
from srnd_qt.ui_framework.views import base_tree_view
from srnd_qt.ui_framework.widgets import searchable_menu

from srnd_multi_shot_render_submitter.constants import Constants
from srnd_multi_shot_render_submitter import utils


constants = Constants()

TIME_TAKEN_MSG = 'Time Taken To "{}": {} Seconds'
NORMAL_ROW_HEIGHT = 30

ICONS_DIR = os.path.join(
    os.getenv('SRND_MULTI_SHOT_RENDER_SUBMITTER_ROOT', str()),
    'icons')
SRND_QT_ROOT = os.getenv('SRND_QT_ROOT')
SRND_QT_ICONS_DIR = os.path.join(SRND_QT_ROOT, 'res', 'icons')
MULTI_SHOT_ICON_PATH = os.path.join(
    ICONS_DIR,
    'Multi_Shot_Render_Submitter_logo_01_128x128.png')

fs = '<b><font color="#33CC33">'
fe = '</b></font>'


########################################################################################


class MultiShotRenderView(base_tree_view.BaseTreeView):
    '''
    A TreeView to show Multi Shot render details.
    Where rows are output render environments, columns are
    source render nodes, and the cells are particular render passes.
    Note: This view is also composed of a MultiShotHeaderView, or a
    reimplemented subclass.

    Args:
        icon_path (str):
    '''

    logMessage = Signal(str, int)
    toggleProgressBarVisible = Signal(bool)
    updateLoadingBarFormat = Signal(int, str)
    updateDetailsPanel = Signal(bool)
    draggingComplete = Signal()
    resetColumnWidthsRequest = Signal()

    def __init__(
            self,
            icon_path=MULTI_SHOT_ICON_PATH,
            *args,
            **kwargs):

        super(MultiShotRenderView, self).__init__(*args, **kwargs)

        self.HOST_APP = constants.HOST_APP
        self.ORGANIZATION_NAME = 'Weta_Digital'
        self.HOST_APP_RENDERABLES_LABEL = constants.HOST_APP_RENDERABLES_LABEL
        self.HOST_APP_ICON = icon_path

        self.NORMAL_ROW_HEIGHT = NORMAL_ROW_HEIGHT
        self.COLUMN_0_WIDTH = 240

        self._overlay_widget = None
        self._in_wait_on_interactive_mode = False

        self._dragging_mouse = False
        self._auto_resolve_versions = False
        self._menu_some_actions_at_top = False
        self._menu_include_search = True        
        self._parent_ui = kwargs.get('parent')

        self._item_selection_sets = collections.OrderedDict()
        self._pass_visibility_sets = collections.OrderedDict()

        self._copied_overrides_dict = dict()
        self._copied_pass_overrides_dict = dict()

        # Colour for view
        self._disabled_passes_are_void_style = False
        self._environment_colour = constants.HEADER_RENDERABLE_COLOUR
        self._pass_colour = constants.CELL_RENDERABLE_COLOUR
        self._unqueued_colour = constants.CELL_ENABLED_NOT_QUEUED_COLOUR
        self._pass_disabled_colour = constants.CELL_DISABLED_COLOUR
        self._render_item_colour = [112, 186, 112]
        self._override_standard_colour = [241, 194, 50]
        self._override_standard_not_colour = [240, 70, 30]
        self._job_override_colour =  [147, 112, 219]
        self._render_override_standard_colour = [5, 187, 245]

        # NOTE: At this point even with a large number of MSRS rows and columns,
        # turning this on has no noticeably performance difference.
        # NOTE: Currently groups are shown different height than normal MSRS rows.
        # NOTE: qt docs suggest turning this on very large amounts of data.
        self.setUniformRowHeights(False)
        self.setSelectionMode(QTreeView.ExtendedSelection)
        self.setSelectionBehavior(QTreeView.SelectItems)
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QTreeView.InternalMove)
        self.setEditTriggers(self.DoubleClicked)
        self.setExpandsOnDoubleClick(False)

        header_view_object = self.get_header_view_object()
        header = header_view_object(
            orientation=Qt.Horizontal,
            parent=self)
        self.setHeader(header)

        # Context menu for header
        header.setContextMenuPolicy(Qt.CustomContextMenu)
        header.customContextMenuRequested.connect(
            self._create_context_menu_header)
        header.sectionDoubleClicked.connect(self._section_double_clicked)

        # Prepare object which will prepare efficient thumbnails for MSRS
        self._thumbnails_prep_thread = None

        if constants.GENERATE_EFFICIENT_THUMBNAILS_IN_THREAD:
            from srnd_multi_shot_render_submitter import thumbnail_prep
            self._thumbnails_prep_thread = thumbnail_prep.ThumbnailPrepThread()
            self._thumbnails_prep_thread.thumbnailsGenerated.connect(
                self._update_all_thumbnails)
            self._thumbnails_prep_thread.thumbnailGenerated.connect(
                self._update_thumbnail_for_environment)

        self.setColumnWidth(0, self.COLUMN_0_WIDTH)


    def _section_double_clicked(self, section):
        '''
        Callback for section double clicked.

        Args:
            section (int):
        '''
        if section >= 1:
            self.header().select_column(section)
            # self.render_node_operation(
            #     section,
            #     operation='Rename Node')


    def focusOutEvent(self, event):
        '''
        Reimplement focus out event to exit interactive define wait on mode.
        For example user might click in host app node graph, and the mouse
        should return to normal now.
        '''
        if self.get_in_wait_on_interactive_mode():
            self.exit_wait_on_interactive()
        base_tree_view.BaseTreeView.focusOutEvent(self, event)


    def set_overlays_widget(self, overlays_widget=None):
        '''
        Set the overlays widget to instance of OverlaysWidget.

        Args:
            overlays_widget (OverlaysWidget):
        '''
        self._overlay_widget = overlays_widget or None

        if self._overlay_widget:
            self.collapsed.connect(self._overlay_widget.update_overlays)
            self.expanded.connect(self._overlay_widget.update_overlays)
            scrollbar = self.horizontalScrollBar()
            scrollbar.valueChanged.connect(self._overlay_widget.update_overlays)
            scrollbar = self.verticalScrollBar()
            scrollbar.valueChanged.connect(self._overlay_widget.update_overlays)
            header = self.header()
            header.sectionResized.connect(self._overlay_widget.update_overlays)
            header.sectionMoved.connect(self._overlay_widget.update_overlays)
            #header.sectionCountChanged.connect(self._overlay_widget.update_overlays)


    def get_overlays_widget(self):
        '''
        Get the overlays widget of this view (if any).

        Returns:
            overlays_widget (OverlaysWidget):
        '''
        return self._overlay_widget


    def set_draw_all_dependency_overlays(self, draw):
        current_value = self._overlay_widget.get_draw_all_dependency_overlays()
        draw = bool(draw)
        self._overlay_widget.set_draw_all_dependency_overlays(draw)
        # Refresh the preferences file to keep in sync
        if draw != current_value:
            model = self.model()
            model.update_preference('draw_dependency_overlays', draw)


    def set_show_environment_thumbnails(
            self, 
            value=True,
            static=None):
        '''
        Set whether when shot environments are added to view, that a shotsub thumbnail
        should be seeked and provided to view.

        Args:
            value (bool):
            static (bool):

        Returns:
            thumbnails_request_resize (dict): mapping of environment string to thumbnail file path
        '''
        self.clearSelection()

        model = self.model()
        current_value = model.get_show_environment_thumbnails()

        value = bool(value)

        thumbnails_request_resize = model.set_show_environment_thumbnails(
            value=value,
            static=static)

        if thumbnails_request_resize:
            self._prepare_thumbnails_for_environments(thumbnails_request_resize)

        render_item_count = len(model.get_render_items())
        # Set the environment column to a default depending if thumbnails visible or not
        if render_item_count:
            self.resize_environment_column_to_optimal()

        if self._overlay_widget:
            self._overlay_widget.update_overlays()

        # Refresh the preferences file to keep in sync
        if value != current_value:
            model = self.model()
            model.update_preference('show_shotsub_thumbnails', value)

        return thumbnails_request_resize


    def get_thumbnail_prep_thread(self):
        '''
        Get the thread owned by this view that prepares efficient thumbnails.

        Returns:
            thumbnails_prep_thread (QThread):
        '''
        return self._thumbnails_prep_thread


    def set_disabled_passes_are_void_style(self, void_style):
        '''
        Set whether disabled items appear as void (no widget).

        Args:
            void_style (bool):
        '''
        void_style = bool(void_style)
        if self._debug_mode:
            msg = 'Set disabled passes are void style: "{}"'.format(void_style)
            self.logMessage.emit(msg, logging.DEBUG)        
        void_style_before = self.get_disabled_passes_are_void_style()            
        self._disabled_passes_are_void_style = void_style
        model = self.model()
        if not model.get_in_initial_state() and void_style != void_style_before:
            for qmodelindex in model.get_pass_for_env_items_indices():
                if not qmodelindex.isValid():
                    continue
                item = qmodelindex.internalPointer()
                widget = self.indexWidget(qmodelindex)
                if not item.get_enabled() and void_style:
                    if widget:
                        self.closePersistentEditor(qmodelindex)
                elif not widget:
                    self.openPersistentEditor(qmodelindex)


    def set_environment_colour(self, rgb):
        '''
        Set and cache the desired colour for environment items.

        Args:
            rgb (tuple):
        '''
        if self._debug_mode:
            msg = 'Set environment colour: "{}"'.format(rgb)
            self.logMessage.emit(msg, logging.DEBUG)        
        colour_before = self.get_environment_colour()            
        self._environment_colour = rgb
        model = self.model()
        if not model.get_in_initial_state() and rgb != colour_before:
            self.clearSelection()
            self.update_environment_delegate_widgets()                         


    def set_pass_colour(self, rgb):
        '''
        Set and cache the desired colour for environment items.

        Args:
            rgb (tuple):
        '''
        if self._debug_mode:
            msg = 'Set pass colour: "{}"'.format(rgb)
            self.logMessage.emit(msg, logging.DEBUG)           
        colour_before = self.get_pass_colour()    
        self._pass_colour = rgb
        model = self.model()
        if not model.get_in_initial_state() and rgb != colour_before:         
            self.clearSelection()
            self.update_pass_for_env_items_delegate_widgets()      


    def set_unqueued_colour(self, rgb):
        '''
        Set and cache the desired colour for unqueued pass and environment items.

        Args:
            rgb (tuple):
        '''
        if self._debug_mode:
            msg = 'Set unqueued colour: "{}"'.format(rgb)
            self.logMessage.emit(msg, logging.DEBUG)        
        colour_before = self.get_unqueued_colour()            
        self._unqueued_colour = rgb
        model = self.model()
        if not model.get_in_initial_state() and rgb != colour_before:
            self.clearSelection()
            self.update_environment_delegate_widgets()            
            self.update_pass_for_env_items_delegate_widgets()                    


    def set_pass_disabled_colour(self, rgb):
        '''
        Set and cache the desired colour for disabled pass items.

        Args:
            rgb (tuple):
        '''
        if self._debug_mode:
            msg = 'Set pass disabled colour: "{}"'.format(rgb)
            self.logMessage.emit(msg, logging.DEBUG)        
        colour_before = self.get_pass_disabled_colour()            
        self._pass_disabled_colour = rgb
        model = self.model()
        if not model.get_in_initial_state() and rgb != colour_before:
            self.clearSelection()
            self.update_environment_delegate_widgets()            
            self.update_pass_for_env_items_delegate_widgets()                    


    def set_render_item_colour(self, rgb):
        '''
        Set and cache the desired colour for environment items.

        Args:
            rgb (tuple):
        '''   
        if self._debug_mode:
            msg = 'Set render item colour: "{}"'.format(rgb)
            self.logMessage.emit(msg, logging.DEBUG)            
        colour_before = self.get_render_item_colour()
        self._render_item_colour = rgb

        model = self.model()
        if not model.get_in_initial_state() and rgb != colour_before:
            header = self.header()
            header.reset()  
    

    def set_override_standard_colour(self, rgb):
        '''
        Set and cache the desired colour for standard overrides.

        Args:
            rgb (tuple):        
        '''
        if self._debug_mode:
            msg = 'Set override standard colour: "{}"'.format(rgb)
            self.logMessage.emit(msg, logging.DEBUG)           
        colour_before = self.get_override_standard_colour()    
        self._override_standard_colour = rgb

        model = self.model()
        if not model.get_in_initial_state() and rgb != colour_before:
            self.clearSelection()
            self.update_environment_delegate_widgets()            
            self.update_pass_for_env_items_delegate_widgets()                      


    def set_override_standard_not_colour(self, rgb):
        '''
        Set and cache the desired colour for standard NOT overrides.

        Args:
            rgb (tuple):        
        '''
        if self._debug_mode:
            msg = 'Set override standard NOT colour: "{}"'.format(rgb)
            self.logMessage.emit(msg, logging.DEBUG)           
        colour_before = self.get_override_standard_not_colour()    
        self._override_standard_not_colour = rgb

        model = self.model()
        if not model.get_in_initial_state() and rgb != colour_before:
            self.clearSelection()
            self.update_environment_delegate_widgets()            
            self.update_pass_for_env_items_delegate_widgets()                     


    def set_job_override_colour(self, rgb):
        '''
        Set and cache the desired colour for job override.

        Args:
            rgb (tuple):        
        '''
        if self._debug_mode:
            msg = 'Set job override colour: "{}"'.format(rgb)
            self.logMessage.emit(msg, logging.DEBUG)           
        colour_before = self.get_job_override_colour()    
        self._job_override_colour = rgb

        model = self.model()
        if not model.get_in_initial_state() and rgb != colour_before:
            self.clearSelection()
            self.update_environment_delegate_widgets()                                   


    def set_render_override_standard_colour(self, rgb):
        '''
        Set and cache the desired colour for standard render overrides.

        Args:
            rgb (tuple):        
        '''
        if self._debug_mode:
            msg = 'Set render override standard colour: "{}"'.format(rgb)
            self.logMessage.emit(msg, logging.DEBUG)           
        colour_before = self.get_render_override_standard_colour()    
        self._render_override_standard_colour = rgb

        model = self.model()
        if not model.get_in_initial_state() and rgb != colour_before:
            self.clearSelection()
            self.update_environment_delegate_widgets()            
            self.update_pass_for_env_items_delegate_widgets()                           


    def get_disabled_passes_are_void_style(self):
        return self._disabled_passes_are_void_style

    def get_environment_colour(self):
        return self._environment_colour

    def get_pass_colour(self):
        return self._pass_colour

    def get_unqueued_colour(self):
        return self._unqueued_colour

    def get_pass_disabled_colour(self):
        return self._pass_disabled_colour

    def get_render_item_colour(self):
        return self._render_item_colour
    
    def get_override_standard_colour(self):
        return self._override_standard_colour

    def get_override_standard_not_colour(self):
        return self._override_standard_not_colour

    def get_job_override_colour(self):
        return self._job_override_colour

    def get_render_override_standard_colour(self):
        return self._render_override_standard_colour


    def _prepare_thumbnails_for_environments(
            self,
            thumbnails_request):
        '''
        Prepare environment thumbnails from a mapping
        of environment strings to thumbnail paths.

        Args:
            thumbnails_request (dict):
        '''
        if not thumbnails_request:
            thumbnails_request = dict()
        if not thumbnails_request:
            return
        thumbnail_prep_thread = self.get_thumbnail_prep_thread()
        if not thumbnail_prep_thread:
            return

        # Filter the requests by thumbnails that are on disc, and not
        # already cached on thread from prior processing.
        thumbnails_request_new = dict()
        thumbnails_results = self._thumbnails_prep_thread.get_resized_thumbnails_results()
        for identifier in thumbnails_request.keys():
            if identifier in thumbnails_results.keys():
                continue
            thumbnail_path = thumbnails_request[identifier]
            if not os.path.isfile(thumbnail_path):
                continue
            thumbnails_request_new[identifier] = thumbnail_path

        # msg = 'Requesting Thumbnails: "{}"'.format(thumbnails_request)
        # self.logMessage.emit(msg, logging.INFO)
        thumbnail_prep_thread.add_thumbnails_request(
            thumbnails_request_new)


    def _update_all_thumbnails(
            self,
            resized_thumbnails_result=None):
        '''
        Update all thumbnails from mapping of identifiers to resized thumbnail path.

        Args:
            resized_thumbnails_result (dict):

        Returns:
            update_count (int):
        '''
        # msg = 'Updating Thumbnails: "{}"'.format(resized_thumbnails_result)
        # self.logMessage.emit(msg, logging.INFO)
        if not resized_thumbnails_result:
            return 0
        model = self.model()
        update_count = 0
        for qmodelindex in model.get_environment_items_indices():
            environment_item = qmodelindex.internalPointer()
            oz_area = environment_item.get_oz_area()
            resized_thumbnail_path = resized_thumbnails_result.get(oz_area)
            if not resized_thumbnail_path:
                continue
            widget = self.indexWidget(qmodelindex)
            if not widget:
                continue
            label = widget.get_thumbnail_movie_container_widget()
            if not label:
                continue
            widget.set_thumbnail_movie(
                thumbnail_path=resized_thumbnail_path)
            update_count += 1
        return update_count


    def _update_thumbnail_for_environment(
            self,
            environment,
            resized_thumbnail_path):
        '''
        Update thumbnails for particular environment identifier.

        Args:
            environment (str):
            movie (QMovie):

        Returns:
            update_count (int):
        '''
        # msg = 'Updating Thumbnail For Environment: "{}". '.format(environment)
        # msg += 'Path: "{}"'.format(resized_thumbnail_path)
        # self.logMessage.emit(msg, logging.INFO)
        if not all([environment, resized_thumbnail_path]):
            return 0

        model = self.model()
        column_count = model.columnCount(QModelIndex())

        environments = list()
        for environment_item in model.get_environment_items():
            environments.append(environment_item.get_oz_area())

        update_count = 0
        for qmodelindex in model.get_environment_items_indices():
            environment_item = qmodelindex.internalPointer()
            oz_area = environment_item.get_oz_area()
            if oz_area != environment:
                continue
            widget = self.indexWidget(qmodelindex)
            if not widget:
                continue
            label = widget.get_thumbnail_movie_container_widget()
            if not label:
                continue
            widget.set_thumbnail_movie(
                thumbnail_path=resized_thumbnail_path)
            update_count += 1
            if environments.count(oz_area) <= 1:
                break
        return update_count


    def resize_environment_column_to_optimal(self):
        '''
        Derive and set the optimal width for environment column.
        '''
        model = self.model()
        show_full_environments = model.get_show_full_environments()
        show_environment_thumbnails = model.get_show_environment_thumbnails()
        width = self.COLUMN_0_WIDTH
        if show_full_environments:
            width += 75
        if show_environment_thumbnails:
            width += 125
        self.setColumnWidth(0, width)
        return width


    def update_environment_delegate_widgets(self, update_cached_details=True):
        '''
        Update all the environment delegate widgets and invoke repaint.

        Args:
            update_cached_details (bool): optionally update the cached 
                details before indirectly invoking repaint
        '''
        model = self.model()
        for qmodelindex in model.get_environment_items_indices():
            if not qmodelindex.isValid():
                continue
            widget = self.indexWidget(qmodelindex)
            if not widget:
                continue
            item = qmodelindex.internalPointer()
            # Update cached info for painting
            if update_cached_details:
                widget.update_overrides_from_item(item)
            # Indirectly invoke repaint
            widget.update()


    def update_pass_for_env_items_delegate_widgets(self, update_cached_details=True):
        '''
        Update all the pass for env delegate widgets and invoke repaint.

        Args:
            update_cached_details (bool): optionally update the cached 
                details before indirectly invoking repaint
        '''
        model = self.model()
        for qmodelindex in model.get_pass_for_env_items_indices():
            if not qmodelindex.isValid():
                continue
            widget = self.indexWidget(qmodelindex)
            if not widget:
                continue
            item = qmodelindex.internalPointer()
            # Update cached info for painting
            if update_cached_details:
                widget.update_overrides_from_item(item)                
            # Indirectly invoke repaint
            widget.update()


    def get_header_view_object(self):
        '''
        Get an MultiShotHeaderView (or subclass) appropiate for this view.
        Returns uninstantiated object.

        Returns:
            header_view_object (MultiShotHeaderView):
        '''
        return MultiShotHeaderView


    def _get_parent_ui(self):
        '''
        Get the parent ui, as originally passed into this
        view constructor parent argument.
        Note: This widget is considered the top level of the
        entire Multi Shot user interface.
        Note: The actual parent may have changed there after to some
        other sub widget of the original parent.

        Args:
            parent_ui (QMainWindow): or other QWidget subclass
        '''
        return self._parent_ui


    def clear_data(self):
        '''
        Clear any core view data which should not persist anymore.
        '''
        self._dragging_mouse = False
        self._auto_resolve_versions = False
        self._item_selection_sets = collections.OrderedDict()
        self._pass_visibility_sets = collections.OrderedDict()


    ##########################################################################
    # Sync (with view selection)


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
        Call the model to perform sync for all required data.
        Then perform any updates to the view as required.

        Args:
            hyref (str): optional project to first open
            from_selected_nodes (bool): optionally only sync / populate from
                selected host app Render nodes
            limit_to (list): optionally provide a list of strings of renderable item names
                to limit which render nodes are populated into MSRS data model
            only_missing (bool): on sync the render nodes not already in this view.
            keep_session_data (bool): whether to reapply previous session data, after sync
                from host app is called.
            include_current_env (bool): optionally add the current oz Environment
                if no other environments were synced
            emit_insertion_signals (bool): whether to batch update view, or emit signal
                as each row added. Note: batch update requires all editors to reopen.
        '''
        limit_to = limit_to or None

        time_start = time.time()

        model = self.model()

        render_nodes_data = dict()
        if keep_session_data:
            render_nodes_data = self.get_header_session_data()

        model.sync_render_nodes_and_environments(
           hyref=hyref,
           from_selected_nodes=from_selected_nodes,
           limit_to=limit_to,
           only_missing=only_missing,
           keep_session_data=keep_session_data,
           include_current_env=include_current_env,
           emit_insertion_signals=emit_insertion_signals)

        if keep_session_data and render_nodes_data:
            msg = 'Now updating column widths from session data...'
            self.logMessage.emit(msg, logging.DEBUG)
            self.apply_render_nodes_session_data(render_nodes_data)

        te = int(time.time() - time_start)
        msg = 'Sync render nodes & environments'
        self.logMessage.emit(TIME_TAKEN_MSG.format(msg, te), logging.DEBUG)


    ##########################################################################
    # Render from view (with view selection)


    def multi_shot_render(
            self,
            selected=True,
            interactive=False,
            current_frame_only=False,
            show_dialog=False,
            **kwargs):
        '''
        Call render from TreeView selection, so only pass the required
        PassForEnvItems (or subclasses) to model for rendering.

        Args:
            selected (bool): optionally render only item/s selected in MultiShotRenderView
            interactive (bool): optionally interactively render, rather than batch render
            current_frame_only (bool): ignore frame range overrides and only render current project frame
            show_dialog (bool): optionally show failure dialog or not

        Returns:
            success, cancelled, msg (tuple):
        '''
        if self._overlay_widget:
            if self._in_wait_on_interactive_mode:
                self.exit_wait_on_interactive()

        # If user is submitting a selection then multi_shot_render is called from
        # the view itself for the selected indices, currently this results 
        # in validate_can_render being skipped from the main MSRS window.
        # TODO: validate_can_render should be moved from main window...
        # TODO: For now invoke the method from this view using a pointer to main window.
        main_window = self._get_parent_ui()
        if selected and main_window and hasattr(main_window, 'validate_can_render'):
            can_render, msg = main_window.validate_can_render()
            if not can_render:
                self.logMessage.emit(msg, logging.WARNING)
                return False, True, msg

        selection = self.selectedIndexes()
        model = self.model()
        parent_ui = self._get_parent_ui()

        # A list of pass for env items in selection or visible will be collected
        pass_for_env_items = list()

        # Filter multi shot render to only selected items
        if selected:
            # First collect pass for env items that are active, visible and selected directly
            _pass_for_env_items, qmodelindices_pass_for_env = self.filter_selection(
                selection,
                include_environment_items=False,
                include_pass_for_env_items=True,
                include_group_items=False)
            for qmodelindex_pass_for_env in qmodelindices_pass_for_env:
                if not constants.HIDDEN_ITEMS_RENDERABLE:
                    hidden = self.isIndexHidden(qmodelindex_pass_for_env)
                    if hidden:
                        continue
                pass_env_item = qmodelindex_pass_for_env.internalPointer()
                if not pass_env_item.get_active():
                    continue
                pass_for_env_items.append(pass_env_item)

            # Then collect any pass for env items that are active and visible if
            # environment selected, but no passes there of
            _environment_items, qmodelindices_env = self.filter_selection(
                selection,
                include_environment_items=True,
                include_pass_for_env_items=False,
                include_group_items=False)
            for qmodelindex_env in qmodelindices_env:
                if not constants.HIDDEN_ITEMS_RENDERABLE:
                    hidden = self.isIndexHidden(qmodelindex_env)
                    if hidden:
                        continue
                # Iterate over all pass for env items of environment
                has_pass_selection_for_env = False
                _qmodelindices_pass_for_env = model.get_pass_for_env_items_indices(
                    env_indices=[qmodelindex_env])
                for qmodelindex_pass in _qmodelindices_pass_for_env:
                    if not constants.HIDDEN_ITEMS_RENDERABLE:
                        hidden = self.isIndexHidden(qmodelindex_pass)
                        if hidden:
                            continue
                    pass_env_item = qmodelindex_pass.internalPointer()
                    # Pass was already in users direct selection
                    if pass_env_item in pass_for_env_items:
                        has_pass_selection_for_env = True
                        break
                # User didnt have selection of passes of environment, so collect all active and visible
                if not has_pass_selection_for_env:
                    for qmodelindex_pass in _qmodelindices_pass_for_env:
                        if not constants.HIDDEN_ITEMS_RENDERABLE:
                            hidden = self.isIndexHidden(qmodelindex_pass)
                            if hidden:
                                continue
                        pass_env_item = qmodelindex_pass.internalPointer()
                        if not pass_env_item.get_active():
                            continue
                        pass_for_env_items.append(pass_env_item)

            if not pass_for_env_items:
                msg = 'Submit selected, active & visible items requested but none found!'
                self.logMessage.emit(msg, logging.CRITICAL)
                return False, False, msg

        # Filter multi shot render to only visible items
        elif not constants.HIDDEN_ITEMS_RENDERABLE:
            for qmodelindex in model.get_pass_for_env_items_indices():
                if not qmodelindex.isValid():
                    continue
                hidden = self.isIndexHidden(qmodelindex)
                if hidden:
                    continue
                pass_env_item = qmodelindex.internalPointer()
                if not pass_env_item.get_active():
                    continue
                pass_for_env_items.append(pass_env_item)

            if not pass_for_env_items:
                msg = 'Submit active & visible items requested but none found!'
                self.logMessage.emit(msg, logging.CRITICAL)
                return False, False, msg

        # This is a workaround in case when running host app API in standalone
        # mode, and current project path doesn't return the expected value,
        # then get the current project from the parent menu bar widget
        current_project = model.get_current_project()
        msg = 'Project for submission: "{}". '.format(current_project)
        self.logMessage.emit(msg, logging.WARNING)
        if not current_project and parent_ui and hasattr(parent_ui, 'get_menu_bar_header_widget'):
            current_project = parent_ui.get_menu_bar_header_widget().get_project()
            msg = 'Derived project for submission from UI: "{}"'.format(current_project)
            self.logMessage.emit(msg, logging.WARNING)
            model._set_project_from_external_widget(current_project)

        render_success, cancelled, render_msg = model.multi_shot_render(
            pass_for_env_items=pass_for_env_items or None,
            interactive=interactive,
            current_frame_only=current_frame_only,
            parent=parent_ui or self)

        # Render did not successfully submit
        if show_dialog and not cancelled and (not render_success and render_msg):
            self.logMessage.emit(render_msg, logging.CRITICAL)
            title_str = 'Submission failed!'
            reply = QMessageBox.critical(
                self,
                title_str,
                render_msg,
                QMessageBox.Ok)
            return False, render_msg

        self.updateDetailsPanel.emit(False)

        return render_success, cancelled, render_msg


    ##########################################################################
    # Session data for view


    def get_session_data(self):
        '''
        Serialize all EnvironmentItem/s, RenderItem/s and PassForEnvItem/s
        into a subset of the overall session data.
        Note: Calls the models get_session_data, then adds additional
        session data from the view.

        Returns:
            session_data (dict):
        '''
        model = self.model()
        session_data = model.get_session_data() or dict()

        multi_shot_data = session_data.get(constants.SESSION_KEY_MULTI_SHOT_DATA, dict())

        identity_ids = self.get_selected_uuids()
        if identity_ids:
            session_data[constants.SESSION_KEY_CURRENT_SELECTION] = list(identity_ids)

        item_selection_sets = self.get_item_selection_sets()
        if item_selection_sets:
            session_data[constants.SESSION_KEY_SELECTION_SETS] = item_selection_sets

        render_nodes_to_visible_map = self.get_pass_visibility_sets()
        if render_nodes_to_visible_map:
            session_data[constants.SESSION_KEY_RENDER_NODES_VIS_SETS] = render_nodes_to_visible_map

        # visible_rows_data = multi_shot_data.get(constants.SESSION_KEY_VISIBLE_ROWS, dict())
        # if visible_rows_data:
        #     session_data[constants.SESSION_KEY_VISIBLE_ROWS] = self.get_row_visibility_data()

        render_nodes_data = multi_shot_data.get(constants.SESSION_KEY_RENDER_NODES, dict())
        if render_nodes_data:
            render_nodes_data = self.get_header_session_data(render_nodes_data)

        session_data[constants.SESSION_KEY_ENV_COLUMN_WIDTH] = self.columnWidth(0)

        render_nodes_data = multi_shot_data.get(constants.SESSION_KEY_RENDER_NODES, dict())
        if render_nodes_data:
            render_nodes_data = self.get_header_session_data(render_nodes_data)
        session_data[constants.SESSION_KEY_RENDER_NODES] = render_nodes_data

        return session_data


    def get_header_session_data(self, render_nodes_data=None):
        '''
        Get all session data for header in isolation.

        Args:
            render_nodes_data (dict):

        Returns:
            render_nodes_data (dict):
        '''
        if not render_nodes_data:
            render_nodes_data = dict()

        model = self.model()
        header = self.header()
        root_index = QModelIndex()

        for c, render_item in enumerate(model.get_render_items()):
            item_full_name = render_item.get_item_full_name()
            if item_full_name not in render_nodes_data.keys():
                render_nodes_data[item_full_name] = dict()
            width = int(self.columnWidth(c + 1))
            render_nodes_data[item_full_name]['column_width'] = width
            hidden = bool(self.isColumnHidden(c + 1))
            render_nodes_data[item_full_name]['column_hidden'] = hidden
            render_nodes_data[item_full_name]['column_index'] = header.visualIndex(c + 1)

        return render_nodes_data


    def apply_session_data(self, session_data=None, **kwargs):
        '''
        Apply all per EnvironmentItem, RenderItem, and
        PassForEnvItem details from primary part of session data.
        Note: Calls the models apply_session_data, then applies
        additional session data to the view.

        Args:
            session_data (dict): number of synced items

        Returns:
            sync_env_count, sync_render_count, sync_pass_count (tuple): number of synced items
        '''
        session_data = session_data or dict()

        model = self.model()
        sync_env_count, sync_render_count, sync_pass_count = model.apply_session_data(
            session_data)

        identity_ids = session_data.get(constants.SESSION_KEY_CURRENT_SELECTION, list())
        if identity_ids:
            self.select_by_identity_uids(identity_ids)

        item_selection_sets = session_data.get(constants.SESSION_KEY_SELECTION_SETS, dict())
        if item_selection_sets:
            self.set_item_selection_sets(item_selection_sets)

        render_nodes_vis_sets = session_data.get(constants.SESSION_KEY_RENDER_NODES_VIS_SETS, list())
        if render_nodes_vis_sets:
            self.set_pass_visibility_sets(render_nodes_vis_sets)

        return sync_env_count, sync_render_count, sync_pass_count


    def apply_render_nodes_session_data(self, render_nodes_data):
        '''
        Apply session data to render nodes, such as column size and visibility.

        Args:
            render_nodes_data (dict):
        '''
        if not render_nodes_data:
            render_nodes_data = dict()

        model = self.model()
        header = self.header()

        if self._overlay_widget:
            self._overlay_widget.set_active(False)

        skip_columns = 0
        for c, render_item in enumerate(model.get_render_items()):
            item_full_name = render_item.get_item_full_name()

            column = c + 1

            render_node_data = render_nodes_data.get(item_full_name, dict())

            column_width = render_node_data.get('column_width', None)
            # Revert to optimal size
            if not column_width:
                # NOTE: Same as default of srnd_qt BaseTreeView.scale_columns
                padding = 50
                column_width = header.sectionSizeFromContents(column).width() + padding
            if column_width:
                render_item._cached_width = column_width
                self.setColumnWidth(column, column_width)

            hidden = render_node_data.get('column_hidden', False)
            if isinstance(hidden, bool):
                self.setColumnHidden(column, hidden)

            session_visual_index = render_node_data.get('column_index')
            if isinstance(session_visual_index, int):
                _session_visual_index = session_visual_index + skip_columns
                visual_index_current = header.visualIndex(column)
                # msg = 'Item: "{}". Column: "{}". '.format(item_full_name, column)
                # msg += 'Session Visual Index: "{}". '.format(session_visual_index)
                # msg += 'Current Visual Index: "{}"'.format(visual_index_current)
                # print(msg)
                # NOTE: Avoid moving sections to and from 0th column index.
                if visual_index_current != _session_visual_index and visual_index_current > 0 and _session_visual_index > 0:
                    header.moveSection(visual_index_current, _session_visual_index)
            # This render node not in session data with previous ordered index.
            # So for all subsquent header order operations add 1 to target column order.
            else:
                skip_columns += 1

        if self._overlay_widget:
            self._overlay_widget.set_active(True)
            self._overlay_widget.update_overlays()


    # def apply_row_visibility_data(
    #         self, 
    #         visible_rows_data=None, 
    #         visible_columns_data=None):
    #     '''
    #     Apply row visibility data for each MSRS UUID.

    #     Args:
    #         visible_rows_data (dict):
    #         visible_columns_data (dict):
    #     '''
    #     if not visible_rows_data:
    #         visible_rows_data = dict()
    #     if not visible_columns_data:
    #         visible_columns_data = dict()            
    #     if not any([visible_rows_data, visible_columns_data]):
    #         return 
    #     model = self.model()
    #     for msrs_uuid in visible_rows_data.keys():
    #         hide = visible_rows_data[msrs_uuid]
    #         qmodelindex = model.get_index_by_uuid(msrs_uuid)
    #         if not qmodelindex or not qmodelindex.isValid():
    #             continue
    #         item = qmodelindex.internalPointer()
    #         identifier = item.get_identifier()
    #         msg = 'Applying row visibility: "{}". '.format(identifier)
    #         msg += 'Hide: {}'.format(hide)
    #         self.logMessage.emit(msg, logging.INFO)
    #         self.setRowHidden(qmodelindex.row(), qmodelindex.parent(), hide)


    # def get_row_visibility_data(self):
    #     '''
    #     Collect cell visibility data for each MSRS UUID.

    #     Args:
    #         cell_visibility_data (dict):
    #     '''
    #     cell_visibility_data = dict()
    #     model = self.model()
    #     for pass_qmodelindex in model.get_pass_for_env_items_indices():
    #         is_hidden = self.isRowHidden(pass_qmodelindex.row(), pass_qmodelindex.parent())
    #         cell_visibility_data[pass_qmodelindex.get_identity_id()] = is_hidden
    #     for group_qmodelindex in model.get_group_items_indices():     
    #         is_hidden = self.isRowHidden(group_qmodelindex.row(), group_qmodelindex.parent())      
    #         cell_visibility_data[group_qmodelindex.get_identity_id()] = is_hidden
    #     return cell_visibility_data


    ##########################################################################
    # Items


    def get_render_item_for_column(self, column):
        '''
        Get a render item for a particular column.

        Args:
            column (int):

        Returns:
            render_item (RenderItem): or subclass
        '''
        return self.model().get_render_item_for_column(column)


    def get_render_items(self, visible_only=False):
        '''
        Get all or visible render item data objects.

        Args:
            visible_only (bool):

        Returns:
            render_items (list):
        '''
        model = self.model()
        if visible_only:
            render_items = list()
            for c, render_item in enumerate(model.get_render_items()):
                if not self.isColumnHidden(c + 1):
                    render_items.append(render_item)
            return render_items
        return model.get_render_items()


    def get_selected_items(self, selection=None):
        '''
        Get all items in this Multi Shot view that have QModelIndices that
        are part of current selection.

        Returns:
            selected_items (list):
        '''
        selection = selection or self.selectedIndexes()
        if not selection:
            return list()
        selected_items = list()
        for i, qmodelindex in enumerate(selection):
            if not qmodelindex.isValid():
                continue
            item = qmodelindex.internalPointer()
            selected_items.append(item)
        return selected_items


    def filter_selection(
            self,
            selection=None,
            include_environment_items=False,
            include_pass_for_env_items=True,
            include_group_items=False,
            visible_only=False):
        '''
        Filter the selection of MSRS QModelIndices to certain data object types.

        Args:
            selection (list): list of QModelIndices
            include_environment_items (bool):
            include_pass_for_env_items (bool):
            include_group_items (bool):
            visible_only (bool):

        Returns:
            items, qmodelindices (list): list of MSRS data objects and list of QModelIndices
        '''
        if selection == None:
            selection = self.selectedIndexes()
        items = list()
        qmodelindices = list()
        for qmodelindex in selection:
            if not qmodelindex.isValid():
                continue
            if visible_only and self.isIndexHidden(qmodelindex):
                continue
            item = qmodelindex.internalPointer()
            if include_environment_items and item.is_environment_item():
                items.append(item)
                qmodelindices.append(qmodelindex)
            elif include_pass_for_env_items and item.is_pass_for_env_item():
                items.append(item)
                qmodelindices.append(qmodelindex)
            elif include_group_items and item.is_group_item():
                items.append(item)
                qmodelindices.append(qmodelindex)
        return items, qmodelindices


    def get_visible_render_node_names(self):
        '''
        Collect visible render node names.

        Returns:
            render_node_names (list):
        '''
        render_node_names = set()
        for c, render_item in enumerate(self.get_render_items()):
            if self.isColumnHidden(c + 1):
                continue
            render_node_names.add(str(render_item.get_node_name()))
        return list(render_node_names)


    def get_selected_uuids(self):
        '''
        Get all the UUIDs of the items in Multi Shot view that have QModelIndices.

        Returns:
            identity_ids (set):
        '''
        identity_ids = set()
        for item in self.get_selected_items():
            identity_id = item.get_identity_id()
            if identity_id:
                identity_ids.add(identity_id)
        return identity_ids


    def get_selected_environment_items(self):
        '''
        Get all the selected EnvironmentItem in this view.

        Returns:
            items (list): list of EnvironmentItem or subclasses
        '''
        items = set()
        for item in self.get_selected_items():
            if item.is_environment_item():
                items.add(item)
        return list(items)


    def get_selected_pass_for_env_items(self):
        '''
        Get all the selected RenderPassForEnvItem in this view.

        Returns:
            items (list): list of RenderPassForEnvItem or subclasses
        '''
        items = set()
        for item in self.get_selected_items():
            if item.is_pass_for_env_item():
                items.add(item)
        return list(items)


    def get_identifiers_in_selection(
            self,
            include_envs=False):
        ''''
        Get all the identifier in selection, optionally including selected environments.

        Args:
            include_envs (bool): whether to include selected environment identifiers from selection or not

        Returns:
            identifiers (list):
        '''
        selection = self.selectedIndexes()
        if not selection:
            return list()
        identifiers = list()
        for i, qmodelindex in enumerate(selection):
            if not qmodelindex.isValid():
                continue
            item = qmodelindex.internalPointer()
            if item.is_group_item():
                continue
            if item.is_environment_item():
                if not include_envs:
                    continue
                identifier = item.get_environment_name_nice()
            else:
                identifier = item.get_identifier(nice_env_name=True)
            identifiers.append(identifier)
        return identifiers


    ##########################################################################
    # Context menus and operations


    def _create_context_menu_header(
            self, 
            pos, 
            show=True):
        '''
        Build a QMenu for tree view header.

        Args:
            show (bool): show the menu after populating or not

        Returns:
            menu (QtGui.QMenu):
        '''
        if self._in_wait_on_interactive_mode:
            return

        from Qt.QtWidgets import QMenu

        font_italic = QFont()
        font_italic.setFamily(constants.FONT_FAMILY)
        font_italic.setItalic(True)

        menu = QMenu('Header actions', self)

        # menu = searchable_menu.SearchableMenu(
        #     'Header actions',
        #     parent=self)

        model = self.model()
        header = self.header()
        column = header.logicalIndexAt(pos)

        # msg = 'Render Nodes Actions'
        # action = srnd_qt.base.utils.context_menu_add_menu_item(menu, msg)
        # action.setFont(font_italic)
        # menu.addAction(action)

        render_items = model.get_render_items()
        is_render_item_column = column > 0 and column < len(render_items) + 1
        if is_render_item_column:
            render_item = model.get_render_items()[column - 1]

            render_node_name = render_item.get_name()
            pass_name = render_item.get_pass_name()

            node_colour = render_item.get_node_colour()
            if not node_colour or isinstance(node_colour, (list, tuple)):
                node_colour = list(node_colour or [0, 0, 0]) # fallback if None
                node_colour.append(1.0)

            action = srnd_qt.base.utils.context_menu_add_menu_item(
                menu,
                'Select',
                icon_path=os.path.join(constants.ICONS_DIR_QT, 'select_s01.png'))
            method_to_call = functools.partial(
                self.render_node_operation,
                column,
                operation='Select')
            action.triggered.connect(method_to_call)
            menu.addAction(action)

            if constants.ALLOW_RENAME_FROM_COLUMN_HEADER:
                action = srnd_qt.base.utils.context_menu_add_menu_item(
                    menu,
                    'Rename')
                method_to_call = functools.partial(
                    self.render_node_operation,
                    column,
                    operation='Rename Node')
                action.triggered.connect(method_to_call)
                menu.addAction(action)

            if constants.ALLOW_TOGGLE_ENABLED_FROM_COLUMN_HEADER and header.get_draw_header_disabled_hint():
                action = srnd_qt.base.utils.context_menu_add_menu_item(
                    menu,
                    'Toggle enabled')
                method_to_call = functools.partial(
                    self.render_node_operation,
                    column,
                    operation='Toggle Enabled')
                action.triggered.connect(method_to_call)
                menu.addAction(action)

            action = srnd_qt.base.utils.context_menu_add_menu_item(
                menu,
                'Refresh',
                icon_path=os.path.join(constants.ICONS_DIR_QT, 'sync.png'))
            method_to_call = functools.partial(
                self.render_node_operation,
                column,
                operation='Sync')
            action.triggered.connect(method_to_call)
            menu.addAction(action)

            if constants.ALLOW_SET_COLOUR_FROM_COLUMN_HEADER and header.get_draw_header_node_colour():
                action = srnd_qt.base.utils.context_menu_add_menu_item(
                    menu,
                    'Set colour')
                pixmap = QPixmap(12, 12)
                if isinstance(node_colour, basestring):
                    colour = QColor(node_colour)
                else:
                    colour = QColor.fromRgbF(*node_colour)
                pixmap.fill(colour)
                icon = QIcon(pixmap)
                action.setIcon(icon)
                method_to_call = functools.partial(
                    self.render_node_operation,
                    column,
                    operation='Pick Colour')
                action.triggered.connect(method_to_call)
                menu.addAction(action)

            action = srnd_qt.base.utils.context_menu_add_menu_item(
                menu,
                'Remove from multi shot submitter',
                icon_path=os.path.join(SRND_QT_ICONS_DIR, 'dismiss.png'))
            method_to_call = functools.partial(
                self.render_node_operation,
                column,
                operation='Remove')
            action.triggered.connect(method_to_call)
            menu.addAction(action)

            if constants.ALLOW_DELETE_FROM_COLUMN_HEADER:
                action = srnd_qt.base.utils.context_menu_add_menu_item(
                    menu,
                    'Delete',
                    icon_path=os.path.join(ICONS_DIR, 'delete_s01.png'))
                method_to_call = functools.partial(
                    self.render_node_operation,
                    column,
                    operation='Delete')
                action.triggered.connect(method_to_call)
                menu.addAction(action)

            menu.addSeparator()

            action = srnd_qt.base.utils.context_menu_add_menu_item(
                menu,
                'Queue all')
            method_to_call = functools.partial(
                self.render_node_operation,
                column,
                operation='Queue enabled passes along column')
            action.triggered.connect(method_to_call)
            menu.addAction(action)

            action = srnd_qt.base.utils.context_menu_add_menu_item(
                menu,
                'Unqueue All')
            method_to_call = functools.partial(
                self.render_node_operation,
                column,
                operation='Unqueue enabled passes along column')
            action.triggered.connect(method_to_call)
            menu.addAction(action)

            menu.addSeparator()

        action = srnd_qt.base.utils.context_menu_add_menu_item(
            menu,
            'Show all columns',
            icon_path=os.path.join(SRND_QT_ICONS_DIR, 'visibility_on_s01.png'))
        action.triggered.connect(
            lambda *x: self.set_all_columns_visible(
                show=True,
                skip_columns=[0]))
        menu.addAction(action)

        action = srnd_qt.base.utils.context_menu_add_menu_item(
            menu,
            'Hide this column',
            icon_path=os.path.join(SRND_QT_ICONS_DIR, 'visibility_off_s01.png'))
        method_to_call = functools.partial(
            self.setColumnHidden,
                column,
                True)
        action.triggered.connect(method_to_call)
        menu.addAction(action)

        more_visibility_actions = QMenu('More column actions', menu)
        menu.addMenu(more_visibility_actions)   

        # msg = 'Render Nodes Visible To View'
        # action = srnd_qt.base.utils.context_menu_add_menu_item(menu, msg)
        # action.setFont(font_italic)
        # menu.addAction(action)

        action = srnd_qt.base.utils.context_menu_add_menu_item(
            menu,
            'Show all enabled columns',
            icon_path=os.path.join(SRND_QT_ICONS_DIR, 'visibility_on_s01.png'))
        action.triggered.connect(
            lambda *x: self.toggle_columns_by_state(show_active=True))
        more_visibility_actions.addAction(action)

        if is_render_item_column:
            action = srnd_qt.base.utils.context_menu_add_menu_item(
                menu,
                'Hide all columns except: "{}"'.format(render_node_name),
                icon_path=os.path.join(SRND_QT_ICONS_DIR, 'visibility_off_s01.png'))
            method_to_call = functools.partial(
                self.set_all_columns_visible,
                show=False,
                skip_columns=[0, column])
            action.triggered.connect(method_to_call)
            more_visibility_actions.addAction(action)

        action = srnd_qt.base.utils.context_menu_add_menu_item(
            menu,
            'Hide all disabled columns',
            icon_path=os.path.join(SRND_QT_ICONS_DIR, 'visibility_off_s01.png'))
        action.triggered.connect(
            lambda *x: self.toggle_columns_by_state(hide_inactive=True))
        more_visibility_actions.addAction(action)

        action = srnd_qt.base.utils.context_menu_add_menu_item(
            menu,
            'Hide columns of selected items',
            icon_path=os.path.join(SRND_QT_ICONS_DIR, 'visibility_off_s01.png'))
        action.triggered.connect(
            lambda *x: self.toggle_columns_by_state(hide_selected=True))
        more_visibility_actions.addAction(action)

        more_visibility_actions.addSeparator()

        action = srnd_qt.base.utils.context_menu_add_menu_item(
            menu,
            'Show disabled hints',
            checkable=True,
            checked=self.header().get_draw_header_disabled_hint())
        action.toggled.connect(self.header().set_draw_header_disabled_hint)
        more_visibility_actions.addAction(action)    

        action = srnd_qt.base.utils.context_menu_add_menu_item(
            menu,
            'Show render node colour hints',
            checkable=True,
            checked=self.header().get_draw_header_node_colour())
        action.toggled.connect(self.header().set_draw_header_node_colour)
        more_visibility_actions.addAction(action)    

        more_visibility_actions.addSeparator()

        action = srnd_qt.base.utils.context_menu_add_menu_item(
            menu,
            'Reset column widths')
        action.triggered.connect(self.reset_column_sizes)
        more_visibility_actions.addAction(action)

        action = srnd_qt.base.utils.context_menu_add_menu_item(
            menu,
            'Alphabetize columns')
        action.triggered.connect(self.setup_columns)
        more_visibility_actions.addAction(action)

        more_visibility_actions.addSeparator()

        toggle_columns_menu = QMenu('Toggle columns', menu)
        more_visibility_actions.addMenu(toggle_columns_menu)

        # Allow specific columns to be hidden, or shown
        for c, render_item in enumerate(model.get_render_items()):
            column = c + 1
            visible = not self.isColumnHidden(column)
            node_name = render_item.get_node_name()
            pass_name = render_item.get_pass_name()
            action_text = node_name + ' (Pass: {})'.format(pass_name)
            action = srnd_qt.base.utils.context_menu_add_menu_item(
                toggle_columns_menu,
                action_text,
                checkable=True,
                checked=visible)
            method_to_call = functools.partial(
                self.toggle_column_visibility,
                columns=[column])
            action.toggled.connect(method_to_call)
            toggle_columns_menu.addAction(action)

        more_visibility_actions.addSeparator()

        self._populate_menu_with_pass_visibility_actions(more_visibility_actions)

        if show:
            menu.exec_(QCursor.pos())
        
        return menu


    def _populate_menu_with_pass_visibility_actions(self, menu):
        '''
        Populate an existing QMenu with render nodes visibility actions.

        Args:
            menu (QMenu)
        '''
        from Qt.QtWidgets import QMenu

        # font_italic = QFont()
        # font_italic.setFamily(constants.FONT_FAMILY)
        # font_italic.setItalic(True)

        # menu_base = QMenu('Pass visibility', self)

        # msg = 'Pass visibility sets'
        # action = srnd_qt.base.utils.context_menu_add_menu_item(menu, msg)
        # action.setFont(font_italic)
        # menu.addAction(action)

        action = srnd_qt.base.utils.context_menu_add_menu_item(
            menu,
            'Create pass visibility set',
            icon_path=os.path.join(SRND_QT_ICONS_DIR, 'visibility_on_s01.png'))
        action.triggered.connect(self.create_pass_visibility_set)
        menu.addAction(action)

        sets_names = self.get_pass_visibility_sets_names()
        if sets_names:
            menu_render_nodes_vis_set_show = QMenu(
                'Set columns visible by pass visibility set',
                menu)
            icon = QIcon(os.path.join(SRND_QT_ICONS_DIR, 'visibility_on_s01.png'))
            menu_render_nodes_vis_set_show.setIcon(icon)
            menu.addMenu(menu_render_nodes_vis_set_show)
            for visibility_set_name in sets_names:
                action = srnd_qt.base.utils.context_menu_add_menu_item(
                    menu_render_nodes_vis_set_show,
                    visibility_set_name)
                method_to_call = functools.partial(
                    self.apply_pass_visibility_set,
                    visibility_set_name)
                action.triggered.connect(method_to_call)
                menu_render_nodes_vis_set_show.addAction(action)

            menu_render_nodes_vis_set_update = QMenu(
                'Update pass visibility set',
                menu)
            menu.addMenu(menu_render_nodes_vis_set_update)

            for visibility_set_name in sets_names:
                action = srnd_qt.base.utils.context_menu_add_menu_item(
                    menu_render_nodes_vis_set_update,
                    visibility_set_name)
                method_to_call = functools.partial(
                    self.update_pass_visibility_set_by_name,
                    visibility_set_name)
                action.triggered.connect(method_to_call)
                menu_render_nodes_vis_set_update.addAction(action)

            menu_render_nodes_vis_set_delete = QMenu(
                'Delete pass visibility set',
                menu)
            icon = QIcon(os.path.join(ICONS_DIR, 'delete_s01.png'))
            menu_render_nodes_vis_set_delete.setIcon(icon)
            menu.addMenu(menu_render_nodes_vis_set_delete)

            for visibility_set_name in sets_names:
                action = srnd_qt.base.utils.context_menu_add_menu_item(
                    menu_render_nodes_vis_set_delete,
                    visibility_set_name)
                method_to_call = functools.partial(
                    self.delete_pass_visibility_set_by_name,
                    visibility_set_name)
                action.triggered.connect(method_to_call)
                menu_render_nodes_vis_set_delete.addAction(action)

            action = srnd_qt.base.utils.context_menu_add_menu_item(
                menu,
                'Delete all pass visibility sets',
                icon_path=os.path.join(ICONS_DIR, 'delete_s01.png'))
            action.triggered.connect(self.delete_all_pass_visibility_sets)
            menu.addAction(action)


    def _create_context_menu(
            self,
            pos=None,
            show=True,
            include_search=True):
        '''
        Build a QMenu for this main MSRS tree view.
        Reimplemented from super class.

        Args:
            pos (QPoint):
            show (bool):
            include_search (bool):

        Returns:
            menu (QtGui.QMenu):
        '''
        if self._in_wait_on_interactive_mode:
            return

        from Qt.QtWidgets import QMenu

        model = self.model()
        selection_model = self.selectionModel()
        selection = selection_model.selectedIndexes()

        # This menu is empty if no click position provided or no selected tree items
        if not any([pos, selection]):
            return QMenu()

        # Default to column 0 for EnvironmentItem actions
        column = 0
        # Column under click position (if pos argument provided)
        if pos:
            column = self.header().logicalIndexAt(pos)
        # Use column from last selected item
        elif selection:
            column = selection[-1].column()

        item = None
        enabled, queued = True, True
        render_overrides_items = collections.OrderedDict()
        version_override = None
        note_override = None
        production_range_source = None
        frame_resolve_order_env_first = True
        split_frame_ranges = False
        colour = None
        frame_range_override = None
        frame_rule_important = False
        frame_rule_fml = False
        frames_rule_x10 = False
        frames_rule_x1 = False
        frames_rule_xn = None
        not_frame_range_override = None
        frame_rule_not_important = False
        frame_rule_not_fml = False
        frame_rule_not_x10 = False
        frame_rule_not_xn = None
        plow_dispatcher_job_id = None
        plow_job_id = None
        plow_layer_id = None
        # plow_task_id = None
        qmodelindex = self.get_first_qmodelindex(pos, selection)
        if qmodelindex:
            item = qmodelindex.internalPointer()
            if qmodelindex.isValid() and not item.is_group_item():
                enabled = item.get_enabled()
                render_overrides_items = item.get_render_overrides_items()
                version_override = item.get_version_override()
                note_override = item.get_note_override()
                if item.is_environment_item():
                    queued = bool(item._get_renderable_count_for_env())
                    production_range_source = item.get_production_range_source()
                    frame_resolve_order_env_first = item.get_frame_resolve_order_env_first()
                    split_frame_ranges = item.get_split_frame_ranges()
                else:
                    queued = item.get_queued()
                colour = item.get_colour()
                frame_range_override = item.get_frame_range_override()
                frame_rule_important = item.get_frames_rule_important()
                frame_rule_fml = item.get_frames_rule_fml()
                frames_rule_x10 = item.get_frames_rule_x10()
                frames_rule_x1 = item.get_frames_rule_x1()
                frames_rule_xn = item.get_frames_rule_xn()
                not_frame_range_override = item.get_not_frame_range_override()
                frame_rule_not_important = item.get_not_frames_rule_important()
                frame_rule_not_fml = item.get_not_frames_rule_fml()
                frame_rule_not_x10 = item.get_not_frames_rule_x10()
                frame_rule_not_xn = item.get_not_frames_rule_xn()
                if item.is_pass_for_env_item():
                    plow_dispatcher_job_id = item.get_dispatcher_plow_job_id()
                    plow_job_id = item.get_plow_job_id_last()
                    plow_layer_id = item.get_plow_layer_id_last()
                    # plow_task_id = item.get_plow_layer_id_last()

        pos = QCursor.pos()

        # Work out if right clicked background of cell, or override within cell
        clicked_override, override_id = False, None
        qmodelindex_under_mouse = self.currentIndex()
        widget = self.indexWidget(qmodelindex_under_mouse)
        if widget:
            widget_pos = widget.mapFromGlobal(pos)
            # NOTE: Context menu requested, so update bounds for overlays under mouse by triggering paintEvent.
            # NOTE: Repainting the widget will insure the cached bounds rectangles are up to date.
            # NOTE: This repaint is not triggered directly from the paintEvent (otherwise infinite recursion).
            widget.repaint()
            # NOTE: Check which override is under cursor from cached rectangles
            override_id, override_info = widget._get_override_info_at_qpoint(widget_pos)
            clicked_override = bool(override_id) and override_id != '..'

        font_italic = QFont()
        font_italic.setFamily(constants.FONT_FAMILY)
        font_italic.setItalic(True)

        if clicked_override:
            menu_base = QMenu(self)

            render_overrides_manager = model.get_render_overrides_manager()
            render_overrides_plugins_ids = render_overrides_manager.get_render_overrides_plugins_ids()

            # # Will be the first action label for context menu for specific override
            # action = srnd_qt.base.utils.context_menu_add_menu_item(
            #     self,
            #     'Modify override')
            # action.setFont(font_italic)
            # action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            # menu_base.addAction(action)
            # menu_base.addSeparator()

            action_remove = None
            if override_id in render_overrides_plugins_ids:
                action_remove = srnd_qt.base.utils.context_menu_add_menu_item(
                    self,
                    'Remove render override',
                    icon_path=os.path.join(SRND_QT_ICONS_DIR, 'dismiss.png'))
                action_remove.setShortcutContext(Qt.WidgetWithChildrenShortcut)
                method_to_call = functools.partial(
                    self.remove_render_overrides_from_selection,
                    override_id)
                action_remove.triggered.connect(method_to_call)
            elif override_id:
                action_remove = srnd_qt.base.utils.context_menu_add_menu_item(
                    self,
                    'Remove override',
                    icon_path=os.path.join(SRND_QT_ICONS_DIR, 'dismiss.png'))
                action_remove.setShortcutContext(Qt.WidgetWithChildrenShortcut)
                method_to_call = functools.partial(
                    self.clear_overrides_in_selection_by_id,
                    override_id)
                action_remove.triggered.connect(method_to_call)
            if action_remove:
                menu_base.addAction(action_remove)

            # Edit override action
            # TODO: The core override id should match render pass for env
            # widget cached key, and session data key, to avoid this if branching...
            # NOTE: Although for edit action, not every override
            # needs to expose this, or has a dedicated dialog to set values...
            action_edit = None
            if override_id in render_overrides_plugins_ids:
                action_edit = srnd_qt.base.utils.context_menu_add_menu_item(
                    self,
                    'Edit render override',
                    icon_path=os.path.join(ICONS_DIR, 'edit_s01.png'))
                action_edit.setShortcutContext(Qt.WidgetWithChildrenShortcut)
                method_to_call = functools.partial(
                    self.add_render_overrides_to_selection,
                    override_id,
                    value=None,
                    show_dialog=True)
                action_edit.triggered.connect(method_to_call)
            # Use collected values for these edit mode
            elif override_id == constants.OVERRIDE_FRAMES_XCUSTOM:
                action_edit = srnd_qt.base.utils.context_menu_add_menu_item(
                    self,
                    'Edit override',
                    icon_path=os.path.join(ICONS_DIR, 'edit_s01.png'))
                action_edit.setShortcutContext(Qt.WidgetWithChildrenShortcut)
                method_to_call = functools.partial(
                    self._tree_view_operations,
                    operation=constants.OVERRIDE_FRAMES_XCUSTOM,
                    value=frames_rule_xn)
                action_edit.triggered.connect(method_to_call)
            elif override_id == constants.OVERRIDE_FRAMES_NOT_XCUSTOM:
                action_edit = srnd_qt.base.utils.context_menu_add_menu_item(
                    self,
                    'Edit override',
                    icon_path=os.path.join(ICONS_DIR, 'edit_s01.png'))
                action_edit.setShortcutContext(Qt.WidgetWithChildrenShortcut)
                method_to_call = functools.partial(
                    self._tree_view_operations,
                    operation=constants.OVERRIDE_FRAMES_NOT_XCUSTOM,
                    value=frame_rule_not_xn)
                action_edit.triggered.connect(method_to_call)
            # Check if can call edit_override_id_for_selection to handle other edit mode of built in override
            elif model.check_override_is_editable(override_id):
                action_edit = srnd_qt.base.utils.context_menu_add_menu_item(
                    self,
                    'Edit override',
                    icon_path=os.path.join(ICONS_DIR, 'edit_s01.png'))
                action_edit.setShortcutContext(Qt.WidgetWithChildrenShortcut)
                method_to_call = functools.partial(
                    self.edit_override_id_for_selection,
                    override_id)
                action_edit.triggered.connect(method_to_call)
            if action_edit:
                menu_base.addAction(action_edit)

            action_copy = None
            if override_id in render_overrides_plugins_ids:
                action_copy = srnd_qt.base.utils.context_menu_add_menu_item(
                    self,
                    'Copy render override',
                    icon_path=os.path.join(ICONS_DIR, 'copy_s01.png'))
                action_copy.setShortcutContext(Qt.WidgetWithChildrenShortcut)
                method_to_call = functools.partial(
                    self.copy_render_overrides_from_selection,
                    override_id)
                action_copy.triggered.connect(method_to_call)
            elif override_id:
                action_copy = srnd_qt.base.utils.context_menu_add_menu_item(
                    self,
                    'Copy override',
                    icon_path=os.path.join(ICONS_DIR, 'copy_s01.png'))
                action_copy.setShortcutContext(Qt.WidgetWithChildrenShortcut)
                method_to_call = functools.partial(
                    self.copy_overrides_in_selection_by_id,
                    override_id)
                action_copy.triggered.connect(method_to_call)
            if action_copy:
                menu_base.addAction(action_copy)

            if override_id in render_overrides_plugins_ids:
                action_validate = srnd_qt.base.utils.context_menu_add_menu_item(
                    self, 'Validate render override')
                action_validate.setShortcutContext(Qt.WidgetWithChildrenShortcut)
                action_validate.triggered.connect(
                    self.validate_all_render_overrides_from_selection)
                menu_base.addAction(action_validate)

            # Allow user to access all other overrides actions via sub menu
            menu_sub = QMenu('Full overrides menu...', menu_base)
            menu_base.addMenu(menu_sub)
            # Setting menu for subsquent add operations to this sub menu
            menu = menu_sub
        else:
            action_label = 'Overrides for selection'
            if include_search and self._menu_include_search:
                menu_base = searchable_menu.SearchableMenu(
                    action_label,
                    parent=self)
            else:
                # This is the zero item to prevent user accidental click on first menu item, as right clicking.
                menu_base = QMenu(action_label, self)
                # action = srnd_qt.base.utils.context_menu_add_menu_item(
                #     self,
                #     'Overrides')
                # action.setFont(font_italic)
                # action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
                # menu_base.addAction(action)
                # menu_base.addSeparator()
            # Setting menu for subsquent add operations to this sub menu
            menu = menu_base

        if column == 0:

            action = srnd_qt.base.utils.context_menu_add_menu_item(
                self,
                'Queue enabled passes',
                checkable=True,
                checked=queued)
            action.toggled.connect(lambda x: self.queue(queue=x))
            action.setShortcut('Q')
            action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            menu.addAction(action)
        else:
            action = srnd_qt.base.utils.context_menu_add_menu_item(
                self,
                'Queued',
                checkable=True,
                checked=queued)
            action.toggled.connect(lambda x: self.queue(queue=x))
            action.setShortcut('Q')
            action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            menu.addAction(action)

            action = srnd_qt.base.utils.context_menu_add_menu_item(
                self,
                'Enabled',
                checkable=True,
                checked=enabled)
            action.toggled.connect(
                lambda x: self._tree_view_operations(x, operation='Enabled'))
            action.setShortcut('D')
            action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            menu.addAction(action)

        menu.addSeparator()

        self._add_render_actions_to_menu(menu, include_batch_all=False)

        menu.addSeparator()

        # Optionally put all versions actions into one menu
        if not self._menu_some_actions_at_top:
            version_menu = QMenu('Version...', self)
            menu.addMenu(version_menu)
            menu_to_add_actions = version_menu
        # Otherwise put some version actions at top of menu
        else:
            menu_to_add_actions = menu

        if column > 0 or constants.EXPOSE_SHOT_OVERRIDES:
            action = srnd_qt.base.utils.context_menu_add_menu_item(
                self,
                'Version up',
                checkable=True,
                checked=version_override == constants.CG_VERSION_SYSTEM_PASS_NEXT)
            action.toggled.connect(
                lambda x: self._tree_view_operations(x, operation='Version up'))
            action.setShortcut('V')
            action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            menu_to_add_actions.addAction(action)

            action = srnd_qt.base.utils.context_menu_add_menu_item(
                self,
                constants.OVERRIDE_VERSION_CUSTOM,
                checkable=True,
                checked=isinstance(version_override, int))
            action.toggled.connect(
                lambda x: self._tree_view_operations(
                    x,
                    operation=constants.OVERRIDE_VERSION_CUSTOM))
            action.setShortcut('SHIFT+V')
            action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            menu_to_add_actions.addAction(action)

            ##################################################################
            # Version sub menu

            if self._menu_some_actions_at_top:
                version_menu = QMenu('More version actions...', self)
                menu.addMenu(version_menu)

            action = srnd_qt.base.utils.context_menu_add_menu_item(
                self,
                'Version up (match passes)',
                checkable=True,
                checked=version_override == constants.CG_VERSION_SYSTEM_PASSES_NEXT)
            action.toggled.connect(
                lambda x: self._tree_view_operations(
                    x, operation='Version up (match passes)'))
            action.setShortcut('P')
            action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            version_menu.addAction(action)

            action = srnd_qt.base.utils.context_menu_add_menu_item(
                self,
                'Version match scene',
                checkable=True,
                checked=version_override == constants.CG_VERSION_SYSTEM_MATCH_SCENE)
            action.toggled.connect(
                lambda x: self._tree_view_operations(
                    x, operation='Version match scene'))
            action.setShortcut('S')
            action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            version_menu.addAction(action)

            if column > 0:
                version_menu.addSeparator()

                action = srnd_qt.base.utils.context_menu_add_menu_item(
                    self,
                    'Derive explicit version from render item')
                action.triggered.connect(
                    lambda *x: self._tree_view_operations(
                        operation='Derive explicit version'))
                action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
                version_menu.addAction(action)

                action = srnd_qt.base.utils.context_menu_add_menu_item(
                    self,
                    'Derive next max version in selection and set as custom')
                action.triggered.connect(self.derive_highest_version_and_apply)
                action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
                version_menu.addAction(action)

            # Resolving versions can be performed as selection changes and details
            # panel is updated, or on demand by right clicking and performing on items.
            if not self.get_auto_resolve_versions():
                version_menu.addSeparator()

                action = srnd_qt.base.utils.context_menu_add_menu_item(
                    self,
                    'Update resolved versions in details panel')
                action.triggered.connect(self._resolve_versions_for_selection)
                action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
                version_menu.addAction(action)

            self._add_more_versions_actions_to_menu(version_menu)

            ##################################################################

            # Optionally put all frame actions into one menu
            if not self._menu_some_actions_at_top:
                frames_menu = QMenu('Frames...', self)
                menu.addMenu(frames_menu)
                menu_to_add_actions = frames_menu
            # Otherwise put some version actions at top of menu
            else:
                menu.addSeparator()
                menu_to_add_actions = menu

            action = srnd_qt.base.utils.context_menu_add_menu_item(
                self,
                constants.OVERRIDE_FRAMES_FML,
                checkable=True,
                checked=bool(frame_rule_fml))
            action.toggled.connect(
                lambda x: self._tree_view_operations(
                    x,
                    operation=constants.OVERRIDE_FRAMES_FML))
            action.setShortcut('F')
            action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            menu_to_add_actions.addAction(action)

            action = srnd_qt.base.utils.context_menu_add_menu_item(
                self,
                constants.OVERRIDE_FRAMES_CUSTOM,
                checkable=True,
                checked=bool(frame_range_override))
            action.toggled.connect(
                lambda x: self._tree_view_operations(
                    x,
                    operation=constants.OVERRIDE_FRAMES_CUSTOM))
            action.setShortcut('SHIFT+F')
            action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            menu_to_add_actions.addAction(action)

            ##################################################################
            # Frames sub menu

            if self._menu_some_actions_at_top:
                frames_menu = QMenu('More frames actions...', self)
                menu.addMenu(frames_menu)

            action = srnd_qt.base.utils.context_menu_add_menu_item(
                self,
                constants.OVERRIDE_FRAMES_X10,
                checkable=True,
                checked=bool(frames_rule_x10))
            action.toggled.connect(
                lambda x: self._tree_view_operations(
                    x,
                    operation=constants.OVERRIDE_FRAMES_X10))
            action.setShortcut('T')
            action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            frames_menu.addAction(action)

            action = srnd_qt.base.utils.context_menu_add_menu_item(
                self,
                constants.OVERRIDE_FRAMES_X1,
                checkable=True,
                checked=bool(frames_rule_x1))
            action.toggled.connect(
                lambda x: self._tree_view_operations(
                    x,
                    operation=constants.OVERRIDE_FRAMES_X1))
            action.setShortcut('O')
            action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            frames_menu.addAction(action)

            action = srnd_qt.base.utils.context_menu_add_menu_item(
                self,
                constants.OVERRIDE_FRAMES_XCUSTOM,
                checkable=True,
                checked=bool(frames_rule_xn))
            action.toggled.connect(
                lambda x: self._tree_view_operations(
                    x,
                    operation=constants.OVERRIDE_FRAMES_XCUSTOM))
            action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            frames_menu.addAction(action)

            action = srnd_qt.base.utils.context_menu_add_menu_item(
                self,
                constants.OVERRIDE_FRAMES_IMPORTANT,
                checkable=True,
                checked=bool(frame_rule_important))
            action.toggled.connect(
                lambda x: self._tree_view_operations(
                    x,
                    operation=constants.OVERRIDE_FRAMES_IMPORTANT))
            action.setShortcut('I')
            action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            frames_menu.addAction(action)

            action = srnd_qt.base.utils.context_menu_add_menu_item(
                self,
                constants.OVERRIDE_FRAMES_NOT_IMPORTANT,
                checkable=True,
                checked=bool(frame_rule_not_important))
            action.toggled.connect(
                lambda x: self._tree_view_operations(
                    x,
                    operation=constants.OVERRIDE_FRAMES_NOT_IMPORTANT))
            action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            frames_menu.addAction(action)

            action = srnd_qt.base.utils.context_menu_add_menu_item(
                self,
                constants.OVERRIDE_FRAMES_NOT_FML,
                checkable=True,
                checked=bool(frame_rule_not_fml))
            action.toggled.connect(
                lambda x: self._tree_view_operations(
                    x,
                    operation=constants.OVERRIDE_FRAMES_NOT_FML))
            action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            frames_menu.addAction(action)

            action = srnd_qt.base.utils.context_menu_add_menu_item(
                self,
                constants.OVERRIDE_FRAMES_NOT_X10,
                checkable=True,
                checked=bool(frame_rule_not_x10))
            action.toggled.connect(
                lambda x: self._tree_view_operations(
                    x,
                    operation=constants.OVERRIDE_FRAMES_NOT_X10))
            action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            frames_menu.addAction(action)

            action = srnd_qt.base.utils.context_menu_add_menu_item(
                self,
                constants.OVERRIDE_FRAMES_NOT_XCUSTOM,
                checkable=True,
                checked=bool(frame_rule_not_xn))
            action.toggled.connect(
                lambda x: self._tree_view_operations(
                    x,
                    operation=constants.OVERRIDE_FRAMES_NOT_XCUSTOM))
            action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            frames_menu.addAction(action)

            action = srnd_qt.base.utils.context_menu_add_menu_item(
                self,
                constants.OVERRIDE_FRAMES_NOT_CUSTOM,
                checkable=True,
                checked=bool(not_frame_range_override))
            action.toggled.connect(
                lambda x: self._tree_view_operations(
                    x,
                    operation=constants.OVERRIDE_FRAMES_NOT_CUSTOM))
            action.setShortcut('SHIFT+ALT+F')
            action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            frames_menu.addAction(action)

            if constants.EXPOSE_SPLIT_FRAME_JOB and column == 0:
                frames_menu.addSeparator()
                
                action = srnd_qt.base.utils.context_menu_add_menu_item(
                    self,
                    'Split frames job',
                    checkable=True,
                    checked=split_frame_ranges)
                action.toggled.connect(self.split_frames_job_selected_environments)
                action.setStatusTip(constants.OVERRIDE_SPLIT_FRAME_RANGES_LONG)
                action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
                frames_menu.addAction(action)

            if production_range_source:
                frames_menu.addSeparator()

                msg = 'Set source production frame range'
                frames_to_resolve_against_menu = QMenu(msg, self)
                frames_menu.addMenu(frames_to_resolve_against_menu)

                action = srnd_qt.base.utils.context_menu_add_menu_item(
                    self,
                    'Cut range',
                    checkable=True,
                    checked='Cut' in production_range_source)
                action.toggled.connect(
                    lambda x: self._tree_view_operations(
                        x,
                        operation='SetSourceProductionRange_Cut'))
                action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
                frames_to_resolve_against_menu.addAction(action)

                action = srnd_qt.base.utils.context_menu_add_menu_item(
                    self,
                    'Delivery range',
                    checkable=True,
                    checked= 'Delivery' in production_range_source)
                action.toggled.connect(
                    lambda x: self._tree_view_operations(
                        x,
                        operation='SetSourceProductionRange_Delivery'))
                action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
                frames_to_resolve_against_menu.addAction(action)

                action = srnd_qt.base.utils.context_menu_add_menu_item(
                    self,
                    'Frame range',
                    checkable=True,
                    checked='FrameRange' in production_range_source)
                action.toggled.connect(
                    lambda x: self._tree_view_operations(
                        x,
                        operation='SetSourceProductionRange_FrameRange'))
                action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
                frames_to_resolve_against_menu.addAction(action)

                action = srnd_qt.base.utils.context_menu_add_menu_item(
                    self,
                    'Important',
                    checkable=True,
                    checked='Important' in production_range_source)
                action.toggled.connect(
                    lambda x: self._tree_view_operations(
                        x,
                        operation='SetSourceProductionRange_Important'))
                action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
                frames_to_resolve_against_menu.addAction(action)

                msg = 'Set frames resolve order'
                frames_resolve_order = QMenu(msg, self)
                frames_menu.addMenu(frames_resolve_order)

                action = srnd_qt.base.utils.context_menu_add_menu_item(
                    self,
                    'Environment first then pass',
                    checkable=True,
                    checked=frame_resolve_order_env_first)
                action.toggled.connect(
                    lambda x: self._tree_view_operations(
                        x,
                        operation='SetFramesResolveOrder'))
                action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
                frames_resolve_order.addAction(action)

                action = srnd_qt.base.utils.context_menu_add_menu_item(
                    self,
                    'Pass first then environment',
                    checkable=True,
                    checked=not frame_resolve_order_env_first)
                action.toggled.connect(
                    lambda x: self._tree_view_operations(
                        not x,
                        operation='SetFramesResolveOrder'))
                action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
                frames_resolve_order.addAction(action)

            if column > 0:
                frames_menu.addSeparator()

                action = srnd_qt.base.utils.context_menu_add_menu_item(
                    self,
                    'Derive frames from render item')
                action.triggered.connect(
                    lambda *x: self._tree_view_operations(
                        operation='Derive frames from render item'))
                action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
                frames_menu.addAction(action)

                msg = 'Set explicit versions on pass columns pointing to existing '
                msg += 'registered versions, to calculate missing frames. '
                action = srnd_qt.base.utils.context_menu_add_menu_item(
                    self,
                    'Derive missing frames for current resolved versions',
                    status_tip=msg)
                action.triggered.connect(self.derive_missing_frames_for_passes)
                action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
                frames_menu.addAction(action)

            ##################################################################
            # Job actions

            # Optionally put all job actions into one menu
            if not self._menu_some_actions_at_top:
                job_menu = QMenu('Job...', self)
                menu.addMenu(job_menu)
                menu_to_add_actions = job_menu
            # Otherwise put some job actions at top of menu
            else:
                menu.addSeparator()
                menu_to_add_actions = menu

            if column == 0:
                action = srnd_qt.base.utils.context_menu_add_menu_item(
                    self,
                    'Set job name')
                action.triggered.connect(
                    lambda *x: self.edit_job_identifier_for_selection())
                action.setShortcut('SHIFT+J')
                action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
                menu_to_add_actions.addAction(action)

            if self._menu_some_actions_at_top:
                job_menu = QMenu('More job actions...', self)
                menu.addMenu(job_menu)

            msg = 'Open dialog to define dependencies between MSRS items or to external jobs and layers.'
            action = srnd_qt.base.utils.context_menu_add_menu_item(
                self,
                'Set dependency',
                icon_path=os.path.join(ICONS_DIR, 'wait_20x20_s01.png'))
            action.setStatusTip(msg)
            action.triggered.connect(
                lambda *x: self.edit_wait_on_for_selection())
            action.setShortcut('SHIFT+CTRL+W')
            action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            job_menu.addAction(action)

            action = srnd_qt.base.utils.context_menu_add_menu_item(
                self,
                'Interactively define dependency',
                icon_path=os.path.join(ICONS_DIR, 'wait_20x20_s01.png'))
            action.triggered.connect(
                lambda *x: self.enter_wait_on_interactive())
            action.setShortcut('SHIFT+W')
            action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            job_menu.addAction(action)

            job_menu.addSeparator()

            if column == 0:
                action = srnd_qt.base.utils.context_menu_add_menu_item(
                    self,
                    'Clear job identifier')
                action.triggered.connect(
                    lambda *x: self.clear_overrides_in_selection_by_id(
                        constants.OVERRIDE_JOB_IDENTIFIER))
                action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
                job_menu.addAction(action)

            action = srnd_qt.base.utils.context_menu_add_menu_item(
                self,
                'Clear dependencies')
            action.triggered.connect(
                lambda *x: self.clear_overrides_in_selection_by_id(
                    constants.OVERRIDE_WAIT))
            action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            job_menu.addAction(action)

            action = srnd_qt.base.utils.context_menu_add_menu_item(
                self,
                'Validate dependencies')
            action.triggered.connect(
                lambda *x: self._tree_view_operations(
                    operation='Validate WAIT On'))
            action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            job_menu.addAction(action)

            action = srnd_qt.base.utils.context_menu_add_menu_item(
                self,
                'Clear render estimates cache')
            action.triggered.connect(
                lambda *x: self._tree_view_operations(
                    operation='Clear Render Estimates Cache'))
            action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            job_menu.addAction(action)

            action = srnd_qt.base.utils.context_menu_add_menu_item(
                self,
                'Clear Plow ids')
            action.triggered.connect(
                lambda *x: self._tree_view_operations(
                    operation='Clear Plow Ids'))
            action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            job_menu.addAction(action)

            job_menu.addSeparator()

            action = srnd_qt.base.utils.context_menu_add_menu_item(
                self,
                'Draw dependency overlays',
                checkable=True,
                checked=self._overlay_widget.get_draw_all_dependency_overlays())
            action.toggled.connect(
                self.set_draw_all_dependency_overlays)
            action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            job_menu.addAction(action)

            job_menu.addSeparator()

            if column > 0:

                show_plow_actions = any([
                    plow_dispatcher_job_id,
                    plow_job_id,
                    plow_job_id and plow_layer_id])

                if show_plow_actions:
                    msg = 'Plow Actions'
                    action = srnd_qt.base.utils.context_menu_add_menu_item(self, msg)
                    action.setFont(font_italic)
                    job_menu.addAction(action)

                if plow_dispatcher_job_id:
                    action = srnd_qt.base.utils.context_menu_add_menu_item(
                        self,
                        'KILL dispatcher plow jobs')
                    action.triggered.connect(
                        lambda *x: self.plow_modify_job_or_layer_stats(job_type='dispatcher'))
                    action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
                    job_menu.addAction(action)

                elif plow_job_id and plow_layer_id:
                    action = srnd_qt.base.utils.context_menu_add_menu_item(
                        self,
                        'EAT render plow layers')
                    action.triggered.connect(
                        lambda *x: self.plow_modify_job_or_layer_stats(job_type='layer'))
                    action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
                    job_menu.addAction(action)

                if plow_job_id:
                    action = srnd_qt.base.utils.context_menu_add_menu_item(
                        self,
                        'KILL render plow jobs')
                    action.triggered.connect(
                        lambda *x: self.plow_modify_job_or_layer_stats(job_type='job'))
                    action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
                    job_menu.addAction(action)

                if show_plow_actions:
                    action = srnd_qt.base.utils.context_menu_add_menu_item(
                        self,
                        'Choose log files to open')
                    action.triggered.connect(self.choose_plow_layer_log_to_open)
                    action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
                    job_menu.addAction(action)

            ##################################################################

            # Optionally put all other actions into one menu
            if not self._menu_some_actions_at_top:
                other_menu = QMenu('Other...', self)
                menu.addMenu(other_menu)
                menu_to_add_actions = other_menu
            # Otherwise put some other actions at top of menu
            else:
                menu.addSeparator()
                menu_to_add_actions = menu

            action = srnd_qt.base.utils.context_menu_add_menu_item(
                self,
                'Set note',
                icon_path=os.path.join(ICONS_DIR, 'nodeCommentActive20_hilite.png'))
            action.triggered.connect(
                lambda *x: self.edit_note_for_selection())
            action.setShortcut('SHIFT+N')
            action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            menu_to_add_actions.addAction(action)

            if self._menu_some_actions_at_top:
                other_menu = QMenu('More other actions...', self)
                menu.addMenu(other_menu)

            action = srnd_qt.base.utils.context_menu_add_menu_item(
                self,
                'Clear note')
            action.triggered.connect(
                lambda *x: self.clear_overrides_in_selection_by_id(
                    constants.OVERRIDE_NOTE))
            action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            other_menu.addAction(action)

            action = srnd_qt.base.utils.context_menu_add_menu_item(
                self,
                'Set colour')
            if not colour:
                colour = [1.0, 1.0, 1.0]
            colour = list(colour)
            colour[0] = int(colour[0] * 255)
            colour[1] = int(colour[1] * 255)
            colour[2] = int(colour[2] * 255)
            pixmap = QPixmap(12, 12)
            pixmap.fill(QColor(*colour))
            icon = QIcon(pixmap)
            action.setIcon(icon)
            action.triggered.connect(
                lambda *x: self.edit_colour_for_selection())
            action.setShortcut('SHIFT+C')
            action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            other_menu.addAction(action)

            action = srnd_qt.base.utils.context_menu_add_menu_item(
                self,
                'Clear colour')
            action.triggered.connect(
                lambda *x: self.clear_overrides_in_selection_by_id('MSRS_Colour'))
            action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            other_menu.addAction(action)

        if column == 0:
            tree = os.getenv('TREE') or 'shots'

            # Optionally put all shotsactions into one menu
            if not self._menu_some_actions_at_top:
                label = '{}...'.format(tree.title())
                shots_menu = QMenu(label, self)
                menu.addMenu(shots_menu)
                menu_to_add_actions = shots_menu
            # Otherwise put some shots actions at top of menu
            else:
                menu.addSeparator()
                menu_to_add_actions = menu

            action = srnd_qt.base.utils.context_menu_add_menu_item(
                self,
                'Duplicate {}'.format(tree),
                icon_path=os.path.join(ICONS_DIR, 'copy_s01.png'))
            action.triggered.connect(
                lambda *x: self._tree_view_operations(
                    operation='Duplicate environments'))
            msg = 'Duplicate the selected environment/s to new rows. '
            msg += '<br><i>Note: Different overrides and frame ranges can be applied to '
            msg += 'multiple instances of environments (rows with same target environment).</i>'
            action.setStatusTip(msg)
            action.setShortcut('CTRL+SHIFT+D')
            action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            menu_to_add_actions.addAction(action)

            action = srnd_qt.base.utils.context_menu_add_menu_item(
                self,
                'Group {}'.format(tree),
                icon_path=os.path.join(ICONS_DIR, 'group_s01.png'))
            action.triggered.connect(
                lambda *x: self.group_selected_items())
            msg = 'Group the selected environment/s to a named group. '
            msg += '<br><i>Note: You can also group environment by using drag and drop. '
            action.setStatusTip(msg)
            action.setShortcut('CTRL+G')
            action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            menu_to_add_actions.addAction(action)

            ##################################################################

            if self._menu_some_actions_at_top:
                label = 'More {} actions...'.format(tree)
                shots_menu = QMenu(label, self)
                menu.addMenu(shots_menu)

            action = srnd_qt.base.utils.context_menu_add_menu_item(
                self,
                'Change area')
            action.triggered.connect(
                lambda *x: self.change_areas_selected_items())
            msg = 'Change the oz areas for the selected environments and '
            msg += 'keep all existing overrides. '
            msg += '<br><i>Note: will also sync production data for new chosen '
            msg += 'area and resolve the frames again.</i>'
            action.setStatusTip(msg)
            action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            shots_menu.addAction(action)

            action = srnd_qt.base.utils.context_menu_add_menu_item(
                self,
                'Refresh from Shotgun',
                icon_path=os.path.join(constants.ICONS_DIR_QT, 'sync.png'))
            action.triggered.connect(
                lambda *x: self._tree_view_operations(
                    operation='Sync production data for environments'))
            msg = 'Sync production data for selected environments from Shotgun. '
            msg += 'In case production data changed since opening MSRS.'
            action.setStatusTip(msg)
            action.setShortcut('X')
            action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            shots_menu.addAction(action)

            action = srnd_qt.base.utils.context_menu_add_menu_item(
                self,
                'Delete {}'.format(tree),
                icon_path=os.path.join(ICONS_DIR, 'delete_s01.png'))
            action.triggered.connect(self.delete_items)
            action.setShortcut('DELETE')
            action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            shots_menu.addAction(action)

            action = srnd_qt.base.utils.context_menu_add_menu_item(
                self,
                'Ungroup {}'.format(tree))
            action.triggered.connect(
                lambda *x: self.ungroup_selected_items())
            msg = 'Ungroup the selected environments'
            action.setStatusTip(msg)
            action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            shots_menu.addAction(action)

            # action = srnd_qt.base.utils.context_menu_add_menu_item(
            #     self,
            #     'Show shotsub thumbnails',
            #     checkable=True,
            #     checked=model.get_show_environment_thumbnails())
            # action.toggled.connect(self.set_show_environment_thumbnails)
            # action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            # shots_menu.addAction(action)

        menu.addSeparator()

        self._create_additional_host_app_actions(menu, item)

        ######################################################################
        # Add render overrides menu

        render_overrides_manager = model.get_render_overrides_manager()
        if render_overrides_manager and render_overrides_manager.get_render_overrides_plugins():
            menu.addSeparator()

            render_overrides_menu = QMenu('Render overrides', self)
            menu.addMenu(render_overrides_menu)

            render_overrides_items_cached = render_overrides_manager.get_render_overrides_plugins()
            for override_id in sorted(render_overrides_items_cached.keys()):
                class_object = render_overrides_items_cached[override_id].get('class_object')
                if not class_object:
                    continue
                label = render_overrides_items_cached[override_id].get('label') or override_id
                category = render_overrides_items_cached[override_id].get('category')
                override_type = render_overrides_items_cached[override_id].get('type')
                description = render_overrides_items_cached[override_id].get('description')
                author = render_overrides_items_cached[override_id].get('author')
                author_department = render_overrides_items_cached[override_id].get('author_department')
                icon_path = render_overrides_items_cached[override_id].get('icon_path')

                # msg = 'Populating Override Id Into Render Overrides Menu: "{}". '.format(override_id)
                # msg += 'Type: "{}"'.format(override_type)
                # self.logMessage.emit(msg, logging.DEBUG)

                render_override_menu = QMenu(label, self)
                if icon_path:
                    render_override_menu.setIcon(QIcon(icon_path))
                render_overrides_menu.addMenu(render_override_menu)

                # Formulate status tip for action
                status_msg = description or label
                if category:
                    status_msg += '. Category: "{}"'.format(category)
                if author:
                    status_msg += '. Author: "{}"'.format(author)
                if author_department:
                    status_msg += '. Department: "{}"'.format(author_department)
                status_msg += '. ID: "{}"'.format(override_id)
                status_msg += '. Type: "{}"'.format(override_type)
                render_override_menu.setStatusTip(status_msg)

                has_override = override_id in render_overrides_items.keys()
                render_override_item = None
                current_value = None
                if has_override:
                    render_override_item = render_overrides_items.get(override_id)
                    current_value = render_override_item.get_value()

                method_to_call_remove = functools.partial(
                    self.remove_render_overrides_from_selection,
                    override_id)

                if override_type == 'enum':
                    enum_descriptions = class_object.get_enum_options_descriptions()
                    for i, enum_option in enumerate(class_object.get_enum_options()):
                        checked = False
                        if render_override_item:
                            checked = enum_option == render_override_item.get_value()
                        label_str = str(enum_option)
                        try:
                            enum_description = enum_descriptions[i]
                        except IndexError:
                            enum_description = status_msg
                        action = srnd_qt.base.utils.context_menu_add_menu_item(
                            self,
                            label_str,
                            checkable=True,
                            checked=checked)
                        action.setStatusTip(enum_description)
                        if checked:
                            method_to_call = method_to_call_remove
                        else:
                            method_to_call = functools.partial(
                                self.add_render_overrides_to_selection,
                                override_id,
                                value=enum_option,
                                show_dialog=False)
                        action.triggered.connect(method_to_call)
                        render_override_menu.addAction(action)
                else:
                    if override_type == 'bool':
                        # An option to add and enable boolean render override (or remove it)
                        _label = 'Enable "{}"'.format(label)
                        action = srnd_qt.base.utils.context_menu_add_menu_item(
                            self,
                            _label,
                            checkable=True,
                            checked=has_override and bool(current_value)) # shows the current state of render override boolean
                        action.setStatusTip(status_msg)
                        render_override_menu.addAction(action)
                        if not has_override or current_value == False:
                            method_to_call = functools.partial(
                                self.add_render_overrides_to_selection,
                                override_id,
                                value=True,
                                show_dialog=False)
                            action.triggered.connect(method_to_call)
                        else:
                            action.triggered.connect(method_to_call_remove)

                        _label = 'Disable "{}"'.format(label)
                        action = srnd_qt.base.utils.context_menu_add_menu_item(
                            self,
                            _label,
                            checkable=True,
                            checked=has_override and not bool(current_value))
                        action.setStatusTip(status_msg)
                        render_override_menu.addAction(action)
                        # Does not have render overide or is already enabled, context menu will add it as False
                        if not has_override or current_value:
                            method_to_call = functools.partial(
                                self.add_render_overrides_to_selection,
                                override_id,
                                value=False,
                                show_dialog=False)
                            action.triggered.connect(method_to_call)
                        else:
                            action.triggered.connect(method_to_call_remove)
                    else:
                        action = srnd_qt.base.utils.context_menu_add_menu_item(
                            self,
                            label,
                            checkable=True,
                            checked=has_override)
                        action.setStatusTip(status_msg)
                        method_to_call = functools.partial(
                            self.add_render_overrides_to_selection,
                            override_id,
                            value=None,
                            show_dialog=True)
                        action.triggered.connect(method_to_call)
                        render_override_menu.addAction(action)

                action = srnd_qt.base.utils.context_menu_add_menu_item(
                    self,
                    'Clear render override')
                method_to_call = functools.partial(
                    self.remove_render_overrides_from_selection,
                    override_id)
                action.triggered.connect(method_to_call)
                render_override_menu.addAction(action)

            render_overrides_menu.addSeparator()

            action = srnd_qt.base.utils.context_menu_add_menu_item(
                self,
                'Clear all render overrides')
            action.triggered.connect(
                self.remove_all_render_overrides_from_selection)
            render_overrides_menu.addAction(action)

            action = srnd_qt.base.utils.context_menu_add_menu_item(
                self,
                'Validate all render overrides values')
            msg = 'Validate all the render overrides values for selected items. '
            msg += 'Note: Invalid render overrides will be removed. '
            action.setStatusTip(msg)
            action.triggered.connect(
                self.validate_all_render_overrides_from_selection)
            render_overrides_menu.addAction(action)

        ######################################################################
        # Clipboard actions for overrides menu

        # menu.addSeparator()

        # menu_clipboard = QMenu('Clipboard', self)
        # menu.addMenu(menu_clipboard)

        # action = srnd_qt.base.utils.context_menu_add_menu_item(
        #     self,
        #     'Copy Overrides',
        #     icon_path=os.path.join(ICONS_DIR, 'copy_s01.png'))
        # action.setShortcut('CTRL+SHIFT+C')
        # action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        # action.triggered.connect(self.copy_overrides_for_selection)
        # menu_clipboard.addAction(action)

        # if self.is_overrides_ready_for_paste():
        #     action = srnd_qt.base.utils.context_menu_add_menu_item(
        #         self,
        #         'Paste Overrides',
        #         icon_path=os.path.join(ICONS_DIR, 'paste_s01.png'))
        #     action.setShortcut('CTRL+SHIFT+V')
        #     action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        #     action.triggered.connect(self.paste_overrides_for_selection)
        #     menu_clipboard.addAction(action)

        # action = srnd_qt.base.utils.context_menu_add_menu_item(
        #     self,
        #     'Clear overrides',
        #     icon_path=os.path.join(SRND_QT_ICONS_DIR, 'dismiss.png'))
        # action.setShortcut('CTRL+BACKSPACE')
        # action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        # action.triggered.connect(
        #     lambda *x: self._tree_view_operations(
        #         operation='Clear overrides'))
        # menu.addAction(action)

        ######################################################################

        if show:
            menu_base.exec_(pos)

        return menu_base


    def _create_additional_host_app_actions(self, menu, item=None):
        '''
        Add any additional host app specific menu actions after "More Other Actions..." fan out menu.
        NOTE: Reimplement for particular host app as this does nothing with default implementation.

        Args:
            menu (QMenu):
            item (OverrideBaseItem): render pass for env or environment item subclass

        Returns:
            menu (QMenu): after additional additional actions
        '''
        return menu


    def remove_override_from_uuid(self, override_id, msrs_uuid):
        '''
        Remove a single core or render override from environment or
        render pass for env given the override id and MSRS uuid.

        Args:
            override_id (str):
            msrs_uuid (str):

        Returns:
            success (bool):
        '''
        override_id = str(override_id)
        msrs_uuid = str(msrs_uuid)
        msg = 'Remove Override: "{}". '.format(override_id)
        msg += 'From UUID: "{}"'.format(msrs_uuid)
        self.logMessage.emit(msg, logging.INFO)

        model = self.model()
        qmodelindex = model.get_index_by_uuid(msrs_uuid)
        if not qmodelindex:
            return False

        render_overrides_manager = model.get_render_overrides_manager()
        render_overrides_plugins_ids = render_overrides_manager.get_render_overrides_plugins_ids()
        if override_id in render_overrides_plugins_ids:
            removed_count = self.remove_render_overrides_from_selection(
                override_id,
                selection=[qmodelindex])
        else:
            removed_count = self.clear_overrides_in_selection_by_id(
                override_id,
                selection=[qmodelindex])

        return bool(removed_count)


    def edit_override_from_uuid(self, override_id, msrs_uuid):
        '''
        Invoke edit for a single core or render override from environment or
        render pass for env given the override id and MSRS uuid.

        Args:
            override_id (str):
            msrs_uuid (str):

        Returns:
            success (bool):
        '''
        override_id = str(override_id)
        msrs_uuid = str(msrs_uuid)
        msg = 'Edit Override: "{}". '.format(override_id)
        msg += 'From UUID: "{}"'.format(msrs_uuid)
        self.logMessage.emit(msg, logging.INFO)

        model = self.model()
        qmodelindex = model.get_index_by_uuid(msrs_uuid)
        if not qmodelindex:
            return False

        render_overrides_manager = model.get_render_overrides_manager()
        render_overrides_plugins_ids = render_overrides_manager.get_render_overrides_plugins_ids()
        if override_id in render_overrides_plugins_ids:
            removed_count = self.add_render_overrides_to_selection(
                override_id,
                selection=[qmodelindex])
        else:
            removed_count = self.edit_override_id_for_selection(
                override_id,
                selection=[qmodelindex])

        return bool(removed_count)


    def add_render_overrides_to_selection(
            self,
            override_id,
            value=None,
            selection=None,
            show_dialog=True):
        '''
        Add render overrides to selected pass for env items and environment items.

        Args:
            override_id (str):
            value (object):
            selection (list):
            show_dialog (bool): optionally show a dialog to choose appropiate
                value for override type if value is None
        '''
        model = self.model()
        selection = selection or self.selectedIndexes()

        render_overrides_manager = model.get_render_overrides_manager()
        render_override_object = render_overrides_manager.get_render_override_object_by_id(override_id)
        if not render_override_object:
            msg = 'Failed To Get Render Override Object By Id: "{}"'.format(override_id)
            self.logMessage.emit(msg, logging.CRITICAL)
            return

        # Find the first render override value in selection
        if value == None:
            msg = 'Finding first value in selection...'
            self.logMessage.emit(msg, logging.INFO)
            for i, qmodelindex in enumerate(selection):
                if not qmodelindex.isValid():
                    continue
                item = qmodelindex.internalPointer()
                if not any([item.is_environment_item(), item.is_pass_for_env_item()]):
                    continue
                render_overrides_items = item.get_render_overrides_items()
                if override_id not in render_overrides_items.keys():
                    continue
                render_override_item = render_overrides_items.get(override_id)
                _value = render_override_item.get_value()
                if _value != None:
                    value = _value
                    break
            msg = 'Found first value in selection: "{}"'.format(value)
            self.logMessage.emit(msg, logging.INFO)

        # If value is not provided optionally let the user choose value from dialog.
        if show_dialog:
            accepted, value = render_override_object.choose_value_from_dialog(
                value=value,
                parent=self)
            if not accepted:
                msg = 'User cancelled add render override: "{}"'.format(override_id)
                self.logMessage.emit(msg, logging.CRITICAL)
                return

        # Must have value for override id at this point
        if value == None:
            msg = 'Cannot add render override id with none value: "{}"'.format(override_id)
            self.logMessage.emit(msg, logging.CRITICAL)
            return

        msg = 'Add render overrides to selection with id: "{}". '.format(override_id)
        msg += 'Value: "{}"'.format(value)
        self.logMessage.emit(msg, logging.INFO)

        added_count = 0
        for i, qmodelindex in enumerate(selection):
            if not qmodelindex.isValid():
                continue
            item = qmodelindex.internalPointer()
            # Can only apply render overrides item to these types
            if not any([item.is_environment_item(), item.is_pass_for_env_item()]):
                continue
            identifier = item.get_identifier()

            # Check if render override value changed to see if delegate widget needs updating
            previous_value = None
            render_overrides_items = item.get_render_overrides_items()
            if override_id in render_overrides_items.keys():
                # msg = 'Updating Existing Render Override Item: "{}"'.format(override_id)
                # self.logMessage.emit(msg, logging.DEBUG)
                render_override_item = render_overrides_items.get(override_id)
                previous_value = render_override_item.get_value()
            else:
                # msg = 'Instantiating New Render Override Item: "{}"'.format(override_id)
                # self.logMessage.emit(msg, logging.DEBUG)
                render_override_item = render_override_object(value=value)
                item.add_render_override_item(render_override_item)

            msg = 'Added render override id: "{}". '.format(override_id)
            msg += 'to: "{}". '.format(identifier)
            msg += 'Previous value: "{}". '.format(previous_value)
            msg += 'New value: "{}"'.format(value)
            self.logMessage.emit(msg, logging.INFO)

            if render_override_item:
                added_count += 1
                render_override_item.set_value(value)
                if not previous_value or value != previous_value:
                    model.dataChanged.emit(qmodelindex, qmodelindex)

        if added_count:
            self.updateDetailsPanel.emit(False)

        return added_count


    def remove_render_overrides_from_selection(self, override_id, selection=None):
        '''
        Remove render override by id from selected pass for env items and environment items.

        Args:
            override_id (str):
            selection (list): list of QModelIndices

        Returns:
            removed_count (int):
        '''
        model = self.model()
        selection = selection or self.selectedIndexes()

        msg = 'Removing Render Overrides From Selection With Id: "{}"'.format(override_id)
        self.logMessage.emit(msg, logging.INFO)

        removed_count = 0
        for i, qmodelindex in enumerate(selection):
            if not qmodelindex.isValid():
                continue
            item = qmodelindex.internalPointer()
            # Can only remove render overrides from these item types
            if not any([item.is_environment_item(), item.is_pass_for_env_item()]):
                continue
            identifier = item.get_identifier()

            success = item.remove_render_override_item_by_id(override_id)
            msg = 'Removed Render Override Id: "{}". '.format(override_id)
            msg += 'From: "{}". '.format(identifier)
            msg += 'Success: "{}"'.format(success)
            self.logMessage.emit(msg, logging.INFO)

            if success:
                removed_count += 1
                model.dataChanged.emit(qmodelindex, qmodelindex)

        if removed_count:
            self.updateDetailsPanel.emit(False)

        return removed_count


    def copy_render_overrides_from_selection(self, override_id):
        '''
        Copy render overrides by id for selected pass for env items and environment items.

        Args:
            override_id (str):
        '''
        model = self.model()
        selection = self.selectedIndexes()
        if not selection:
            msg = 'No selected items to copy render overrides for!'
            self.logMessage.emit(msg, logging.WARNING)
            return

        msg = 'Copying render overrides from selection with id: "{}"'.format(override_id)
        self.logMessage.emit(msg, logging.INFO)

        self._copied_overrides_dict = dict()
        self._copied_pass_overrides_dict = dict()

        for i, qmodelindex in enumerate(selection):
            if not qmodelindex.isValid():
                continue
            item = qmodelindex.internalPointer()
            # Can only copy render overrides from these item types
            if not any([item.is_environment_item(), item.is_pass_for_env_item()]):
                continue
            identifier = item.get_identifier()

            # Get all the overrides and render overrides data as dict
            overrides_dict = item.copy_overrides()
            # Extract only the render overrides
            render_overrides_data = overrides_dict.get('render_overrides_data')
            # Check if copied data has the specific render override id
            value = render_overrides_data.get(override_id)
            if value == None:
                continue

            # Formulate only the target override id data to copy
            overrides_dict_clean = dict()
            overrides_dict_clean['render_overrides_data'] = dict()
            overrides_dict_clean['render_overrides_data'][override_id] = value

            msg = 'Copying render override from identifier: "{}". '.format(identifier)
            msg += 'Render override id: "{}". '.format(override_id)
            msg += 'Value: "{}"'.format(value)
            self.logMessage.emit(msg, logging.INFO)

            if item.is_environment_item():
                self._copied_overrides_dict = overrides_dict_clean
            else:
                render_item = item.get_source_render_item()
                item_full_name = render_item.get_item_full_name()
                self._copied_pass_overrides_dict[item_full_name] = dict()
                self._copied_pass_overrides_dict[item_full_name] = overrides_dict_clean


    def remove_all_render_overrides_from_selection(self):
        '''
        Remove all the render overrides from selected pass for env items and environment items.

        Returns:
            removed_count (int):
        '''
        model = self.model()
        selection = self.selectedIndexes()

        msg = 'Removing all render overrides in selection...'
        self.logMessage.emit(msg, logging.WARNING)

        removed_count = 0
        for i, qmodelindex in enumerate(selection):
            if not qmodelindex.isValid():
                continue
            item = qmodelindex.internalPointer()
            # Can only remove render overrides item to these types
            if not any([item.is_environment_item(), item.is_pass_for_env_item()]):
                continue

            _removed_count = item.remove_all_render_override_items()

            if _removed_count:
                removed_count += _removed_count
                model.dataChanged.emit(qmodelindex, qmodelindex)

        if removed_count:
            self.updateDetailsPanel.emit(False)

        return removed_count


    def validate_all_render_overrides_from_selection(self):
        '''
        Validate all the render overrides values from selected pass for env items and environment items.

        Returns:
            changed_count (int):
        '''
        model = self.model()
        selection = self.selectedIndexes()

        msg = 'Validating all render overrides in msrs selection...'
        self.logMessage.emit(msg, logging.WARNING)

        changed_count = 0
        for i, qmodelindex in enumerate(selection):
            if not qmodelindex.isValid():
                continue
            item = qmodelindex.internalPointer()
            # Can only validate render overrides item to these types
            if not any([item.is_environment_item(), item.is_pass_for_env_item()]):
                continue
            _changed_count = item.validate_render_overrides()
            if _changed_count:
                changed_count += _changed_count
                model.dataChanged.emit(qmodelindex, qmodelindex)

        if changed_count:
            self.updateDetailsPanel.emit(False)

        return changed_count


    def _add_render_actions_to_menu(self, menu, include_batch_all=False):
        '''
        Add render actions to menu.

        Args:
            menu (QMenu):
            include_batch_all (bool):
        '''
        font_italic = QFont()
        font_italic.setFamily(constants.FONT_FAMILY)
        font_italic.setItalic(True)

        # msg = 'Launch Render Summary'
        # action = srnd_qt.base.utils.context_menu_add_menu_item(self, msg)
        # action.setFont(font_italic)
        # menu.addAction(action)

        if include_batch_all:
            action = srnd_qt.base.utils.context_menu_add_menu_item(
                self,
                'Batch render',
                icon_path=self.HOST_APP_ICON)
            action.triggered.connect(
                lambda *x: self.multi_shot_render(
                    selected=False,
                    interactive=False,
                    show_dialog=True))
            msg = 'Start a batch render of all active item/s for all resolved frames. '
            msg += 'Note: Will respect state of "dispatch on plow" option.'
            action.setStatusTip(msg)
            action.setToolTip(msg)
            action.setShortcut('CTRL+SHIFT+R')
            action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            menu.addAction(action)

        action = srnd_qt.base.utils.context_menu_add_menu_item(
            self,
            'Batch render selected',
            icon_path=self.HOST_APP_ICON)
        action.triggered.connect(
            lambda *x: self.multi_shot_render(
                selected=True,
                interactive=False,
                show_dialog=True))
        msg = 'Start a batch render of all active and selected item/s for all resolved frames. '
        msg += 'Note: Will respect state of "dispatch on plow" option.'
        action.setStatusTip(msg)
        action.setToolTip(msg)
        action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
        menu.addAction(action)

        # Expose interactive render, if host app has support
        # and implementation is available
        if constants.EXPOSE_INTERACTIVE_RENDER:
            action = srnd_qt.base.utils.context_menu_add_menu_item(
                self,
                'Interactive render selected',
                icon_path=self.HOST_APP_ICON)
            action.triggered.connect(
                lambda *x: self.multi_shot_render(
                    selected=True,
                    interactive=True,
                    show_dialog=True))
            action.setShortcut('CTRL+SHIFT+K')
            action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            menu.addAction(action)

            action = srnd_qt.base.utils.context_menu_add_menu_item(
                self,
                'Interactive render selected on current frame',
                icon_path=self.HOST_APP_ICON)
            action.triggered.connect(
                lambda *x: self.multi_shot_render(
                    selected=True,
                    interactive=True,
                    current_frame_only=True,
                    show_dialog=True))
            action.setShortcutContext(Qt.WidgetWithChildrenShortcut)
            menu.addAction(action)


    def _add_more_versions_actions_to_menu(self, menu):
        '''
        Add any additional version actions to menu.
        Reimplement this to add host app specific more version actions.

        Args:
            menu (QMenu):
        '''
        return


    def get_first_qmodelindex(self, pos=None, selection=None):
        '''
        Get the first QModelIndex under mouse cursor otherwise in selection.

        Args:
            pos (QPoint):
            selection (list): list of qmodelindices
        '''
        pos = pos or QCursor.pos()

        # Prefer to use item under mouse
        qmodelindex = None
        _qmodelindex = self.indexAt(pos)
        if _qmodelindex.isValid() and _qmodelindex.internalPointer():
            qmodelindex = _qmodelindex

        # Otherwise find first non group item in selection
        if not qmodelindex:
            if not selection:
                selection_model = self.selectionModel()
                selection = selection_model.selectedIndexes()
            for _qmodelindex in selection:
                if not _qmodelindex.isValid():
                    continue
                item = _qmodelindex.internalPointer()
                # NOTE: Only specified item types supported for this expanded menu
                if any([item.is_pass_for_env_item(), item.is_environment_item()]):
                    qmodelindex = _qmodelindex
                    break

        return qmodelindex


    def render_node_operation(self, column, operation='Select'):
        '''
        Perform an operation on one render node.

        Args:
            column (int):
            operation (str):

        Returns:
            success (bool):
        '''
        try:
            render_item = self.model().get_render_items()[column - 1]
        except IndexError as error:
            return False

        model = self.model()
        node_name = render_item.get_node_name()
        item_full_name = render_item.get_item_full_name()

        msg = 'Render item operation. '
        msg += 'Item name: "{}". '.format(item_full_name)
        msg += 'Operation: "{}". '.format(operation)
        msg += 'Column: "{}". '.format(column)
        self.logMessage.emit(msg, logging.INFO)

        header_columns_to_update = set()

        if operation == 'Select':
            render_item.select_node_in_host_app()

        elif operation in ['Remove', 'Delete']:

            # Confirm delete operation
            if operation == 'Delete':
                msg = 'Confirm delete render node: "{}"'.format(item_full_name)
                reply = QMessageBox.warning(
                    self,
                    'Confirm delete render node operation?',
                    msg,
                    QMessageBox.Ok | QMessageBox.Cancel)
                if reply == QMessageBox.Cancel:
                    msg = 'User skipped delete render node operation!'
                    self.logMessage.emit(msg, logging.WARNING)
                    return False

            # Delete from abstract data model
            removed_count = model.clear_render_items(columns=[column])

            if self._overlay_widget:
                self._overlay_widget.update_overlays()

            # Update the overview
            model.updateOverviewRequested.emit()

            # Optionally remove the node in host app as well
            if operation == 'Delete':
                render_item.delete_node_in_host_app()

            return bool(removed_count)

        elif operation == 'Rename Node':
            msg = '{}{}{}'.format(fs, node_name, fe)
            from srnd_qt.ui_framework.dialogs import input_dialog
            dialog = input_dialog.GetInputDialog(
                title_str='Choose new name for pass: {}'.format(msg),
                input_type_required=str(),
                value=node_name,
                parent=self)
            dialog.setWindowTitle('Choose new name for pass: {}'.format(node_name))
            dialog.setMinimumHeight(125)
            dialog.resize(575, 150)

            options_box_header = dialog.get_header_widget()
            style_sheet = 'QGroupBox {background: rgb(70, 70, 70);'
            style_sheet += 'border:rgb(70, 70, 70)}'
            options_box_header.setStyleSheet(style_sheet)
            result = dialog.exec_()

            if result == QDialog.Accepted and dialog.get_result():
                result = dialog.get_result()
                render_item.rename_node(str(result))
                self.scale_columns(columns=[column])
                # The version system preview needs updating
                self.updateDetailsPanel.emit(False)
                return True
            return False

        elif operation == 'Toggle Enabled':
            enabled = render_item.get_enabled()
            render_item.set_enabled(not enabled)
            # Update enabled / disabled indicator
            model.headerDataChanged.emit(
                Qt.Horizontal,
                column,
                column)
            return True

        elif operation == 'Sync':
            # Check node is still in host application
            render_node = render_item.get_node_in_host_app()
            if not render_node:
                removed_count = model.clear_render_items(columns=[column])
            # Sync details from available render node
            else:
                # NOTE: Syncing details for only one item so do full more expensive cook now.
                render_item.sync_render_details(fast=False)
            # Node colour might have changed
            model.headerDataChanged.emit(
                Qt.Horizontal,
                column,
                column)
            return True

        elif operation == 'Pick Colour':
            colour = tuple(render_item.get_node_colour() or (0.1, 0.1, 0.1)) # fallback if None
            from srnd_qt.ui_framework.dialogs.color_picker_dialog import ColorPickerDialog
            color_picker_dialog = ColorPickerDialog(
                color=colour,
                allowed_outside_range=False,
                color_palettes_visible=False,
                color_sliders_have_numbers=True,
                has_okay_cancel_button=True,
                has_temperature_and_gel_swatch=False,
                parent=self)
            color_picker_dialog.show()
            color_picker_dialog.rgbChanged.connect(
                lambda *x: self._set_node_colour(render_item, x, column))

        elif operation in [
                'Queue enabled passes along column',
                'Unqueue enabled passes along column']:
            queue = bool('Queue' in operation)
            qmodelindices = model.get_pass_for_env_items_indices(column=column)
            update_count = 0
            for qmodelindex in qmodelindices:
                if not qmodelindex.isValid():
                    continue
                pass_env_item = qmodelindex.internalPointer()
                # if not pass_env_item.is_pass_for_env_item():
                #     continue
                if not pass_env_item.get_enabled():
                    msg = 'Cannot toggle queued mode for disabled items!'
                    self.logMessage.emit(msg, logging.WARNING)
                    continue                

                was_queued = pass_env_item.get_queued()
                queued_modified = queue != was_queued
                if queue:
                    pass_env_item.set_queued(True)
                else:
                    pass_env_item.set_queued(False)
                update_count += int(queued_modified)

                if queued_modified:
                    model.dataChanged.emit(qmodelindex, qmodelindex)
                    renderable_offset = 1 if pass_env_item.get_queued() else -1
                    pass_env_item._update_renderable_count_for_index(
                        qmodelindex,
                        renderable_offset=renderable_offset)
                    model.framesResolveRequest.emit(qmodelindex) 

            if update_count:
                header_columns_to_update.add(column)

        if header_columns_to_update:
            self._update_header_columns(header_columns_to_update)
            model.updateOverviewRequested.emit()

        return False


    def get_selection_or_item_under_mouse(self, selection=None):
        '''
        Get QModelIndex selection of this view.
        NOTE: If no selection then try to use QModelIndex under mouse.

        Args:
            selection (list): optionally pass in an explicit QModelIndex list

        Returns:
            selection (list): list of QModelIndex
        '''
        selection = selection or self.selectedIndexes()
        if not selection:
            pos = self.mapFromGlobal(QCursor.pos())
            pos -= QPoint(0, self.header().height())
            qmodelindex = self.indexAt(pos)
            if qmodelindex.isValid() and qmodelindex.internalPointer():
                selection = [qmodelindex]
        return selection


    def _tree_view_operations(
            self,
            value=None,
            operation='WIP',
            selection=None):
        '''
        Perform an operation on all selected Envrionments.
        TODO: Break this up into many discrete actions.

        Args:
            value (bool):
            operation (str):
            selection (list): optionally pass in an explicit QModelIndex list

        Returns:
            update_count (int):
        '''
        selection = self.get_selection_or_item_under_mouse(selection=selection)

        model = self.model()

        has_menu_toggle_value = isinstance(value, bool)
        count = len(selection)

        progress_msg = 'About to perform operation: "{}". '.format(operation)
        progress_msg += 'On {} selected indexes'.format(count)
        self.logMessage.emit(progress_msg, logging.DEBUG)

        custom_ver_num = None
        custom_frame_range = None
        custom_not_frame_range = None
        custom_frame_increment = None
        wait_on_list = list()

        # If operation is to set Custom Version, then get it from user with popup dialog
        if operation == constants.OVERRIDE_VERSION_CUSTOM and (value or not has_menu_toggle_value):
            # Don't even show the dialog depending on selection
            items, _qmodelindices = self.filter_selection(
                selection,
                include_environment_items=True,
                include_pass_for_env_items=True,
                include_group_items=False)
            if not items:
                msg = 'No environment or render pass for env items in selection!'
                self.logMessage.emit(msg, logging.WARNING)
                return 0
            initial_value = 1
            qmodelindex = selection[-1]
            _item = qmodelindex.internalPointer()
            if _item and not _item.is_group_item():
                initial_value = _item.get_version_override() or 1
            if not str(initial_value).isdigit():
                initial_value = 1

            msg = '<i>Choose explicit cg version number. '
            msg += 'Can be future version that doesn\'t yet exist.</i>'

            from srnd_qt.ui_framework.dialogs import input_dialog
            dialog = input_dialog.GetInputDialog(
                title_str='Choose {}custom cg version{}'.format(fs, fe),
                description=msg,
                description_by_title=False,
                input_type_required=int(),
                value=initial_value,
                min_number=1,
                max_number=9999,
                parent=self)
            dialog.setWindowTitle('Choose custom cg version')
            dialog.setMinimumHeight(175)
            dialog.resize(575, 20)

            options_box_header = dialog.get_header_widget()
            style_sheet = 'QGroupBox {background: rgb(70, 70, 70);'
            style_sheet += 'border:rgb(70, 70, 70)}'
            options_box_header.setStyleSheet(style_sheet)

            result = dialog.exec_()
            if result == QDialog.Rejected:
                return 0
            result = dialog.get_result()
            custom_ver_num = int(result)

        elif operation == constants.OVERRIDE_FRAMES_CUSTOM and \
                (value or not has_menu_toggle_value):
            # Don't even show the dialog depending on selection
            items, _qmodelindices = self.filter_selection(
                selection,
                include_environment_items=True,
                include_pass_for_env_items=True,
                include_group_items=False)
            if not items:
                msg = 'No environment or render pass for env items in selection!'
                self.logMessage.emit(msg, logging.WARNING)
                return 0
            accepted, custom_frame_range = self.choose_custom_frame_range_dialog(selection)
            if not accepted:
                return 0

        elif operation == constants.OVERRIDE_FRAMES_NOT_CUSTOM and \
                (value or not has_menu_toggle_value):
            # Don't even show the dialog depending on selection
            items, _qmodelindices = self.filter_selection(
                selection,
                include_environment_items=True,
                include_pass_for_env_items=True,
                include_group_items=False)
            if not items:
                msg = 'No environment or render pass for env items in selection!'
                self.logMessage.emit(msg, logging.WARNING)
                return 0
            initial_value = str()
            qmodelindex = selection[-1]
            _item = qmodelindex.internalPointer()
            if _item:
                initial_value = _item.get_not_frame_range_override() or str()
            if initial_value:
                try:
                    initial_value = str(fileseq.FrameSet(initial_value))
                except Exception:
                    initial_value = str()

            msg = '<i>This NOT frames will be taken away from resolved frames.</i>'

            from srnd_qt.ui_framework.dialogs import input_dialog
            dialog = input_dialog.GetInputDialog(
                title_str='Choose frames to {}NOT{} render'.format(fs, fe),
                description=msg,
                description_by_title=False,
                input_type_required=str(),
                value=initial_value,
                parent=self)
            dialog.setWindowTitle('Choose frames to NOT render')
            dialog.setMinimumHeight(175)
            dialog.resize(575, 200)

            options_box_header = dialog.get_header_widget()
            style_sheet = 'QGroupBox {background: rgb(70, 70, 70);'
            style_sheet += 'border:rgb(70, 70, 70)}'
            options_box_header.setStyleSheet(style_sheet)

            value_widget = dialog.get_value_widget()
            from srnd_qt.ui_framework.validators import frames_validator
            validator = frames_validator.FramesValidator()
            value_widget.setValidator(validator)
            dialog.resize(500, 135)
            # dialog.adjustSize()
            qsize = dialog.size()
            result = dialog.exec_()
            if result == QDialog.Rejected:
                return 0
            result = dialog.get_result()
            custom_not_frame_range = str(result)
            # Try to parse custom NOT frame range
            try:
                custom_not_frame_range = str(fileseq.FrameSet(custom_not_frame_range))
            except fileseq.ParseException as error:
                msg = 'Failed to parse custom NOT frames: "{}"'.format(custom_not_frame_range)
                msg += 'Full exception: "{}".'.format(traceback.format_exc())
                self.logMessage.emit(msg, logging.WARNING)
                return 0

        elif operation in [
                    constants.OVERRIDE_FRAMES_XCUSTOM,
                    constants.OVERRIDE_FRAMES_NOT_XCUSTOM] and \
                (value or not has_menu_toggle_value):
            # Don't even show the dialog depending on selection
            items, _qmodelindices = self.filter_selection(
                selection,
                include_environment_items=True,
                include_pass_for_env_items=True,
                include_group_items=False)
            if not items:
                msg = 'No environment or render pass for env items in selection!'
                self.logMessage.emit(msg, logging.WARNING)
                return 0
            initial_value = 10
            for _qmodelindex in selection:
                _item = _qmodelindex.internalPointer()
                if _item.is_group_item():
                    continue
                is_plus = operation == constants.OVERRIDE_FRAMES_XCUSTOM
                if _item and is_plus:
                    initial_value = _item.get_frames_rule_xn() or str()
                    break
                elif _item:
                    initial_value = _item.get_not_frames_rule_xn() or str()
                    break
            if not str(initial_value).isdigit():
                initial_value = 10

            if is_plus:
                title_str = 'Choose to render {}every nth{} frame'.format(fs, fe)
                msg = '<i>Choose frame increment to render every nth frame.</i>'
                window_title = 'Choose to render every Nth frame'
            else:
                title_str = 'Choose to {}NOT{} '.format(fs, fe)
                title_str += 'render {}every Nth{} frame.'.format(fs, fe)
                msg = '<i>Choose a NOT frame increment to NOT render every nth frame. '
                msg += '<br>This NOT frames will be taken away from resolved frames.</i>'
                window_title = 'Choose to NOT render every nth frame'

            from srnd_qt.ui_framework.dialogs import input_dialog
            dialog = input_dialog.GetInputDialog(
                title_str=title_str,
                description=msg,
                description_by_title=False,
                input_type_required=int(),
                value=initial_value,
                min_number=1,
                max_number=9999,
                parent=self)
            dialog.setWindowTitle(window_title)

            dialog.setMinimumHeight(150)
            dialog.resize(575, 175)

            options_box_header = dialog.get_header_widget()
            style_sheet = 'QGroupBox {background: rgb(70, 70, 70);'
            style_sheet += 'border:rgb(70, 70, 70)}'
            options_box_header.setStyleSheet(style_sheet)

            value_widget = dialog.get_value_widget()
            result = dialog.exec_()
            if result == QDialog.Rejected or not str(result).isdigit():
                return 0
            result = dialog.get_result()
            if is_plus:
                custom_frame_increment = result
            else:
                custom_frame_increment = result

        # Block the selection model selectionChanged signals from possibly
        # updating the details panel via the updateDetailsPanel signal.
        selection_model = self.selectionModel()
        selection_model.blockSignals(True)

        # Show progress bar
        model.toggleProgressBarVisible.emit(True)
        model.updateLoadingBarFormat.emit(0, progress_msg + ' - %p%')

        parent_index = QModelIndex()
        columns = range(1, model.columnCount(parent_index))

        update_count = 0
        for i, qmodelindex in enumerate(selection):
            if not qmodelindex.isValid():
                continue

            # Continue if on 0th index for certain operations.
            # NOTE: The operation will be prevented to run by later type checking anyway
            if operation in [
                    'Sync production data for environments',
                    'Duplicate environments'] and qmodelindex.column() != 0:
                continue

            item = qmodelindex.internalPointer()
            column = qmodelindex.column()
            row = qmodelindex.row()
            if item.is_group_item():
                continue
            is_environment_item = item.is_environment_item()
            is_pass_for_env_item = item.is_pass_for_env_item()

            percent = int((float(i) / count) * 100)
            msg = 'Performing operation: "{}". '.format(operation)
            msg += 'On type: "{}". '.format(item.get_node_type())

            if not is_pass_for_env_item:
                environment_item = item
            else:
                environment_item = item.get_environment_item()
            oz_area_id = id(environment_item)

            # Update loading bar
            self.logMessage.emit(msg, logging.INFO)
            self.updateLoadingBarFormat.emit(percent, msg + ' - %p%')

            if operation == 'Enabled' and column >= 1:
                was_active = item.get_active()
                was_enabled = item.get_enabled()
                if has_menu_toggle_value:
                    item.set_enabled(value)
                else:
                    item.set_enabled(not was_enabled)
                enable_modified = item.get_enabled() != was_enabled
                update_count += int(enable_modified)
                if enable_modified:
                    if self.get_disabled_passes_are_void_style():
                        if item.get_enabled():
                            self.openPersistentEditor(qmodelindex)
                        else:
                            self.closePersistentEditor(qmodelindex)
                    else:
                        model.dataChanged.emit(qmodelindex, qmodelindex)
                    if item.get_queued():
                        renderable_offset = 1 if item.get_enabled() else -1
                        item._update_renderable_count_for_index(
                            qmodelindex,
                            renderable_offset=renderable_offset)
                    model.framesResolveRequest.emit(qmodelindex)
                continue

            elif operation in [
                    'Version up (match passes)',
                    'Version up',
                    'Version match scene']:
                current_version_override = item.get_version_override()
                if has_menu_toggle_value:
                    if not value:
                        version_override = None
                    elif operation == 'Version up (match passes)':
                        version_override = constants.CG_VERSION_SYSTEM_PASSES_NEXT
                    elif operation == 'Version up':
                        version_override = constants.CG_VERSION_SYSTEM_PASS_NEXT
                    elif operation == 'Version match scene':
                        version_override = constants.CG_VERSION_SYSTEM_MATCH_SCENE
                    else:
                        version_override = None
                else:
                    if operation == 'Version up (match passes)':
                        VSYS = constants.CG_VERSION_SYSTEM_PASSES_NEXT
                        version_override = None if current_version_override == VSYS else VSYS
                    elif operation == 'Version up':
                        VSYS = constants.CG_VERSION_SYSTEM_PASS_NEXT
                        version_override = None if current_version_override == VSYS else VSYS
                    elif operation == 'Version match scene':
                        VSYS = constants.CG_VERSION_SYSTEM_MATCH_SCENE
                        version_override = None if current_version_override == VSYS else VSYS
                item.set_version_override(version_override)
                version_modified = current_version_override != version_override
                update_count += int(version_modified)
                if version_modified:
                    model.dataChanged.emit(qmodelindex, qmodelindex)
                continue

            elif operation == constants.OVERRIDE_VERSION_CUSTOM:
                custom_ver_num = custom_ver_num or None
                current_ver_num = item.get_version_override()
                item.set_version_override(custom_ver_num)
                version_changed = custom_ver_num != current_ver_num
                update_count += int(version_changed)
                if version_changed:
                    model.dataChanged.emit(qmodelindex, qmodelindex)
                continue

            elif operation == 'Derive explicit version' and is_pass_for_env_item:
                render_item = item.get_source_render_item()
                render_item.sync_render_details()
                current_version = item.get_version_override()
                explicit_version = render_item.get_explicit_version()
                item.set_version_override(explicit_version)
                explicit_version_changed = explicit_version != current_version
                update_count += int(explicit_version_changed)
                if explicit_version_changed:
                    model.dataChanged.emit(qmodelindex, qmodelindex)
                continue

            elif operation in constants.OVERRIDES_FRAME_RULES:
                if is_pass_for_env_item and environment_item.get_split_frame_ranges():
                    msg = 'Cannot currently apply per pass frame overrides for '
                    msg += 'split frames job: "{}"'.format(environment_item.get_oz_area())
                    self.logMessage.emit(msg, logging.WARNING)
                    continue

                frames_changed = False

                if operation == constants.OVERRIDE_FRAMES_IMPORTANT:
                    current_frames_rule_important = item.get_frames_rule_important()
                    if has_menu_toggle_value:
                        item.set_frames_rule_important(bool(value))
                    else:
                        item.set_frames_rule_important(not bool(current_frames_rule_important))
                    frames_changed = current_frames_rule_important != item.get_frames_rule_important()

                elif operation == constants.OVERRIDE_FRAMES_FML:
                    current_frames_rule_fml = item.get_frames_rule_fml()
                    if has_menu_toggle_value:
                        item.set_frames_rule_fml(bool(value))
                    else:
                        item.set_frames_rule_fml(not bool(current_frames_rule_fml))
                    frames_changed = current_frames_rule_fml != item.get_frames_rule_fml()

                elif operation == constants.OVERRIDE_FRAMES_X1:
                    current_frames_rule_x1 = item.get_frames_rule_x1()
                    if has_menu_toggle_value:
                        item.set_frames_rule_x1(bool(value))
                    else:
                        item.set_frames_rule_x1(not bool(current_frames_rule_x1))
                    frames_changed = current_frames_rule_x1 != item.get_frames_rule_x1()

                elif operation == constants.OVERRIDE_FRAMES_X10:
                    current_frames_rule_x10 = item.get_frames_rule_x10()
                    if has_menu_toggle_value:
                        item.set_frames_rule_x10(bool(value))
                    else:
                        item.set_frames_rule_x10(not bool(current_frames_rule_x10))
                    frames_changed = current_frames_rule_x10 != item.get_frames_rule_x10()

                elif operation == constants.OVERRIDE_FRAMES_XCUSTOM:
                    current_frames_rule_xn = item.get_frames_rule_xn()
                    if has_menu_toggle_value and not value:
                        item.set_frames_rule_xn(None)
                    else:
                        item.set_frames_rule_xn(custom_frame_increment)
                    frames_changed = current_frames_rule_xn != item.get_frames_rule_xn()

                elif operation == constants.OVERRIDE_FRAMES_NOT_IMPORTANT:
                    current_not_frames_rule_important = item.get_not_frames_rule_important()
                    if has_menu_toggle_value:
                        item.set_not_frames_rule_important(value)
                    else:
                        item.set_not_frames_rule_important(not bool(current_not_frames_rule_important))
                    frames_changed = current_not_frames_rule_important != item.get_not_frames_rule_important()

                elif operation == constants.OVERRIDE_FRAMES_NOT_FML:
                    current_not_frames_rule_fml = item.get_not_frames_rule_fml()
                    if has_menu_toggle_value:
                        item.set_not_frames_rule_fml(value)
                    else:
                        item.set_not_frames_rule_fml(not bool(current_not_frames_rule_fml))
                    frames_changed = current_not_frames_rule_fml != item.get_not_frames_rule_fml()

                elif operation == constants.OVERRIDE_FRAMES_NOT_X10:
                    current_not_frames_rule_x10 = item.get_not_frames_rule_x10()
                    if has_menu_toggle_value:
                        item.set_not_frames_rule_x10(value)
                    else:
                        item.set_not_frames_rule_x10(not bool(current_not_frames_rule_x10))
                    frames_changed = current_not_frames_rule_x10 != item.get_not_frames_rule_x10()

                elif operation == constants.OVERRIDE_FRAMES_NOT_XCUSTOM:
                    current_not_frames_rule_xn = item.get_not_frames_rule_xn()
                    if has_menu_toggle_value and not value:
                        item.set_not_frames_rule_xn(None)
                    else:
                        item.set_not_frames_rule_xn(custom_frame_increment)
                    frames_changed = current_not_frames_rule_xn != item.get_not_frames_rule_xn()

                update_count += int(frames_changed)
                if frames_changed:
                    model.dataChanged.emit(qmodelindex, qmodelindex)
                    model.framesResolveRequest.emit(qmodelindex)
                continue

            elif operation in [
                    constants.OVERRIDE_FRAMES_CUSTOM,
                    constants.OVERRIDE_FRAMES_NOT_CUSTOM]:
                if is_pass_for_env_item and environment_item.get_split_frame_ranges():
                    msg = 'Cannot currently apply per pass frame overrides for '
                    msg += 'split frames job: "{}"'.format(environment_item.get_oz_area())
                    self.logMessage.emit(msg, logging.WARNING)
                    continue
                current_frames = item.get_frame_range_override()
                current_not_frames = item.get_not_frame_range_override()
                is_not_operation = 'NOT' in operation
                if has_menu_toggle_value:
                    if operation == constants.OVERRIDE_FRAMES_CUSTOM:
                        frames_str = custom_frame_range
                    else:
                        frames_str = custom_not_frame_range
                else:
                    if operation == constants.OVERRIDE_FRAMES_CUSTOM:
                        frames_str = custom_frame_range or None
                    else:
                        frames_str = custom_not_frame_range or None
                if is_not_operation:
                    item.set_not_frame_range_override(frames_str)
                    frames_changed = current_not_frames != frames_str
                else:
                    item.set_frame_range_override(frames_str)
                    frames_changed = current_frames != frames_str
                update_count += int(frames_changed)
                if frames_changed:
                    model.dataChanged.emit(qmodelindex, qmodelindex)
                    model.framesResolveRequest.emit(qmodelindex)
                continue

            elif operation == 'Validate WAIT On':
                current_wait_on = item.get_wait_on()
                current_wait_on_plow_ids = item.get_wait_on_plow_ids()
                # First validate UUIDS for dependency to other Multi Shot items
                wait_on_list = model.validate_wait_on_multi_shot_uuids(
                    current_wait_on,
                    source_uuid=item.get_identity_id())
                item.set_wait_on(wait_on_list)
                wait_on_changed = wait_on_list != current_wait_on
                update_count += int(wait_on_changed)
                # Then validate WAIT on to existing Plow ids
                scheduler_operations = model.get_scheduler_operations()
                wait_on_plow_ids = scheduler_operations.validate_plow_ids(
                    current_wait_on_plow_ids)
                wait_on_plow_ids_changed = wait_on_plow_ids != current_wait_on_plow_ids
                if any([wait_on_changed, wait_on_plow_ids_changed]):
                    model.dataChanged.emit(qmodelindex, qmodelindex)
                continue

            elif operation == 'Clear Plow Ids':
                plow_job_id_last_changed = False
                plow_layer_id_last_changed = False
                plow_task_ids_last_changed = False

                current_dispatcher_job_id = item.get_dispatcher_plow_job_id()
                plow_dispatcher_job_id_new = None
                item.set_dispatcher_plow_job_id(plow_dispatcher_job_id_new)
                plow_dispatcher_job_id_changed = plow_dispatcher_job_id_new != current_dispatcher_job_id

                if is_pass_for_env_item:
                    current_plow_job_id_last = item.get_plow_job_id_last()
                    current_plow_layer_id_last = item.get_plow_layer_id_last()
                    current_plow_task_ids_last = item.get_plow_task_ids_last()
                    plow_job_id_new = None
                    plow_layer_id_new = None
                    plow_task_ids_new = None
                    item.set_plow_job_id_last(plow_job_id_new)
                    item.set_plow_layer_id_last(plow_layer_id_new)
                    item.set_plow_task_ids_last(plow_task_ids_new)
                    plow_job_id_last_changed = plow_job_id_new != current_plow_job_id_last
                    plow_layer_id_last_changed = plow_layer_id_new != current_plow_layer_id_last
                    plow_task_ids_last_changed = plow_task_ids_new != current_plow_task_ids_last
                    item.set_render_progress(None)

                if any([
                        plow_dispatcher_job_id_changed,
                        plow_job_id_last_changed,
                        plow_layer_id_last_changed,
                        plow_task_ids_last_changed]):
                    update_count += 1
                    model.dataChanged.emit(qmodelindex, qmodelindex)
                continue

            elif operation == 'Clear Render Estimates Cache':
                current_render_estimate_average_frame = item.get_render_estimate_average_frame()
                if current_render_estimate_average_frame != None:
                    item.set_render_estimate_average_frame(None)                    
                    update_count += 1                          
                    continue

            elif operation == 'Open Log Files' and is_pass_for_env_item:
                plow_job_id_last = item.get_plow_job_id_last()
                plow_task_id_last = item.get_plow_task_ids_last()
                if all([plow_job_id_last, plow_task_id_last]):
                    environment_item = item.get_environment_item()
                    render_item = item.get_source_render_item()
                    pass_name = render_item.get_pass_name()
                    window_title = 'Plow Task log for pass: "{}". '.format(pass_name)
                    window_title += 'env: "{}"'.format(environment_item.get_oz_area())
                    utils.open_task_log_file_as_window(
                        plow_job_id=plow_job_id_last,
                        plow_task_id=plow_task_id_last,
                        window_title=window_title,
                        show=True,
                        parent=self)
                continue

            elif operation == 'Derive frames from render item' and is_pass_for_env_item:
                render_item = item.get_source_render_item()
                render_item.sync_render_details()
                frames_for_render_item = render_item.get_frames()
                frames_current = item.get_resolved_frames_queued()
                try:
                    frame_set = fileseq.FrameSet(frames_for_render_item)
                except Exception as error:
                    frame_set = None
                if frame_set and frames_for_render_item != frames_current:
                    item.set_frame_range_override(str(frame_set))
                    model.dataChanged.emit(qmodelindex, qmodelindex)
                    model.framesResolveRequest.emit(qmodelindex)
                continue

            ##################################################################
            # Clear all or multiple frames overrides

            elif operation == 'Clear overrides':
                item.clear_overrides()
                update_count += 1
                model.dataChanged.emit(qmodelindex, qmodelindex)
                model.framesResolveRequest.emit(qmodelindex)
                continue

            elif operation == 'Clear Frames':
                item.set_frame_range_override(None)
                item.set_frames_rule_important(False)
                item.set_frames_rule_fml(False)
                item.set_frames_rule_x1(False)
                item.set_frames_rule_x10(False)
                item.set_frames_rule_xn(None)
                update_count += 1
                model.dataChanged.emit(qmodelindex, qmodelindex)
                model.framesResolveRequest.emit(qmodelindex)
                continue

            elif operation == 'Clear NOT Frames':
                item.set_not_frame_range_override(None)
                item.set_not_frames_rule_important(False)
                item.set_not_frames_rule_fml(False)
                item.set_not_frames_rule_x10(False)
                item.set_not_frames_rule_xn(None)
                update_count += 1
                model.dataChanged.emit(qmodelindex, qmodelindex)
                model.framesResolveRequest.emit(qmodelindex)
                continue

            ##################################################################
            # Operations to perform on Environment item

            elif operation == 'Sync production data for environments' and is_environment_item:
                env_nice_name = item.get_environment_name_nice()
                msg = 'Syncing production data for environment: "{}". '.format(env_nice_name)
                self.logMessage.emit(msg, logging.INFO)
                item.sync_production_data()
                model.resolve_frames_for_index(
                    qmodelindex,
                    update_overview_requested=False)
                update_count += 1
                continue

            elif operation == 'Duplicate environments' and is_environment_item:
                oz_area = item.get_oz_area()
                msg = 'Duplicating environment: "{}". '.format(oz_area)
                self.logMessage.emit(msg, logging.INFO)
                env_item_new = model.add_environment(
                    oz_area=oz_area,
                    copy_overrides_from=environment_item,
                    copy_from=environment_item,
                    sync_production_data=False)
                if env_item_new:
                    update_count += 1
                continue

            # Set which source production frame range type to resolve rules against
            elif operation in [
                    'SetSourceProductionRange_Cut',
                    'SetSourceProductionRange_Delivery',
                    'SetSourceProductionRange_FrameRange',
                    'SetSourceProductionRange_Important'] and is_environment_item:
                env_nice_name = item.get_environment_name_nice()
                current_production_range_source = item.get_production_range_source()
                production_range_source = operation.split('_')[-1]
                msg = 'Setting source production range to: "{}". '.format(production_range_source)
                msg += 'For env: "{}"'.format(env_nice_name)
                self.logMessage.emit(msg, logging.INFO)
                item.set_production_range_source(production_range_source)
                production_range_source_changed = production_range_source != current_production_range_source
                update_count += int(production_range_source_changed)
                if production_range_source_changed:
                    model.framesResolveRequest.emit(qmodelindex)
                    model.dataChanged.emit(qmodelindex, qmodelindex)
                    for column in columns:
                        _qmodelindex = model.index(row, column, qmodelindex.parent())
                        model.dataChanged.emit(_qmodelindex, _qmodelindex)
                continue
        
            elif operation == 'SetFramesResolveOrder' and is_environment_item:
                env_nice_name = item.get_environment_name_nice()
                value = bool(value)
                current_value = item.get_frame_resolve_order_env_first()
                msg = 'Setting frame resolve order env first then pass: "{}". '.format(value)
                msg += 'For env: "{}"'.format(env_nice_name)
                self.logMessage.emit(msg, logging.INFO)           
                item.set_frame_resolve_order_env_first(value)
                frames_resolve_order_changed = current_value != value
                if frames_resolve_order_changed:
                    model.framesResolveRequest.emit(qmodelindex)
                    model.dataChanged.emit(qmodelindex, qmodelindex)
                    for column in columns:
                        _qmodelindex = model.index(row, column, qmodelindex.parent())
                        model.dataChanged.emit(_qmodelindex, _qmodelindex)    
                continue
              
            msg = 'Operation not implemented or permitted: "{}"'.format(operation)
            self.logMessage.emit(msg, logging.WARNING)

        # Allow selection model signals again.
        selection_model.blockSignals(False)

        model.toggleProgressBarVisible.emit(False)

        # Emit the updateDetailsPanel so details panel now updates
        if update_count:
            self.updateDetailsPanel.emit(False)
            model.updateOverviewRequested.emit()

        # NOTE: Make sure this tree view has focus for next key press shortcut
        self.setFocus(Qt.ShortcutFocusReason)

        return update_count
    

    def queue(self, queue=None, selection=None):
        '''
        Queue or unqueue all the passes within selection.
        NOTE: If environment is in selection then all passes there of (or selected there of)
        will have queue state toggled at once.

        Args:
            selection (list): 
            queue (bool): provide boolean of whether to queue or unqueue selection.
                if not provided then derive target queued state from inverse 
                state of first selected item.
        
        Returns:
            update_count (int):
        '''
        selection = self.get_selection_or_item_under_mouse(selection=selection)
        if not selection:
            msg = 'No selected items to queue or unqueue!'
            self.logMessage.emit(msg, logging.WARNING)
            return 0

        # Filter selection
        items, env_qmodelindices = self.filter_selection(
            selection,
            include_environment_items=True,
            include_pass_for_env_items=False,
            include_group_items=False)
        env_qmodelindices = set(env_qmodelindices)
        items, pass_qmodelindices = self.filter_selection(
            selection,
            include_environment_items=False,
            include_pass_for_env_items=True,
            include_group_items=False)                
        selected_pass_qmodelindices = set(pass_qmodelindices)
        for pass_qmodelindex in pass_qmodelindices:
            env_qmodelindex = pass_qmodelindex.sibling(pass_qmodelindex.row(), 0)
            env_qmodelindices.add(env_qmodelindex)

        if not isinstance(queue, bool):
            queue = self._get_queued_state_from_qmodelindices(
                pass_qmodelindices=pass_qmodelindices,
                env_qmodelindices=env_qmodelindices)

        model = self.model()
        selection_model = self.selectionModel()
        selection_model.blockSignals(True)

        update_count = 0
        for env_qmodelindex in env_qmodelindices:
            if not env_qmodelindex.isValid():
                continue
            environment_item = env_qmodelindex.internalPointer()
            pass_qmodelindices = model.get_pass_for_env_items_indices([env_qmodelindex])
            if selected_pass_qmodelindices:
                _pass_qmodelindices = selected_pass_qmodelindices.intersection(pass_qmodelindices)
                if _pass_qmodelindices:
                    pass_qmodelindices = _pass_qmodelindices
            for pass_qmodelindex in pass_qmodelindices:
                if not pass_qmodelindex.isValid():
                    continue
                pass_for_env_item = pass_qmodelindex.internalPointer()
                # if not pass_env_item.is_pass_for_env_item():
                #     continue                
                if not pass_for_env_item.get_enabled():
                    msg = 'Cannot toggle queued state for disabled item!'
                    self.logMessage.emit(msg, logging.WARNING)
                    continue

                was_queued = pass_for_env_item.get_queued()
                queued_modified = queue != was_queued
                if queue:
                    pass_for_env_item.set_queued(True)
                else:
                    pass_for_env_item.set_queued(False)
                update_count += int(queued_modified)

                if queued_modified:
                    model.dataChanged.emit(pass_qmodelindex, pass_qmodelindex)
                    renderable_offset = 1 if pass_for_env_item.get_queued() else -1
                    pass_for_env_item._update_renderable_count_for_index(
                        pass_qmodelindex,
                        renderable_offset=renderable_offset)
                    model.framesResolveRequest.emit(pass_qmodelindex)                        

        selection_model.blockSignals(False)
        if update_count:
            self.updateDetailsPanel.emit(False)
            model.updateOverviewRequested.emit()
            # Update column headers
            all_columns = set(range(0, model.columnCount(QModelIndex())))
            self._update_header_columns(all_columns)
        self.setFocus(Qt.ShortcutFocusReason)

        return update_count


    def _get_queued_state_from_qmodelindices(
            self, 
            pass_qmodelindices=None,
            env_qmodelindices=None):
        '''
        Derive queued state from pass and env qmodelindices.

        Args:
            pass_qmodelindices (list):
            env_qmodelindices (list):
        
        Returns:
            queue (bool):
        '''
        queue = None
        if pass_qmodelindices:
            qmodelindex = list(pass_qmodelindices)[0]
            item = qmodelindex.internalPointer()
            queue = not item.get_queued()
        elif env_qmodelindices:
            qmodelindex = list(env_qmodelindices)[0]
            item = qmodelindex.internalPointer()
            queue = not bool(item._get_renderable_count_for_env())
        # Fallback to unqueue target state
        if not isinstance(queue, bool):
            queue = False
        return queue


    ##########################################################################
    # Copy, paste, clear, and edit all overriddes in view selection


    def copy_overrides_for_selection(self, selection=None):
        '''
        Copy overrides for selected environment and pass for env items and
        cache as class member data, ready to be later pasted.

        Args:
            selection (list): optionally pass in an explicit QModelIndex list

        Returns:
            overrides_dict, pass_overrides_dict (tuple):
        '''
        selection = self.get_selection_or_item_under_mouse(selection=selection)
        if not selection:
            msg = 'No selected items to copy overrides for!'
            self.logMessage.emit(msg, logging.WARNING)
            return 0

        selection_count = len(selection)
        msg = 'Copying overrides for selection count: {}'.format(selection_count)
        self.logMessage.emit(msg, logging.WARNING)

        overrides_dict, pass_overrides_dict = (dict(), dict())
        for qmodelindex in selection:
            if not qmodelindex.isValid():
                continue
            item = qmodelindex.internalPointer()
            if item.is_group_item():
                continue
            is_pass_for_env_item = item.is_pass_for_env_item()
            if is_pass_for_env_item:
                render_item = item.get_source_render_item()
                item_full_name = render_item.get_item_full_name()
                pass_overrides_dict[item_full_name] = item.copy_overrides()
            else:
                overrides_dict = item.copy_overrides()

        self._copied_overrides_dict = dict()
        self._copied_pass_overrides_dict = dict()
        if overrides_dict:
            if self._debug_mode:
                msg = 'Copying overrides: {}'.format(overrides_dict)
                self.logMessage.emit(msg, logging.DEBUG)
            self._copied_overrides_dict = overrides_dict
        if pass_overrides_dict:
            if self._debug_mode:
                msg = 'Copying pass overrides: {}'.format(pass_overrides_dict)
                self.logMessage.emit(msg, logging.DEBUG)
            self._copied_pass_overrides_dict = pass_overrides_dict
        return overrides_dict, pass_overrides_dict


    def paste_overrides_for_selection(
            self,
            overrides_dict=None,
            pass_overrides_dict=None,
            selection=None):
        '''
        Paste cached overrides to selection, or use explicit overrides dict.

        Args:
            overrides_dict (dict): overrides to paste
            pass_overrides_dict (dict): overrides to paste mapped to specific item names
            selection (list): optionally pass in an explicit QModelIndex list

        Returns:
            update_count (int):
        '''
        overrides_dict = overrides_dict or self._copied_overrides_dict
        pass_overrides_dict = pass_overrides_dict or self._copied_pass_overrides_dict
        if not any([overrides_dict, pass_overrides_dict]):
            msg = 'No Cached Or Provided Overrides Previously Copied To Paste!'
            self.logMessage.emit(msg, logging.WARNING)
            return 0

        selection = self.get_selection_or_item_under_mouse(selection=selection)
        if not selection:
            msg = 'No Selected Items To Paste Overrides For!'
            self.logMessage.emit(msg, logging.WARNING)
            return 0
        model = self.model()

        selection_model = self.selectionModel()
        selection_model.blockSignals(True)
        selection_count = len(selection)
        msg = 'Pasting Overrides For Selection Count: {}'.format(selection_count)
        self.logMessage.emit(msg, logging.WARNING)

        update_count = 0
        for i, qmodelindex in enumerate(selection):
            if not qmodelindex.isValid():
                continue
            item = qmodelindex.internalPointer()
            if item.is_group_item():
                continue
            is_pass_for_env_item = item.is_pass_for_env_item()
            if is_pass_for_env_item and self._copied_pass_overrides_dict:
                # If only one pass in copied data, then paste on to every selected cell
                if len(self._copied_pass_overrides_dict.keys()) == 1:
                    _key = self._copied_pass_overrides_dict.keys()[0]
                    overrides_dict = self._copied_pass_overrides_dict[_key]
                # Otherwise get the copied data for particular render node for this selected cell (if any)
                else:
                    render_item = item.get_source_render_item()
                    overrides_dict = self._copied_pass_overrides_dict.get(
                        render_item.get_item_full_name(), dict())
            else:
                # Get copied shot data, and apply to every selected cell
                overrides_dict = self._copied_overrides_dict or dict()
                # Otherwise paste first copied pass details to this environment
                if not overrides_dict and len(self._copied_pass_overrides_dict.keys()) >= 1:
                    _key = self._copied_pass_overrides_dict.keys()[0]
                    overrides_dict = self._copied_pass_overrides_dict[_key]
            # Paste the override and update the view
            if overrides_dict:
                overrides_applied = item.paste_overrides(overrides_dict)
                if overrides_applied:
                    update_count += 1
                    model.dataChanged.emit(qmodelindex, qmodelindex)

        selection_model.blockSignals(False)
        if update_count:
            self.updateDetailsPanel.emit(False)
            model.updateOverviewRequested.emit()
        self.setFocus(Qt.ShortcutFocusReason)
        return update_count


    def is_overrides_ready_for_paste(self):
        '''
        Return whether any overrides are cached ready to be pasted on to selected MSRS view items.

        Returns:
            overrides_ready_for_paste (bool):
        '''
        return any([
            self._copied_overrides_dict,
            self._copied_pass_overrides_dict])


    def clear_overrides_in_selection_by_id(self, override_id, selection=None):
        '''
        Clear all core / built in overrides in this tree view selection by override id.
        NOTE: For render overrides call remove_render_overrides_from_selection instead.

        Args:
            override_id (str): the override display label / id as passed from
                render pass for env widget
            selection (list): optionally pass in an explicit QModelIndex list

        Returns:
            update_count (int):
        '''
        selection = self.get_selection_or_item_under_mouse(selection=selection)
        if not selection:
            msg = 'No Selected Items To Clear Overrides For!'
            self.logMessage.emit(msg, logging.WARNING)
            return 0
        model = self.model()

        selection_model = self.selectionModel()
        selection_model.blockSignals(True)
        selection_count = len(selection)
        msg = 'Clearing Overrides For Selection Count: {}. '.format(selection_count)
        msg += 'By Override Id: "{}"'.format(override_id)
        self.logMessage.emit(msg, logging.WARNING)

        update_count = 0
        for i, qmodelindex in enumerate(selection):
            if not qmodelindex.isValid():
                continue
            item = qmodelindex.internalPointer()
            if item.is_group_item():
                continue

            ##################################################################
            # Clear each frame rule

            # TODO: The core override id should match render pass for env
            # widget cached key, and session data key, to avoid this if branching...

            # key = render_pass_for_env_widget.get_session_key_for_override(override_id)

            # TODO: Check session key against constants session keys...
            if override_id == constants.OVERRIDE_FRAMES_CUSTOM:
                current_value = item.get_frame_range_override()
                item.set_frame_range_override(None)
                if current_value != item.get_frame_range_override():
                    update_count += 1
                    model.dataChanged.emit(qmodelindex, qmodelindex)
                    model.framesResolveRequest.emit(qmodelindex)

            elif override_id == constants.OVERRIDE_FRAMES_IMPORTANT:
                current_value = item.get_frames_rule_important()
                item.set_frames_rule_important(False)
                if current_value != item.get_frames_rule_important():
                    update_count += 1
                    model.dataChanged.emit(qmodelindex, qmodelindex)
                    model.framesResolveRequest.emit(qmodelindex)

            elif override_id == constants.OVERRIDE_FRAMES_FML:
                current_value = item.get_frames_rule_fml()
                item.set_frames_rule_fml(False)
                if current_value != item.get_frames_rule_fml():
                    update_count += 1
                    model.dataChanged.emit(qmodelindex, qmodelindex)
                    model.framesResolveRequest.emit(qmodelindex)

            elif override_id == constants.OVERRIDE_FRAMES_X1:
                current_value = item.get_frames_rule_x1()
                item.set_frames_rule_x1(False)
                if current_value != item.get_frames_rule_x1():
                    update_count += 1
                    model.dataChanged.emit(qmodelindex, qmodelindex)
                    model.framesResolveRequest.emit(qmodelindex)

            elif override_id == constants.OVERRIDE_FRAMES_X10:
                current_value = item.get_frames_rule_x10()
                item.set_frames_rule_x10(False)
                if current_value != item.get_frames_rule_x10():
                    update_count += 1
                    model.dataChanged.emit(qmodelindex, qmodelindex)
                    model.framesResolveRequest.emit(qmodelindex)

            elif override_id == constants.OVERRIDE_FRAMES_XCUSTOM:
                current_value = item.get_frames_rule_xn()
                item.set_frames_rule_xn(None)
                if current_value != item.get_frames_rule_xn():
                    update_count += 1
                    model.dataChanged.emit(qmodelindex, qmodelindex)
                    model.framesResolveRequest.emit(qmodelindex)

            ##################################################################
            # Clear each NOT frame rule

            elif override_id == constants.OVERRIDE_FRAMES_NOT_CUSTOM:
                current_value = item.get_not_frame_range_override()
                item.set_not_frame_range_override(None)
                if current_value != item.get_not_frame_range_override():
                    update_count += 1
                    model.dataChanged.emit(qmodelindex, qmodelindex)
                    model.framesResolveRequest.emit(qmodelindex)

            elif override_id == constants.OVERRIDE_FRAMES_NOT_IMPORTANT:
                current_value = item.get_not_frames_rule_important()
                item.set_not_frames_rule_important(False)
                if current_value != item.get_not_frames_rule_important():
                    update_count += 1
                    model.dataChanged.emit(qmodelindex, qmodelindex)
                    model.framesResolveRequest.emit(qmodelindex)

            elif override_id == constants.OVERRIDE_FRAMES_NOT_FML:
                current_value = item.get_not_frames_rule_fml()
                item.set_not_frames_rule_fml(False)
                if current_value != item.get_not_frames_rule_fml():
                    update_count += 1
                    model.dataChanged.emit(qmodelindex, qmodelindex)
                    model.framesResolveRequest.emit(qmodelindex)

            elif override_id == constants.OVERRIDE_FRAMES_NOT_X10:
                current_value = item.get_not_frames_rule_x10()
                item.set_not_frames_rule_x10(False)
                if current_value != item.get_not_frames_rule_x10():
                    update_count += 1
                    model.dataChanged.emit(qmodelindex, qmodelindex)
                    model.framesResolveRequest.emit(qmodelindex)

            elif override_id == constants.OVERRIDE_FRAMES_NOT_XCUSTOM:
                current_value = item.get_not_frames_rule_xn()
                item.set_not_frames_rule_xn(None)
                if current_value != item.get_not_frames_rule_xn():
                    update_count += 1
                    model.dataChanged.emit(qmodelindex, qmodelindex)
                    model.framesResolveRequest.emit(qmodelindex)

            ##################################################################

            elif override_id == constants.OVERRIDE_NOTE:
                current_note_override = item.get_note_override()
                _value = None
                item.set_note_override(_value)
                note_changed = _value != current_note_override
                update_count += int(note_changed)
                if note_changed:
                    model.dataChanged.emit(qmodelindex, qmodelindex)
                continue

            elif override_id == constants.OVERRIDE_WAIT:
                current_wait_on = item.get_wait_on()
                current_wait_on_plow_ids = item.get_wait_on_plow_ids()
                _wait_on_list = list()
                item.set_wait_on(_wait_on_list)
                wait_on_changed = _wait_on_list != current_wait_on
                _wait_on_plow_ids_list = list()
                item.set_wait_on_plow_ids(_wait_on_plow_ids_list)
                wait_on_plow_ids_changed = _wait_on_plow_ids_list != current_wait_on_plow_ids
                update_count += int(wait_on_changed)
                if any([wait_on_changed, wait_on_plow_ids_changed]):
                    model.dataChanged.emit(qmodelindex, qmodelindex)
                continue

            elif override_id == constants.OVERRIDE_JOB_IDENTIFIER and item.is_environment_item():
                current_job_identifier = item.get_job_identifier()
                _value = None
                item.set_job_identifier(_value)
                job_identifier_changed = _value != current_job_identifier
                update_count += int(job_identifier_changed)
                if job_identifier_changed:
                    model.dataChanged.emit(qmodelindex, qmodelindex)
                continue

            elif override_id == constants.OVERRIDE_SPLIT_FRAME_RANGES and item.is_environment_item():
                current_split_frame_ranges = item.get_split_frame_ranges()
                _value = None
                item.set_split_frame_ranges(_value)
                split_frame_ranges_changed = _value != current_split_frame_ranges
                update_count += int(split_frame_ranges_changed)
                if split_frame_ranges_changed:
                    model.dataChanged.emit(qmodelindex, qmodelindex)
                continue

            ##################################################################
            # Overrides which have an id to indicate multiple possible states

            elif override_id == 'Version':
                current_ver_num = item.get_version_override()
                _value = None
                item.set_version_override(_value)
                version_changed = _value != current_ver_num
                update_count += int(version_changed)
                if version_changed:
                    model.dataChanged.emit(qmodelindex, qmodelindex)
                continue

            ##################################################################
            # Overrides that don't appear as box within cell

            elif override_id == 'MSRS_Colour':
                current_colour = item.get_colour()
                _value = None
                item.set_colour(_value)
                colour_changed = _value != current_colour
                update_count += int(colour_changed)
                if colour_changed:
                    model.dataChanged.emit(qmodelindex, qmodelindex)
                continue

            else:
                msg = 'Remove Override For Id Not Implemeneted Or Permitted: "{}"'.format(override_id)
                self.logMessage.emit(msg, logging.WARNING)

        selection_model.blockSignals(False)
        if update_count:
            self.updateDetailsPanel.emit(False)
            model.updateOverviewRequested.emit()
        self.setFocus(Qt.ShortcutFocusReason)
        if override_id == constants.OVERRIDE_WAIT and self._overlay_widget:
            self._overlay_widget.update_overlays()
        return update_count


    def copy_overrides_in_selection_by_id(self, override_id, selection=None):
        '''
        Copy all core / built in overrides in this tree view selection by override id.

        Args:
            override_id (str): the override display label / id as passed from
                render pass for env widget
            selection (list): optionally pass in an explicit QModelIndex list
        '''
        selection = self.get_selection_or_item_under_mouse(selection=selection)
        if not selection:
            msg = 'No Selected Items To Copy Overrides For!'
            self.logMessage.emit(msg, logging.WARNING)
            return
        model = self.model()

        selection_count = len(selection)

        msg = 'Copying Overrides From Selection With Id: "{}"'.format(override_id)
        self.logMessage.emit(msg, logging.INFO)

        self._copied_overrides_dict = dict()
        self._copied_pass_overrides_dict = dict()

        delegate = self.itemDelegate()
        render_pass_for_env_widget = delegate.get_render_pass_for_env_object()

        for i, qmodelindex in enumerate(selection):
            if not qmodelindex.isValid():
                continue
            item = qmodelindex.internalPointer()
            column = qmodelindex.column()
            row = qmodelindex.row()
            if item.is_group_item():
                continue
            identifier = item.get_identifier()

            # Get all the overrides and render overrides data as dict
            overrides_dict = item.copy_overrides()

            # Check if copied data has the specific core override id.
            key = render_pass_for_env_widget.get_session_key_for_override(override_id)

            if not key:
                continue
            value = overrides_dict.get(key)
            if value == None:
                continue

            # Formulate only the target override id data to copy
            overrides_dict_clean = dict()
            overrides_dict_clean[key] = value

            msg = 'Copying Override From Identifier: "{}". '.format(identifier)
            msg += 'Override Id: "{}". '.format(key)
            msg += 'Value: "{}"'.format(value)
            self.logMessage.emit(msg, logging.INFO)

            if item.is_environment_item():
                self._copied_overrides_dict = overrides_dict_clean
            else:
                render_item = item.get_source_render_item()
                item_full_name = render_item.get_item_full_name()
                self._copied_pass_overrides_dict[item_full_name] = dict()
                self._copied_pass_overrides_dict[item_full_name] = overrides_dict_clean


    ##########################################################################
    # Modify various built in overrides in isolation


    def edit_override_id_for_selection(
            self,
            override_id,
            selection=None):
        '''
        Invoke the edit / set mode for a given override id.
        NOTE: For render overrides call add_render_overrides_to_selection instead.

        Args:
            override_id (str):
        '''
        if override_id == constants.OVERRIDE_NOTE:
            self.edit_note_for_selection(selection=selection)
        elif override_id == constants.OVERRIDE_JOB_IDENTIFIER:
            self.edit_job_identifier_for_selection(selection=selection)
        elif override_id == constants.OVERRIDE_WAIT:
            self.edit_wait_on_for_selection(selection=selection)
        elif override_id == 'Version':
            self._tree_view_operations(
                operation=constants.OVERRIDE_VERSION_CUSTOM,
                selection=selection)
        else:
            self._tree_view_operations(
                operation=override_id,
                selection=selection)

    def edit_job_identifier_for_selection(
            self,
            job_identifier=str(),
            selection=None,
            show_dialog=True):
        '''
        Set job identifier for selected MSRS environment items.

        Args:
            job_identifier (str):
            selection (list): optionally pass in an explicit QModelIndex list
            show_dialog (bool):

        Returns:
            update_count (int):
        '''
        selection = self.get_selection_or_item_under_mouse(selection=selection)
        if not selection:
            msg = 'No selected items to set job identifier for!'
            self.logMessage.emit(msg, logging.WARNING)
            return 0

        # Don't even show the dialog depending on selection
        items, _qmodelindices = self.filter_selection(
            selection,
            include_environment_items=True,
            include_pass_for_env_items=False,
            include_group_items=False)
        if not items:
            msg = 'No environment items in selection!'
            self.logMessage.emit(msg, logging.WARNING)
            return 0

        if show_dialog:
            initial_value = str()
            qmodelindex = selection[-1]
            _item = qmodelindex.internalPointer()
            if len(selection) == 1:
                initial_value = _item.get_job_identifier() or str()

            msg = '<i>Job identifier will become part of job name at submission.</i>'
            msg += '<br><i>Note: Use camelCase or underscore as spaces not permitted.</i>'

            from srnd_qt.ui_framework.dialogs import input_dialog
            dialog = input_dialog.GetInputDialog(
                title_str='Choose {}job identifier{}'.format(fs, fe),
                description=msg,
                description_by_title=False,
                input_type_required=str(),
                value=initial_value,
                parent=self)
            dialog.setWindowTitle('Choose job identifier')
            dialog.setMinimumHeight(150)
            dialog.resize(575, 175)

            options_box_header = dialog.get_header_widget()
            style_sheet = 'QGroupBox {background: rgb(70, 70, 70);'
            style_sheet += 'border:rgb(70, 70, 70)}'
            options_box_header.setStyleSheet(style_sheet)

            value_widget = dialog.get_value_widget()
            validator = QRegExpValidator()
            validator.setRegExp(QRegExp('[A-Za-z0-9_]+'))
            value_widget.setValidator(validator)
            result = dialog.exec_()
            if result == QDialog.Rejected:
                return 0
            job_identifier = str(dialog.get_result() or str())
            msg = 'User picked job identifier to apply to selection: "{}"'.format(job_identifier)
            self.logMessage.emit(msg, logging.WARNING)

        model = self.model()
        selection_model = self.selectionModel()
        selection_model.blockSignals(True)

        update_count = 0
        for i, qmodelindex in enumerate(selection):
            if not qmodelindex.isValid():
                continue
            item = qmodelindex.internalPointer()
            if not item.is_environment_item():
                continue
            current_job_identifier = item.get_job_identifier()
            item.set_job_identifier(job_identifier)
            job_identifier_changed = job_identifier != current_job_identifier
            update_count += int(job_identifier_changed)
            if job_identifier_changed:
                model.dataChanged.emit(qmodelindex, qmodelindex)

        selection_model.blockSignals(False)
        if update_count:
            self.updateDetailsPanel.emit(False)
        self.setFocus(Qt.ShortcutFocusReason)
        return update_count


    def edit_note_for_selection(
            self,
            note=str(),
            selection=None,
            show_dialog=True):
        '''
        Set note for selected MSRS items.

        Args:
            note (list): RGB list
            selection (list): optionally pass in an explicit QModelIndex list
            show_dialog (bool):

        Returns:
            update_count (int):
        '''
        selection = self.get_selection_or_item_under_mouse(selection=selection)
        if not selection:
            msg = 'No selected items to set note for!'
            self.logMessage.emit(msg, logging.WARNING)
            return 0

        # Don't even show the dialog depending on selection
        items, _qmodelindices = self.filter_selection(
            selection,
            include_environment_items=True,
            include_pass_for_env_items=True,
            include_group_items=False)
        if not items:
            msg = 'No environment or render pass for env items in selection!'
            self.logMessage.emit(msg, logging.WARNING)
            return 0

        if show_dialog:
            initial_value = str()
            qmodelindex = selection[-1]
            _item = qmodelindex.internalPointer()
            if _item:
                initial_value = _item.get_note_override() or initial_value

            title_str = 'Choose {}note{} for selecttion'.format(fs, fe)
            if len(selection) == 1:
                initial_value = _item.get_note_override() or str()
                if _item.is_environment_item():
                    title_str = 'Choose {}note{} for selected environment'.format(fs, fe)
                if _item.is_pass_for_env_item():
                    title_str = 'Choose {}note{} for selected pass'.format(fs, fe)

            msg = '<i>Notes are used for Shotsub or Koba tasks '
            msg += 'or just to help organize the session.</i>'

            from srnd_qt.ui_framework.dialogs import input_dialog
            dialog = input_dialog.GetInputDialog(
                title_str=title_str,
                description=msg,
                description_by_title=False,
                input_type_required=str(),
                value=initial_value,
                parent=self)
            dialog.setWindowTitle('Choose note for selection')
            dialog.setMinimumHeight(150)
            dialog.resize(725, 175)

            options_box_header = dialog.get_header_widget()
            style_sheet = 'QGroupBox {background: rgb(70, 70, 70);'
            style_sheet += 'border:rgb(70, 70, 70)}'
            options_box_header.setStyleSheet(style_sheet)

            value_widget = dialog.get_value_widget()
            result = dialog.exec_()
            if result == QDialog.Rejected:
                return 0
            note = str(dialog.get_result() or str())
            msg = 'User picked note to apply to selection: "{}"'.format(note)
            self.logMessage.emit(msg, logging.WARNING)

        model = self.model()
        selection_model = self.selectionModel()
        selection_model.blockSignals(True)

        update_count = 0
        for i, qmodelindex in enumerate(selection):
            if not qmodelindex.isValid():
                continue
            item = qmodelindex.internalPointer()
            if item.is_group_item():
                continue
            current_note_override = item.get_note_override()
            item.set_note_override(note)
            note_changed = note != current_note_override
            update_count += int(note_changed)
            if note_changed:
                model.dataChanged.emit(qmodelindex, qmodelindex)
            continue

        selection_model.blockSignals(False)
        if update_count:
            self.updateDetailsPanel.emit(False)
        self.setFocus(Qt.ShortcutFocusReason)
        return update_count


    def edit_colour_for_selection(
            self,
            colour=None,
            selection=None,
            show_dialog=True):
        '''
        Set colour for selected MSRS items.

        Args:
            colour (list): RGB list
            selection (list): optionally pass in an explicit QModelIndex list
            show_dialog (bool):

        Returns:
            update_count (int):
        '''
        selection = self.get_selection_or_item_under_mouse(selection=selection)
        if not selection:
            msg = 'No Selected Items To Set Colour For!'
            self.logMessage.emit(msg, logging.WARNING)
            return 0

        # Don't even show the dialog depending on selection
        items, _qmodelindices = self.filter_selection(
            selection,
            include_environment_items=True,
            include_pass_for_env_items=True,
            include_group_items=False)
        if not items:
            msg = 'No Environment Or Render Pass For Env Items In Selection!'
            self.logMessage.emit(msg, logging.WARNING)
            return 0

        if show_dialog:
            initial_value = [1.0, 1.0, 1.0]
            qmodelindex = selection[-1]
            _item = qmodelindex.internalPointer()
            if _item:
                initial_value = _item.get_colour() or initial_value
            from srnd_qt.ui_framework.dialogs.color_picker_dialog import ColorPickerDialog
            color_picker_dialog = ColorPickerDialog(
                color=initial_value,
                allowed_outside_range=False,
                color_palettes_visible=False,
                color_sliders_have_numbers=True,
                has_okay_cancel_button=True,
                has_temperature_and_gel_swatch=False,
                parent=self)
            result = color_picker_dialog.exec_()
            if result == QDialog.Rejected or not color_picker_dialog.get_rgb():
                return
            colour = color_picker_dialog.get_rgb()
            msg = 'User Picked Colour To Apply To Selection: "{}"'.format(colour)
            self.logMessage.emit(msg, logging.WARNING)

        if not colour or not isinstance(colour, (list, tuple)):
            return 0

        model = self.model()
        selection_model = self.selectionModel()
        selection_model.blockSignals(True)

        update_count = 0
        for i, qmodelindex in enumerate(selection):
            if not qmodelindex.isValid():
                continue
            item = qmodelindex.internalPointer()
            if item.is_group_item():
                continue
            current_colour = item.get_colour()
            item.set_colour(colour)
            colour_changed = colour != current_colour
            update_count += int(colour_changed)
            if colour_changed:
                model.dataChanged.emit(qmodelindex, qmodelindex)

        selection_model.blockSignals(False)
        self.setFocus(Qt.ShortcutFocusReason)
        return update_count


    def derive_missing_frames_for_passes(
            self,
            selection=None,
            show_dialog=True):
        '''
        Derive missing frames for selected passes and set as custom frames.

        Args:
            selection (list): optionally pass in an explicit QModelIndex list
            show_dialog (bool):

        Returns:
            update_count (int):
        '''
        msg_no_select = 'No Selected Pass For Env Items To '
        msg_no_select += 'Derive Missing Frames For!'
        selection = self.get_selection_or_item_under_mouse(selection=selection)
        if not selection:
            self.logMessage.emit(msg_no_select, logging.WARNING)
            return 0
        items, _qmodelindices = self.filter_selection(
            selection,
            include_environment_items=False,
            include_pass_for_env_items=True,
            include_group_items=False)
        if not items:
            self.logMessage.emit(msg_no_select, logging.WARNING)
            return 0

        model = self.model()
        selection_model = self.selectionModel()
        selection_model.blockSignals(True)

        update_count = 0
        for i, qmodelindex in enumerate(selection):
            if not qmodelindex.isValid():
                continue
            item = qmodelindex.internalPointer()
            if not item.is_pass_for_env_item():
                continue
            env_item = item.get_environment_item()
            frames_current = item.get_resolved_frames_queued()
            oz_area = env_item.get_oz_area()
            render_item = item.get_source_render_item()
            pass_name = render_item.get_pass_name()
            render_item = item.get_source_render_item()
            project_version_number = render_item.get_current_project_version()
            version_number = item.resolve_version(
                source_project_version=project_version_number,
                cache_values=False)
            if not isinstance(version_number, int):
                msg = 'Failed To Resolve Version To Get Missing Frames! '
                msg += 'For Env: "{}". Pass: "{}"'.format(oz_area, pass_name)
                self.logMessage.emit(msg, logging.WARNING)
                continue
            hydra_version = utils.get_cg_version(
                pass_name, # product name
                environment=oz_area,
                version_number=version_number) # the user should set explicit version to previous version
            try:
                hydra_resource = hydra_version.getDefaultResource()
            except Exception:
                hydra_resource = None
            if not hydra_resource:
                msg = 'Failed To Get Cg Version Or Default Resource To Get Missing Frames! '
                msg += 'Version: "{}". '.format(version_number)
                msg += 'For Env: "{}". Pass: "{}"'.format(oz_area, pass_name)
                self.logMessage.emit(msg, logging.WARNING)
                continue
            location = hydra_resource.location
            file_sequence = fileseq.findSequenceOnDisk(location)
            frameset = file_sequence.frameSet()
            msg = 'All Frames: "{}". For Location: "{}". '.format(str(frameset), location)
            msg += 'Hyref: "{}"'.format(hydra_version.getHyref())
            self.logMessage.emit(msg, logging.WARNING)
            frames = set()
            for frame in range(frameset.start(), frameset.end()):
                frame_str = str(frame).zfill(2)
                output_path = location.replace('.#.', '.{}.'.format(frame_str))
                output_path = os.path.realpath(output_path)
                try:
                    # Skip files on disc and that are greater than zero bytes
                    if os.path.isfile(output_path) and os.stat(output_path).st_size > 0:
                        continue
                except Exception:
                    # Mark frame as missing if check fails
                    pass
                frames.add(frame)
            new_frame_range = str(fileseq.FrameSet(frames))
            if new_frame_range and new_frame_range != frames_current:
                # Clear existing frames overrides
                item.set_frame_range_override(None)
                item.set_frames_rule_important(False)
                item.set_frames_rule_fml(False)
                item.set_frames_rule_x1(False)
                item.set_frames_rule_x10(False)
                item.set_frames_rule_xn(None)
                item.set_not_frame_range_override(None)
                item.set_not_frames_rule_important(False)
                item.set_not_frames_rule_fml(False)
                item.set_not_frames_rule_x10(False)
                item.set_not_frames_rule_xn(None)
                # Apply custom missing frames
                item.set_frame_range_override(str(new_frame_range))
                model.dataChanged.emit(qmodelindex, qmodelindex)
                model.framesResolveRequest.emit(qmodelindex)
                update_count += 1

        selection_model.blockSignals(False)
        self.setFocus(Qt.ShortcutFocusReason)

        if update_count:
            title = 'Successfully Derived Some Missing Frames!'
            msg = 'Missing Frames Were Successfully Derived & '
            msg += 'Set As Custom Frames Overrides. '
            msg += '<br><i>Note: Missing Frames Were Calculated Using The '
            msg += 'Current Resolved Cg Version (Or Explicit).</i>'
            msg += '<br><i>Note: Please Insure To Later Remove The Custom '
            msg += 'Frames Override When Rendering To Future Versions.</i>'
            QMessageBox.warning(None, title, msg, QMessageBox.Ok)
        else:
            title = 'Failed To Derive Any Missing Frames!'
            msg = '<i>Note: Set Pass Or Environment To Explicit Cg '
            msg += 'Version Override So Missing Frames Can Be Calculated!</i>'
            QMessageBox.warning(None, title, msg, QMessageBox.Ok)

        return update_count


    ##########################################################################
    # Plow actions


    def plow_modify_job_or_layer_stats(
            self,
            job_type='job',
            selection=None,
            show_dialog=True):
        '''
        KILL or EAT Plow Jobs or Layers for the selected MSRS environment or render pass items.

        Args:
            job_type (str): type of MSRS Plow target to kill.
                either "job", "layer","dispatcher"
            selection (list): optionally pass in an explicit QModelIndex list
            show_dialog (bool): optionally show confirm dialog before killing job/s or task/s

        Returns:
            killed_job_count (int):
        '''
        selection = self.get_selection_or_item_under_mouse(selection=selection)
        if not selection:
            msg = 'No Selected Items To KILL Plow Jobs For!'
            self.logMessage.emit(msg, logging.WARNING)
            return 0

        # Don't even show the dialog depending on selection
        items, _qmodelindices = self.filter_selection(
            selection,
            include_environment_items=True,
            include_pass_for_env_items=True,
            include_group_items=False)
        if not items:
            msg = 'No Environment Or Render Pass For Env Items In Selection!'
            self.logMessage.emit(msg, logging.WARNING)
            return 0

        job_type = str(job_type)
        if not job_type:
            msg = 'Unknown Plow Operation Requested!'
            self.logMessage.emit(msg, logging.WARNING)
            return 0

        if show_dialog:
            # Count number of Plow operations in selection
            dispatcher_jobs_count = 0
            render_jobs_count = 0
            layers_count = 0
            for i, qmodelindex in enumerate(selection):
                if not qmodelindex.isValid():
                    continue
                item = qmodelindex.internalPointer()
                if job_type == 'dispatcher' and item.get_dispatcher_plow_job_id():
                    dispatcher_jobs_count += 1
                if job_type == 'job' and item.is_pass_for_env_item():
                    if item.get_plow_job_id_last():
                        render_jobs_count += 1
                if job_type == 'layer' and item.is_pass_for_env_item():
                    if item.get_plow_job_id_last() and item.get_plow_layer_id_last():
                        layers_count += 1

            if not any([dispatcher_jobs_count, render_jobs_count, layers_count]):
                msg = 'No Plow Ids To Perform Operation On!'
                self.logMessage.emit(msg, logging.WARNING)
                return 0

            title = 'Confirm Plow Operation?'
            msg = str()
            if job_type == 'dispatcher':
                msg = 'Are You Sure You Want To Kill {} '.format(dispatcher_jobs_count)
                msg += 'Dispatcher Jobs? '
                msg += '<br><i>Note: The Dispatcher Might Have Already Launched '
                msg += 'A Subset Of The Requested Environments</i>'
            elif job_type == 'job':
                msg = 'Are You Sure You Want To Kill {} '.format(render_jobs_count)
                msg += 'Render Jobs?'
            elif job_type == 'layer':
                msg = 'Are You Sure You Want To EAT {} '.format(layers_count)
                msg += 'Render Job Layers?'
            reply = QMessageBox.warning(
                self,
                title,
                msg or title,
                QMessageBox.Ok | QMessageBox.Cancel)
            if reply == QMessageBox.Cancel:
                msg = 'User Skipped Plow Operation!'
                self.logMessage.emit(msg, logging.WARNING)
                return 0

        import plow

        model = self.model()

        kill_msg = 'Kill Job Request From Multi Shot Render Submitter'

        scheduler_operations = model.get_scheduler_operations()

        update_count = 0
        for i, qmodelindex in enumerate(selection):
            if not qmodelindex.isValid():
                continue
            item = qmodelindex.internalPointer()

            # Kill dispatcher Plow Jobs
            dispatcher_plow_job_id = item.get_dispatcher_plow_job_id()
            if job_type == 'dispatcher' and dispatcher_plow_job_id:
                job = scheduler_operations.get_job(dispatcher_plow_job_id)
                if job:
                    item.set_dispatcher_plow_job_id(None)
                    if job.state == plow.job.JobState.FINISHED:
                        msg = 'Dispatcher Plow Job Id Already FINISHED '
                        msg += 'Or KILLED: "{}"'.format(dispatcher_plow_job_id)
                        self.logMessage.emit(msg, logging.WARNING)
                        continue
                    msg = 'Killing Dispatcher Plow Job Id: "{}"'.format(dispatcher_plow_job_id)
                    self.logMessage.emit(msg, logging.WARNING)
                    job.kill(kill_msg)

            # Kill Render Plow Jobs
            if job_type == 'job' and item.is_pass_for_env_item():
                plow_job_id_last = item.get_plow_job_id_last()
                plow_layer_id_last = item.get_plow_layer_id_last()
                if not plow_job_id_last:
                    continue
                job = scheduler_operations.get_job(plow_job_id_last)
                if job:
                    item.set_plow_job_id_last(None)
                    item.set_plow_layer_id_last(None)
                    if job.state == plow.job.JobState.FINISHED:
                        msg = 'Render Plow Job Id Already FINISHED '
                        msg += 'Or KILLED: "{}"'.format(plow_job_id_last)
                        self.logMessage.emit(msg, logging.WARNING)
                        continue
                    msg = 'Killing Render Plow Job Id: "{}"'.format(plow_job_id_last)
                    self.logMessage.emit(msg, logging.WARNING)
                    job.kill(kill_msg)

            # EAT Render Plow layers
            if job_type == 'layer' and item.is_pass_for_env_item():
                plow_job_id_last = item.get_plow_job_id_last()
                plow_layer_id_last = item.get_plow_layer_id_last()
                if not all([plow_job_id_last, plow_layer_id_last]):
                    continue
                job = scheduler_operations.get_job(plow_job_id_last)
                if job:
                    item.set_plow_layer_id_last(None)
                    if job.state == plow.job.JobState.FINISHED:
                        msg = 'Render Layer Plow Job Id Already FINISHED '
                        msg += 'Or KILLED: "{}"'.format(plow_job_id_last)
                        self.logMessage.emit(msg, logging.WARNING)
                        continue
                    layer = scheduler_operations.get_layer_for_job(job, plow_layer_id_last)
                    if not layer:
                        continue
                    msg = 'EAT Render Plow Layer Id: "{}"'.format(plow_layer_id_last)
                    self.logMessage.emit(msg, logging.WARNING)
                    layer.eat_tasks()

        self.updateDetailsPanel.emit(False)

        return  0


    def choose_plow_layer_log_to_open(
            self,
            log_locations=None,
            selection=None,
            show_dialog=True):
        '''
        Open a dialog to let the user pick Plow log file/s pertaining
        to Plow Layer/s of current MSRS view selection.

        Args:
            log_locations (list):
            selection (list): optionally pass in an explicit QModelIndex list
            show_dialog (bool):

        Returns:
            chosen_log_locations (list):
        '''
        if not log_locations:
            log_locations = list()

        selection = self.get_selection_or_item_under_mouse(selection=selection)
        if not selection:
            msg = 'No selected pass for env items to open log files for!'
            self.logMessage.emit(msg, logging.WARNING)
            return 0

        # Only pass for env items has cached Plow ids
        items, _qmodelindices = self.filter_selection(
            selection,
            include_environment_items=False,
            include_pass_for_env_items=True,
            include_group_items=False)
        if not items:
            msg = 'No selected pass for env items to open log files for!'
            self.logMessage.emit(msg, logging.WARNING)
            return 0

        chosen_log_locations = list(log_locations)

        import plow

        model = self.model()
        scheduler_operations = model.get_scheduler_operations()

        # Collect all log files of MSRS selection
        if not chosen_log_locations:
            # msg = 'Gathering Log Files From MSRS Selection'
            # self.logMessage.emit(msg, logging.INFO)
            _log_locations = set()
            update_count = 0
            for i, qmodelindex in enumerate(selection):
                if not qmodelindex.isValid():
                    continue
                item = qmodelindex.internalPointer()
                dispatcher_plow_job_id = item.get_dispatcher_plow_job_id()
                plow_job_id_last = item.get_plow_job_id_last()
                plow_layer_id_last = item.get_plow_layer_id_last()
                if dispatcher_plow_job_id:
                    job = scheduler_operations.get_job(dispatcher_plow_job_id)
                    if not job:
                        continue
                    for layer in job.get_layers():
                        for task in layer.get_tasks():
                            log_location = task.get_log_file(retryNum=-1) # latest
                            if log_location and os.path.isfile(log_location):
                                _log_locations.add(log_location)
                elif plow_job_id_last and plow_layer_id_last:
                    job = scheduler_operations.get_job(plow_job_id_last)
                    if not job:
                        continue
                    layer = scheduler_operations.get_layer_for_job(job, plow_layer_id_last)
                    if not layer:
                        continue
                    for task in layer.get_tasks():
                        log_location = task.get_log_file(retryNum=-1) # latest
                        if log_location and os.path.isfile(log_location):
                            _log_locations.add(log_location)
            chosen_log_locations = sorted(list(_log_locations))
            # msg = 'Gathered Log Files: "{}"'.format(chosen_log_locations)
            # self.logMessage.emit(msg, logging.INFO)

        if show_dialog:
            from srnd_qt.ui_framework.dialogs import base_popup_dialog
            from srnd_qt.ui_framework.widgets import list_widget_with_add_remove

            msg = 'Select Plow log file/s to open. '
            msg += '<br><i>Note: A window will open for each selected log file location.</i>'
            version = model.get_multi_shot_render_submitter_version()

            dialog = base_popup_dialog.BasePopupDialog(
                tool_name='Choose Plow log file/s',
                version=version,
                do_validate=False,
                window_size=(900, 400),
                description=msg,
                description_by_title=True,
                description_is_dismissible=True,
                debug_mode=self._debug_mode,
                parent=self)
            dialog.build_okay_cancel_buttons()
            layout = dialog.get_content_widget_layout()

            list_widget_add_remove = list_widget_with_add_remove.ListWidgetWithAddRemoveButtons(
                allow_duplicates=False,
                multi_select=True,
                has_visible_add_button=False,
                has_visible_remove_button=False)
            layout.addWidget(list_widget_add_remove)
            list_widget = list_widget_add_remove.get_list_widget()
            list_widget.setSizePolicy(
                QSizePolicy.Expanding,
                QSizePolicy.Expanding)
            list_widget_add_remove.add_items(list_widget, chosen_log_locations)

            from Qt.QtWidgets import QDialog
            if dialog.exec_() != QDialog.Accepted:
                msg = 'User cancelled opening log files!'
                self.logMessage.emit(msg, logging.WARNING)
                return list()
            chosen_log_locations = list_widget_add_remove.get_items(
                list_widget,
                role=Qt.DisplayRole,
                selected_only=True)

        if not chosen_log_locations:
            msg = 'User choose no log files to open!'
            self.logMessage.emit(msg, logging.WARNING)
            return list()

        for log_location in chosen_log_locations:
            if not os.path.isfile(log_location):
                msg = 'Log not on disc: "{}"'.format(log_location)
                self.logMessage.emit(msg, logging.WARNING)
                continue
            utils.open_task_log_file_as_window(
                log_location=log_location,
                show=True,
                parent=self)

        return chosen_log_locations


    ##########################################################################


    def delete_items(self, show_dialog=True):
        '''
        Delete selected environment and group item and optionally popup confirm dialog first.

        Args:
            show_dialog (bool):

        Returns:
            deleted_environments (list):
        '''
        # # Batch all updates into one update for view
        # # NOTE: This would then required reopening all editors
        # model.beginResetModel()

        organized_indices, selection_count = self.get_selected_organized_environment_indices()

        delete_item_ids = set()

        # Filter selection for deletable items
        envs_to_delete, groups_to_delete = 0, 0
        for parent_item_id in organized_indices.keys():
            rows = reversed(sorted(organized_indices[parent_item_id].keys()))
            for row in rows:
                source_qmodelindex = organized_indices[parent_item_id][row]
                item = source_qmodelindex.internalPointer()
                if source_qmodelindex.column() != 0:
                    continue
                if item.is_environment_item():
                    envs_to_delete += 1
                elif item.is_group_item():
                    groups_to_delete += 1

        # Must have deletable items in selection
        if not any([envs_to_delete, groups_to_delete]):
            msg = 'Select environments or groups on the first column to delete'
            title_str = 'No selected environments to delete!'
            self.logMessage.emit(msg, logging.WARNING)
            if show_dialog:
                QMessageBox.warning(None, title_str, msg, QMessageBox.Ok)
            return

        # Optional confim delete operation
        if show_dialog:
            delete_items = list()
            if envs_to_delete:
                delete_items.append('{} environments'.format(envs_to_delete))
            if groups_to_delete:
                delete_items.append('{} groups (& child environments)'.format(groups_to_delete))
            msg = 'Confirm delete ' + ', '.join(delete_items) + ' operation?'
            reply = QMessageBox.warning(
                self,
                msg,
                msg,
                QMessageBox.Ok | QMessageBox.Cancel)
            if reply == QMessageBox.Cancel:
                msg = 'User skipped delete operation!'
                self.logMessage.emit(msg, logging.WARNING)
                return

        model = self.model()

        # Block the selection model selectionChanged signals from possibly
        # updating the details panel via the updateDetailsPanel signal.
        selection_model = self.selectionModel()
        selection_model.blockSignals(True)

        progress_msg = 'Selection count to consider for delete: {}'.format(selection_count)
        self.logMessage.emit(progress_msg, logging.WARNING)

        # Show progress bar
        model.toggleProgressBarVisible.emit(True)
        model.updateLoadingBarFormat.emit(0, progress_msg + ' - %p%')

        # On first pass delete all selected environment item
        i = 0
        items_removed = list()
        for parent_item_id in organized_indices.keys():
            rows = reversed(sorted(organized_indices[parent_item_id].keys()))
            for row in rows:
                source_qmodelindex = organized_indices[parent_item_id][row]
                if not source_qmodelindex.isValid():
                    continue
                if source_qmodelindex.column() != 0:
                    continue
                item = source_qmodelindex.internalPointer()
                if not item.is_environment_item():
                    continue
                row = source_qmodelindex.row()

                percent = int((float(i) / selection_count) * 100)
                msg = 'Performing delete'

                # Update loading bar
                self.logMessage.emit(msg, logging.INFO)
                self.updateLoadingBarFormat.emit(percent, msg + ' - %p%')

                oz_area = item.get_oz_area()
                items_removed.append(oz_area)

                msg = 'Deleting environment: "{}". '.format(oz_area)
                msg += 'Row: "{}"'.format(row)
                self.logMessage.emit(msg, logging.WARNING)
                # Update the total renderable count for every column where this
                # environment item sibling items render pass for items was
                # contributing to renderable count.
                for pass_for_env_item in item.get_pass_for_env_items():
                    if not pass_for_env_item.get_active():
                        continue
                    render_item = pass_for_env_item.get_source_render_item()
                    render_item._renderable_count_for_render_node -= 1
                    if render_item._renderable_count_for_render_node < 0:
                        render_item._renderable_count_for_render_node = 0

                delete_item_ids.add(id(item))

                parent_item = item.parent()
                model.beginRemoveRows(source_qmodelindex.parent(), row, row)
                if parent_item:
                    parent_item.remove_child(row)
                model.endRemoveRows()

                i += 1

        # On second pass delete all selected group item
        organized_indices, selection_count = self.get_selected_organized_environment_indices()
        for parent_item_id in organized_indices.keys():
            rows = reversed(sorted(organized_indices[parent_item_id].keys()))
            for row in rows:
                source_qmodelindex = organized_indices[parent_item_id][row]
                if not source_qmodelindex.isValid():
                    continue
                if source_qmodelindex.column() != 0:
                    continue
                item = source_qmodelindex.internalPointer()
                if not item.is_group_item():
                    continue
                row = source_qmodelindex.row()

                # Remove Groups children first
                _row_count = item.child_count()
                if _row_count:
                    model.beginRemoveRows(source_qmodelindex, 0, _row_count)
                    for _row in range(_row_count):
                        _child = item.children()[0]
                        msg = ' - Deleting environment: "{}". '.format(_child.get_oz_area())
                        self.logMessage.emit(msg, logging.WARNING)
                        item.remove_child(0)
                    model.endRemoveRows()

                group_name = item.get_group_name()
                msg = 'Deleting group: "{}". '.format(group_name)
                msg += 'Row: "{}"'.format(row)
                self.logMessage.emit(msg, logging.WARNING)

                delete_item_ids.add(id(item))
                items_removed.append(group_name)

                # Now remove this item at this level
                model.beginRemoveRows(source_qmodelindex.parent(), row, row)
                item.parent().remove_child(row)
                model.endRemoveRows()

        if delete_item_ids:
            # Some environments were deleted so update cached indices
            model._update_environments_indices()
            # Update column headers
            all_columns = set(range(0, model.columnCount(QModelIndex())))
            self._update_header_columns(all_columns)

        # Emit signal so splash screen might become visible
        if items_removed:
            model.itemsRemoved.emit(items_removed)

        # Allow selection model signals again.
        selection_model.blockSignals(False)

        model.toggleProgressBarVisible.emit(False)

        if delete_item_ids:
            self.updateDetailsPanel.emit(False)
            model.updateOverviewRequested.emit()


    def group_selected_items(
            self,
            group=True,
            group_name='myGroupName',
            show_dialog=True):
        '''
        Group or ungroup the selected items related to QModelIndex selection.

        Args:
            group (bool): set to False to ungroup
            group_name (str):
            show_dialog (bool):

        Returns:
            success_count (int):
        '''
        organized_indices, selection_count = self.get_selected_organized_environment_indices()

        model = self.model()

        # Optionally show dialog so user can pick group name
        if show_dialog and group:
            # Count number of EnvironmentItem to group)
            rows_to_modify = 0
            for parent_item_id in organized_indices.keys():
                rows = reversed(sorted(organized_indices[parent_item_id].keys()))
                for row in rows:
                    source_qmodelindex = organized_indices[parent_item_id][row]
                    if not source_qmodelindex.isValid():
                        continue
                    if source_qmodelindex.column() != 0:
                        continue
                    item = source_qmodelindex.internalPointer()
                    if item and item.is_environment_item():
                        rows_to_modify += 1

            # Show popup dialog so user can confirm operation
            msg = '<i>Group {} selected environments to new '.format(rows_to_modify)
            msg += 'group name</i>'

            from srnd_qt.ui_framework.dialogs import input_dialog
            dialog = input_dialog.GetInputDialog(
                title_str='Choose {}group{} name'.format(fs, fe),
                description=msg,
                description_by_title=False,
                input_type_required=str(),
                value='myGroupName',
                parent=self)
            dialog.setWindowTitle('Choose group name')
            dialog.setMinimumHeight(150)
            dialog.resize(575, 175)

            options_box_header = dialog.get_header_widget()
            style_sheet = 'QGroupBox {background: rgb(70, 70, 70);'
            style_sheet += 'border:rgb(70, 70, 70)}'
            options_box_header.setStyleSheet(style_sheet)

            value_widget = dialog.get_value_widget()
            from srnd_qt.ui_framework.validators import element_name_validator
            validator = element_name_validator.ElementNameValidator(
                allow_underscores=True,
                allow_spaces=True)
            value_widget.setValidator(validator)
            result = dialog.exec_()

            # Get group name dialog result
            new_group_name = dialog.get_result()
            if result == QDialog.Rejected or not new_group_name:
                msg = 'User skipped group environment/s operation!'
                self.logMessage.emit(msg, logging.WARNING)
                return False
            group_name = str(dialog.get_result() or group_name or str())

        self.clearSelection()

        # Block the selection model selectionChanged signals from possibly
        # updating the details panel via the updateDetailsPanel signal.
        selection_model = self.selectionModel()
        selection_model.blockSignals(True)

        progress_msg = 'Selection count to consider: {}'.format(selection_count)
        self.logMessage.emit(progress_msg, logging.WARNING)

        # Show progress bar
        model.toggleProgressBarVisible.emit(True)
        model.updateLoadingBarFormat.emit(0, progress_msg + ' - %p%')

        if group:
            group_item, qmodelindex_group = model.add_group(group_name=group_name)
            model.expandRequested.emit(qmodelindex_group)
        else:
            root_item = model.get_root_node()
            row_count_root_before = root_item.child_count()

        i = 0
        environments_ids_modified = set()
        for parent_item_id in organized_indices.keys():
            rows = reversed(sorted(organized_indices[parent_item_id].keys()))
            for row in rows:

                percent = int((float(i) / selection_count) * 100)
                msg = 'Performing group or ungroup'

                # Update loading bar
                self.logMessage.emit(msg, logging.INFO)
                self.updateLoadingBarFormat.emit(percent, msg + ' - %p%')

                source_qmodelindex = organized_indices[parent_item_id][row]
                if not source_qmodelindex.isValid():
                    continue
                if source_qmodelindex.column() != 0:
                    continue
                item = source_qmodelindex.internalPointer()
                if not item:
                    continue

                if group and item.is_environment_item():
                    oz_area = item.get_oz_area()
                    oz_area_id = id(item)

                    msg = 'Parenting environment: "{}"'.format(oz_area)
                    msg += 'To group: "{}". '.format(group_name)
                    msg += 'Moving row: "{}"'.format(row)
                    self.logMessage.emit(msg, logging.WARNING)

                    # Remove the row
                    model.beginRemoveRows(source_qmodelindex.parent(), row, row)
                    item.parent().remove_child(row)
                    model.endRemoveRows()

                    # Insert the row under group
                    model.beginInsertRows(qmodelindex_group, 0, 0)
                    group_item.insert_child(0, item)
                    model.endInsertRows()

                    # # Move the rows at once (is currently problematic)....
                    # model.beginMoveRows(
                    #     source_qmodelindex.parent(),
                    #     row,
                    #     row,
                    #     qmodelindex_group,
                    #     0)
                    # item.parent().remove_child(row)
                    # group_item.insert_child(0, item)
                    # model.endMoveRows()

                    environments_ids_modified.add(oz_area_id)

                elif not group and item.is_environment_item() and item.parent().is_group_item():
                    oz_area = item.get_oz_area()
                    oz_area_id = id(item)
                    msg = 'Ungroup environment: "{}"'.format(oz_area)
                    self.logMessage.emit(msg, logging.WARNING)

                    model.beginMoveRows(
                        source_qmodelindex.parent(),
                        row,
                        row,
                        QModelIndex(),
                        row_count_root_before)
                    item.parent().remove_child(row)
                    root_item.insert_child(row_count_root_before, item)
                    model.endMoveRows()

                    environments_ids_modified.add(oz_area_id)

                elif not group and item.is_group_item():
                    group_name = item.get_group_name()
                    msg = 'Ungroup contents of group: "{}"'.format(group_name)
                    self.logMessage.emit(msg, logging.WARNING)

                    _environment_items = item.children()

                    model.beginMoveRows(
                        source_qmodelindex,
                        0,
                        item.child_count(),
                        QModelIndex(),
                        row_count_root_before)
                    item.remove_children()
                    for _environment_item in _environment_items:
                        oz_area = _environment_item.get_oz_area()
                        _oz_area_id = id(_environment_item)
                        msg = 'Ungroup environment: "{}"'.format(oz_area)
                        self.logMessage.emit(msg, logging.WARNING)
                        environments_ids_modified.add(_oz_area_id)
                        root_item.add_child(_environment_item)
                    model.endMoveRows()

                i += 1

        if group:
            for row in range(model.rowCount(qmodelindex_group)):
                qmodelindex_new = model.index(row, 0, qmodelindex_group)
                model.openPersisentEditorForRowRequested.emit(qmodelindex_new)
        else:
            row_count = model.rowCount(QModelIndex())
            for row in range(row_count_root_before, row_count, 1):
                qmodelindex_new = model.index(row, 0, QModelIndex())
                model.openPersisentEditorForRowRequested.emit(qmodelindex_new)

        # Allow selection model signals again.
        selection_model.blockSignals(False)

        model.toggleProgressBarVisible.emit(False)

        if environments_ids_modified:
            # Some environments might have changed order during group so update cached indices
            model._update_environments_indices()
            # Emit the updateDetailsPanel so details panel now updates
            self.updateDetailsPanel.emit(False)
            # Update overview of Multi Shot targets
            model.updateOverviewRequested.emit()

        # NOTE: Make sure this tree view has focus for next key press shortcut
        self.setFocus(Qt.ShortcutFocusReason)

        return len(environments_ids_modified)


    def change_areas_selected_items(
            self,
            area=None,
            environment_item_indices=None,
            show_dialog=True):
        '''
        Popup a dialog to allow the user to pick a new Weta area for the selected environment items.

        Args:
            area (str):
            environment_item_indices (list):
            show_dialog (bool):

        Returns:
            success_count (int):
        '''
        area = area or os.getenv('OZ_CONTEXT')

        selection = self.get_selection_or_item_under_mouse(
            selection=environment_item_indices)

        environment_items, _qmodelindices = self.filter_selection(
            selection,
            include_environment_items=True,
            include_pass_for_env_items=False,
            include_group_items=False)

        if not environment_items:
            msg = 'No environment items in selection to change areas for!'
            self.logMessage.emit(msg, logging.WARNING)
            return 0

        if show_dialog:
            area = environment_items[-1].get_oz_area() or area
            from srnd_multi_shot_render_submitter.dialogs import change_area_dialog
            dialog = change_area_dialog.ChangeAreaDialog(area=area)
            result = dialog.exec_()
            if result == QDialog.Rejected or not dialog.get_area():
                msg = 'User cancelled or provided no area value to change environment!'
                self.logMessage.emit(msg, logging.WARNING)
                return 0
            area = dialog.get_area()

        model = self.model()

        environments_ids_modified = 0
        for qmodelindex in selection:
            if not qmodelindex.isValid:
                continue
            item = qmodelindex.internalPointer()
            if not item.is_environment_item():
                continue
            identifier = item.get_identifier()
            current_area = item.get_oz_area()
            if current_area == area:
                msg = 'No change to environment required: "{}"'.format(identifier)
                self.logMessage.emit(msg, logging.WARNING)
                continue
            item.set_area(area)

            model.dataChanged.emit(qmodelindex, qmodelindex)

            environments_ids_modified += 1

        if environments_ids_modified:
            # Emit the updateDetailsPanel so details panel now updates
            self.updateDetailsPanel.emit(False)
            # Update overview of Multi Shot targets
            model.updateOverviewRequested.emit()

        return environments_ids_modified


    def split_frames_job_selected_environments(self, split=True):
        '''
        Apply split frame jobs to selected Environment items.
        NOTE: This also removes any per pass frame overrides along all other columns.

        Args:
            split (bool):

        Returns:
            success_count (int):
        '''
        model = self.model()

        environment_items = self.get_selected_environment_items()
        if not environment_items:
            return 0

        column_count = model.columnCount(QModelIndex())
        selection =  self.selectedIndexes()

        success_count = 0
        for qmodelindex in selection:
            if not qmodelindex.isValid:
                continue
            item = qmodelindex.internalPointer()
            if not item.is_environment_item():
                continue
            is_split = item.get_split_frame_ranges()
            if split == is_split:
                continue
            item.set_split_frame_ranges(split)
            model.dataChanged.emit(qmodelindex, qmodelindex)
            success_count += 1

            # Remove any frame overrides on pass for env cells
            for c in range(1, column_count):
                qmodelindex_cell = qmodelindex.sibling(qmodelindex.row(), c)
                if not qmodelindex_cell.isValid():
                    continue
                pass_env_item = qmodelindex_cell.internalPointer()
                pass_env_item.clear_frame_overrides()
                model.dataChanged.emit(qmodelindex_cell, qmodelindex_cell)

        msg = 'Setting split frames jobs to: {}. '.format(split)
        msg += 'For {} selected environment item/s'.format(len(environment_items))
        self.logMessage.emit(msg, logging.WARNING)

        if success_count:
            # Emit the updateDetailsPanel so details panel now updates
            self.updateDetailsPanel.emit(False)

        return 0


    def ungroup_selected_items(self):
        '''
        Ungroup the selected items related to QModelIndex selection.

        Returns:
            success_count (int):
        '''
        return self.group_selected_items(group=False)


    def create_item_selection_set(self, name=None, show_dialog=True):
        '''
        Get all selected environment and render pass for env items, and store
        a named selection set, containing UUID strings.

        Args:
            show_dialog (bool): whether to open dialog to let user pick selection set name

        Returns:
            name, identity_ids (tuple): the new selection set name and list of UUIDs that
                are in selection set
        '''
        if not name:
            name = str()

        identity_ids = self.get_selected_uuids()
        if not identity_ids:
            msg = 'No selected items with UUIDs to make selection set for!'
            self.logMessage.emit(msg, logging.WARNING)
            if show_dialog:
                reply = QMessageBox.warning(
                    self,
                    'No Selected Items With UUIDs!',
                    msg,
                    QMessageBox.Ok)
            return None, list()

        if show_dialog:
            msg = '<i>Choose name to represent new selection set name</i>'

            from srnd_qt.ui_framework.dialogs import input_dialog
            dialog = input_dialog.GetInputDialog(
                title_str='Choose selection {}set name{}'.format(fs, fe),
                description=msg,
                description_by_title=False,
                input_type_required=str(),
                value=name,
                parent=self)
            dialog.setWindowTitle('Choose selection set name')
            dialog.setMinimumHeight(150)
            dialog.resize(575, 175)

            options_box_header = dialog.get_header_widget()
            style_sheet = 'QGroupBox {background: rgb(70, 70, 70);'
            style_sheet += 'border:rgb(70, 70, 70)}'
            options_box_header.setStyleSheet(style_sheet)

            value_widget = dialog.get_value_widget()
            validator = QRegExpValidator()
            validator.setRegExp(QRegExp('[A-Za-z0-9_ ]+'))
            value_widget.setValidator(validator)
            result = dialog.exec_()
            if result == QDialog.Rejected or not value_widget.text():
                msg = 'User cancelled or provided no value for selection set name!'
                self.logMessage.emit(msg, logging.WARNING)
                return None, list()
            name = str(value_widget.text() or str())

        if not name or not isinstance(name, basestring):
            msg = 'Must provide item selection set name!'
            self.logMessage.emit(msg, logging.WARNING)
            return None, list()

        if show_dialog and name in self._item_selection_sets.keys():
            msg = 'Selection set name not unique!'
            self.logMessage.emit(msg, logging.WARNING)
            reply = QMessageBox.warning(
                self,
                msg,
                msg,
                QMessageBox.Ok)
            return None, list()

        self._item_selection_sets[name] = list(identity_ids)

        msg = 'Successfully created selection set name: "{}". '.format(name)
        msg += 'Containing UUIDs: "{}"'.format(identity_ids)
        self.logMessage.emit(msg, logging.INFO)

        return name, self._item_selection_sets[name]


    def select_named_selection_set(self, selection_set_name):
        '''
        Select all items in the named selection set (if available), via a list of UUIDS.

        Args:
            selection_set_name (str):

        Returns:
            identity_ids (list): list of UUIDs that were selected
        '''
        if not selection_set_name:
            msg = 'No selection set provided to select!'
            self.logMessage.emit(msg, logging.WARNING)
            return list()

        identity_ids = self._item_selection_sets.get(str(selection_set_name))
        if not identity_ids:
            msg = 'Selection set by name not found or empty!'
            self.logMessage.emit(msg, logging.WARNING)
            return list()

        self.select_by_identity_uids(identity_ids)

        return identity_ids


    def select_by_identity_uids(
            self,
            identity_ids=None,
            identifiers=None,
            scroll_to=False):
        '''
        Given a list if UUIDs and / or identifiers select the Multi Shot items in this view.

        Args:
            identity_ids (list): list of UUIDs to select in Multi Shot view
            identifiers (list): list of identifiers to select in Multi Shot view
            scroll_to (True): whether to scroll the view to the first selected item,

        Returns:
            selected_count (int):
        '''
        if not identity_ids:
            identity_ids = list()
        if not identifiers:
            identifiers = list()

        if not any([identity_ids, identifiers]):
            msg = 'No UUIDs or identifiers to select by!'
            self.logMessage.emit(msg, logging.WARNING)
            return 0

        msg = 'Selecting By. '
        if identity_ids:
            msg += 'UUIDS: "{}". '.format(identity_ids)
        if identifiers:
            msg += 'Identifiers: "{}"'.format(identifiers)
        self.logMessage.emit(msg, logging.INFO)

        model = self.model()

        selection_model = self.selectionModel()
        self.clearSelection()

        selected_count = 0
        scroll_qmodelindex = None

        for qmodelindex in model.get_environment_items_indices():
            if not qmodelindex.isValid():
                continue
            item = qmodelindex.internalPointer()
            do_select = False
            # Check for matching uuid for environment
            if not do_select and identity_ids:
                do_select = item.get_identity_id() in identity_ids
            # Otherwise check for matching environment name
            if not do_select and identifiers:
                # Nice name might include job name or index as part of environment string
                do_select = item.get_environment_name_nice() in identifiers
                # Otherwise fallback for simple area match
                if not do_select:
                    do_select = item.get_oz_area() in identifiers   
            if do_select:
                selection_model.select(qmodelindex, QItemSelectionModel.Select)
                selected_count += 1
                if scroll_to and not scroll_qmodelindex:
                    scroll_qmodelindex = qmodelindex

        for qmodelindex in model.get_pass_for_env_items_indices():
            if not qmodelindex.isValid():
                continue
            item = qmodelindex.internalPointer()
            do_select = False
            # Check for matching uuid for pass
            if not do_select and identity_ids:
                do_select = item.get_identity_id() in identity_ids
            # Otherwise check for matching pass name
            if not do_select and identifiers:
                # Nice env name is included as full item path to pass.
                # Which includes job name or index of environment.
                do_select = item.get_identifier(nice_env_name=True) in identifiers
            if do_select:
                selection_model.select(qmodelindex, QItemSelectionModel.Select)
                selected_count += 1
                if scroll_to and not scroll_qmodelindex:
                    scroll_qmodelindex = qmodelindex
        
        if scroll_qmodelindex and scroll_qmodelindex.isValid():
            self.scrollTo(scroll_qmodelindex, hint=self.PositionAtCenter)

        self.updateDetailsPanel.emit(False)

        return selected_count


    def delete_selection_set_by_name(self, selection_set_name):
        '''
        Delete a named selection set (if available).

        Args:
            selection_set_name (str):

        Returns:
            success (bool): if named selection set was successfully deleted
        '''
        if not selection_set_name:
            msg = 'No selection set provided to select!'
            self.logMessage.emit(msg, logging.WARNING)
            return False

        identity_ids = self._item_selection_sets.get(str(selection_set_name))
        if not identity_ids:
            msg = 'Selection set by name not found or empty!'
            self.logMessage.emit(msg, logging.WARNING)
            return False

        msg = 'Deleting selection set name: "{}"'.format(selection_set_name)
        self.logMessage.emit(msg, logging.INFO)

        self._item_selection_sets.pop(selection_set_name)

        return True


    def update_selection_set_by_name(self, selection_set_name):
        '''
        Update a named selection set in place.

        Args:
            selection_set_name (str):

        Returns:
            success (bool): if named selection set was successfully update
        '''   
        name, uuids = self.create_item_selection_set(
            selection_set_name, 
            show_dialog=False)
        return bool(name)


    def open_uuids_or_identifiers_select_dialog(self):
        '''
        Open dialog to collect a list of UUIDs or identifiers.
        When Okay button is pushed the chosen UUIDs and identifiers will
        be seeked in model, and QModelIndices will be selected in selection model.
        '''
        from srnd_multi_shot_render_submitter.dialogs import select_by_dialog
        dialog = select_by_dialog.SelectByDialog(parent=self)
        dialog.selectByRequested.connect(self.select_by_identity_uids)
        dialog.show()


    ##########################################################################


    def create_pass_visibility_set(self, name=None, show_dialog=True):
        '''
        Create pass visibility set by name, containing the currently
        visible pass names.

        Args:
            show_dialog (bool): whether to open dialog to let user pick name

        Returns:
            name, render_nodes (tuple): the new selection set name and list of passes that
                are in selection set
        '''
        if not name:
            name = str()

        model = self.model()

        # Collect mapping of item full names, mapped to visibility states
        render_nodes_to_visible_map = collections.OrderedDict()
        for c, render_item in enumerate(model.get_render_items()):
            visible = not self.isColumnHidden(c + 1)
            item_full_name = render_item.get_item_full_name()
            render_nodes_to_visible_map[item_full_name] = visible

        if not render_nodes_to_visible_map:
            msg = 'No columns to make pass visibility set for!'
            self.logMessage.emit(msg, logging.WARNING)
            if show_dialog:
                reply = QMessageBox.warning(
                    self,
                    'No pass columns!',
                    msg,
                    QMessageBox.Ok)
            return None, list()

        if show_dialog:
            msg = '<i>Choose name to represent new pass visibility set</i>'

            from srnd_qt.ui_framework.dialogs import input_dialog
            dialog = input_dialog.GetInputDialog(
                title_str='Choose Pass Visibility {}Set Name{}'.format(fs, fe),
                description=msg,
                description_by_title=False,
                input_type_required=str(),
                value=name,
                parent=self)
            dialog.setWindowTitle('Choose Pass Visibility Set Name')
            dialog.setMinimumHeight(150)
            dialog.resize(575, 175)

            options_box_header = dialog.get_header_widget()
            style_sheet = 'QGroupBox {background: rgb(70, 70, 70);'
            style_sheet += 'border:rgb(70, 70, 70)}'
            options_box_header.setStyleSheet(style_sheet)

            value_widget = dialog.get_value_widget()
            validator = QRegExpValidator()
            validator.setRegExp(QRegExp('[A-Za-z0-9_ ]+'))
            value_widget.setValidator(validator)
            result = dialog.exec_()
            if result == QDialog.Rejected or not value_widget.text():
                msg = 'User cancelled or provided no value for render node visibility set name!'
                self.logMessage.emit(msg, logging.WARNING)
                return None, list()
            name = str(value_widget.text() or str())

        # Must have selection set name at this point
        if not name or not isinstance(name, basestring):
            msg = 'Must provide render node visibility set name!'
            self.logMessage.emit(msg, logging.WARNING)
            return None, list()

        if show_dialog and name in self._pass_visibility_sets.keys():
            msg = 'Pass visibility set name not unique!'
            self.logMessage.emit(msg, logging.WARNING)
            reply = QMessageBox.warning(
                self,
                msg,
                msg,
                QMessageBox.Ok)
            return None, list()

        self._pass_visibility_sets[name] = render_nodes_to_visible_map

        msg = 'Successfully created pass visibility set name: "{}". '.format(name)
        msg += 'Containing iender items: "{}"'.format(render_nodes_to_visible_map.keys())
        self.logMessage.emit(msg, logging.INFO)

        return name, self._pass_visibility_sets[name]


    def apply_pass_visibility_set(self, name):
        '''
        Toggle columns visible by pass name visiblity set.

        Args:
            name (str):

        Returns:
            pass_names_visible, pass_names_hidden (tuple):
        '''
        if not name:
            msg = 'No Render Node Visibility Set Provided To Select!'
            self.logMessage.emit(msg, logging.WARNING)
            return list(), list()

        if self._overlay_widget:
            self._overlay_widget.set_active(False)

        model = self.model()

        render_nodes_to_visible_map = self._pass_visibility_sets.get(str(name))
        if not render_nodes_to_visible_map:
            msg = 'Render Node Visibility Set By Name Not Found Or Empty!'
            self.logMessage.emit(msg, logging.WARNING)
            return list(), list()

        pass_names_visible = list()
        pass_names_hidden = list()
        for c, render_item in enumerate(model.get_render_items()):
            item_full_name = render_item.get_item_full_name()
            if item_full_name not in render_nodes_to_visible_map.keys():
                continue
            visible = bool(render_nodes_to_visible_map.get(item_full_name, True))
            self.setColumnHidden(c + 1, not visible)
            if visible:
                pass_names_visible.append(item_full_name)
            else:
                pass_names_hidden.append(item_full_name)

        if self._overlay_widget:
            self._overlay_widget.set_active(True)
            self._overlay_widget.update_overlays()

        msg = 'Pass columns made visibile by apply set: "{}"'.format(pass_names_visible)
        self.logMessage.emit(msg, logging.WARNING)

        msg = 'Pass columns made hidden by apply set: "{}"'.format(pass_names_hidden)
        self.logMessage.emit(msg, logging.WARNING)

        return pass_names_visible, pass_names_hidden


    def delete_pass_visibility_set_by_name(self, name):
        '''
        Delete pass visibility set by name.

        Args:
            name (str):

        Returns:
            success (bool): if pass visibility set was successfully deleted
        '''
        if not name:
            msg = 'No pass visibility set provided to select!'
            self.logMessage.emit(msg, logging.WARNING)
            return False

        render_nodes_to_visible_map = self._pass_visibility_sets.get(str(name))
        if not render_nodes_to_visible_map:
            msg = 'Pass visibility set by name not found or empty!'
            self.logMessage.emit(msg, logging.WARNING)
            return False

        msg = 'Deleting pass visibility set name: "{}"'.format(name)
        self.logMessage.emit(msg, logging.INFO)

        self._pass_visibility_sets.pop(name)

        return True


    def update_pass_visibility_set_by_name(self, name):
        '''
        Update pass visibility set by name in place.

        Args:
            name (str):

        Returns:
            success (bool): if pass visibility set was successfully update
        '''        
        name, render_nodes = self.create_pass_visibility_set(
            name, 
            show_dialog=False)
        return bool(name)


    ##########################################################################


    def get_column_states(self):
        '''
        Formulate a mapping of column number to active state list.

        Returns:
            columns_state (list):
        '''
        model = self.model()
        columns_state = dict()
        for qmodelindex in model.get_environment_items_indices():
            if not qmodelindex.isValid():
                continue
            env_item = qmodelindex.internalPointer()
            for c, pass_for_env in enumerate(env_item.get_pass_for_env_items()):
                column = c + 1
                active = pass_for_env.get_active()
                if column not in columns_state:
                    columns_state[column] = list()
                columns_state[column].append(active)
        return columns_state


    def toggle_columns_by_state(
            self,
            hide_inactive=False,
            show_active=False,
            hide_selected=False):
        '''
        Check the active (queued and enabled) state of all columns,
        and hide columns that have no active items.

        Args:
            hide_inactive (bool):
            show_active (bool):
            hide_selected (bool):
        '''
        if self._overlay_widget:
            self._overlay_widget.set_active(False)

        selected_columns = set()
        if hide_selected:
            for qmodelindex in self.selectedIndexes():
                if not qmodelindex.isValid():
                    continue
                selected_columns.add(qmodelindex.column())

        # Formulate a mapping of column number to active state list.
        columns_state = self.get_column_states()

        for c in columns_state:
            hide = None
            # Check if any one row of column is active
            visible_current = any(columns_state[c])
            # Show columns that have at least one active row
            if show_active and visible_current:
                hide = False
            # Hide columns that have no active rows
            if hide_inactive and not visible_current:
                hide = True
            # Hide selected columns and not already hidden
            if hide_selected and selected_columns and c in selected_columns:
                hide = True
            if isinstance(hide, bool):
                self.setColumnHidden(c, hide)

        if self._overlay_widget:
            self._overlay_widget.set_active(True)
            self._overlay_widget.update_overlays()


    def set_all_columns_visible(self, show=True, skip_columns=None):
        '''
        Reimplemented method.
        '''
        if not skip_columns:
            skip_columns = list()
        if self._overlay_widget:
            self._overlay_widget.set_active(False)
        base_tree_view.BaseTreeView.set_all_columns_visible(
            self,
            show=show,
            skip_columns=skip_columns)
        if self._overlay_widget:
            self._overlay_widget.set_active(True)
            self._overlay_widget.update_overlays()


    def derive_highest_version_and_apply(self):
        '''
        Traverse over all selected pass for environment or environment cells,
        and get the highest version, then apply to all.
        Note: If seleted at Environment level, then the highest version is set here.

        Returns:
            success, version_override (tuple):
        '''
        # Request the details panel to get all the highest versions and cache them
        self.updateDetailsPanel.emit(True)

        selection =  self.selectedIndexes()
        selection_count = len(selection)
        msg = 'Deriving Highest Version For Selection Count: {}'.format(selection_count)
        self.logMessage.emit(msg, logging.INFO)

        # Gather highest version for Environment or pass
        # NOTE: Dont cache versions on pass for env items.
        # TODO: Add method elsewhere to do this.
        versions = set()
        environment_ids = set()
        for qmodelindex in selection:
            if not qmodelindex.isValid():
                continue
            item = qmodelindex.internalPointer()
            if item.is_pass_for_env_item():
                version_number = item.resolve_version(
                    version_system=constants.CG_VERSION_SYSTEM_PASS_NEXT,
                    cache_values=False,
                    collapse_version_overrides=False)
                if version_number:
                    versions.add(version_number)
            if item.is_environment_item():
                for pass_env_item in item.get_pass_for_env_items():
                    # Resolve the version again
                    version_number = pass_env_item.resolve_version(
                        version_system=constants.CG_VERSION_SYSTEM_PASS_NEXT,
                        cache_values=False,
                        collapse_version_overrides=False)
                    if version_number:
                        versions.add(version_number)
                environment_ids.add(id(item))
        if not versions:
            msg = 'Derived No Highest Version To Apply!'
            self.logMessage.emit(msg, logging.WARNING)
            return False, 1

        version_override = max(versions)
        msg = 'Derived Highest Version To Apply: {}'.format(version_override)
        self.logMessage.emit(msg, logging.INFO)

        model = self.model()
        for qmodelindex in selection:
            if not qmodelindex.isValid():
                continue
            item = qmodelindex.internalPointer()
            is_environment_item = item.is_environment_item()
            is_pass_for_env_item = item.is_pass_for_env_item()

            if not any([is_environment_item, is_pass_for_env_item]):
                continue

            # If the environment was also selected, only apply the override at this level
            do_set_version = True
            if item.is_pass_for_env_item() and environment_ids:
                environment_item = item.parent()
                do_set_version = id(environment_item) in environment_ids

            if do_set_version:
                was_version_override = item.get_version_override()
                item.set_version_override(version_override)
                version_modified = was_version_override != version_override
                if version_modified:
                    model.dataChanged.emit(
                        qmodelindex,
                        qmodelindex)

        return True, version_override


    ##########################################################################
    # Other popup dialogs


    def choose_custom_frame_range_dialog(self, selected_indices):
        '''
        Open a dialog to pick a custom frame range.

        Args:
            selected_indices (list): list of QModelIndices to set frame range for

        Returns:
            accepted, frame_range (tuple):
        '''
        app = QApplication.instance()

        msg_preview = str()

        initial_value = '1-10'

        widths = list()
        for i, qmodelindex in enumerate(selected_indices):
            item = qmodelindex.internalPointer()
            if item.is_group_item():
                continue
            if not item.get_active():
                continue
            identifier = item.get_identifier()
            is_pass_for_env_item = item.is_pass_for_env_item()
            if is_pass_for_env_item:
                env_item = item.get_environment_item()
            else:
                env_item = item
            production_range_source = env_item.get_production_range_source()
            cut_range = env_item.get_cut_range()
            delivery_range = env_item.get_delivery_range()
            frame_range = env_item.get_frame_range()
            if is_pass_for_env_item:
                initial_value = item.get_frame_range_override() or item.get_resolved_frames_queued() or cut_range or '1'
            else:
                initial_value = item.get_frame_range_override() or cut_range or '1'

            msg_item = str()
            msg_item += '<b>{}</b>'.format(identifier)

            msg_item += '<ul>'

            msg_item += '<li>'
            label_active = str()
            if 'Cut' in production_range_source:
                label_active = ' (active)'
            msg_item += 'Cut Range{}: <b>"{}"</b>'.format(label_active, cut_range)
            msg_item += '</li>'

            msg_item += '<li>'
            label_active = str()
            if 'Delivery' in production_range_source:
                label_active = ' (active)'
            msg_item += 'Delivery{}: <b>"{}"</b>'.format(label_active, delivery_range)
            msg_item += '</li>'

            msg_item += '<li>'
            label_active = str()
            if 'FrameRange' in production_range_source:
                label_active = ' (active)'
            msg_item += 'Frame Range{}: <b>"{}"</b>'.format(label_active, frame_range)
            msg_item += '</li>'

            msg_item += '</ul>'

            widths.append(QFontMetrics(app.font()).width(identifier))

            msg_preview += msg_item

        title_str = 'Set {}custom frames{} for {} selected items'.format(fs, fe, len(selected_indices))

        msg_more_details = '<i>Entering values outside each respective '
        msg_more_details += 'shot frame range is possible.</i>'

        from srnd_qt.ui_framework.dialogs import input_dialog
        dialog = input_dialog.GetInputDialog(
            title_str=title_str,
            description=msg_more_details,
            description_by_title=False,
            message=msg_preview,
            input_type_required=str(),
            value=initial_value,
            window_size=None,
            parent=self)
        
        window_title = 'Set custom frames for {} selected items'.format(len(selected_indices))
        dialog.setWindowTitle(window_title)

        options_box_header = dialog.get_header_widget()
        style_sheet = 'QGroupBox {background: rgb(70, 70, 70);'
        style_sheet += 'border:rgb(70, 70, 70)}'
        options_box_header.setStyleSheet(style_sheet)

        value_widget = dialog.get_value_widget()
        from srnd_qt.ui_framework.validators import frames_validator
        validator = frames_validator.FramesValidator()
        value_widget.setValidator(validator)
        dialog.adjustSize()

        qsize = dialog.size()
        height = qsize.height() + 40
        if widths and max(widths):
            width = max(widths) + 225
        else:
            width = qsize.width() + 225
        if width < 550:
            width = 550
        if height < 160:
            height = 160
        dialog.resize(width, height)

        result = dialog.exec_()
        if result == QDialog.Rejected:
            return False, None

        result = dialog.get_result()
        custom_frame_range = str(result)

        # Try to parse custom frame range
        try:
            custom_frame_range = str(fileseq.FrameSet(custom_frame_range))
        except fileseq.ParseException:
            msg = 'Failed to parse custom frames: "{}"'.format(custom_frame_range)
            msg += 'Full Exception: "{}".'.format(traceback.format_exc())
            self.logMessage.emit(msg, logging.WARNING)
            return False, None

        return True, custom_frame_range


    ##########################################################################
    # Temporary view filtering


    def search_view_by_filters(
            self, 
            search_filters=None, 
            invert=False):
        '''
        Temporarily hide rows and columns by checking search filters
        against data objects values of interest.
        Note: Search filters is a mapping where the keys are the search terms
        and can be literal strings, or regular expressions (Perl / Python style).
        Each key contains another mapping of search details, which act is modifers of search,
        such as whether search filter is "active".
        Note: This is a temporary search filter only, so not filtering by a proxy model any further here.
        Note: Hidden indices should not be filtered out of the model by this search.

        Args:
            search_filters (dict):
            invert (bool): optionally filp the results of search filters to reveal other items

        Returns:
            count (int): number of rows or columns toggled visible state
        '''
        model = self.model()
        if not model:
            return 0

        if self._overlay_widget:
            if self._in_wait_on_interactive_mode:
                self.exit_wait_on_interactive()
            self._overlay_widget.set_active(False)

        # Show everything first
        self._show_all_rows_and_columns()

        # msg = 'Apply Search Filters Requested: "{}"'.format(search_filters)
        # self.logMessage.emit(msg, logging.INFO)

        column_count = model.columnCount(QModelIndex())

        FILTER_MODIFIERS = (
            'env:', 'area:', 'environment:', 'shot:', 'job:', # for environment items
            'pass:', 'frame:', 'frames:', 'note:', 'notes:') # for pass for env items
        ENV_FILTERS_MODIFIERS = ('env:', 'area:', 'environment:', 'shot:', 'job:')
        PASS_FILTERS_MODIFIERS = ('pass:')

        count = 0

        # Now search for matches on every cell
        active_search_filter_count = 0
        columns_to_show = set()
        columns_to_hide = set()
        item_ids_rows_to_show = set()
        item_ids_rows_to_hide = set()
        for qmodelindex_env in model.get_environment_items_indices():
            if not qmodelindex_env.isValid():
                continue
            env_item = qmodelindex_env.internalPointer()
            row_match_count = 0
            row_not_match_count = 0
            for c in range(column_count):
                qmodelindex_cell = qmodelindex_env.sibling(qmodelindex_env.row(), c)
                if not qmodelindex_cell.isValid():
                    continue
                item = qmodelindex_cell.internalPointer()
                # Check for match for this cell for every possible rule
                for search_filter in search_filters.keys():
                    # Search filter not active
                    active = search_filters[search_filter].get('active', True)
                    search_mode = search_filters[search_filter].get('search_mode', str())
                    if not active:
                        continue
                    active_search_filter_count += 1
                    # Request to check only pass items
                    if search_filter.startswith(PASS_FILTERS_MODIFIERS) and not item.is_pass_for_env_item():
                        continue
                    # Request to check only environment items
                    if search_filter.startswith(ENV_FILTERS_MODIFIERS) and not item.is_environment_item():
                        continue
                    found = item.search_for_string(search_filter)
                    if found and 'Hide' in search_mode:
                        if search_filter.startswith(('frame:', 'frames:', 'note:', 'notes:')):
                            columns_to_hide.add(c)
                            row_not_match_count += 1
                        elif item.is_pass_for_env_item() or search_filter.startswith(PASS_FILTERS_MODIFIERS):
                            columns_to_hide.add(c)
                        else:
                            row_not_match_count += 1
                        # break
                    elif found:
                        if search_filter.startswith(('frame:', 'frames:', 'note:', 'notes:')):
                            columns_to_show.add(c)
                            row_match_count += 1
                        elif item.is_pass_for_env_item() or search_filter.startswith(PASS_FILTERS_MODIFIERS):
                            columns_to_show.add(c)
                        else:
                            row_match_count += 1
                        # break
            # Row has at least one NOT match
            if row_not_match_count:
                item_ids_rows_to_hide.add(id(env_item))
            # Found a match on any column of row
            if row_match_count:
                item_ids_rows_to_show.add(id(env_item))

            # msg = 'Env: "{}". '.format(env_item.get_environment_name_nice())
            # msg += 'Row Match Count: "{}". '.format(row_match_count)
            # msg += 'Not Match Count: "{}"'.format(row_not_match_count)
            # self.logMessage.emit(msg, logging.DEBUG)

        # msg = 'Columns To Show: "{}"'.format(columns_to_show)
        # self.logMessage.emit(msg, logging.DEBUG)

        if columns_to_hide:
            for c in range(1, column_count):
                hide = c in columns_to_hide
                if invert:
                    hide = not hide
                
                self.setColumnHidden(c, hide)
                count += 1

        # Show and hide particular columns
        if columns_to_show:
            # NOTE: Column 0 is prevented from being filtered out
            for c in range(1, column_count):
                hide = c not in columns_to_show
                if invert:
                    hide = not hide
                self.setColumnHidden(c, hide)
                count += 1

        # Hide rows
        if item_ids_rows_to_hide:
            # msg = 'Row Item Ids To Hide: "{}"'.format(item_ids_rows_to_hide)
            # self.logMessage.emit(msg, logging.DEBUG)
            for qmodelindex_env in model.get_environment_items_indices():
                if not qmodelindex_env.isValid():
                    continue
                env_item = qmodelindex_env.internalPointer()
                hide = id(env_item) in item_ids_rows_to_hide
                if invert:
                    hide = not hide
                self.setRowHidden(
                    qmodelindex_env.row(),
                    qmodelindex_env.parent(),
                    hide)
                count += 1

        # Show rows
        if item_ids_rows_to_show:
            # msg = 'Row Item Ids To Show: "{}"'.format(item_ids_rows_to_show)
            # self.logMessage.emit(msg, logging.DEBUG)
            for qmodelindex_env in model.get_environment_items_indices():
                if not qmodelindex_env.isValid():
                    continue
                env_item = qmodelindex_env.internalPointer()
                hide = id(env_item) not in item_ids_rows_to_show
                if invert:
                    hide = not hide
                self.setRowHidden(
                    qmodelindex_env.row(),
                    qmodelindex_env.parent(),
                    hide)
                count += 1

        # Fallback search mode. Searches env items only for matches.
        if not any([item_ids_rows_to_show, item_ids_rows_to_hide]) \
                and not any([columns_to_show, columns_to_hide]):
            if search_filters and active_search_filter_count:
                for qmodelindex_env in model.get_environment_items_indices():
                    if not qmodelindex_env.isValid():
                        continue
                    env_item = qmodelindex_env.internalPointer()
                    show = False
                    for search_filter in search_filters.keys():
                        active = search_filters[search_filter].get('active', True)
                        if not active:
                            continue
                        found = env_item.search_for_string(search_filter)
                        if found:
                            show = True
                            break
                    hide = not show
                    if invert:
                        hide = not hide
                    self.setRowHidden(
                        qmodelindex_env.row(),
                        qmodelindex_env.parent(),
                        hide)
                    count += 1

        if self._overlay_widget:
            self._overlay_widget.set_active(True)
            # QApplication.processEvents()
            self._overlay_widget.update_overlays()

        return count


    def _show_all_rows_and_columns(self):
        '''
        Show all rows and columns for entire view of model.
        '''
        model = self.model()
        if not model:
            return
        render_items = model.get_render_items()
        for i in range(model.columnCount(QModelIndex())):
            self.setColumnHidden(i, False)
        for qmodelindex in model.get_environment_items_indices():
            row = qmodelindex.row()
            self.setRowHidden(
                row,
                qmodelindex.parent(),
                False)


    ##########################################################################
    # State options


    def get_auto_resolve_versions(self):
        '''
        Get whether auto resolve versions is enabled.

        Returns:
            value (bool):
        '''
        return self._auto_resolve_versions


    def set_auto_resolve_versions(self, value):
        '''
        Set whether auto resolve versions is enabled.

        Args:
            value (bool):
        '''
        value = bool(value)
        if self._debug_mode:
            msg = 'View. Set auto resolve versions: {}'.format(value)
            self.logMessage.emit(msg, logging.DEBUG)                
        self._auto_resolve_versions = value


    def set_menu_some_actions_at_top(self, value):
        '''
        Set whether the main menu of this view has some common actions at the top or not,

        Args:
            value (bool):
        '''
        value = bool(value)
        if self._debug_mode:
            msg = 'View. Set menu some actions at top: {}'.format(value)
            self.logMessage.emit(msg, logging.DEBUG)        
        self._menu_some_actions_at_top = value


    def set_menu_include_search(self, value):
        '''
        Set whether the main menu of this view has some common actions at the top or not,

        Args:
            value (bool):
        '''
        value = bool(value)
        if self._debug_mode:
            msg = 'View. Set menu include search: {}'.format(value)
            self.logMessage.emit(msg, logging.DEBUG)
        self._menu_include_search = value


    def get_item_selection_sets_names(self):
        '''
        Get list of named selection sets.

        Returns:
            value (list):
        '''
        return self._item_selection_sets.keys()


    def get_item_selection_sets(self):
        '''
        Get a mapping of selection set names to contained item UUIDs.

        Returns:
            value (dict):
        '''
        return self._item_selection_sets


    def set_item_selection_sets(self, value):
        '''
        Set mapping of selection set names to contained item UUIDs.

        Returns:
            value (dict):
        '''
        msg = 'Setting all selection sets to: "{}"'.format(value)
        self.logMessage.emit(msg, logging.WARNING)
        self._item_selection_sets = value or collections.OrderedDict()


    def delete_all_selection_sets(self):
        '''
        Delete all selection sets.
        '''
        msg = 'Deleting all selection sets!'
        self.logMessage.emit(msg, logging.WARNING)
        self.set_item_selection_sets(collections.OrderedDict())


    def get_pass_visibility_sets_names(self):
        '''
        Get list of named pass visibility sets.

        Returns:
            value (list):
        '''
        return self._pass_visibility_sets.keys()


    def get_pass_visibility_sets(self):
        '''
        Get mapping of selection set names to mapping of pass names to visibility states.

        Returns:
            value (dict):
        '''
        return self._pass_visibility_sets


    def set_pass_visibility_sets(self, value):
        '''
        Set mapping of selection set names to mapping of pass names to visibility states.

        Returns:
            value (dict):
        '''
        msg = 'Setting pass visibility sets: "{}"'.format(value)
        self.logMessage.emit(msg, logging.WARNING)
        self._pass_visibility_sets = value or collections.OrderedDict()


    def delete_all_pass_visibility_sets(self):
        '''
        Delete all pass visibility sets.
        '''
        msg = 'Deleting all pass visibility sets!'
        self.logMessage.emit(msg, logging.WARNING)
        self.set_pass_visibility_sets(collections.OrderedDict())
        

    ##########################################################################
    # Callbacks


    def selection_changed(
            self,
            selected_qitemselection,
            deselected_qitemselection):
        '''
        This views selection model selectionChanged signal just fired.

        Args:
            selected_qitemselection (QItemSelection):
            deselected_qitemselection (QItemSelection):
        '''
        # Force delegate widget to update / repaint to look selected
        for qmodelindex in selected_qitemselection.indexes():
            item = qmodelindex.internalPointer()
            # try:
            item._set_is_selected_in_msrs(True)
            # except AttributeError:
            #     continue
            widget = self.indexWidget(qmodelindex)
            if not item.is_group_item() and widget:
                widget.set_is_selected(True)
                widget.update()
        # Force delegate widget to update / repaint to look deselected
        for qmodelindex in deselected_qitemselection.indexes():
            item = qmodelindex.internalPointer()
            # try:
            item._set_is_selected_in_msrs(False)
            # except AttributeError:
            #     continue               
            widget = self.indexWidget(qmodelindex)
            if not item.is_group_item() and widget:
                widget.set_is_selected(False)
                widget.update()


    def setColumnHidden(self, column, hidden):
        '''
        Reimplemented method to update overlays whenever columns visibility changes.
        '''
        base_tree_view.BaseTreeView.setColumnHidden(self, column, hidden)
        if self._overlay_widget:
            self._overlay_widget.update_overlays()


    def reset_column_sizes(self):
        '''
        Reset the column sizes.
        '''
        self.scale_columns(first_column_width=self.COLUMN_0_WIDTH)
        header = self.header()
        model = self.model()
        for i, render_item in enumerate(model.get_render_items()):
            render_item._cached_width = header.sectionSize(i + 1)


    def _update_header_columns(self, columns):
        '''
        Emit headerDataChanged for multiple columns.

        Args:
            columns (list):
        '''
        model = self.model()
        for c in columns:
            model.headerDataChanged.emit(Qt.Horizontal, c, c)


    def _set_node_colour(self, render_item, node_colour, column=None):
        '''
        Set node colour for column.
        Callback from ColorPickerDialog rgbChanged.

        Args:
            render_item (RenderItem): or subclass of
            node_colour (list):
            column (int):
        '''
        render_item.set_node_colour(node_colour)
        if column:
            self.model().headerDataChanged.emit(
                Qt.Horizontal,
                column,
                column)


    def _update_envrionment_renderable_hint(
            self,
            qmodelindex,
            has_renderables=True):
        '''
        Update the column 0 for row of specified index, of EnvironmentItem.

        Args:
            qmodelindex (QModelIndex):
            has_renderables (bool):

        '''
        widget = self.indexWidget(qmodelindex)
        if widget:
            widget.set_has_renderables(has_renderables)
            widget.update()


    def _set_widget_processing_state(
            self,
            qmodelindex,
            is_processing=True,
            process_msg='Processing'):
        '''
        Given a particular QModelIndex, get the related delegate widget,
        and update the is_rendering state, and an optional display string,
        and make the widget update / repaint.

        Args:
            qmodelindex (QModelIndex):
            is_processing (bool):
            process_msg (str):

        Returns:
            success (bool);
        '''
        # Update widget to show progress of rendering
        widget = self.indexWidget(qmodelindex)

        widget.set_is_processing(is_processing)
        widget.set_process_msg(process_msg)
        self.scrollTo(qmodelindex)
        widget.update()

        return True


    def _resolve_versions_for_selection(self):
        '''
        Request the details panel to update and resolve all versions.
        '''
        self.updateDetailsPanel.emit(True)


    ##########################################################################
    # Core view


    def selectAll(self):
        '''
        Reimplemented method of QTreeView.
        '''
        base_tree_view.BaseTreeView.selectAll(self)
        self.updateDetailsPanel.emit(False)


    def clearSelection(self):
        '''
        Reimplemented method of QTreeView.
        '''
        base_tree_view.BaseTreeView.clearSelection(self)
        self.updateDetailsPanel.emit(False)


    def setModel(self, model):
        '''
        Reimplemented method of srnd_qt BaseTreeView.

        Args:
            model (QtCore.QAbstractItemModel):
        '''
        base_tree_view.BaseTreeView.setModel(self, model)

        model.environmentHasRenderables.connect(
            self._update_envrionment_renderable_hint)
        model.processingPassForEnv.connect(
            self._set_widget_processing_state)
        model.rescaleColumnsDefaultRequest.connect(
            lambda x: self.scale_columns(columns=x))
        model.setColumnWidthRequest.connect(self.setColumnWidth)


    def mousePressEvent(self, event):
        '''
        Reimplementing QTreeView mousePressEvent to keep track of mouse press than release event.
        '''
        if self._overlay_widget and self._in_wait_on_interactive_mode:
            event.ignore()
            return
        base_tree_view.BaseTreeView.mousePressEvent(self, event)
        if event.buttons() in [Qt.LeftButton, Qt.MiddleButton]:
            self._dragging_mouse = True


    def mouseReleaseEvent(self, event):
        '''
        Reimplementing to keep track of mouse press than release event.
        '''
        # NOTE: The following is only relevant when in interactive WAIT on mode
        if self._overlay_widget and self._in_wait_on_interactive_mode:
            if event.button() != Qt.LeftButton:
                event.ignore()
                return
            qpoint = self.mapFromGlobal(QCursor.pos())
            qpoint -= QPoint(0, self.header().height())
            qmodelindex_under_mouse = self.indexAt(qpoint)
            item = qmodelindex_under_mouse.internalPointer()
            if qmodelindex_under_mouse.isValid() and not item.is_group_item():
                if not self._overlay_widget.get_interactive_source_qmodelindex():
                    self._overlay_widget.set_interactive_source_qmodelindex(qmodelindex_under_mouse)
                elif not self._overlay_widget.get_interactive_destination_qmodelindex():
                    self._overlay_widget.set_interactive_destination_qmodelindex(qmodelindex_under_mouse)
                self._overlay_widget._update_interactive_overlay_points()
            return

        # Call super class to handle press event
        base_tree_view.BaseTreeView.mouseReleaseEvent(self, event)

        # If was doing a drag and drop rearrange of items
        if self._dragging_mouse:
            self._dragging_mouse = False
            self.draggingComplete.emit()


    def mouseDoubleClickEvent(self, event):
        '''
        Reimplemented so double click on Environment item launches change areas dialog.
        '''
        qpoint = self.mapFromGlobal(QCursor.pos())
        qpoint -= QPoint(0, self.header().height())
        qmodelindex_under_mouse = self.indexAt(qpoint)
        if not qmodelindex_under_mouse.isValid():
            base_tree_view.BaseTreeView.mouseDoubleClickEvent(self, event)
            return
        item = qmodelindex_under_mouse.internalPointer()
        if item.is_environment_item():
            self._select_row_from_qmodel_index(qmodelindex_under_mouse)
            # self.change_areas_selected_items()
            return
        base_tree_view.BaseTreeView.mouseDoubleClickEvent(self, event)


    def open_persistent_editors_for_row(
            self,
            qmodelindex,
            columns=list(),
            close_existing=True,
            recursive=False):
        if not qmodelindex.isValid():
            return
        item = qmodelindex.internalPointer()
        if item.is_group_item():
            return
        base_tree_view.BaseTreeView.open_persistent_editors_for_row(
            self,
            qmodelindex,
            columns=columns,
            close_existing=close_existing,
            recursive=recursive)
    
    
    def _select_row_from_qmodel_index(self, qmodelindex):
        selection = QItemSelection()
        model = qmodelindex.model()
        column_count = model.columnCount(QModelIndex())
        for c in range(column_count):
            qmodelindex_sibling = qmodelindex.sibling(qmodelindex.row(), c)
            selection.append(QItemSelectionRange(qmodelindex_sibling))
        selection_model = self.selectionModel()
        selection_model.select(selection, QItemSelectionModel.ClearAndSelect)


    ##########################################################################
    # WAIT on


    def edit_wait_on_for_selection(self, selection=None):
        '''
        Invoke the edit / set mode for WAIT on for selected items.
        Open dialog to define WAIT on other Multi Shot items and / or Plow Job and Task ids.

        Args:
            selection (list):

        Returns:
            update_count (int):
        '''
        msg = 'Opening WAIT On Dialog...'
        self.logMessage.emit(msg, logging.INFO)

        model = self.model()

        wait_on_multi_shot = list()
        wait_on_plow_ids = list()

        selection = selection or self.selectedIndexes()

        for item in self.get_selected_items(selection=selection):
            if item.is_environment_item() or item.is_pass_for_env_item():
                if any([item.get_wait_on(), item.get_wait_on_plow_ids()]):
                    wait_on_multi_shot = item.get_wait_on()
                    wait_on_plow_ids = item.get_wait_on_plow_ids()
                    break

        version = model.get_multi_shot_render_submitter_version()

        from srnd_multi_shot_render_submitter.dialogs import set_depends_dialog
        dialog = set_depends_dialog.SetDependsDialog(
            self, # the view which has the selected multi shot items
            wait_on_multi_shot=wait_on_multi_shot,
            wait_on_plow_ids=wait_on_plow_ids,
            version=version,
            host_app=self.HOST_APP,
            parent=self)
        dialog.logMessage.connect(model.emit_message)

        if dialog.exec_() == QDialog.Rejected:
            return

        wait_on_multi_shot = dialog.get_wait_on_multi_shot_items_uuids() or list()
        wait_on_plow_ids = dialog.get_wait_on_plow_ids() or list()

        update_count = 0
        for i, qmodelindex in enumerate(selection):
            if not qmodelindex.isValid():
                continue
            item = qmodelindex.internalPointer()
            if not any([item.is_environment_item(), item.is_pass_for_env_item()]):
                continue
            current_wait_on_multi_shot = item.get_wait_on()
            current_wait_on_plow_ids = item.get_wait_on_plow_ids()
            # NOTE: Avoid setting self depedency
            identity_id = item.get_identity_id()
            if identity_id in wait_on_multi_shot:
                wait_on_multi_shot.pop(identity_id)
            item.set_wait_on(wait_on_multi_shot)
            item.set_wait_on_plow_ids(wait_on_plow_ids)
            wait_on_multi_shot_changed = current_wait_on_multi_shot != wait_on_multi_shot
            wait_on_plow_ids_changed = current_wait_on_plow_ids != wait_on_plow_ids
            if any([wait_on_multi_shot_changed, wait_on_plow_ids_changed]):
                model.dataChanged.emit(qmodelindex, qmodelindex)
                update_count += 1

        if update_count and self._overlay_widget:
            self._overlay_widget.update_overlays()

        return update_count


    def get_in_wait_on_interactive_mode(self):
        '''
        Get whether in WAIT on intreactive define mode.
        '''
        return self._in_wait_on_interactive_mode


    def enter_wait_on_interactive(self, show_dialog=False):
        '''
        Enter a view mode where user can edit WAIT on interactively.

        Args:
            show_dialog (bool) :
        '''
        msg = 'Entering WAIT On Interactive Mode!'
        self.logMessage.emit(msg, logging.WARNING)

        self._overlay_widget.clear_interactive_overlays()

        model = self.model()

        column_count = model.columnCount(QModelIndex())
        for qmodelindex_env in model.get_environment_items_indices():
            if not qmodelindex_env.isValid():
                continue
            for c in range(column_count):
                qmodelindex_cell = qmodelindex_env.sibling(qmodelindex_env.row(), c)
                widget = self.indexWidget(qmodelindex_cell)
                if widget:
                    widget.setAttribute(Qt.WA_TransparentForMouseEvents, True)
                    widget.setMouseTracking(False)

        cursor = QCursor(QPixmap(constants.WAIT_ICON_PATH))
        QApplication.setOverrideCursor(cursor)
        self.setMouseTracking(True)

        self._in_wait_on_interactive_mode = True
        model._in_wait_on_interactive_mode = True

        self._overlay_widget.set_draw_all_interactive_overlays(True)
        self._overlay_widget.update_overlays()


    def exit_wait_on_interactive(self):
        '''
        Exit a view mode where user can edit WAIT on interactively.
        '''
        msg = 'Exiting WAIT On Interactive Mode!'
        self.logMessage.emit(msg, logging.WARNING)

        self._overlay_widget.clear_interactive_overlays()

        QApplication.restoreOverrideCursor()
        self.setMouseTracking(False)

        model = self.model()

        self._in_wait_on_interactive_mode = False
        model._in_wait_on_interactive_mode = False

        column_count = model.columnCount(QModelIndex())
        for qmodelindex_env in model.get_environment_items_indices():
            if not qmodelindex_env.isValid():
                continue
            for c in range(column_count):
                qmodelindex_cell = qmodelindex_env.sibling(qmodelindex_env.row(), c)
                widget = self.indexWidget(qmodelindex_cell)
                if widget:
                    widget.setAttribute(Qt.WA_TransparentForMouseEvents, False)
                    widget.setMouseTracking(True)

        self._overlay_widget.set_draw_all_interactive_overlays(False)
        self._overlay_widget.update_overlays()

        self.updateDetailsPanel.emit(False)


    def accept_wait_on_interacive(self):
        '''
        Apply the interactively chosen WAIT on, from source to target.
        '''
        if not self._in_wait_on_interactive_mode:
            self.exit_wait_on_interactive()
            return

        msg = 'Accepted WAIT ON Interactive!'
        self.logMessage.emit(msg, logging.WARNING)

        model = self.model()

        source_qmodelindex = self._overlay_widget.get_interactive_source_qmodelindex()
        destination_qmodelindex = self._overlay_widget.get_interactive_destination_qmodelindex()
        if all([source_qmodelindex, destination_qmodelindex]) and \
                source_qmodelindex != destination_qmodelindex:
            destination_item = destination_qmodelindex.internalPointer()
            identity_id = destination_item.get_identity_id()
            msg = 'Destination MSRS UUID: "{}"'.format(identity_id)
            self.logMessage.emit(msg, logging.WARNING)
            source_item = source_qmodelindex.internalPointer()
            current_wait_on = source_item.get_wait_on()
            wait_on = set(current_wait_on).union(set([identity_id]))
            source_item.set_wait_on(list(wait_on))
            model.dataChanged.emit(source_qmodelindex, source_qmodelindex)
            # model.updateOverviewRequested.emit()
        else:
            msg = 'No Source Or Target (Or Same) Defined In WAIT On Interactive Mode!'
            self.logMessage.emit(msg, logging.WARNING)
        self.exit_wait_on_interactive()


    ##########################################################################


    def keyPressEvent(self, event):
        '''
        NOTE: This is only reimplemented for interactive WAIT On edit mode.
        '''
        if self._overlay_widget and self._in_wait_on_interactive_mode:
            if event.key() == Qt.Key_Backspace:
                if self._overlay_widget.has_interactive_points_defined():
                    self._overlay_widget.set_interactive_destination_qmodelindex(None)
                elif self._overlay_widget.get_interactive_source_qmodelindex():
                    self._overlay_widget.set_interactive_source_qmodelindex(None)
                # No more points to backspace, so exit interactive edit context
                else:
                    self.exit_wait_on_interactive()
                    return
                self._overlay_widget._update_interactive_overlay_points()
                return
            elif event.key() == Qt.Key_Escape:
                self.exit_wait_on_interactive()
                return
            if event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
                self.accept_wait_on_interacive()
        base_tree_view.BaseTreeView.keyPressEvent(self, event)


    def mouseMoveEvent(self, event):
        '''
        NOTE: This is only reimplemented for interactive WAIT On edit mode.
        '''
        if not self._overlay_widget or not self._in_wait_on_interactive_mode:
            base_tree_view.BaseTreeView.mouseMoveEvent(self, event)
            return
        qpoint = self.mapFromGlobal(QCursor.pos())
        qpoint -= QPoint(0, self.header().height())
        qmodelindex_under_mouse = self.indexAt(qpoint)
        is_valid = qmodelindex_under_mouse.isValid()
        item = qmodelindex_under_mouse.internalPointer()
        if is_valid and not item.is_group_item():
            self._overlay_widget.set_interactive_item_current_qmodelindex(qmodelindex_under_mouse)
        else:
            self._overlay_widget.set_interactive_item_current_qmodelindex(None)
        self._overlay_widget._update_interactive_overlay_points()


    def resizeEvent(self, event):
        '''
        Propagate this tree view widget size to optional overlay widget.
        NOTE: This is only reimplemented for overlays widget.
        '''
        base_tree_view.BaseTreeView.resizeEvent(self, event)
        if self._overlay_widget:
            self._overlay_widget.update_overlays()


    ##########################################################################


    def _get_destination_item_and_index_for_event(self, event):
        '''
        Get the destination item and index for event.

        Args:
            event (QtCore.QEvent):

        Returns:
            destination_item, destination_node_type, destination_qmodelindex, is_between (tuple):
        '''
        pos = event.pos()
        destination_qmodelindex = self.indexAt(pos)
        rect = self.visualRect(destination_qmodelindex)
        destination_item, destination_node_type = None, None
        y = pos.y()
        padding = 16
        is_between = (y <= rect.top() + padding) and (y >= rect.top() - padding)
        if destination_qmodelindex.isValid():
            destination_item = destination_qmodelindex.internalPointer()
            destination_node_type = destination_item.get_node_type()
        return (
            destination_item,
            destination_node_type,
            destination_qmodelindex,
            is_between)


    def get_selected_organized_environment_indices(self, selection=None):
        '''
        Get an organized mapping of Environment indices related to items to perform operation on.
        Note: Mapped by parent internal id, then row number, mapped to QModelIndex.

        Args:
            selection (list): of QModelIndex

        Returns:
            organized_indices, selection_count (tuple):
        '''
        if not selection:
            selection = list()
        selection = selection or self.selectedIndexes()
        selection_count = 0
        organized_indices = collections.OrderedDict()
        for i, qmodelindex in enumerate(selection):
            if not qmodelindex.isValid():
                continue
            if qmodelindex.column() != 0:
                continue
            row = qmodelindex.row()
            parent_item_id = qmodelindex.parent().internalId()
            if not parent_item_id in organized_indices.keys():
                organized_indices[parent_item_id] = collections.OrderedDict()
            organized_indices[parent_item_id][row] = qmodelindex
            selection_count += 1
        return organized_indices, selection_count


    def _gather_environments_from_mime(self, mime_data):
        '''
        Gather environments names from mime data of event.

        Args:
            mime_data (QMimeData):

        Returns:
            environments (list): prevalidated environments.
                NOTE: has expected number of slashes.
                NOTE: Will be further validated on drop.
        '''
        areas = mime_data.text()
        # Split on line break or comma
        import re
        areas_list = re.split('\n|,', areas)
        environments = list()
        for area in areas_list:
            area = str(area).replace(' ', str())
            if area.startswith('/') and area.count('/') <= 5:
                area = area.rstrip('/')
                environments.append(area)
        return environments


    def _gather_render_node_names_from_mime(self, mime_data):
        '''
        Gather render node names from mime data of event.

        Args:
            mime_data (QMimeData):

        Returns:
            render_node_names (list):
        '''
        model = self.model()
        item_full_names = mime_data.text()
        # Split on line break or comma
        import re
        item_full_names_list = re.split('\n|,', item_full_names)
        render_node_names = list()
        for item_full_name in item_full_names_list:
            item_full_name = str(item_full_name).replace(' ', str())
            render_item_object = model.get_render_item_object()
            render_item = render_item_object(
                item_full_name=item_full_name)
            render_node = render_item.get_node_in_host_app()
            if render_node:
                render_node_names.append(item_full_name)
        return render_node_names


    def _gather_source_items_to_drag(self, event):
        '''
        Get an organized mapping of Environment and Group indices related to items to drag and drop.
        Note: Mapped by parent internal id, then row number, mapped to QModelIndex.

        Args:
            event (QtCore.QEvent):

        Returns:
            organized_indices, selection_count (tuple):
        '''
        selection = self.selectedIndexes()
        all_items_must_be = None
        organized_indices = collections.OrderedDict()
        selection_count = 0
        for i, qmodelindex in enumerate(selection):
            if not qmodelindex.isValid():
                continue
            if qmodelindex.column() != 0:
                continue
            item = qmodelindex.internalPointer()
            # For drag and drop all source items must be the same as the first type.
            # So filter out unwanted indices here.
            node_type = item.get_node_type()
            if item.is_environment_item():
                if not all_items_must_be:
                    all_items_must_be = node_type
            elif item.is_group_item():
                if not all_items_must_be:
                    all_items_must_be = node_type
            if node_type != all_items_must_be:
                continue
            row = qmodelindex.row()
            parent_item_id = qmodelindex.parent().internalId()
            if not parent_item_id in organized_indices.keys():
                organized_indices[parent_item_id] = collections.OrderedDict()
            organized_indices[parent_item_id][row] = qmodelindex
            selection_count += 1
        return organized_indices, selection_count


    def dragEnterEvent(self, event):
        '''
        Drag enter event.

        Args:
            event (QtCore.QEvent):
        '''
        # Check if dragging from other external tool a string of environments
        has_areas = False
        has_render_nodes = False
        mime_data = event.mimeData()
        if mime_data.hasText() and not hasattr(mime_data, 'from_msrs'):
            environments = self._gather_environments_from_mime(mime_data)
            has_areas = bool(environments)
            if not has_areas and constants.ALLOW_TOGGLE_ENABLED_FROM_COLUMN_HEADER:
                render_node_names = self._gather_render_node_names_from_mime(mime_data)
                has_render_nodes = bool(render_node_names)
            if any([has_areas, has_render_nodes]):
                QTreeView.dragEnterEvent(self, event)
                event.acceptProposedAction()
                return

        # Must have indices to drag move!ki
        organized_indices, selection_count = self._gather_source_items_to_drag(event)
        if organized_indices:
            QTreeView.dragEnterEvent(self, event)
            event.acceptProposedAction()
            return

        event.ignore()


    def dragLeaveEvent(self, event):
        '''
        Drag enter event.

        Args:
            event (QtCore.QEvent):
        '''
        self._rect_tmp = None
        base_tree_view.BaseTreeView.dragLeaveEvent(self, event)


    def dragMoveEvent(self, event):
        '''
        Drag move event.

        Args:
            event (QtCore.QEvent):
        '''
        # Check if dragging from other external tool a string of environments
        has_areas = False
        has_render_nodes = False
        environments = list()
        render_node_names = list()
        mime_data = event.mimeData()
        if mime_data.hasText() and not hasattr(mime_data, 'from_msrs'):
            environments = self._gather_environments_from_mime(mime_data)
            has_areas = bool(environments)
            if not has_areas and constants.ALLOW_TOGGLE_ENABLED_FROM_COLUMN_HEADER:
                render_node_names = self._gather_render_node_names_from_mime(mime_data)
                has_render_nodes = bool(render_node_names)

        # Must have indices to drag move
        organized_indices = dict()
        selection_count = 0
        if not any([has_areas, has_render_nodes]):
            organized_indices, selection_count = self._gather_source_items_to_drag(event)
            if not organized_indices:
                event.ignore()
                return

        result  = self._get_destination_item_and_index_for_event(event)
        destination_item, destination_node_type, destination_qmodelindex, is_between = result

        if has_areas:
            # Dragging new environments into Multi Shot view at index from string mime data
            if is_between:
                rect = self.visualRect(destination_qmodelindex)
                msg = 'Adding {} Environments'.format(len(environments))
                self._draw_in_between = rect.top()
                self.update()
                QTreeView.dragMoveEvent(self, event)
                event.acceptProposedAction()
                return
            # Dragging new environments into Multi Shot view at end from string mime data
            elif not destination_qmodelindex.isValid():
                msg = 'Adding {} Environments'.format(len(environments))
                self._draw_in_between = None
                self.update()
                QTreeView.dragMoveEvent(self, event)
                event.acceptProposedAction()
                return
            # Dragging new environments into Multi Shot view on to group from string mime data
            elif destination_node_type and 'GroupItem' in destination_node_type:
                msg = 'Adding {} Environments Into Group'.format(len(environments))
                self._draw_in_between = None
                self.update()
                QTreeView.dragMoveEvent(self, event)
                event.acceptProposedAction()
                return
            event.ignore()
            return
        elif has_render_nodes:
            msg = 'Adding {} Render Nodes'.format(len(render_node_names))
            self._draw_in_between = None
            self.update()
            QTreeView.dragMoveEvent(self, event)
            event.acceptProposedAction()
            return

        parent_item_id = organized_indices.keys()[0]
        rows = organized_indices[parent_item_id].keys()
        row = rows[-1]
        source_qmodelindex = organized_indices[parent_item_id][row]
        source_item = source_qmodelindex.internalPointer()
        source_node_type = source_item.get_node_type()

        # Get parent node type
        parent_node_type = None
        if destination_item:
            parent_item = destination_item.parent()
            if parent_item:
                parent_node_type = parent_item.get_node_type()

        # Dragging GroupItem between two indices, where parent isn't the root of view
        if is_between and 'GroupItem' in source_node_type and 'Root' not in parent_node_type:
            msg = 'Groups Can Only Be Dragged To Root Of Tree'
            self._draw_in_between = None
            self.update()
            event.ignore()
            return

        # Dragging EnvironmentItem or GroupItem between two indices
        if is_between:
            rect = self.visualRect(destination_qmodelindex)
            msg = 'Rearranging {} {}/s Items'.format(selection_count, source_node_type)
            self._draw_in_between = rect.top()
            self.update()
            QTreeView.dragMoveEvent(self, event)
            event.acceptProposedAction()
            return

        # Dragging to non index, so at end of view
        if not destination_qmodelindex.isValid():
            msg = 'Dragging {} {}/s Items'.format(selection_count, source_node_type)
            self._draw_in_between = None
            self.update()
            QTreeView.dragMoveEvent(self, event)
            event.acceptProposedAction()
            return

        # Dragging an EnvironmentItem on to GroupItem
        elif 'EnvironmentItem' in source_node_type and destination_node_type \
                and 'GroupItem' in destination_node_type:
            _source_node_type = 'Environment/s'
            msg = 'Dragging {} {}/s To {}'.format(
                selection_count,
                source_node_type,
                destination_node_type)
            self._draw_in_between = None
            self.update()
            QTreeView.dragMoveEvent(self, event)
            event.acceptProposedAction()
            return

        msg = 'Image/s Can Only Be Rearranged By Dropping In Between'
        self._draw_in_between = None
        self.update()
        event.ignore()


    def dropEvent(self, event):
        '''
        Handle drop event and perform drag and drop.
        Reimplemented method.

        Args:
            event (QtCore.QEvent):
        '''
        self._draw_in_between = None

        model = self.model()

        # Check if dragging from other external tool a string of environments
        has_areas = False
        has_render_nodes = False
        environments = list()
        render_node_names = list()
        mime_data = event.mimeData()
        if mime_data.hasText() and not hasattr(mime_data, 'from_msrs'):
            environments = self._gather_environments_from_mime(mime_data)
            has_areas = bool(environments)
            if not has_areas and constants.ALLOW_TOGGLE_ENABLED_FROM_COLUMN_HEADER:
                render_node_names = self._gather_render_node_names_from_mime(mime_data)
                has_render_nodes = bool(render_node_names)

        # Must have indices to drag move
        organized_indices = dict()
        if not any([has_areas, has_render_nodes]):
            organized_indices, selection_count = self._gather_source_items_to_drag(event)
            if not organized_indices:
                event.ignore()
                self.update()
                return

        self.clearSelection()

        result  = self._get_destination_item_and_index_for_event(event)
        destination_item, destination_node_type, destination_qmodelindex, is_between = result

        # Is dropping at root of model and next index
        if not destination_qmodelindex.isValid():
            destination_qmodelindex = QModelIndex()
            destination_row = model.rowCount(destination_qmodelindex)
        else:
            destination_row = destination_qmodelindex.row()

        # Is dragging between two indices
        if is_between:
            # Has no destination item or dragging at root of model
            if not destination_item or not destination_item.parent():
                destination_item = model.get_root_node()
            # Dragging at lower level
            else:
                destination_row = destination_qmodelindex.row()
                destination_qmodelindex = destination_qmodelindex.parent()
                destination_item = destination_item.parent()
        # Dragging one item on to another
        else:
            if not destination_item:
                destination_item = model.get_root_node()

        # Parent to next index of target Groupitem
        if destination_node_type == 'GroupItem' and not is_between:
            destination_row = model.rowCount(destination_qmodelindex)

        if has_areas:
            model.add_environments(
                environments,
                in_group_item=destination_item,
                in_group_index=destination_qmodelindex,
                insertion_row=destination_row)
            return

        elif has_render_nodes:
            model.add_render_nodes(render_node_names)
            return

        # # Collect details
        # msg = '\n\nSource Type: "{}"'.format(source_node_type)
        # msg += '\n->Destination Type: "{}"'.format(destination_node_type)
        # if self._debug_mode:
        #     msg += '\n->Destination QModelIndex: "{}"'.format(destination_qmodelindex)
        #     msg += '\n->Destination QModelIndex Is Valid: "{}"'.format(destination_qmodelindex.isValid())
        #     msg += '\n->Destination Row: "{}"'.format(destination_row)
        #     msg += '\n->Is Between: "{}"'.format(is_between)
        # msg += '\n->Selection Count To Drag: "{}"'.format(selection_count)
        # self.logMessage.emit(msg, logging.CRITICAL)

        ######################################################################
        # Unparent source items and remove rows for drag and drop operation

        items_to_insert = list()
        for parent_item_id in organized_indices.keys():
            rows = reversed(sorted(organized_indices[parent_item_id].keys()))
            for row in rows:
                source_qmodelindex = organized_indices[parent_item_id][row]
                if not source_qmodelindex.isValid():
                    continue
                if source_qmodelindex.column() != 0:
                    continue
                qmodelindex_parent = source_qmodelindex.parent()
                item = source_qmodelindex.internalPointer()
                row = source_qmodelindex.row()

                parent_item = item.parent()
                if not parent_item:
                    continue

                # Remove the remove row and item
                row_count = model.rowCount(qmodelindex_parent)
                if row > row_count:
                    remove_row = row_count
                else:
                    remove_row = row

                ##############################################################
                # Remove each row in reverse order to start with.
                # Will later insert the rows at destination, to avoid complex index issues.

                model.beginRemoveRows(qmodelindex_parent, remove_row, remove_row)
                parent_item.remove_child(remove_row)
                model.endRemoveRows()

                items_to_insert.append(item)

                ##############################################################
                # Close existing editor

                qmodelindex = model.index(remove_row, 0, qmodelindex_parent)
                model.modify_persistent_editors_recursive(
                    qmodelindex,
                    open_editor=False,
                    recursive=True,
                    auto_expand=False)

        ######################################################################
        # Parent items to new destination items, and insert rows again

        model.beginInsertRows(
            destination_qmodelindex,
            destination_row,
            destination_row + len(items_to_insert) - 1)
        select_by_uuids = list()
        for item in items_to_insert:
            destination_item.insert_child(destination_row, item)
            select_by_uuids.append(item.get_identity_id())
        model.endInsertRows()

        recursive = destination_item.is_group_item() or destination_item.is_root()

        model.modify_persistent_editors_recursive(
            destination_qmodelindex.parent(),
            open_editor=True,
            recursive=recursive,
            auto_expand=True)

        # Reselect the Environments that were rearranged, thereby creating new QModelIndices
        self.select_by_identity_uids(select_by_uuids)

        # Environments might have changed order so update cached indices
        model._update_environments_indices()

        self.update()

        if self._overlay_widget:
            self._overlay_widget.update_overlays()


##############################################################################


class MultiShotHeaderView(QHeaderView):
    '''
    Custom header for the MultiShotRenderView.
    Reimplementing for custom paint events.

    Args:
        orientation (Qt.Orientation):
        host_app (str):
        constants (Constants): optionally pass a shared instance of Constants module
    '''

    def __init__(
            self,
            orientation=Qt.Horizontal,
            parent=None):
        super(MultiShotHeaderView, self).__init__(
            orientation,
            parent=parent)

        self.HOST_APP = constants.HOST_APP
        self.NORMAL_ROW_HEIGHT = NORMAL_ROW_HEIGHT

        self._draw_header_node_colour = True
        self._draw_header_disabled_hint = True

        self._draw_node_type_icons = False

        import Qt as qt_shim
        if any([qt_shim.IsPySide2, qt_shim.IsPyQt5]):
            self.setSectionsClickable(True)
            self.setSectionsMovable(True)
            # self.setFirstSectionMovable(False)
        else:
            self.setClickable(True)
            self.setMovable(True)
        self.setDefaultAlignment(Qt.AlignCenter)
        self.setStretchLastSection(False)


    def get_draw_header_node_colour(self):
        return self._draw_header_node_colour

    def set_draw_header_node_colour(self, value):
        value = bool(value)
        value_before = self.get_draw_header_node_colour()
        self._draw_header_node_colour = value
        self.reset()
        if value_before != value:
            view = self.parent()
            model = view.model()
            model.update_preference('show_render_item_colour_hints', value)

    def get_draw_header_disabled_hint(self):
        return self._draw_header_disabled_hint

    def set_draw_header_disabled_hint(self, value):
        value = bool(value)
        value_before = self.get_draw_header_disabled_hint()        
        self._draw_header_disabled_hint = value
        self.reset()
        if value_before != value:
            view = self.parent()
            model = view.model()
            model.update_preference('show_render_item_disabled_hints', value)        


    # def sectionSizeFromContents(self, column):
    #     '''
    #     Reimplemented from base QHeaderView class.

    #     Args:
    #         column (int):
    #     '''
    #     if not self._draw_node_type_icons:
    #         return QHeaderView.sectionSizeFromContents(self, column)

    #     model = self.model()

    #     display_str = model.headerData(
    #         column,
    #         Qt.Horizontal,
    #         role=Qt.DisplayRole)
    #     font = model.headerData(
    #         column,
    #         Qt.Horizontal,
    #         role=Qt.FontRole)

    #     size = QHeaderView.sectionSizeFromContents(self, column)

    #     if display_str and font:
    #         ICON_WIDTH = 30
    #         font_metrics = QFontMetrics(font)
    #         width = font_metrics.width(display_str)
    #         width += ICON_WIDTH
    #         size.setWidth(width)

    #     return size


    def mousePressEvent(self, event):
        '''
        Reimplementing QHeaderView mousePressEvent to allow entire column to be selected.
        '''
        # Call default mousePressEvent (accept for LeftButton)
        if event.buttons() != Qt.LeftButton:
            QHeaderView.mousePressEvent(self, event)
            return

        overlays_widget = self.parent().get_overlays_widget()
        if overlays_widget and overlays_widget.get_active():
            overlays_widget.set_active(False)

        # Call default mousePressEvent (if item not valid)
        view = self.parent()
        qmodelindex = view.indexAt(event.pos())
        if not qmodelindex.isValid():
            QHeaderView.mousePressEvent(self, event)
            return

        column = qmodelindex.column()
        # self.select_column(section)

        render_item = self.parent().get_render_item_for_column(column)
        if render_item:
            render_item.select_node_in_host_app()
        
        # Update the details panel for the new selection in QTreeView
        view.updateDetailsPanel.emit(False)

        QHeaderView.mousePressEvent(self, event)


    def select_column(self, section):
        '''
        Select all pass for env items along particular column.

        Args:
            section (int):
        '''
        model = self.model()
        view = self.parent()
        selection_model = view.selectionModel()
        previous = selection_model.selection()
        modifiers = QApplication.keyboardModifiers()
        add = modifiers == Qt.ShiftModifier or modifiers == Qt.ControlModifier
        if not add:
            selection_model.clearSelection()
        for qmodelindex in model.get_environment_items_indices():
            if not qmodelindex.isValid():
                continue
            qmodelindex_column = qmodelindex.sibling(qmodelindex.row(), section)
            if not qmodelindex_column.isValid():
                continue
            selection_model.select(qmodelindex_column, QItemSelectionModel.Select)


    def mouseReleaseEvent(self, event):
        '''
        Update the overlays widget if not active after mouse release event.
        NOTE: This is to prevent overlays updating while user resizes column.
        '''
        overlays_widget = self.parent().get_overlays_widget()
        if overlays_widget and not overlays_widget.get_active():
            overlays_widget.set_active(True)
            overlays_widget.update_overlays()
        QHeaderView.mouseReleaseEvent(self, event)


    def paintSection(self, painter, rect, column):
        '''
        Paint a specific column header.

        Args:
            painter (QPainter):
            rect (QRect):
            column (int):
        '''
        # painter.setRenderHint(QPainter.HighQualityAntialiasing)
        painter.setRenderHint(QPainter.Antialiasing)

        painter.fillRect(rect, QColor(*constants.HEADER_BACKGROUND_COLOUR))

        if column == 0:
            #QHeaderView.paintSection(self, painter, rect, column)
            return

        view = self.parent()
        render_item = view.get_render_item_for_column(column)
        if not render_item:
            #QHeaderView.paintSection(self, painter, rect, column)
            return

        node_colour = render_item.get_node_colour()
        enabled = render_item.get_enabled()
        renderable_count_for_render_node = render_item._get_renderable_count_for_render_node()

        # if not node_colour:
        #     QHeaderView.paintSection(self, painter, rect, column)
        #     return

        rect_new_area = rect.adjusted(2, 2, -2, -2)

        if renderable_count_for_render_node:
            render_node_colour = view.get_render_item_colour()
            state_colour = QColor(*render_node_colour) #constants.HEADER_RENDERABLE_COLOUR)
        else:
            state_colour = QColor(*constants.CELL_ENABLED_NOT_QUEUED_COLOUR)
        painter.fillRect(rect_new_area, state_colour)

        # Draw node colour
        if self._draw_header_node_colour and node_colour:
            # Colour notch on left side
            rect_node_colour = QRect(rect_new_area)
            rect_node_colour.setWidth(8)
            if isinstance(node_colour, basestring):
                colour = QColor(node_colour)
            else:
                node_colour = list(node_colour or [0, 0, 0]) # fallback if None
                node_colour.append(1.0)
                colour = QColor.fromRgbF(*node_colour)
            painter.fillRect(rect_node_colour, colour)

            # Colour stroke on outline
            pen = QPen()
            pen.setWidth(1)
            pen.setColor(colour)
            painter.setPen(pen)
            painter.drawRect(rect_new_area)

        # Paint a disabled hint
        if self._draw_header_disabled_hint and not enabled:
            hint_width = 10
            hint_color = QColor(200, 30, 30)
            rect_disabled_hint = QRect(rect_new_area)
            # rect_disabled_hint.translate(rect_disabled_hint.width() - 9, 0)
            # rect_disabled_hint.setWidth(8)
            rect_disabled_hint.translate(rect_disabled_hint.width() - (hint_width + 1), 0)
            rect_disabled_hint.setWidth(hint_width)
            pen = QPen()
            pen.setWidth(2)
            # pen.setColor(QColor(255, 0, 0))
            pen.setColor(hint_color)
            painter.setPen(pen)
            painter.drawLine(
                rect_disabled_hint.topLeft(),
                rect_disabled_hint.bottomRight())
            painter.drawLine(
                rect_disabled_hint.bottomLeft(),
                rect_disabled_hint.topRight())

        model = self.model()

        # Paint the column display label
        label_str = model.headerData(
            column,
            Qt.Horizontal,
            role=Qt.DisplayRole)
        if label_str:
            font = model.headerData(
                column,
                Qt.Horizontal,
                role=Qt.FontRole)

            painter.setFont(font)

            pen = QPen()
            pen.setColor(QColor(0, 0, 0))
            painter.setPen(pen)

            painter.drawText(
                rect,
                Qt.AlignCenter,
                label_str)


##############################################################################


def get_default_stylesheet():
    '''
    Get default stylesheet for QHeaderView.

    Returns:
        default_style_sheet (str):
    '''
    default_style_sheet = '''
QHeaderView::section {
    padding-left: 0px;
    padding-right: 0px;
    padding-top: 8px;
    padding-bottom: 8px;
}
QHeaderView::down-arrow {
    image: url(down_arrow.png);
}
QHeaderView::up-arrow {
    image: url(up_arrow.png);
}
QTreeView {
    background-color: rgb(56,56,56);
    selection-background-color: rgb(120,120,120);
    selection-color: rgb(255,204,51);
    show-decoration-selected: 1;
}
'''
    return default_style_sheet