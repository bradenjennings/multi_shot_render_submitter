

import logging
import os

from Qt.QtWidgets import (QTreeView, QItemDelegate, QComboBox,
    QLineEdit, QCheckBox, QFrame, QHBoxLayout)
from Qt.QtGui import QIcon, QFont
from Qt.QtCore import (Qt, QSortFilterProxyModel, QSize,
    Signal, QModelIndex, QEvent)

import srnd_qt.base.utils
from srnd_qt.ui_framework.models.base_abstract_item_model import BaseAbstractItemDelegates

from srnd_multi_shot_render_submitter.widgets import post_tasks_combo_box
from srnd_multi_shot_render_submitter.widgets import validation_hints_widget


##############################################################################


class SummaryDelegates(BaseAbstractItemDelegates):
    '''
    A delegate with multiple widgets for different columns.

    Args:
        debug_mode (bool):
        summary_model (SummaryModel): pass a pointer to the single summary model
    '''

    logMessage = Signal(str, int)

    def __init__(
            self,
            debug_mode=False,
            summary_model=None,
            parent=None,
            **kwargs):
        super(SummaryDelegates, self).__init__(parent=parent)
        self._summary_model = summary_model


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
           return None

        model = qmodelindex.model()
        source_model = model
        if isinstance(model, QSortFilterProxyModel):
            qmodelindex = model.mapToSource(qmodelindex)
            source_model = model.sourceModel()

        c = qmodelindex.column()
        item = qmodelindex.internalPointer()
        if not item or item.is_group_item():
            return None

        is_environment_item = item.is_environment_item()

        widget = None
        if c == source_model.COLUMN_OF_VALIDATION and is_environment_item:
            widget = validation_hints_widget.ValidationHintsWidget(
                critical_count=item.get_validation_warning_counter(),
                warning_count=item.get_validation_critical_counter(),
                parent=parent_widget)
            widget.setContextMenuPolicy(Qt.NoContextMenu)
            widget.setFixedHeight(source_model.NORMAL_ROW_HEIGHT)

        elif c == source_model.COLUMN_OF_POST_TASK:
            post_tasks_combo_box_object = self.get_post_tasks_combo_box_object()
            widget = post_tasks_combo_box_object(
                item,
                qmodelindex,
                parent=parent_widget)
            widget.setFixedHeight(source_model.NORMAL_ROW_HEIGHT)
            widget.postTasksChanged.connect(
                lambda *x: self.commit_widget(widget=widget))
            widget.postTasksChanged.connect(
                lambda *x: self._commit_other_post_task_widgets(widget=widget))
            widget.setFocusPolicy(Qt.NoFocus)

        elif c == source_model.COLUMN_OF_KOBA_SHOTSUB:
            widget = QCheckBox(parent=parent_widget)
            widget.toggled.connect(
                lambda *x: self.commit_widget(widget=widget))
            widget.toggled.connect(
                lambda *x: self._commit_other_koba_shotsub_widgets(widget=widget))
            widget.setFocusPolicy(Qt.NoFocus)

        elif c == source_model.COLUMN_OF_SUBMISSION_NOTE:
            note_override = item.get_note_override()
            item.set_note_override_submission(note_override or None)

            widget = _LineEditWithFrame(parent=parent_widget)
            # widget = QLineEdit(parent=parent_widget)
            widget.setFixedHeight(source_model.NORMAL_ROW_HEIGHT)
            line_edit = widget.get_line_edit()
            line_edit.setText(note_override or str())
            line_edit.textChanged.connect(
                lambda *x: self.commit_widget(widget=widget))
            line_edit.textChanged.connect(
                lambda *x: self._commit_other_note_widgets(widget=widget))

        return widget


    def commit_widget(self, widget=None, *args, **kwargs):
        '''
        When custom editor has completed editing data, emit
        commitData, to write data back to model.

        Args:
            widget (QtGui.QWidget):
        '''
        if widget:
            self.commitData.emit(widget)


    def _commit_other_post_task_widgets(self, widget=None, *args, **kwargs):
        '''
        When post task changed in any one row, then apply the state
        to all other selected items of selection.

        Args:
            widget (PostTasksComboBoxWidget):
        '''
        if not widget:
            return
        if not self._summary_model:
            return
        is_environment = widget.is_environment_item()
        post_tasks = widget.get_checked_post_tasks()
        summary_view = widget.parent().parent()
        for qmodelindex in summary_view.selectedIndexes():
            if not qmodelindex.isValid():
                continue
            qmodelindex_post_task = qmodelindex.sibling(
                qmodelindex.row(),
                self._summary_model.COLUMN_OF_POST_TASK)
            _widget = summary_view.indexWidget(qmodelindex_post_task)
            if not _widget or _widget == widget:
                continue
            # Must be same type
            if _widget.is_environment_item() != is_environment:
                continue
            _widget.set_post_task_check_states(post_tasks)
            self.commitData.emit(_widget)


    def _commit_other_koba_shotsub_widgets(self, widget=None, *args, **kwargs):
        '''
        When Koba shotsub checkbox changed in any one row, then apply the state
        to all other selected items of selection.

        Args:
            widget (QCheckBox):
        '''
        if not widget:
            return
        if not self._summary_model:
            return
        koba_shotsub = widget.isChecked()
        summary_view = widget.parent().parent()
        for qmodelindex in summary_view.selectedIndexes():
            if not qmodelindex.isValid():
                continue
            qmodelindex_post_task = qmodelindex.sibling(
                qmodelindex.row(),
                self._summary_model.COLUMN_OF_KOBA_SHOTSUB)
            _widget = summary_view.indexWidget(qmodelindex_post_task)
            if not _widget or _widget == widget:
                continue
            _widget.setChecked(koba_shotsub)
            self.commitData.emit(_widget)


    def _commit_other_note_widgets(self, widget=None, *args, **kwargs):
        '''
        When note line edit changed in any one row, then apply the state
        to all other selected items of selection.

        Args:
            widget (QCheckBox):
        '''
        if not widget:
            return
        if not self._summary_model:
            return
        submission_note = str(widget.text())
        summary_view = widget.parent().parent()
        for qmodelindex in summary_view.selectedIndexes():
            if not qmodelindex.isValid():
                continue
            qmodelindex_note = qmodelindex.sibling(
                qmodelindex.row(),
                self._summary_model.COLUMN_OF_SUBMISSION_NOTE)
            _widget = summary_view.indexWidget(qmodelindex_note)
            if not _widget or _widget == widget:
                continue
            _widget.setText(submission_note)
            self.commitData.emit(_widget)


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

        c = qmodelindex.column()
        _qmodelindex = qmodelindex

        model = qmodelindex.model()
        source_model = model
        if isinstance(model, QSortFilterProxyModel):
            qmodelindex = model.mapToSource(qmodelindex)
            source_model = model.sourceModel()

        item = qmodelindex.internalPointer()
        if not item:
            return

        is_environment_item = item.is_environment_item()
        is_group_item = item.is_group_item()

        if c == source_model.COLUMN_OF_VALIDATION and is_environment_item:
            count = item.get_validation_critical_counter()
            widget.set_validation_critical_counter(count)

            count = item.get_validation_warning_counter()
            widget.set_validation_warning_counter(count)

            widget.update()

        elif c == source_model.COLUMN_OF_KOBA_SHOTSUB and is_environment_item:
            koba_shotsub = item.get_koba_shotsub()
            widget_koba_shotsub = widget.isChecked()
            koba_shotsub_changed = koba_shotsub != widget_koba_shotsub
            if koba_shotsub:
                widget.setChecked(koba_shotsub)

        elif c == source_model.COLUMN_OF_SUBMISSION_NOTE and not is_group_item:
            note_override = item.get_note_override_submission()
            widget_note_override = str(widget.text())
            note_override_changed = note_override != widget_note_override
            if note_override_changed:
                widget.setText(note_override or str())

        else:
            QItemDelegate.setEditorData(
                self,
                widget,
                qmodelindex)


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

        _qmodelindex = qmodelindex

        model = qmodelindex.model()
        source_model = model
        if isinstance(model, QSortFilterProxyModel):
            qmodelindex = model.mapToSource(qmodelindex)
            source_model = model.sourceModel()

        c = qmodelindex.column()
        item = qmodelindex.internalPointer()
        if not item:
            return

        is_environment_item = item.is_environment_item()
        is_group_item = item.is_group_item()

        if c == source_model.COLUMN_OF_POST_TASK and not is_group_item:
            post_tasks = widget.get_checked_post_tasks(update_summary=True)
            item.set_post_tasks(post_tasks)

        elif c == source_model.COLUMN_OF_KOBA_SHOTSUB and is_environment_item:
            koba_shotsub = widget.isChecked()
            item.set_koba_shotsub(koba_shotsub)

        elif c == source_model.COLUMN_OF_SUBMISSION_NOTE and not is_group_item:
            note_override = item.get_note_override_submission()
            widget_note_override = str(widget.text())
            note_override_changed = note_override != widget_note_override
            if note_override_changed:
                item.set_note_override_submission(widget_note_override)

        else:
            QItemDelegate.setModelData(
                self,
                widget,
                abstract_item_model,
                qmodelindex)


    ##########################################################################


    def get_post_tasks_combo_box_object(self):
        '''
        Get the post tasks combobox widget object in uninstantiated state.
        Note: Reimplemented to return host app specific widget.

        Returns:
            post_tasks_combo_box (PostTasksComboBoxWidget):
        '''
        from srnd_multi_shot_render_submitter.widgets import post_tasks_combo_box
        return post_tasks_combo_box.PostTasksComboBoxWidget


    ##########################################################################


    # def sizeHint(self, option_style, qmodelindex):
    #     '''
    #     Reimplemented method.
    #     '''
    #     model = qmodelindex.model()
    #     source_model = model
    #     if isinstance(model, QSortFilterProxyModel):
    #         qmodelindex = model.mapToSource(qmodelindex)
    #         source_model = model.sourceModel()
    #     return QSize(0, source_model.NORMAL_ROW_HEIGHT


