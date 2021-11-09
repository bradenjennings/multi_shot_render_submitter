

import collections
import logging
import os

from Qt.QtWidgets import QLineEdit, QItemDelegate
from Qt.QtGui import QPixmap
from Qt.QtCore import (Qt, QSize, Signal)

from srnd_qt.ui_framework.models.base_abstract_item_model import BaseAbstractItemDelegates


##############################################################################


class MultiShotRenderDelegates(BaseAbstractItemDelegates):
    '''
    A delegate with multiple widgets for different columns.
    '''

    logMessage = Signal(str, int)

    def __init__(self, debug_mode=False, parent=None):
        super(MultiShotRenderDelegates, self).__init__(
            debug_mode=debug_mode,
            parent=parent)


    def createEditor(self, parent_widget, option_style, qmodelindex):
        '''
        Create different editors for different columns.
        Reimplemented virtual method.

        Args:
            parent_widget (QtGui.QWidget):
            option_style (QtGui.QStyleOptionViewItem):
            qmodelindex (QtCore.QModelIndex):

        Returns:
            widget (QtGui.QWidget):
        '''
        if not qmodelindex.isValid():
           return

        c = qmodelindex.column()
        item = qmodelindex.internalPointer()
        if not item:
            return None

        # NOTE: Group items do not need a widget, and are instead provided by models data method.
        if item.is_group_item():
            if c == 0:
                return QItemDelegate.createEditor(
                    self,
                    parent_widget,
                    option_style,
                    qmodelindex)
            # Default delegate widgets not desired for other group columns
            else:
                return

        msrs_view = parent_widget.parent()

        # NOTE: Void style disabled passes do not require a delegate widget at all
        is_pass_for_env_item = item.is_pass_for_env_item()
        if is_pass_for_env_item and not item.get_enabled() and \
                msrs_view.get_disabled_passes_are_void_style():
            return None

        model = qmodelindex.model()

        show_environment_thumbnails = model.get_show_environment_thumbnails()
        resized_thumbnail_path = None

        if is_pass_for_env_item:
            environment_item = item.get_environment_item()
            queued = item.get_queued()
            enabled = item.get_enabled()
        else:
            environment_item = item
            queued = True
            enabled = True
            if show_environment_thumbnails:
                if msrs_view:
                    thumbnail_prep_thread = msrs_view.get_thumbnail_prep_thread()
                    if thumbnail_prep_thread:
                        resized_thumbnail_path = thumbnail_prep_thread.get_resized_thumbnail_from_results(
                            environment_item.get_oz_area())
                    else:
                        resized_thumbnail_path = environment_item.get_thumbnail_path()

        ######################################################################
        # Build the render pass for env widget with required initial state

        is_pass = c >= 1
        widget_object = self.get_render_pass_for_env_object()
        widget = widget_object(
            queued=queued,
            enabled=enabled,
            is_pass=is_pass,
            include_thumbnail=show_environment_thumbnails,
            thumbnail_path=resized_thumbnail_path,
            parent=parent_widget)

        if show_environment_thumbnails:
            widget.setFixedHeight(model.THUMBNAIL_HEIGHT)
        else:
            widget.setFixedHeight(model.NORMAL_ROW_HEIGHT)

        widget.update_overrides_from_item(item, model=model)

        widget.queuedToggled.connect(
            lambda *x: self.commit_widget(widget=widget))
        widget.enabledToggled.connect(
            lambda *x: self.commit_widget(widget=widget))

        return widget


    def setEditorData(self, widget, qmodelindex):
        '''
        Set editor display and editable data from the data model at index.
        Reimplemented virtual method.

        Args:
            widget (QtGui.QWidget):
            qmodelindex (QtCore.QModelIndex):
        '''
        if not qmodelindex.isValid():
           return
        if not widget:
            return

        c = qmodelindex.column()
        item = qmodelindex.internalPointer()

        if item.is_group_item():
            return QItemDelegate.setEditorData(self, widget, qmodelindex)

        is_pass_for_env_item = item.is_pass_for_env_item()
        if is_pass_for_env_item:
            item = item.sibling(c)

        model = qmodelindex.model()

        widget.update_overrides_from_item(item, model=model)


    def setModelData(self, widget, abstract_item_model, qmodelindex):
        '''
        Set model data from editor value at qmodelindex.
        Reimplemented virtual method.

        Args:
            widget (QtGui.QWidget):
            abstract_item_model (QtGui.QAbstractItemModel):
            qmodelindex (QtCore.QModelIndex):
        '''
        if not qmodelindex.isValid():
           return
        if not widget:
            return

        c = qmodelindex.column()
        item = qmodelindex.internalPointer()

        if item.is_group_item():
            return QItemDelegate.setModelData(self, widget, abstract_item_model, qmodelindex)

        is_pass_for_env_item = item.is_pass_for_env_item()
        if is_pass_for_env_item:
            item = item.sibling(c)

        if not item:
            return

        model = qmodelindex.model()

        if is_pass_for_env_item:
            queued = item.get_queued()
            widget_queued = widget.get_queued()
            queued_changed = queued != widget_queued
            if queued_changed:
                item.set_queued(widget_queued)

            widget_enabled = widget.get_enabled()

            # If queued or enabled just changed update cached renderable counts
            if any([queued_changed]): # enabled_changed
                renderable_offset = 1 if (widget_queued and widget_enabled) else -1
                item._update_renderable_count_for_index(
                    qmodelindex,
                    renderable_offset=renderable_offset)
                model.headerDataChanged.emit(Qt.Horizontal, c, c)
                # Request frames to be resolved where just middle clicked
                model.framesResolveRequest.emit(qmodelindex)


    def sizeHint(self, option_style, qmodelindex):
        '''
        Reimplemented method.
        '''
        if not qmodelindex.isValid():
            return QItemDelegate.sizeHint(self, option_style, qmodelindex)
        model = qmodelindex.model()
        if model.get_show_environment_thumbnails():
            return QSize(0, model.THUMBNAIL_HEIGHT)
        elif qmodelindex.internalPointer().is_group_item():
            return QSize(0, model.GROUP_HEIGHT)
        else:
            return QSize(0, model.NORMAL_ROW_HEIGHT)


    ##########################################################################


    def get_render_pass_for_env_object(self):
        '''
        Get the render pass for env widget object in uninstantiated state.
        Note: Reimplemented to return host app specific widget.

        Returns:
            render_pass_for_env_widget (RenderPassForEnvWidget):
        '''
        from srnd_multi_shot_render_submitter.widgets import render_pass_for_env_widget
        return render_pass_for_env_widget.RenderPassForEnvWidget