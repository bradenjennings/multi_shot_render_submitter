
import os

from Qt.QtWidgets import QFormLayout, QSizePolicy
from Qt.QtGui import QIcon
from Qt.QtCore import Signal

import srnd_qt.base.utils
from srnd_qt.ui_framework.dialogs import base_popup_dialog


fs = '<b><font color="#33CC33">'
fe = '</b></font>'
DESCRIPTION = 'Select {0}shot/s{1} or {0}variant/s{1} or entire  '.format(fs, fe)
DESCRIPTION += '{0}scene/s{1} or {0}asset/s{1} and press Add. '.format(fs, fe)
DESCRIPTION += '<br>Alternately {0}click & drag{1} '.format(fs, fe)
DESCRIPTION += 'the selected environment/s into the Multi Shot view.'

DIALOG_WH = (575, 625)

ICONS_DIR_QT = srnd_qt.base.utils.get_srnd_qt_icon_dir()
ADD_ICON_PATH = os.path.join(ICONS_DIR_QT, 'add.png')

fs = '<b><font color="#33CC33">'
fe = '</b></font>'


##############################################################################


class AddEnvironmentsDialog(base_popup_dialog.BasePopupDialog):
    '''
    A dialog to choose render environmnent/s to add.

    Args:
        environment (str): initial environment to show in environment chooser widget
        icon_path (str):
    '''

    addEnvironmentsRequest = Signal(list)

    def __init__(
            self,
            environment=os.getenv('OZ_AREA'),
            icon_path=None,
            parent=None,
            **kwargs):

        environment = environment or os.getenv('OZ_AREA')
        try:
            _env_split = environment.split('/')
            shot = _env_split.pop()
            scene = _env_split.pop()
            tree = _env_split.pop() or os.getenv('TREE')
        except Exception:
            tree = os.getenv('TREE')
        if tree == 'shots':
            title = 'Add Shots'
        elif tree in ['assets', 'dev']:
            title = 'Add Assets'
        else:
            title = 'Add Area'

        super(AddEnvironmentsDialog, self).__init__(
            tool_name=title,
            description=DESCRIPTION,
            description_by_title=False,
            description_is_dismissible=False,
            do_validate=True,
            icon_path=icon_path,
            icon_size=20,
            parent=parent)

        self.resize(*DIALOG_WH)
        self.center()

        self.layout().setContentsMargins(6, 6, 6, 6)

        options_box_header = self.get_header_widget()
        style_sheet = 'QGroupBox {background: rgb(70, 70, 70);'
        style_sheet += 'border:rgb(70, 70, 70)}'
        options_box_header.setStyleSheet(style_sheet)
        options_box_header.set_title(title)

        vertical_layout = self.get_content_widget_layout()
        vertical_layout.setContentsMargins(6, 6, 6, 6)

        from srnd_qt.ui_framework.widgets import collection_widget
        self._widget_collections = collection_widget.CollectionEditorWidget(
            current_area=environment,
            show_scenes=True,
            show_test_scenes=False,
            show_stacks=False,
            show_slates=False,
            show_assets=True,
            show_user=False,
            show_collections_widget=False,
            # area_label='Choose environment/s',
            autoexpand_to_current_env=True,
            show_all_variants=True,
            include_child_mime_data=True)
        view = self._widget_collections.get_area_browser_widget().get_view()
        view.header().setVisible(False)
        self._widget_collections.layout().setContentsMargins(0, 0, 0, 0)
        self._widget_collections.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding)
        vertical_layout.addWidget(self._widget_collections)

        buttons = self.build_okay_cancel_buttons()
        buttons[0].setIcon(QIcon(ADD_ICON_PATH))
        buttons[0].setText('Add')


    def get_environments_to_add(self):
        '''
        Get list of environments to add as Multi Shot data objects.

        Returns:
            environments (list):
        '''
        return self._widget_collections.get_environments_selected_in_areas_widget()


    def accept_and_validate(self):
        '''
        Reimplemented to emit the signal so environments being added can be added externally.

        Returns:
            is_valid (bool):
        '''
        environments = self.get_environments_to_add()
        if environments:
            self.accept()
        else:
            self.reject()
        self.addEnvironmentsRequest.emit(environments)
        return bool(environments)