##############################################################################


class _LineEditWithFrame(QFrame):
    '''
    Wrap the QLineEdit in a frame, because cannot get the focus to work
    as desired within SummaryView.
    NOTE: The user should be able to multi select rows, and then select
    in one note QLineEdit, and focus on the one widget without losing selection in view.
    NOTE: This behaviour was problematic because SummaryView is set to SelectRows selection
    behaviour, however some columns purposefully don't return ItemIsSelectable flag.
    '''

    def __init__(self, text=str(), parent=None):
        super(_LineEditWithFrame, self).__init__(parent=parent)
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setLayout(layout)
        self._line_edit = QLineEdit(str(text))
        self._line_edit.setContextMenuPolicy(Qt.NoContextMenu)
        self._line_edit.setStyleSheet('background-color: rgba(0, 0, 0, 0);')
        layout.addWidget(self._line_edit)
        # when return is pressed ensure to clear focus on line edit
        self._line_edit.returnPressed.connect(self._line_edit.clearFocus)

    def get_line_edit(self):
        return self._line_edit

    def text(self):
        return self._line_edit.text()

    def setText(self, text):
        return self._line_edit.setText(text)

    def mousePressEvent(self, event):
        if event.buttons() == Qt.RightButton:
            event.ignore()
            return
        QFrame.mousePressEvent(self, event)