

import os

from Qt.QtGui import (QStandardItemModel, QStandardItem,
    QIcon, QFont, QBrush, QColor)
from Qt.QtWidgets import QComboBox, QTreeView
from Qt.QtCore import Qt, Signal, QSize, QModelIndex, QSortFilterProxyModel

import srnd_multi_shot_render_submitter.koba_helper
koba_helper = srnd_multi_shot_render_submitter.koba_helper.KobaHelper(do_cache_results=True)

from srnd_multi_shot_render_submitter.constants import Constants
constants = Constants()

ICONS_DIR = os.path.join(
    os.getenv('SRND_MULTI_SHOT_RENDER_SUBMITTER_ROOT', str()),
    'icons')
KOBA_ICON_PATH = os.path.join(
    ICONS_DIR,
    'koba_32x32_s01.png')
NUKE_ICON_PATH = os.path.join(
    ICONS_DIR,
    'nuke_20x20_s01.png')
STAR_ICON_PATH = os.path.join(
    ICONS_DIR,
    'star_s01.png')


##############################################################################


class PostTasksComboBoxWidget(QComboBox):
    '''
    Create Multi Shot post tasks combo box widget.

    Args:
        item (BaseMultiShotItem):
        qmodelindex (QModelIndex): index in MultiShotRenderView
        searchable (bool): whether to expose search box to quickly find post tasks
        parent (QWidget):
    '''

    postTasksChanged = Signal()

    def __init__(
            self,
            item,
            qmodelindex,
            searchable=True,
            parent=None):
        super(PostTasksComboBoxWidget, self).__init__(parent=parent)

        self._lineEdit_filter = None
        self._is_environment_item = item.is_environment_item()

        self.setContextMenuPolicy(Qt.NoContextMenu)

        self._model = QStandardItemModel(parent=self)
        standard_item = QStandardItem(str())
        standard_item.setSelectable(False)
        self._model.appendRow(standard_item)

        self.setModel(self._model)

        self._tree_view = QTreeView()
        self._tree_view.setHeaderHidden(True)
        self._tree_view.setRootIsDecorated(True)
        self.setView(self._tree_view)
        self.setMaxVisibleItems(100)
        self.setMinimumContentsLength(150)

        self._populate_model(item)

        # Populate widget with posts tasks from data stored in item
        post_tasks = item.get_post_tasks()
        if post_tasks:
            self._set_post_task_states_from_index(qmodelindex, post_tasks)

        self._model.itemChanged.connect(self._post_task_item_changed)

        # Setup this widget to be searchable
        if searchable:
            self._build_search_widget()
            self._lineEdit_filter.searchRequest.connect(
                self._filter_view_by_search_text)


    def is_environment_item(self):
        '''
        Get whether this post task is for environment otherwise pass for env.

        Returns:
            is_environment_item (bool):
        '''
        return self._is_environment_item


    ##########################################################################


    def set_post_task_check_states(
            self,
            post_tasks=None,
            uncheck_no_match=True):
        '''
        Apply post task check states based on post task name list.

        Args:
            post_tasks (list):
            uncheck_no_match (bool):
        '''
        if not post_tasks:
            post_tasks = list()
        self.blockSignals(True)
        model = self.model()
        icon = None

        # Categories
        for row in range(model.rowCount(QModelIndex())):
            qmodelindex = model.index(row, 0, QModelIndex())

            standard_item_category = model.itemFromIndex(qmodelindex)
            category = standard_item_category.data(Qt.UserRole)
            if hasattr(category, 'toString'):
                category = category.toString()
            category = str(category)

            # Post tasks in category
            for row_item in range(model.rowCount(qmodelindex)):
                qmodelindex_item = model.index(row_item, 0, qmodelindex)
                standard_item = model.itemFromIndex(qmodelindex_item)
                post_task_name = standard_item.data(Qt.UserRole)
                post_task_type = standard_item.data(Qt.UserRole + 1)
                if hasattr(post_task_name, 'toString'):
                    post_task_name = post_task_name.toString()
                if hasattr(post_task_type, 'toString'):
                    post_task_type = post_task_type.toString()
                post_task_name = str(post_task_name or str())
                post_task_type = str(post_task_type or str())
                if post_tasks:
                    found = self._check_post_task_name_in_post_tasks(
                        post_tasks,
                        post_task_name,
                        post_task_type,
                        category=category)
                    if found:
                        standard_item.setCheckState(Qt.Checked)
                        if not icon:
                            icon = standard_item.data(Qt.DecorationRole)
                    elif uncheck_no_match:
                        standard_item.setCheckState(Qt.Unchecked)
                else:
                    standard_item.setCheckState(Qt.Unchecked)
        self.blockSignals(False)
        post_tasks = self.get_checked_post_tasks(update_summary=False)
        self._update_display_text(list(post_tasks), icon=icon)


    def get_checked_post_tasks(self, update_summary=False):
        '''
        Get the currently checked post task names from QComboBox
        which has a standard model.

        Args:
            update_summary (bool): optionally refresh the QComboBox display text
                label and icon after getting post tasks, since the target standard
                items are within handy reach.

        Returns:
            post_tasks (list):
        '''
        post_tasks = list()
        model = self.model()
        icon = None
        for row in range(model.rowCount(QModelIndex())):
            qmodelindex = model.index(row, 0, QModelIndex())

            standard_item_category = model.itemFromIndex(qmodelindex)
            category = standard_item_category.data(Qt.UserRole)
            if hasattr(category, 'toString'):
                category = category.toString()
            category = str(category)

            for row_item in range(model.rowCount(qmodelindex)):
                qmodelindex_item = model.index(row_item, 0, qmodelindex)
                standard_item = model.itemFromIndex(qmodelindex_item)
                post_task_name = standard_item.data(Qt.UserRole)
                post_task_type = standard_item.data(Qt.UserRole + 1)
                if hasattr(post_task_name, 'toString'):
                    post_task_name = post_task_name.toString()
                if hasattr(post_task_type, 'toString'):
                    post_task_type = post_task_type.toString()
                post_task_name = str(post_task_name or str())
                post_task_type = str(post_task_type or str())
                if not all([post_task_name, post_task_type]):
                    continue
                check_state = standard_item.data(Qt.CheckStateRole)
                if check_state == Qt.Checked:
                    post_task_details = dict()
                    post_task_details['name'] = post_task_name
                    post_task_details['type'] = post_task_type
                    post_task_details['category'] = category
                    post_tasks.append(post_task_details)
                    if not icon:
                        icon = standard_item.data(Qt.DecorationRole)
        if update_summary:
            self._update_display_text(list(post_tasks), icon=icon)
        return post_tasks


    @classmethod
    def _check_post_task_name_in_post_tasks(
            cls,
            post_tasks,
            post_task_name,
            post_task_type,
            category=None):
        '''
        Check post task name and of type is in post tasks list.

        Args:
            post_tasks (list): list of post task dict to check
            post_task_name (str): post task of name to find
            post_task_type (str): post task of type name to find
            category (str): optionally also find post task with particular category

        Returns:
            found (bool): if found post task of name, type and category
        '''
        for post_task_details in post_tasks:
            _name = post_task_details.get('name')
            _type = post_task_details.get('type')
            if _name == post_task_name and _type == post_task_type:
                _category = post_task_details.get('category')
                if category and _category == category:
                    return True
                else:
                    continue
                return True
        return False

    ##########################################################################


    def _build_search_widget(self):
        '''
        Build search widget and insert into tree view within first qmodelindex.
        '''
        from srnd_qt.ui_framework import search_line_edit
        self._lineEdit_filter = search_line_edit.SearchLineEdit(parent=self)
        msg = 'Filter Post Tasks By String Search'
        self._lineEdit_filter.setToolTip(msg)
        standard_item = self._model.item(0)
        self._tree_view.setIndexWidget(
            standard_item.index(),
            self._lineEdit_filter)


    def _populate_model(self, item):
        '''
        Populate the model of this post task combo box based on provided MSRS item.

        Args:
            item (BaseMultiShotItem):
        '''
        model = self.model()
        is_pass_for_env_item = item.is_pass_for_env_item()
        is_environment_item = item.is_environment_item()

        font_bold = QFont()
        font_bold.setBold(True)

        standard_items_to_expand = list()

        if is_pass_for_env_item:
            environment_item = item.get_environment_item()
        else:
            environment_item = item
        oz_area = environment_item.get_oz_area()
        project = oz_area.lstrip('/').split('/')[0]

        if is_pass_for_env_item:
            item.get_environment_item()
            render_item = item.get_source_render_item()
            resource_names = render_item.get_render_node_resource_names()
            render_category = render_item.get_render_category()

            standard_item_resources = QStandardItem('Shotsub Resource')
            category = 'shotsub'
            standard_item_resources.setData(category, Qt.UserRole)
            msg = 'Shotsub Particular Resource/s After Render Finishes'
            standard_item_resources.setData(msg, Qt.ToolTipRole)
            standard_item_resources.setData(QSize(0, 26), Qt.SizeHintRole)
            standard_item_resources.setSelectable(False)
            standard_item_resources.setFont(font_bold)
            model.appendRow(standard_item_resources)
            standard_items_to_expand.append(standard_item_resources)

            for i, resource_name in enumerate(sorted(resource_names)):
                resource_name = str(resource_name)
                standard_item = QStandardItem(resource_name)
                standard_item.setCheckable(True)
                standard_item.setCheckState(Qt.Unchecked)
                standard_item.setSelectable(False)
                standard_item.setData(resource_name, Qt.UserRole)
                standard_item.setData('shotsub', Qt.UserRole + 1)
                standard_item.setData(QSize(0, 20), Qt.SizeHintRole)
                msg = 'Resource Name: <b>{}</b>'.format(resource_name)
                standard_item.setData(msg, Qt.ToolTipRole)
                standard_item_resources.appendRow(standard_item)

            if constants.EXPOSE_DENOISE:
                standard_item_denoise = QStandardItem('Denoise')
                category = 'denoise'
                standard_item_denoise.setData(category, Qt.UserRole)
                msg = 'Choose Denoise Post Task To Run After Render Finishes'
                standard_item_denoise.setData(msg, Qt.ToolTipRole)
                standard_item_denoise.setData(QSize(0, 26), Qt.SizeHintRole)
                standard_item_denoise.setSelectable(False)
                standard_item_denoise.setFont(font_bold)
                model.appendRow(standard_item_denoise)
                standard_items_to_expand.append(standard_item_denoise)

                denoise_presets = koba_helper.get_denoise_presets(
                    project=project,
                    include_weta=True,
                    name_filter=None) or dict()
                denoise_presets_added = set()
                for preset_name in sorted(denoise_presets.keys()):
                    if not preset_name:
                        continue
                    denoise_preset_info = denoise_presets[preset_name]
                    if denoise_preset_info.get('from_weta', False):
                        continue
                    standard_item = self._build_denoise_item_from_preset_info(
                        preset_name,
                        denoise_preset_info,
                        render_category=render_category)
                    standard_item_denoise.appendRow(standard_item)
                    denoise_presets_added.add(preset_name)

                standard_item_denoise_weta = QStandardItem('Denoise (Weta)')
                category = 'denoise_weta'
                standard_item_denoise_weta.setData(category, Qt.UserRole)
                msg = 'Choose Denoise Post Task To Run After Render Finishes'
                standard_item_denoise_weta.setData(msg, Qt.ToolTipRole)
                standard_item_denoise_weta.setData(QSize(0, 26), Qt.SizeHintRole)
                standard_item_denoise_weta.setSelectable(False)
                standard_item_denoise_weta.setFont(font_bold)
                model.appendRow(standard_item_denoise_weta)
                standard_items_to_expand.append(standard_item_denoise_weta)

                for preset_name in sorted(denoise_presets.keys()):
                    if not preset_name:
                        continue
                    if preset_name in denoise_presets_added:
                        continue
                    denoise_preset_info = denoise_presets[preset_name]
                    if not denoise_preset_info.get('from_weta', False):
                        continue
                    standard_item = self._build_denoise_item_from_preset_info(
                        preset_name,
                        denoise_preset_info,
                        render_category=render_category)
                    standard_item_denoise_weta.appendRow(standard_item)

        elif is_environment_item:
            standard_item_env = QStandardItem('Shot Koba Assemblies')
            category = 'koba_shot'
            standard_item_env.setData(category, Qt.UserRole)
            msg = 'Koba Assemblies For Environment: "{}"'.format(oz_area)
            standard_item_env.setData(msg, Qt.ToolTipRole)
            standard_item_env.setData(QSize(0, 26), Qt.SizeHintRole)
            standard_item_env.setSelectable(False)
            standard_item_env.setFont(font_bold)
            model.appendRow(standard_item_env)
            standard_items_to_expand.append(standard_item_env)
            hydra_versions_assemblies = koba_helper.get_assemblies(
                environment=oz_area,
                override=True)
            # koba_products_added = set()
            for i, product_name in enumerate(sorted(hydra_versions_assemblies.keys())):
                hydra_version = hydra_versions_assemblies[product_name]
                standard_item = self._build_koba_item_for_hydra_version(hydra_version)
                standard_item_env.appendRow(standard_item)
                # koba_products_added.add(product_name)

            # Additional groups of assemblies
            standard_item_project = QStandardItem(
                'Project Koba Assemblies'.format(project))
            category = 'koba_project'
            standard_item_project.setData(category, Qt.UserRole)
            msg = 'Koba Assemblies For Project: "{}"'.format(project)
            standard_item_project.setData(msg, Qt.ToolTipRole)
            standard_item_project.setData(QSize(0, 26), Qt.SizeHintRole)
            standard_item_project.setSelectable(False)
            standard_item_project.setFont(font_bold)
            model.appendRow(standard_item_project)
            standard_items_to_expand.append(standard_item_project)
            hydra_versions_assemblies = koba_helper.get_assemblies(
                project=project,
                project_only=True)
            for i, product_name in enumerate(sorted(hydra_versions_assemblies.keys())):
                # if product_name in koba_products_added:
                #     continue
                hydra_version = hydra_versions_assemblies[product_name]
                standard_item = self._build_koba_item_for_hydra_version(hydra_version)
                standard_item_project.appendRow(standard_item)

        for standard_item in standard_items_to_expand:
            self._tree_view.setExpanded(standard_item.index(), True)


    @classmethod
    def _build_koba_item_for_hydra_version(cls, hydra_version):
        '''
        Build a Koba post task standard item populated for particular Hydra version.

        Args:
            hydra_version (hydra.Version).

        Returns:
            standard_item (QStandardItem):
        '''
        product = hydra_version.getParentProduct()
        product_name = str(product.name or str())
        template_type = product.facets['template_type'][0]
        description = hydra_version.attrs.get('description')
        hyref = str(hydra_version.getHyref() or str())
        standard_item = QStandardItem(str(product_name))
        standard_item.setCheckable(True)
        standard_item.setCheckState(Qt.Unchecked)
        standard_item.setSelectable(False)
        standard_item.setData(product_name, Qt.UserRole)
        standard_item.setData('koba', Qt.UserRole + 1)
        standard_item.setData(QIcon(KOBA_ICON_PATH), Qt.DecorationRole)
        standard_item.setData(QSize(0, 20), Qt.SizeHintRole)
        msg = '<img src="{}" width=22 height=22>'.format(NUKE_ICON_PATH)
        msg += 'Product Name: <b>{}</b>'.format(product_name)
        msg += '<br>Template Type: <b>{}</b>'.format(template_type)
        msg += '<br>Description: <b>{}</b>'.format(description)
        msg += '<br>Hyref: <b>{}</b>'.format(hyref)
        try:
            resource = hydra_version.getDefaultResource()
        except Exception:
            resource = None
        if resource:
            msg += '<br>Path: <b>{}</b>'.format(resource.location)
        standard_item.setData(msg, Qt.ToolTipRole)
        return standard_item


    @classmethod
    def _build_denoise_item_from_preset_info(
            cls,
            preset_name,
            denoise_preset_info=None,
            render_category=None):
        '''
        Build a denoiser post task standard item populated
        for particular denoise preset info.

        Args:
            preset_name (str):
            denoise_preset_info (dict).
            render_category (str):

        Returns:
            standard_item (QStandardItem):
        '''
        if not denoise_preset_info:
            denoise_preset_info = dict()
        if not all([preset_name, denoise_preset_info]):
            return
        assembly_name = str(denoise_preset_info.get('assembly', str()))
        from_weta = bool(denoise_preset_info.get('from_weta', False))
        shotsub = bool(denoise_preset_info.get('shotsub', False))
        label = str(preset_name)
        standard_item = QStandardItem()
        standard_item.setCheckable(True)
        standard_item.setCheckState(Qt.Unchecked)
        standard_item.setSelectable(False)
        standard_item.setData(preset_name, Qt.UserRole)
        standard_item.setData('denoise', Qt.UserRole + 1)
        standard_item.setData(QSize(0, 20), Qt.SizeHintRole)
        msg = '<img src="{}" width=22 height=22>'.format(NUKE_ICON_PATH)
        msg += 'Preset Name: <b>{}</b>'.format(preset_name)
        if from_weta:
            msg += '<br>From Weta: <b>{}</b>'.format(from_weta)
        if assembly_name:
            msg += '<br>Assembly: <b>{}</b>'.format(assembly_name)
        if shotsub:
            msg += '<br>Shotsub: <b>{}</b>'.format(shotsub)
        matches_render_category = render_category and preset_name == render_category
        if preset_name == 'default' or matches_render_category:
            standard_item.setData(QIcon(STAR_ICON_PATH), Qt.DecorationRole)
            if matches_render_category:
                msg += '<br><b>Matches Render Category</b>'
            _font = standard_item.font()
            _font.setUnderline(True)
            standard_item.setFont(_font)
            standard_item.setForeground(QBrush(QColor(150, 255, 150)))
        else:
            standard_item.setData(QIcon(KOBA_ICON_PATH), Qt.DecorationRole)
        standard_item.setText(label)
        standard_item.setData(msg, Qt.ToolTipRole)
        return standard_item


    ##########################################################################


    def _set_post_task_states_from_index(
            self,
            qmodelindex,
            post_tasks=None,
            uncheck_no_match=True):
        '''
        Set the post task QComboBox to have the list of post tasks checked.

        Args:
            qmodelindex (QModelIndex):
            post_task_name (list):
            uncheck_no_match (bool):
        '''
        if not qmodelindex.isValid():
            return
        if not post_tasks:
            post_tasks = list()

        model = qmodelindex.model()
        if isinstance(model, QSortFilterProxyModel):
            qmodelindex = model.mapToSource(qmodelindex)
        item = qmodelindex.internalPointer()

        if post_tasks:
            item.set_post_tasks(post_tasks)
            self.set_post_task_check_states(
                post_tasks,
                uncheck_no_match=bool(uncheck_no_match))
        else:
            item.set_post_tasks(list())
            self.set_post_task_check_states(list())


    def _update_display_text(self, post_tasks, icon=None):
        '''
        Update the display text of this QComboBox depending on number of post tasks.

        Args:
            post_tasks (list):
            icon (QIcon): optionally update the overview QComboBox label
                to particular QIcon
        '''
        count = len(post_tasks)
        if count > 1:
            item_text = '{} Post Tasks'.format(count)
        elif post_tasks:
            item_text = post_tasks[0].get('name')
        else:
            item_text = str()
        model = self.model()

        model.blockSignals(True)
        model.removeRow(0)
        standard_item = QStandardItem(str(item_text))
        standard_item.setSelectable(False)

        if icon:
            standard_item.setData(icon, Qt.DecorationRole)

        model.insertRow(0, standard_item)
        if self._lineEdit_filter:
            self._lineEdit_filter.setParent(self)
            self._tree_view.setIndexWidget(
                standard_item.index(),
                self._lineEdit_filter)

        self.setCurrentIndex(0)

        model.blockSignals(False)


    def _filter_view_by_search_text(self, search_str):
        '''
        Temporarily filter the post tasks view by string search.

        Args:
            search_str (str):
        '''
        search_str = str(search_str or str()).lower()
        model = self.model()
        for row in range(1, model.rowCount(QModelIndex()), 1):
            qmodelindex = model.index(row, 0, QModelIndex())
            for row_item in range(model.rowCount(qmodelindex)):
                qmodelindex_item = model.index(row_item, 0, qmodelindex)
                standard_item = model.itemFromIndex(qmodelindex_item)
                post_task_name = standard_item.data(Qt.UserRole)
                if hasattr(post_task_name, 'toString'):
                    post_task_name = post_task_name.toString()
                visible = search_str in str(post_task_name).lower()
                self._tree_view.setRowHidden(row_item, qmodelindex, not visible)


    ##########################################################################


    def showPopup(self):
        QComboBox.showPopup(self)
        if self._lineEdit_filter:
            # if c++ objecxt pointer already cleaned up
            try:
                self._lineEdit_filter.setFocus()
            except Exception:
                pass


    def hidePopup(self):
        if self._lineEdit_filter:
            # if c++ objecxt pointer already cleaned up
            try:
                self._lineEdit_filter.setText(str())
                self._lineEdit_filter.clearFocus()
            except Exception:
                pass
        QComboBox.hidePopup(self)


    def _post_task_item_changed(self):
        self.postTasksChanged.emit()