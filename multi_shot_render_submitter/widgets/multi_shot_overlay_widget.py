

import copy
import logging


from Qt.QtWidgets import (QApplication, QWidget, QVBoxLayout, QSizePolicy)
from Qt.QtGui import (QFont, QColor, QCursor, QPainter, QBrush, QPen, QPixmap)
from Qt.QtCore import (Qt, QModelIndex, QRectF, QPoint, Signal)

from srnd_multi_shot_render_submitter import utils


from srnd_multi_shot_render_submitter.constants import Constants
constants = Constants()


class MultiShotOverlayWidget(QWidget):
    '''
    A widget to draw over entire QTreeView and be raised above it.
    This allows painting over top the QTreeView delegates and the
    view itself, using one co-ordinate system.

    Args:
        tree_view (QTreeView): the view this overlay widget is drawing over.
            Note: Is required to gather QModelIndices & QPoint positions, to visualize dependencies etc.
    '''

    logMessage = Signal(str, int)

    def __init__(self, tree_view, parent=None):
        super(MultiShotOverlayWidget, self).__init__(parent=parent)

        self._tree_view = tree_view
        self._active = True

        self._draw_all_interactive_overlays = False
        # Cached QModelIndices and QPoints
        self._interactive_item_current_qmodelindex = None
        self._interactive_source_qmodelindex = None
        self._interactive_destination_qmodelindex = None
        self._interactive_item_current_point = None
        self._interactive_source_point = None
        self._interactive_destination_point = None

        # Overlay mode to show all all depends as arrows
        self._dependencies_points = list()
        self._draw_all_dependency_overlays = False

        self._dependency_arrow_colour = [0, 255, 255]

        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setMouseTracking(False)

        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setLayout(layout)

        self._update_size_to_match_parent()

        self._cursor = QCursor(QPixmap(constants.WAIT_ICON_PATH))


    def set_active(self, active):
        '''
        Set whether this widget will update as expected when next requested.

        Args:
            active (bool):
        '''
        self._active = active


    def get_active(self):
        '''
        Get whether this widget will update as expected when next requested.

        Returns:
            active (bool):
        '''
        return self._active
    

    def set_dependency_arrow_colour(self, rgb):
        '''
        Set and cache the desired dependency arrows colours.

        Args:
            rgb (tuple):         
        '''
        msg = 'Setting dependency arrows colours to rgb: "{}"'.format(rgb)
        self.logMessage.emit(msg, logging.INFO)          
        self._dependency_arrow_colour = rgb
        self.update()


    def requires_overlays_to_draw(self):
        '''
        Get whether this widget requires any overlays to be drawn.

        Returns:
            requires_overlays_to_draw (bool):
        '''
        if not self._active:
            return False
        if self._draw_all_interactive_overlays:
            return True
        if self._draw_all_dependency_overlays:
            return True
        return False


    def clear_all(self):
        '''
        Clear all cached overlay details for all dependencies and interactive mode.
        '''
        value_changed1 = self.clear_interactive_overlays()
        value_changed2 = self.clear_dependencies_points(update=False)
        if any([value_changed1, value_changed2]):
            self.update()


    def update_overlays(self):
        '''
        Destory the cached overlays QPoints, and recalculate for current viewport and sizes.
        '''
        if not self._tree_view:
            return
        if not self.requires_overlays_to_draw():
            self.lower()
            return
        self._update_size_to_match_parent()
        # Destory cached dependency overlays and recalculate
        if self._draw_all_dependency_overlays:
            self._update_dependency_overlays_points(update=False)
        # Clear all dependency overlays data
        else:
            self.clear_dependencies_points(update=False)
        # Destory cached interactive overlays and recalculate
        if self._draw_all_interactive_overlays:
            self._update_interactive_overlay_points(update=False)
        # Clear all interactive overlays data
        else:
            self.clear_interactive_overlays()
        # Repaint with new cached QPoint positions, relating to latest QModelIndices
        self.update()


    def _update_size_to_match_parent(self):
        '''
        Force this overlay widget to match the tree view viewport size.
        '''
        if not self._tree_view:
            return
        viewport = self._tree_view.viewport()
        if viewport and self._active:
            self.setGeometry(viewport.geometry())


    ##########################################################################
    # Dependencies points methods


    def set_draw_all_dependency_overlays(self, value=False, update=True):
        '''
        Set whether to draw all the dependency overlays.
        NOTE: When toggling off draw all dependency overlays the cache is destroyed.

        Args:
            value (bool):
            update (bool): whether to update the widget with update / repaint
        '''
        msg = 'Set Draw All Dependency Overlays Set To: "{}"'.format(value)
        self.logMessage.emit(msg, logging.WARNING)
        value = bool(value)
        self._draw_all_dependency_overlays = value
        if value:
            self.set_active(True)
            self.update_overlays()
            # self._update_dependency_overlays_points(update=update)
        else:
            self.clear_dependencies_points(update=update)


    def get_draw_all_dependency_overlays(self):
        '''
        Get whether to draw all the dependency overlays.

        Returns:
            value (bool):
        '''
        return self._draw_all_dependency_overlays


    def toggle_draw_all_dependency_overlays(self):
        '''
        Toggle draw all dependencies overlays, depending on current state.
        '''
        value = bool(self._draw_all_dependency_overlays)
        self.set_draw_all_dependency_overlays(not value)


    def set_dependencies_points(self, dependencies_points=None, update=True):
        '''
        Set all the QPoint positions to visualize as depedencies.

        Returns:
            dependencies_points (list): a list of lists of QPoints.
                each sub list zero item is the source point of dependencies.
            update (bool): whether to update the widget with update / repaint
        '''
        if not dependencies_points or not isinstance(dependencies_points, (list, tuple)):
            dependencies_points = list()
        self._dependencies_points = list(dependencies_points)
        if update:
            self.update()


    def get_dependencies_points(self):
        '''
        Get all the QPoint positions to visualize as depedencies.

        Returns:
            dependencies_points (list):
        '''
        return self._dependencies_points


    def clear_dependencies_points(self, update=True):
        '''
        Clear all the cached dependencies points.

        Args:
            update (bool):

        Returns:
            value_changed (bool):
        '''
        previous_dependencies_points = copy.copy(self._dependencies_points)
        self._dependencies_points = list()
        if update:
            self.update()
        return self._dependencies_points != previous_dependencies_points


    def has_dependencies_overlays(self):
        '''
        Get whether this overlay widget has any current dependencies points to visualize.

        Returns:
            has_dependencies_overlays (bool):
        '''
        return self._active and bool(self._dependencies_points)


    def _update_dependency_overlays_points(self, update=True):
        '''
        Gather dependency overlays QPoints in relation to view.

        Args:
            update (bool):

        Returns:
            value_changed (bool):
        '''
        if not self._active:
            return False
        previous_qpoints = self._dependencies_points
        self.clear_dependencies_points(update=False)
        if not self._tree_view:
            return
        model = self._tree_view.model()
        if not model:
            return
        qpoints = list()
        column_count = model.columnCount(QModelIndex())
        header_height = self._tree_view.header().height()
        env_offset = None
        for qmodelindex in model.get_environment_items_indices():
            if not qmodelindex.isValid():
                continue

            # If the QModelIndex is hidden to MSRS view, then skip drawing overlays
            if self._tree_view.isIndexHidden(qmodelindex):
                continue

            # If this environment is within a group item, then check if the QModelIndex of view is expanded
            item = qmodelindex.internalPointer()
            if item.parent():
                parent_is_group = item.parent().is_group_item()
                if parent_is_group and not self._tree_view.isExpanded(qmodelindex.parent()):
                    continue

            row_height_half = int(self._tree_view.rowHeight(qmodelindex) * 0.5)
            env_indices = model.get_item_wait_on_target_indices(qmodelindex)
            if env_indices:
                env_indices.insert(0, qmodelindex)
                _qpoints = list()
                for _qmodelindex in env_indices:
                    if not _qmodelindex.isValid() or self._tree_view.isIndexHidden(_qmodelindex):
                        continue
                    _item = _qmodelindex.internalPointer()
                    if _item.parent():
                        _parent_is_group = _item.parent().is_group_item()
                        if _parent_is_group and not self._tree_view.isExpanded(_qmodelindex.parent()):
                            continue
                    rect = self._tree_view.visualRect(_qmodelindex)
                    qpoint = rect.topLeft() + QPoint(25, row_height_half)
                    if env_offset:
                        qpoint = qpoint + env_offset
                    _qpoints.append(qpoint)
                if _qpoints:
                    qpoints.append(_qpoints)
                    if env_offset:
                        env_offset = None
                    else:
                        env_offset = QPoint(30, 0)
            for c in range(1, column_count, 1):
                qmodelindex_column = qmodelindex.sibling(qmodelindex.row(), c)
                if not qmodelindex_column.isValid():
                    continue
                if self._tree_view.isIndexHidden(qmodelindex_column):
                    continue
                pass_for_env_indices = model.get_item_wait_on_target_indices(qmodelindex_column)
                if pass_for_env_indices:
                    pass_for_env_indices.insert(0, qmodelindex_column)
                    _qpoints = list()
                    for _qmodelindex in pass_for_env_indices:
                        if not _qmodelindex.isValid() or self._tree_view.isIndexHidden(_qmodelindex):
                            continue
                        _item = _qmodelindex.internalPointer()
                        if _item.parent():
                            _parent_is_group = _item.parent().is_group_item()
                            if _parent_is_group and not self._tree_view.isExpanded(_qmodelindex.parent()):
                                continue
                        rect = self._tree_view.visualRect(_qmodelindex)
                        qpoint = rect.topLeft() + QPoint(25, row_height_half)
                        _qpoints.append(qpoint)
                    if _qpoints:
                        qpoints.append(_qpoints)
        self._dependencies_points = qpoints
        if update:
            self.update()
        return qpoints != previous_qpoints


    ##########################################################################
    # Interactive points methods


    def set_draw_all_interactive_overlays(self, value=False):
        '''
        Set whether to draw all interactive overlays or not.

        Args:
            value (bool):
        '''
        msg = 'Set Draw All Interactive Overlays Set To: "{}"'.format(value)
        self.logMessage.emit(msg, logging.WARNING)
        value = bool(value)
        self._draw_all_interactive_overlays = value
        if value:
            self.set_active(True)


    def get_draw_all_interactive_overlays(self):
        '''
        Get whether to draw all interactive overlays or not.

        Returns:
            value (bool):
        '''
        return self._draw_all_interactive_overlays


    def set_interactive_item_current_qmodelindex(self, qmodelindex):
        '''
        Store the current QModelIndex of tree view closest to mouse.

        Args:
            qmodelindex (QModelIndex):
        '''
        self._interactive_item_current_qmodelindex = qmodelindex


    def get_interactive_source_qmodelindex(self):
        '''
        Get the interactively placed source position as QModelIndex in tree view.

        Returns:
            qmodelindex (QModelIndex):
        '''
        return self._interactive_source_qmodelindex


    def set_interactive_source_qmodelindex(self, qmodelindex):
        '''
        Store the interactively placed source position as QModelIndex in tree view.

        Args:
            qmodelindex (QModelIndex):
        '''
        self._interactive_source_qmodelindex = qmodelindex


    def get_interactive_destination_qmodelindex(self):
        '''
        Get the interactively placed destination position as QModelIndex in tree view.

        Returns:
            qmodelindex (QModelIndex):
        '''
        return self._interactive_destination_qmodelindex


    def set_interactive_destination_qmodelindex(self, qmodelindex):
        '''
        Store the interactively placed destination position as QModelIndex in tree view.

        Args:
            qmodelindex (QModelIndex):
        '''
        self._interactive_destination_qmodelindex = qmodelindex


    def has_interactive_overlays(self):
        '''
        Get whether have any current interactive overlay points to draw.

        Returns:
            has_interactive_overlays (bool):
        '''
        return self._active and any([
            self._interactive_item_current_qmodelindex,
            self._interactive_source_qmodelindex,
            self._interactive_destination_qmodelindex])


    def has_interactive_points_defined(self):
        '''
        Check whether the source and destination dependency
        points have been defined, when in interactive mode.

        Returns:
            has_interactive_points_defined (bool):
        '''
        return all([
            self._interactive_source_qmodelindex,
            self._interactive_destination_qmodelindex])


    def clear_interactive_overlays(self):
        '''
        Clear all the cached QModelIndices and QPoints for visualizing interactive overlays.

        Returns:
            value_change (bool):
        '''
        value_changed = any([
            self._interactive_item_current_qmodelindex,
            self._interactive_source_qmodelindex,
            self._interactive_destination_qmodelindex])
        self._interactive_item_current_qmodelindex = None
        self._interactive_source_qmodelindex = None
        self._interactive_destination_qmodelindex = None
        self._interactive_item_current_point = None
        self._interactive_source_point = None
        self._interactive_destination_point = None
        return value_changed


    def _update_interactive_overlay_points(self, update=True):
        '''
        Gather and cache the interactive overlay points from QModelIndices.

        Args:
            update (bool):

        Returns:
            value_changed (bool):
        '''
        if not self._active:
            return False

        previous_values = [
            self._interactive_item_current_point,
            self._interactive_source_point,
            self._interactive_destination_point]

        self._interactive_item_current_point = None
        self._interactive_source_point = None
        self._interactive_destination_point = None

        if self._interactive_item_current_qmodelindex and self._interactive_item_current_qmodelindex.isValid():
            row_height_half = int(self._tree_view.rowHeight(self._interactive_item_current_qmodelindex) * 0.5)
            rect = self._tree_view.visualRect(self._interactive_item_current_qmodelindex)
            self._interactive_item_current_point = rect.topLeft() + QPoint(25, row_height_half)

        if self._interactive_source_qmodelindex and self._interactive_source_qmodelindex.isValid():
            row_height_half = int(self._tree_view.rowHeight(self._interactive_source_qmodelindex) * 0.5)
            rect = self._tree_view.visualRect(self._interactive_source_qmodelindex)
            self._interactive_source_point = rect.topLeft() + QPoint(25, row_height_half)

        if self._interactive_destination_qmodelindex and self._interactive_destination_qmodelindex.isValid():
            row_height_half = int(self._tree_view.rowHeight(self._interactive_destination_qmodelindex) * 0.5)
            rect = self._tree_view.visualRect(self._interactive_destination_qmodelindex)
            self._interactive_destination_point = rect.topLeft() + QPoint(25, row_height_half)

        if update:
            self.update()

        new_values = [
            self._interactive_item_current_point,
            self._interactive_source_point,
            self._interactive_destination_point]

        return new_values != previous_values


    ##########################################################################


    def paintEvent(self, event):
        '''
        Paint cached dependency overlay QPoints or cached interactive placed points.
        NOTE: When external QTreeview viewport is resized or scrolled, the cache is updated.

        Args:
            event (QPaintEvent)
        '''
        if not self._active or not self.requires_overlays_to_draw():
            QWidget.paintEvent(self, event)
            self.lower()
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.HighQualityAntialiasing)

        if self.has_interactive_overlays():
            self._paint_dependencies_for_interactive_placement(painter)

        if self.has_dependencies_overlays() and self._draw_all_dependency_overlays:
            self._paint_all_dependency_overlays(painter)

        self.raise_()


    def _paint_all_dependency_overlays(self, painter):
        '''
        Paint all the cached dependency overlays.

        Args:
            painter (QPainter):
        '''
        for points in self._dependencies_points:
            for i in range(1, len(points), 1):
                pen = QPen()
                pen.setWidth(2)
                pen.setColor(QColor(*self._dependency_arrow_colour))
                pen.setStyle(Qt.CustomDashLine)
                pen.setDashPattern([1, 2])
                painter.setPen(pen)
                painter.drawLine(points[0],  points[i])

                angle = utils.geometry_angle_bewteen_two_points(
                    points[0].x(),
                    points[0].y(),
                    points[i].x(),
                    points[i].y())

                polygon = utils.get_triangle_polygon(
                    points[i],
                    angle,
                    5)
                pen.setStyle(Qt.SolidLine)
                painter.setPen(Qt.NoPen)
                brush = QBrush(QColor(*self._dependency_arrow_colour))
                painter.setBrush(brush)
                painter.drawPolygon(polygon)

                brush = QBrush(QColor(*self._dependency_arrow_colour))
                painter.setBrush(brush)
                rect_source = QRectF(
                    points[0].x() - 5,
                    points[0].y() - 5,
                    10,
                    10)
                painter.drawEllipse(rect_source)


    def _paint_dependencies_for_interactive_placement(self, painter):
        '''
        Paint all the cached interactive placement points.

        Args:
            painter (QPainter):
        '''
        has_interactive_points_defined = self.has_interactive_points_defined()

        # Draw a circle on nearest item in view (on left hand side of delegate widget)
        rect_current_item = None
        if self._interactive_item_current_point:
            rect_current_item = QRectF(
                self._interactive_item_current_point.x() - 12,
                self._interactive_item_current_point.y() - 12,
                24,
                24)
            if not has_interactive_points_defined:
                colour = QColor(*self._dependency_arrow_colour)
                pen = QPen()
                pen.setWidth(4)
                pen.setColor(colour)
                painter.setPen(pen)
                painter.drawEllipse(rect_current_item)

        msg = None
        if not self._interactive_source_point:
            msg = 'Left Click Item Which Should WAIT On...'
        elif not self._interactive_destination_point:
            msg = 'Left Click What The Item Should WAIT On...'
        else:
            msg = 'Press Enter To Complete Or Backspace To Remove Point'

        if msg:
            pos = self.mapFromGlobal(QCursor.pos())
            rect_text = QRectF(pos.x() + 20, pos.y(), 500, 40)

            font = QFont()
            font.setItalic(True)
            font.setBold(True)
            font.setPointSize(10)
            painter.setFont(font)

            pen = QPen()
            pen.setColor(QColor(255, 255, 255))
            painter.setPen(pen)

            painter.drawText(rect_text, msg)

        # The already placed source point
        rect_source = None
        if self._interactive_source_point:
            colour = QColor(*self._dependency_arrow_colour)
            pen = QPen()
            pen.setWidth(4)
            pen.setColor(colour)
            painter.setPen(pen)
            rect_source = QRectF(
                self._interactive_source_point.x() - 12,
                self._interactive_source_point.y() - 12,
                24,
                24)
            painter.drawEllipse(rect_source)

        # The already placed destination point
        rect_destination = None
        if self._interactive_destination_point:
            colour = QColor(*self._dependency_arrow_colour)
            pen = QPen()
            pen.setWidth(4)
            pen.setColor(colour)
            painter.setPen(pen)
            rect_destination = QRectF(
                self._interactive_destination_point.x() - 12,
                self._interactive_destination_point.y() - 12,
                24,
                24)
            painter.drawEllipse(rect_destination)

        # Draw line between initial point and preview of next point, or actual next point
        if self._interactive_source_point and any([
                self._interactive_item_current_point,
                self._interactive_destination_point]):
            rect = rect_destination if rect_destination else rect_current_item
            if rect:
                pen = QPen()
                pen.setWidth(4)
                pen.setColor(QColor(255, 255, 0))
                pen.setStyle(Qt.CustomDashLine)
                pen.setDashPattern([1, 3])
                painter.setPen(pen)
                painter.drawLine(rect_source.center(), rect.center())

                p1 = rect_source.center()
                p2 = rect.center()
                angle = utils.geometry_angle_bewteen_two_points(
                    p1.x(),
                    p1.y(),
                    p2.x(),
                    p2.y())

                pen.setStyle(Qt.SolidLine)
                painter.setPen(Qt.NoPen)
                brush = QBrush(QColor(255, 255, 0))
                painter.setBrush(brush)
                polygon = utils.get_triangle_polygon(
                    rect_source.center(),
                    angle,
                    7)
                painter.drawPolygon(polygon)

                polygon = utils.get_triangle_polygon(
                    rect.center(),
                    angle,
                    5)
                painter.drawPolygon(polygon)