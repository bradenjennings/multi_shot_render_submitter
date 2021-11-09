

import os

from Qt.QtWidgets import (QApplication, QWidget, QToolButton,
    QLineEdit, QHBoxLayout, QSizePolicy)
from Qt.QtGui import QIcon
from Qt.QtCore import Qt, Signal, QSize

from srnd_multi_shot_render_submitter.constants import Constants
import srnd_multi_shot_render_submitter.utils
from srnd_multi_shot_render_submitter.widgets import version_system_line_edit
from srnd_multi_shot_render_submitter.widgets import widgets_utils


constants = Constants()

MENU_CORNER_WIDGET_HEIGHT = 44


##############################################################################


class MenuBarHeaderWidget(QWidget):
    '''
    A widget containing multiple sub widgets such as project picker,
    search widget, and other option widgets.
    # NOTE: This might be moved to srnd_multi_shot_render_submitter soon.

    Args:
        project (str):
        project_product_types (list):
        project_file_types (list):
        host_app (str):
    '''

    syncRequest = Signal()
    syncMenuRequested = Signal()
    newEnvironmentRequest = Signal()
    populateAssignedShotsForProjectRequest = Signal()
    populateAssignedShotsForProjectAndSequenceRequest = Signal()
    projectChanged = Signal(str)

    def __init__(
            self,
            project=None,
            project_product_types=['GEN'],
            project_file_types=list(),
            parent=None):
        super(MenuBarHeaderWidget, self).__init__(parent)

        self.HOST_APP = constants.HOST_APP

        self._project_initial = project
        self._last_project = str()

        self._project_product_types = project_product_types
        self._project_file_types = project_file_types

        self._use_hyref_widget = constants.MENU_BAR_USE_HYREF_WIDGET

        ######################################################################

        self._horizontal_layout = QHBoxLayout()
        self._horizontal_layout.setSpacing(0)
        self._horizontal_layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(self._horizontal_layout)

        self.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Fixed)

        self._build_widgets()

        self._wire_events()


    def _wire_events(self):
        '''
        Additional events to connect for MenuBarHeaderWidget.
        '''
        self._toolButton_add_environment.clicked.connect(
            self._request_new_environment)
        self._toolButton_get_assigned_shots.clicked.connect(
            self._request_populate_assigned_shots_for_project_and_sequence)


    def get_project_widget(self):
        '''
        Get the widget that allows project to be specified.

        Returns:
            line_edit_hyref (HyrefPreviewWidget):
        '''
        return self._project_widget


    def get_search_filter_widget(self):
        '''
        Get the search with filters widget.

        Returns:
            search_with_filters_widget (SearchWithFiltersWidget):
        '''
        return self._search_with_filters_widget


    def get_search_widget(self):
        '''
        Get the search widget.

        Returns:
            line_edit_filter (SearchLineEdit):
        '''
        return self._lineEdit_filter


    def _update_project_widget(self, project):
        '''
        Update the HyrefPreviewWidget to project hyref.

        Args:
            project (str):
        '''
        # Check the incoming value is different, than value in widget
        project = str(project or str())
        if project == self._last_project:
            return

        # Optionally cast current project file location, back
        # to hyref if possible (file path returns if no associated Hydra Product).
        if self._use_hyref_widget and project and os.path.isfile(project):
            project = srnd_multi_shot_render_submitter.utils.get_hyref_for_location(project)

        self._last_project = project

        # Block signal propagation when setting hyref
        self._project_widget.blockSignals(True)
        self.set_project(project, emit_signals=False)
        self._project_widget.blockSignals(False)

        # Run validation (to get styling)
        self._project_widget.validate()


    def get_content_widget_layout(self):
        '''
        Get this MenuBarHeaderWidget main layout.

        Returns:
            horizontal_layout (QHBoxLayout):
        '''
        return self._horizontal_layout


    def _build_widgets(self):
        '''
        Build all the child widgets of this MenuBarHeaderWidget.
        '''
        layout =  self.get_content_widget_layout()

        # self._toolButton_sync = QToolButton()
        # self._toolButton_sync.setToolTip(constants.TOOLTIP_SYNC)
        # self._toolButton_sync.setAutoRaise(True)
        # self._toolButton_sync.setIconSize(QSize(18, 18))
        # icon = QIcon(os.path.join(constants.ICONS_DIR_QT, 'sync.png'))
        # self._toolButton_sync.setIcon(icon)
        # layout.addWidget(self._toolButton_sync)

        # layout.addSpacing(6)

        # self._toolButton_sync_options = widgets_utils._build_toolbutton_with_triangle_icon()
        # msg = 'Drop down menu for other Passes actions'
        # self._toolButton_sync_options.setToolTip(msg)
        # layout.addWidget(self._toolButton_sync_options)
        # self._toolButton_sync_options.setContextMenuPolicy(Qt.CustomContextMenu)
        # self._toolButton_sync_options.customContextMenuRequested.connect(
        #     self._request_sync_menu)
        # self._toolButton_sync_options.clicked.connect(
        #     self._request_sync_menu)
        # layout.addSpacing(10)

        self._toolButton_get_assigned_shots = QToolButton()
        self._toolButton_get_assigned_shots.setToolTip(
            constants.LABEL_GET_ALL_ASSIGNED_SHOTS_FOR_SEQUENCE)
        self._toolButton_get_assigned_shots.setAutoRaise(True)
        self._toolButton_get_assigned_shots.setIconSize(QSize(18, 18))
        icon = QIcon(os.path.join(constants.ICONS_DIR_QT, 'user_s01.png'))
        self._toolButton_get_assigned_shots.setIcon(icon)
        layout.addWidget(self._toolButton_get_assigned_shots)

        layout.addSpacing(6)

        # self._toolButton_get_assigned_shots_options = widgets_utils._build_toolbutton_with_triangle_icon()
        # msg = 'Drop down menu for more assigned Shots actions'
        # self._toolButton_get_assigned_shots_options.setToolTip(msg)
        # layout.addWidget(self._toolButton_get_assigned_shots_options)
        # self._toolButton_get_assigned_shots_options.setContextMenuPolicy(Qt.CustomContextMenu)
        # parent = self.parent()
        # self._toolButton_get_assigned_shots_options.customContextMenuRequested.connect(
        #     lambda *x: parent._create_context_menu_get_assigned_shots())
        # self._toolButton_get_assigned_shots_options.clicked.connect(
        #     lambda *x: parent._create_context_menu_get_assigned_shots())
        # layout.addSpacing(8)

        self._toolButton_add_environment = QToolButton()
        msg = 'Open dialog to pick environment/s to add'
        self._toolButton_add_environment.setToolTip(msg)
        self._toolButton_add_environment.setAutoRaise(True)
        self._toolButton_add_environment.setIconSize(QSize(18, 18))
        icon = QIcon(os.path.join(constants.ICONS_DIR_QT, 'add.png'))
        self._toolButton_add_environment.setIcon(icon)
        layout.addWidget(self._toolButton_add_environment)

        layout.addSpacing(8)

        widget = version_system_line_edit.VersionSystemLineEdit(parent=self)
        self._lineEdit_version_system_global = widget
        msg = '<b>Set Global cg Version System</b>'
        msg += '<ul>'
        msg += '<li><b>VP+</b> - Resolves cg Version To Highest Version+1 Of All cg Passes Of Each Env</li>'
        msg += '<li><b>V+</b> - Resolves cg Version To Highest Version+1 Of Each cg Pass</li>'
        msg += '<li><b>VS</b> - Resolves cg Version To Same As Source Scene Version '
        msg += '(Otherwise Use VP+ As Fallback System)</li>'
        msg += '<li><b>2</b> - Example of Providing Global Explicit Version For All Passes</li>'
        msg += '</ul>'
        msg += '<i>Note: This Global Version System Can Be Overridden '
        msg += 'For Each Environment Or Render Pass For Env.</b>'
        self._lineEdit_version_system_global.setToolTip(msg)
        self._lineEdit_version_system_global.setFixedHeight(
            MENU_CORNER_WIDGET_HEIGHT - 10)
        layout.addWidget(self._lineEdit_version_system_global)

        layout.addSpacing(10)

        if self._use_hyref_widget:
            # Host app project file type/s can be picked with HyrefPreviewWidget
            products_settings = dict()
            for product_type in self._project_product_types:
                products_settings[product_type] = dict()
                products_settings[product_type]['productContext'] = {
                    'productType': [product_type]}

            from srnd_qt.ui_framework.widgets import hyref_preview_widget
            self._project_widget = hyref_preview_widget.HyrefPreviewWidget(
                self._project_initial or str(),
                editable=True,
                has_browse_button=True,
                hyref_browser_window_size=(1100, 600),
                include_preview=False,
                products_settings=products_settings,
                exclude_statuses=['referenced', 'unsupported'],
                browse_includes_element_details=False,
                show_drag_indicator=False,
                initial_space=0,
                margin=0,
                height=None,
                style_sheet_when_valid=constants.STYLE_SHEET_LINE_EDIT_ORANGE)

            browse_button = self._project_widget.get_hyref_browse_button()
            browse_button.setIconSize(QSize(18, 18))

            line_edit = self._project_widget.get_hyref_preview_line_edit()
            font = line_edit.font()
            font.setPointSize(9)
            font.setFamily(constants.FONT_FAMILY)
            line_edit.setFont(font)

            self._project_widget.hyrefChanged.connect(
                self._project_changed)
        else:
            from srnd_qt.ui_framework.widgets import file_line_edit
            self._project_widget = file_line_edit.FileLineEdit(
                file_path=self._project_initial or str(),
                file_format=self._project_file_types,
                initial_space=0,
                margin=0,
                height=None)

            browse_button = self._project_widget.get_browse_button()

        browse_button.clicked.disconnect()

        self._project_widget.editingFinished.connect(
            self._project_changed)
        self._project_widget.returnPressed.connect(
            self._project_changed)

        msg = 'Choose {} Project Hyref'.format(self.HOST_APP)
        self._project_widget.setToolTip(msg)
        self._project_widget.setFixedHeight(
            MENU_CORNER_WIDGET_HEIGHT - 10)
        self._project_widget.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Fixed)
        layout.addWidget(self._project_widget)

        layout.addSpacing(10)

        msg_lines = ['Filter View By Searching For Literal String Or Regular Expression. ']
        msg_lines.append('<br><i>Note: Python / Perl Style Regular Expressions Are Supported.</i>')
        msg_lines.append('<br><i>Note: Supports Additional Search Modifiers To Help Narrow The Results.</i>')
        msg_lines.append('<br><i>Note: If No Modifier Is Specified Then All Types Of Data Is Searched.</i>')
        msg_lines.append('<br><i>Note: Press The Plus Button After Entering Search Text To Add ')
        msg_lines.append('To List Of Active Filters.</i>')

        msg_lines.append('<br><br><b>Search By Regular Expressions</b>')
        msg_lines.append('<ul>')
        msg_lines.append('<li><b>"char.*"</b> - dot star, match any number of characters</li>')
        msg_lines.append('<li><b>"^env"</b> - match start of string</li>')
        msg_lines.append('<li><b>"Man01$"</b> - match end of string</li>')
        msg_lines.append('<li><b>"Man[0-9]"</b> - match single number</li>')
        msg_lines.append('<li><b>"Man[0-9]*"</b> - match multiple numbers</li>')
        msg_lines.append('<li><b>"^(char).*(Man01)$"</b> - match start and end of string</li>')
        msg_lines.append('</ul>')

        msg_lines.append('<b>Search With Prefix Modifiers</b>')
        msg_lines.append('<ul>')
        msg_lines.append('<li><b>"env:"</b> - Filter By Environments Explicitly. ')
        msg_lines.append('Equivalent Filters: <b>"area:"</b>, ')
        msg_lines.append('<b>"shot:"</b>, <b>"environment"<b></li>')
        msg_lines.append('<li><b>"frame:"</b> - Filter Environments And Passes To Those Which ')
        msg_lines.append('Include Resolved Frame/s Explicitly. ')
        msg_lines.append('Equivalent Filters: <b>"frames:"</b></li>')
        msg_lines.append('<li><b>"job:"</b> - Filter By Job Identifier Explicitly</li>')
        msg_lines.append('<li><b>"note:"</b> - Filter By Notes Explicitly. ')
        msg_lines.append('Equivalent Filters: <b>"notes:"</b></li>')
        msg_lines.append('</ul>')

        msg_lines.append('<b>Example Of Searching With Prefix Modifier & Regular Expressions</b>')
        msg_lines.append('<ul>')
        msg_lines.append('<li><b>"env:20$"</b> - Explicitly filter by environments ending with "20"</li>')
        msg_lines.append('<li><b>"pass:^cat"</b> - Explicitly filter by passes starting with "cat"</li>')
        msg_lines.append('</ul>')

        layout.addSpacing(10)

        from srnd_qt.ui_framework.widgets import search_with_filters_widget
        msg = ''.join(msg_lines)
        self._search_with_filters_widget = search_with_filters_widget.SearchWithFiltersWidget(
            include_options_menu=True,
            description_long=msg)
        layout.addWidget(self._search_with_filters_widget)

        msg_lines.insert(1, '<br>Hotkey To Bring Search In Focus: <b>ALT+F</b>')
        msg_lines.insert(2, '<br>Hotkey To Open Add Search Filter Dialog: <b>CTRL+SHIFT+ALT+F</b>')
        msg = ''.join(msg_lines)

        self._lineEdit_filter = self._search_with_filters_widget.get_search_widget()
        self._lineEdit_filter.setToolTip(msg)
        self._lineEdit_filter.setFixedWidth(250)
        self._lineEdit_filter.setFixedHeight(
            MENU_CORNER_WIDGET_HEIGHT - 10)
        self._lineEdit_filter.setSizePolicy(
            QSizePolicy.Fixed,
            QSizePolicy.Fixed)


    def set_project(self, project, emit_signals=True):
        '''
        Set the project on the project widget.

        Args:
            project (str):
            emit_signals (bool):
        '''
        if project == self.get_project():
            return

        if self._use_hyref_widget:
            self._project_widget.set_hyref(project)
        else:
            self._project_widget.set_file_path(project)

        if emit_signals:
            self.projectChanged.emit(project)


    def get_project(self):
        '''
        Get the project from the project widget.

        Returns:
            project (str):
        '''
        if self._use_hyref_widget:
            return self._project_widget.get_hyref()
        else:
            return self._project_widget.get_file_path()


    def get_version_system_global_widget(self):
        return self._lineEdit_version_system_global

    def get_project_widget(self):
        return self._project_widget

    def get_browse_button(self):
        if self._use_hyref_widget:
            return self._project_widget.get_hyref_browse_button()
        else:
            return self._project_widget.get_browse_button()


    def sizeHint(self):
        '''
        Return the suggested size for entire MenuBarHeaderWidget.
        Should take up the rest of the QMenuBar.
        '''
        parent_widget = self.parent()
        if parent_widget:
            width = parent_widget.width() - (len(parent_widget.actions()) * 70)
            return QSize(width, MENU_CORNER_WIDGET_HEIGHT)


    def _project_changed(self):
        '''
        Validate the project actually did change from before.
        '''
        project = self.get_project()
        if project != self._last_project:
            self._last_project = project
            # self._project_widget.validate()
            self.projectChanged.emit(str(project or str()))


    def _request_sync(self):
        self.syncRequest.emit()

    def _request_sync_menu(self):
        self.syncMenuRequested.emit()

    def _request_new_environment(self):
        self.newEnvironmentRequest.emit()

    def _request_populate_assigned_shots_for_project(self):
        self.populateAssignedShotsForProjectRequest.emit()

    def _request_populate_assigned_shots_for_project_and_sequence(self):
        self.populateAssignedShotsForProjectAndSequenceRequest.emit()