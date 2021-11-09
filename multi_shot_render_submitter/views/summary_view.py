

import functools
import logging
import os

from Qt.QtWidgets import QTreeView, QHeaderView
from Qt.QtCore import Qt, QSortFilterProxyModel, QModelIndex, Signal

from srnd_qt.ui_framework.views import base_tree_view

from srnd_multi_shot_render_submitter.constants import Constants
constants = Constants()

ICONS_DIR = os.path.join(
    os.getenv('SRND_MULTI_SHOT_RENDER_SUBMITTER_ROOT', str()),
    'icons')
SRND_QT_ROOT = os.getenv('SRND_QT_ROOT')
SRND_QT_ICONS_DIR = os.path.join(SRND_QT_ROOT, 'res', 'icons')


########################################################################################


class SummaryView(base_tree_view.BaseTreeView):
    '''
    A view to show a summary of all Multi Shot Render operations
    about to be submitted. Hints are also shown about any validation issues.
    Reimplement this model for a particular host app (if required).
    Note: This is designed to work with MultiShotRenderableProxyModel (and SummaryModel).

    Args:
        show_render_categories (bool):
    '''

    logMessage = Signal(str, int)
    updateMainViewRequest = Signal(QModelIndex)

    def __init__(
            self,
            show_render_categories=False,
            parent=None):
        super(SummaryView, self).__init__(
            include_context_menu=True,
            palette=None,
            parent=parent)

        self.HOST_APP = constants.HOST_APP
        self.COLUMN_0_WIDTH = 250
        self._show_render_categories = bool(show_render_categories)

        self._copied_post_tasks = None
        self._copied_submission_note = None

        ######################################################################

        self.setUniformRowHeights(True)
        self.setSelectionMode(QTreeView.ExtendedSelection)
        self.setSelectionBehavior(QTreeView.SelectRows)
        self.setItemsExpandable(True)

        header = self.header()
        header.setContextMenuPolicy(Qt.CustomContextMenu)
        header.customContextMenuRequested.connect(
            self._create_context_menu_header)


    ##########################################################################


    def sizeHintForColumn(self, column):
        '''
        Reimplement to add some extra padding to size hint.

        Args:
            column (int):
        '''
        size = base_tree_view.BaseTreeView.sizeHintForColumn(self, column)
        size += 30
        return size


    def set_all_columns_visible(self, show=True, skip_columns=None):
        '''
        Reimplemented method.
        '''
        base_tree_view.BaseTreeView.set_all_columns_visible(
            self,
            show=show,
            skip_columns=skip_columns)
        self.reset_column_sizes()


    def reset_column_sizes(self):
        '''
        Reset the column sizes.
        '''
        model = self.model()
        if not model:
            return

        # Get the source model, from the proxy model (if any)
        if isinstance(model, QSortFilterProxyModel):
            model = model.sourceModel()

        self._column_widths = dict()
        self._column_widths[model.COLUMN_OF_NAME] = self.COLUMN_0_WIDTH
        self._column_widths[model.COLUMN_OF_VALIDATION] = 90
        self._column_widths[model.COLUMN_OF_JOB_ID] = 155
        self._column_widths[model.COLUMN_OF_VERSION] = 130
        self._column_widths[model.COLUMN_OF_RENDER_CATEGORY] = 105
        self._column_widths[model.COLUMN_OF_RENDER_ESTIMATE] = 150
        self._column_widths[model.COLUMN_OF_WAIT_ON_IDENTIFIERS] = 250
        self._column_widths[model.COLUMN_OF_WAIT_ON_PLOW_IDS] = 350
        self._column_widths[model.COLUMN_OF_PRODUCTION_FRAMES] = 140
        self._column_widths[model.COLUMN_OF_FRAME_RANGE] = 140
        self._column_widths[model.COLUMN_OF_FRAMES] = 70
        self._column_widths[model.COLUMN_OF_POST_TASK] = 270
        self._column_widths[model.COLUMN_OF_KOBA_SHOTSUB] = 110
        self._column_widths[model.COLUMN_OF_SUBMISSION_NOTE] = 100

        self.setColumnWidth(
            model.COLUMN_OF_NAME,
            self._column_widths.get(model.COLUMN_OF_NAME))
        self.setColumnWidth(
            model.COLUMN_OF_VALIDATION,
            self._column_widths.get(model.COLUMN_OF_VALIDATION))
        self.setColumnWidth(
            model.COLUMN_OF_JOB_ID,
            self._column_widths.get(model.COLUMN_OF_JOB_ID))
        self.setColumnWidth(
            model.COLUMN_OF_VERSION,
            self._column_widths.get(model.COLUMN_OF_VERSION))
        self.setColumnWidth(
            model.COLUMN_OF_RENDER_CATEGORY,
            self._column_widths.get(model.COLUMN_OF_RENDER_CATEGORY))
        self.setColumnWidth(
            model.COLUMN_OF_RENDER_ESTIMATE,
            self._column_widths.get(model.COLUMN_OF_RENDER_ESTIMATE))
        self.setColumnWidth(
            model.COLUMN_OF_WAIT_ON_IDENTIFIERS,
            self._column_widths.get(model.COLUMN_OF_WAIT_ON_IDENTIFIERS))
        self.setColumnWidth(
            model.COLUMN_OF_WAIT_ON_PLOW_IDS,
            self._column_widths.get(model.COLUMN_OF_WAIT_ON_PLOW_IDS))
        self.setColumnWidth(
            model.COLUMN_OF_PRODUCTION_FRAMES,
            self._column_widths.get(model.COLUMN_OF_PRODUCTION_FRAMES))
        self.setColumnWidth(
            model.COLUMN_OF_FRAME_RANGE,
            self._column_widths.get(model.COLUMN_OF_FRAME_RANGE))
        self.setColumnWidth(
            model.COLUMN_OF_FRAMES,
            self._column_widths.get(model.COLUMN_OF_FRAMES))
        self.setColumnWidth(
            model.COLUMN_OF_POST_TASK,
            self._column_widths.get(model.COLUMN_OF_POST_TASK))
        self.setColumnWidth(
            model.COLUMN_OF_KOBA_SHOTSUB,
            self._column_widths.get(model.COLUMN_OF_KOBA_SHOTSUB))
        self.setColumnWidth(
            model.COLUMN_OF_SUBMISSION_NOTE,
            self._column_widths.get(model.COLUMN_OF_SUBMISSION_NOTE))


    def get_column_widths(self):
        return self._column_widths


    ##########################################################################


    def _create_context_menu(
            self,
            pos=None,
            show=True,
            include_search=True):
        '''
        Build a QMenu for this Summary tree view.
        Reimplemented from super class.
        Note: These should be dynamically populate
        depending in type of item right clicked.

        Args:
            pos (QPoint):
            show (bool):
            include_search (bool): whether to include search if this
                is the full overrides menu

        Returns:
            menu (QtGui.QMenu):
        '''
        from Qt.QtWidgets import QMenu
        from Qt.QtGui import QCursor, QFont
        import srnd_qt.base.utils

        menu = QMenu('Summary view actions', self)

        font_italic = QFont()
        font_italic.setFamily(constants.FONT_FAMILY)
        font_italic.setItalic(True)

        model = self.model()

        env_count = 0
        pass_for_env_count = 0
        for qmodelindex in self.selectedIndexes():
            if not qmodelindex.isValid():
                continue
            qmodelindex_source = model.mapToSource(qmodelindex)
            if not qmodelindex_source.isValid():
                continue
            item = qmodelindex_source.internalPointer()
            if item.is_group_item():
                continue
            elif item.is_environment_item():
                env_count += 1
            elif item.is_pass_for_env_item():
                pass_for_env_count += 1

        if any([env_count, pass_for_env_count]):
            # msg = 'Post tasks'
            # action = srnd_qt.base.utils.context_menu_add_menu_item(menu, msg)
            # action.setFont(font_italic)
            # menu.addAction(action)

            action = srnd_qt.base.utils.context_menu_add_menu_item(
                menu,
                'Copy post tasks',
                icon_path=os.path.join(ICONS_DIR, 'copy_s01.png'))
            action.triggered.connect(self.copy_post_tasks)
            menu.addAction(action)

            action = srnd_qt.base.utils.context_menu_add_menu_item(
                menu,
                'Paste post tasks',
                icon_path=os.path.join(ICONS_DIR, 'paste_s01.png'))
            action.triggered.connect(self.paste_post_tasks)
            menu.addAction(action)

            action = srnd_qt.base.utils.context_menu_add_menu_item(
                menu,
                'Clear post tasks')
            action.triggered.connect(self.clear_post_tasks)
            menu.addAction(action)

            menu.addSeparator()

            msg = 'Shotsub description'
            action = srnd_qt.base.utils.context_menu_add_menu_item(menu, msg)
            action.setFont(font_italic)
            menu.addAction(action)

            action = srnd_qt.base.utils.context_menu_add_menu_item(
                menu,
                'Copy notes',
                icon_path=os.path.join(ICONS_DIR, 'copy_s01.png'))
            action.triggered.connect(self.copy_submission_notes)
            menu.addAction(action)

            action = srnd_qt.base.utils.context_menu_add_menu_item(
                menu,
                'Paste notes',
                icon_path=os.path.join(ICONS_DIR, 'paste_s01.png'))
            action.triggered.connect(self.paste_submission_notes)
            menu.addAction(action)

            action = srnd_qt.base.utils.context_menu_add_menu_item(
                menu,
                'Bake notes to overrides')
            action.triggered.connect(self.bake_submission_notes)
            menu.addAction(action)

            action = srnd_qt.base.utils.context_menu_add_menu_item(
                menu,
                'Clear notes')
            action.triggered.connect(self.clear_submission_notes)
            menu.addAction(action)

        if show and menu.actions():
            menu.exec_(QCursor.pos())

        return menu


    def _create_context_menu_header(self, pos, show=True):
        '''
        Build a QMenu for tree view header.

        Args:
            show (bool): show the menu after populating or not

        Returns:
            menu (QtGui.QMenu):
        '''
        from Qt.QtWidgets import QMenu
        from Qt.QtGui import QCursor, QFont
        import srnd_qt.base.utils

        header = self.header()
        column = header.logicalIndexAt(pos)

        font_italic = QFont()
        font_italic.setFamily(constants.FONT_FAMILY)
        font_italic.setItalic(True)

        menu = QMenu('Summary view header actions', self)

        # msg = 'Column Actions'
        # action = srnd_qt.base.utils.context_menu_add_menu_item(menu, msg)
        # action.setFont(font_italic)
        # menu.addAction(action)

        action = srnd_qt.base.utils.context_menu_add_menu_item(
            menu,
            'Show all columns',
            icon_path=os.path.join(SRND_QT_ICONS_DIR, 'visibility_on_s01.png'))
        action.triggered.connect(
            lambda *x: self.set_all_columns_visible(show=True))
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

        action = srnd_qt.base.utils.context_menu_add_menu_item(
            menu,
            'Reset column widths')
        action.triggered.connect(self.reset_column_sizes)
        menu.addAction(action)

        action = srnd_qt.base.utils.context_menu_add_menu_item(
            menu,
            'Reset column order')
        action.triggered.connect(self.setup_columns)
        menu.addAction(action)

        menu.addSeparator()

        model = self.model()
        column_count = model.columnCount(QModelIndex())

        toggle_columns_menu = QMenu('Toggle particular columns', menu)
        menu.addMenu(toggle_columns_menu)

        # Allow specific columns to be hidden, or shown
        for column in range(1, column_count, 1):
            value = model.headerData(
                column,
                Qt.Horizontal,
                role=Qt.DisplayRole)
            if hasattr(value, 'toString'):
                value = value.toString()
            value = str(value)
            visible = not self.isColumnHidden(column)
            action = srnd_qt.base.utils.context_menu_add_menu_item(
                toggle_columns_menu,
                value,
                checkable=True,
                checked=visible)
            method_to_call = functools.partial(
                self.toggle_column_visibility,
                columns=[column],
                width=self._column_widths.get(column))
            action.toggled.connect(method_to_call)
            toggle_columns_menu.addAction(action)

        if show:
            menu.exec_(QCursor.pos())

        return menu


    ##########################################################################


    def clear_post_tasks(self):
        '''
        Clear all post task/s of selected items.
        '''
        model = self.model()
        source_model = model
        if isinstance(model, QSortFilterProxyModel):
            source_model = model.sourceModel()

        selection = self.selectionModel().selectedRows()
        for qmodelindex in selection:
            if not qmodelindex.isValid():
                continue
            qmodelindex_source = model.mapToSource(qmodelindex)
            if not qmodelindex_source.isValid():
                continue
            item = qmodelindex_source.internalPointer()
            if item.is_group_item():
                continue

            qmodelindex_post_task = qmodelindex.sibling(
                qmodelindex.row(),
                source_model.COLUMN_OF_POST_TASK)
            widget = self.indexWidget(qmodelindex_post_task)
            if not widget:
                continue

            identifier = item.get_identifier()

            msg =  'Clearing post task for identifier: "{}"'.format(identifier)
            self.logMessage.emit(msg, logging.WARNING)

            item.set_post_tasks(list())
            widget.set_post_task_check_states(list())

            # Also clear Koba shotsub state
            if item.is_environment_item():
                qmodelindex_koba_shotsub = qmodelindex.sibling(
                    qmodelindex.row(),
                    source_model.COLUMN_OF_KOBA_SHOTSUB)
                if item.is_environment_item():
                    item.set_koba_shotsub(False)
                widget = self.indexWidget(qmodelindex_koba_shotsub)
                if not widget:
                    continue
                widget.setChecked(False)


    def copy_post_tasks(self):
        '''
        Copy the post task/s in selection.
        NOTE: For now only the first post task name in selected items is copied.
        '''
        model = self.model()
        source_model = model
        if isinstance(model, QSortFilterProxyModel):
            source_model = model.sourceModel()

        self._copied_post_tasks = None

        selection = self.selectionModel().selectedRows()
        for qmodelindex in selection:
            if not qmodelindex.isValid():
                continue
            qmodelindex_source = model.mapToSource(qmodelindex)
            if not qmodelindex_source.isValid():
                continue
            item = qmodelindex_source.internalPointer()
            if item.is_group_item():
                continue

            qmodelindex_post_task = qmodelindex.sibling(
                qmodelindex.row(),
                source_model.COLUMN_OF_POST_TASK)
            widget = self.indexWidget(qmodelindex_post_task)
            if not widget:
                continue

            post_tasks = widget.get_checked_post_tasks()
            if not post_tasks:
                continue
            koba_shotsub = None
            is_environment = item.is_environment_item()
            if is_environment:
                koba_shotsub = item.get_koba_shotsub()
            self._copied_post_tasks = is_environment, post_tasks, koba_shotsub
            msg =  'Copied post task/s names: "{}"'.format(post_tasks)
            self.logMessage.emit(msg, logging.INFO)
            break


    def paste_post_tasks(self):
        '''
        Paste the previously copied post task/s to selected items.
        '''
        if not self._copied_post_tasks:
            msg =  'No post task/s previously copied to paste!'
            self.logMessage.emit(msg, logging.WARNING)
            return list()

        is_environment, post_tasks, koba_shotsub = self._copied_post_tasks

        model = self.model()
        source_model = model
        if isinstance(model, QSortFilterProxyModel):
            source_model = model.sourceModel()

        selection = self.selectionModel().selectedRows()
        for qmodelindex in selection:
            if not qmodelindex.isValid():
                continue
            qmodelindex_source = model.mapToSource(qmodelindex)
            if not qmodelindex_source.isValid():
                continue
            item = qmodelindex_source.internalPointer()
            if item.is_group_item():
                continue

            qmodelindex_post_task = qmodelindex.sibling(
                qmodelindex.row(),
                source_model.COLUMN_OF_POST_TASK)
            widget = self.indexWidget(qmodelindex_post_task)
            if not widget:
                continue

            if widget.is_environment_item() != is_environment:
                continue

            identifier = item.get_identifier()
            msg =  'Setting post task/s for identifier: "{}". '.format(identifier)
            msg += 'Post task/s: "{}"'.format(post_tasks)
            self.logMessage.emit(msg, logging.WARNING)
            widget._set_post_task_states_from_index(
                qmodelindex,
                post_tasks=post_tasks)

            if widget.is_environment_item():
                qmodelindex_koba_shotsub = qmodelindex.sibling(
                    qmodelindex.row(),
                    source_model.COLUMN_OF_KOBA_SHOTSUB)
                item.set_koba_shotsub(koba_shotsub)
                widget = self.indexWidget(qmodelindex_koba_shotsub)
                if not widget:
                    continue
                widget.setChecked(koba_shotsub)


    ##########################################################################


    def clear_submission_notes(self):
        '''
        Clear all submission notes of selected items.
        '''
        model = self.model()
        source_model = model
        if isinstance(model, QSortFilterProxyModel):
            source_model = model.sourceModel()

        selection = self.selectionModel().selectedRows()
        for qmodelindex in selection:
            if not qmodelindex.isValid():
                continue
            qmodelindex_source = model.mapToSource(qmodelindex)
            if not qmodelindex_source.isValid():
                continue
            item = qmodelindex_source.internalPointer()
            if item.is_group_item():
                continue

            qmodelindex_notes = qmodelindex.sibling(
                qmodelindex.row(),
                source_model.COLUMN_OF_SUBMISSION_NOTE)
            widget = self.indexWidget(qmodelindex_notes)
            if not widget:
                continue

            identifier = item.get_identifier()
            msg =  'Clearing submission notes for identifier: "{}"'.format(identifier)
            self.logMessage.emit(msg, logging.WARNING)
            item.set_note_override_submission(None)
            widget.setText(str())


    def bake_submission_notes(self):
        '''
        Submission notes are initially populated from note overrides.
        But can be edited using this summary view for this particular
        submission without changing the note override.
        The user can choose to bake the submission notes back
        to note overrides on demand.
        '''
        model = self.model()
        source_model = model
        if isinstance(model, QSortFilterProxyModel):
            source_model = model.sourceModel()

        selection = self.selectionModel().selectedRows()
        for qmodelindex in selection:
            if not qmodelindex.isValid():
                continue
            qmodelindex_source = model.mapToSource(qmodelindex)
            if not qmodelindex_source.isValid():
                continue
            item = qmodelindex_source.internalPointer()
            if item.is_group_item():
                continue

            qmodelindex_notes = qmodelindex.sibling(
                qmodelindex.row(),
                source_model.COLUMN_OF_SUBMISSION_NOTE)
            widget = self.indexWidget(qmodelindex_notes)
            if not widget:
                continue

            if item.is_environment_item():
                identifier = item.get_environment_name_nice()
            else:
                identifier = item.get_identifier()
            note_override_submission = item.get_note_override_submission() or None
            msg =  'Baking submission notes for identifier: "{}". '.format(identifier)
            msg += 'Note: "{}"'.format(note_override_submission)
            self.logMessage.emit(msg, logging.WARNING)
            item.set_note_override(note_override_submission)
            self.updateMainViewRequest.emit(qmodelindex_source)


    def copy_submission_notes(self):
        '''
        Copy submission notes of selected items.
        NOTE: For now only the first note in selected items is copied.
        '''
        model = self.model()
        source_model = model
        if isinstance(model, QSortFilterProxyModel):
            source_model = model.sourceModel()

        self._copied_submission_note = None
        selection = self.selectionModel().selectedRows()
        for qmodelindex in selection:
            if not qmodelindex.isValid():
                continue
            qmodelindex_source = model.mapToSource(qmodelindex)
            if not qmodelindex_source.isValid():
                continue
            item = qmodelindex_source.internalPointer()
            if item.is_group_item():
                continue
            submission_note = item.get_note_override_submission()
            if submission_note:
                self._copied_submission_note = submission_note
                msg =  'Copied submission note: "{}". '.format(submission_note)
                self.logMessage.emit(msg, logging.INFO)
                break


    def paste_submission_notes(self):
        '''
        Paste submission notes on to selected items.
        '''
        if not self._copied_submission_note:
            msg =  'No submission notes previously copied to paste!'
            self.logMessage.emit(msg, logging.WARNING)
            return list()

        model = self.model()
        source_model = model
        if isinstance(model, QSortFilterProxyModel):
            source_model = model.sourceModel()

        selection = self.selectionModel().selectedRows()
        for qmodelindex in selection:
            if not qmodelindex.isValid():
                continue
            qmodelindex_source = model.mapToSource(qmodelindex)
            if not qmodelindex_source.isValid():
                continue
            item = qmodelindex_source.internalPointer()
            if item.is_group_item():
                continue

            qmodelindex_notes = qmodelindex.sibling(
                qmodelindex.row(),
                source_model.COLUMN_OF_SUBMISSION_NOTE)
            widget = self.indexWidget(qmodelindex_notes)
            if not widget:
                continue

            identifier = item.get_identifier()
            msg =  'Setting submission note for identifier: "{}". '.format(identifier)
            msg += 'Note: "{}"'.format(self._copied_submission_note)
            self.logMessage.emit(msg, logging.WARNING)
            item.set_note_override_submission(self._copied_submission_note)

            widget.setText(self._copied_submission_note)