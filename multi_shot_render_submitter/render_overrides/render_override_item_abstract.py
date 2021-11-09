

import abc
import logging
import os
import traceback


logging.basicConfig()
LOGGER = logging.getLogger('render_override')
LOGGER.setLevel(logging.DEBUG)


##############################################################################


class RenderOverrideItemAbstract(object):
    '''
    The abstract interface for a Render Override Item, which has methods
    to apply and revert an override for a host app render node.

    Args:
        value (object): current value of this override according to override item type
    '''

    # NOTE: Must provide unique override id and label string
    OVERRIDE_ID = None
    OVERRIDE_TYPE = 'string'
    OVERRIDE_LABEL = None
    OVERRIDE_ACRONYM = str()
    OVERRIDE_CATEGORY = None
    OVERRIDE_DESCRIPTION = None
    # Optionally provide a different description for popup edit dialog
    OVERRIDE_DESCRIPTION_FOR_UI = None
    OVERRIDE_COLOUR = None
    OVERRIDE_ICON_PATH = None
    USE_OVERRIDE_ICON_IN_VIEW = False
    VALID_TYPES = ['string', 'bool', 'int', 'float', 'enum', 'tuple', 'dict']
    AUTHOR = str()
    AUTHOR_DEPARTMENT = str()
    # Optionally only expose this MSRS override when user oz into specific projects
    EXPOSED_FOR_PROJECTS = list()
    # Optionally only expose override for particular user/s
    EXPOSED_FOR_USERS = list()
    # For int and float values a min and max can be defined
    OVERRIDE_DEFAULT_VALUE = 100
    OVERRIDE_MIN_VALUE = -2147483647
    OVERRIDE_MAX_VALUE = 2147483647
    # String render overrides can optionally be single or multiple lines
    STRING_OVERRIDE_IS_MULTILINE = False
    # For tuples optionally provide a label to show in any UI for each component
    TUPLE_LABELS = None
    # Whether MSRS framework should auto apply and revert this override
    # during submission or not. If False then this override will only be applied
    # if some reimplemented logic during submission invokes it.
    AUTO_APPLY_AT_SUBMIT = True

    __metaclass__ = abc.ABCMeta


    def __init__(self, value=None):

        if value == None:
            value = self.OVERRIDE_DEFAULT_VALUE
        self._value = value

        # For enum default to first enum label option, if value not yet set.
        if self.OVERRIDE_TYPE == 'enum' and not self._value:
            enum_options = self.get_enum_options()
            if enum_options:
                self._value = enum_options[0]

        # Validate all constants
        self.validate_override()

        # Transient attribute data
        self._render_override_nodes_to_delete = list()

        # msg = 'Instantiated Render Override Item: "{}"'.format(self.OVERRIDE_ID)
        # LOGGER.info(msg)


    ##########################################################################
    # Core override methods


    @abc.abstractmethod
    def apply_render_override(self, render_node, pass_for_env_item, value):
        '''
        Apply the render override value to target host app render node, or
        add a host app node and modify a value. Make sure to cache any changes in relation to
        render node or added node, so revert override can be applied as expected.
        This method also gives access to the relevant MSRS data objects, in case these
        need to be introspected during apply override.

        Args:
            render_node (object): the host app Render node object. For example in Katana this is a "Render" node.
            pass_for_env_item (RenderPassForEnvItem):
            value (object): the value to apply as override with type according to this render override item

        Returns:
            success, result_msg (tuple): a tuple of whether override was applied, and any relevant message to pass to client
        '''
        msg = 'Must Implement apply_render_override!'
        raise NotImplementedError(msg)


    @abc.abstractmethod
    def revert_render_override(self, render_node, pass_for_env_item):
        '''
        Revert the just applied override value of this render override, returning the host app project back to it's previous state.
        This method also gives access to the relevant MSRS data objects, in case these need to be introspected during revert override.

        Args:
            render_node (object): the host app Render node object. For example in Katana this is a "Render" node.
            pass_for_env_item (RenderPassForEnvItem):

        Returns:
            success, result_msg (tuple): a tuple of whether override was reverted, and any relevant message to pass to client
        '''
        msg = 'Must Implement revert_render_override!'
        raise NotImplementedError(msg)


    def validate_override(self):
        '''
        Validate override is valid based on all core constants set, otherwise raise error.
        Reimplement if custom validation is required.

        Raises:
            AttributeError: if current override not valid
        '''
        if not self.OVERRIDE_ID:
            msg = 'Override Must Have Id!'
            raise AttributeError(msg)

        # if not self.OVERRIDE_LABEL:
        #     msg = 'Override Must Have Display Label!'
        #     raise AttributeError(msg)

        if self.OVERRIDE_TYPE not in self.VALID_TYPES:
            msg = 'Override Type Of "{}" Not Currently Supported!'.format(self.OVERRIDE_TYPE)
            raise AttributeError(msg)

        if self.OVERRIDE_TYPE == 'enum' and not self.get_enum_options():
            msg = 'Override Type Of "enum" And No Labels Implemented!'
            raise AttributeError(msg)


    def clear_cached_values(self):
        '''
        Clear any cached values to ensure no dirty values.
        NOTE: Reimplement this method to clear any transient data that might be cached between
        apply and revert render override. For example this might reset a variable that keeps track of
        what render node was connected to, and what node/s were added during
        apply override that should be deleted.
        '''
        self._render_override_nodes_to_delete = list()


    def get_suggested_override_node_name(self, node_name):
        '''
        Get suggested name for the node that is created to apply the render override (if any).
        NOTE: Call this in apply_render_override if a consistent suggested node name should be used.
        NOTE: Some render overrides might be applied directly to render node,
        in which case this method can be ignored.

        Args:
            node_name (str): the name of the render node in host app

        Returns:
            override_node_name (str):
        '''
        if not node_name:
            node_name = str()
        prefix = 'MSRS'
        override_label = self.OVERRIDE_LABEL.replace(' ', str())
        override_node_name = '_'.join([prefix, node_name, override_label])
        return override_node_name


    ##########################################################################
    # Core value methods


    def get_value(self):
        '''
        Get the current MSRS value of this override according to override item type.

        Returns:
            value (object):
        '''
        return self._value


    def set_value(self, value):
        '''
        Set the current MSRS value of this render override item,
        without changing anything in host app.

        Args
            value (object):
        '''
        msg = 'Setting Render Override Item: "{}". '.format(self.OVERRIDE_ID)
        # if self._pass_for_env_item:
        #     identifier = self._pass_for_env_item.get_identifier(nice_env_name=True)
        #     msg += 'For Pass For Env Identifier: "{}". '.format(identifier)
        msg += 'To Value: "{}"'.format(value)
        LOGGER.info(msg)
        self._value = value


    @classmethod
    def serialize_value(cls, value):
        '''
        Serialize render overrides value to a value which can be stored in json file.
        Reimplement this if serialization of other render override types is required.
        NOTE: If user manually modifies json file, they could create type errors that should be avoided.

        Args
            value (object): value to serialize to value appropiate for json file

        Returns:
            value (object): if None then value is not valid
        '''
        # Render override cannot be None value (is invalid)
        if value == None:
            return
        # Cast render override value to value appropiate for data file (json)
        try:
            if cls.OVERRIDE_TYPE in ['string', 'enum']:
                value = str(value)
            elif cls.OVERRIDE_TYPE == 'bool':
                value = bool(value)
            elif cls.OVERRIDE_TYPE == 'int':
                value = int(value)
            elif cls.OVERRIDE_TYPE == 'float':
                value = float(value)
            # NOTE: json doesn't natively support tuple, so cast to list
            elif cls.OVERRIDE_TYPE == 'tuple' and isinstance(value, (tuple, list)):
                value = list(value)
            elif cls.OVERRIDE_TYPE == 'dict':
                return value
            else:
                value = None
        except ValueError:
            value = None
        return value


    @classmethod
    def deserialize_value(cls, value):
        '''
        Deserialize value returned from json file into type appropiate for this render override item.
        Reimplement this if deserialization of other render override types is required.
        NOTE: If user manually modifies json file, they could create type errors that should be avoided.

        Args
            value (object): value to deserialize to value appropiate for this render value

        Returns:
            value (object): if None then value is not valid
        '''
        # Render override cannot be None value (is invalid)
        if value == None:
            return
        # Cast value extracted from data file (json) to this rendr override type
        try:
            if cls.OVERRIDE_TYPE in ['string', 'enum']:
                value = str(value)
            elif cls.OVERRIDE_TYPE == 'bool':
                value = bool(value)
            elif cls.OVERRIDE_TYPE == 'int':
                value = int(value)
            elif cls.OVERRIDE_TYPE == 'float':
                value = float(value)
            elif cls.OVERRIDE_TYPE == 'dict':
                value = value
            # NOTE: For json this will cast a list with length of 2, back to tuple value
            elif cls.OVERRIDE_TYPE == 'tuple' and isinstance(value, (tuple, list)) and len(value) == 2:
                value = tuple(value)
            else:
                value = None
        except Exception:
            value = None
        return value


    @classmethod
    def validate_value(cls, value):
        '''
        Validate render override value is of correct type.
        Reimplement this method of other override types (not built in), need to be validated.

        Args
            value_is_valid (bool):
        '''
        # msg = 'Validating Value: "{}". '.format(value)
        # msg += 'Render Override Type: "{}"'.format(cls.OVERRIDE_TYPE)
        # LOGGER.warning(msg)
        if cls.OVERRIDE_TYPE == 'string' and isinstance(value, basestring):
            return True
        # NOTE: For enum values the value must actually be valid enum choice
        elif cls.OVERRIDE_TYPE == 'enum' and isinstance(value, basestring):
            return value in cls.get_enum_options()
        elif cls.OVERRIDE_TYPE == 'bool' and isinstance(value, bool):
            return True
        elif cls.OVERRIDE_TYPE == 'dict' and isinstance(value, dict):
            return True
        # NOTE: Allow int or float to be used interchangeably within this render override item
        elif cls.OVERRIDE_TYPE in ['int', 'float'] and isinstance(value, (int, float)):
            return True
        # NOTE: Currently tuples of only length 2 is supported by core system (for overrides like resolution)
        elif cls.OVERRIDE_TYPE == 'tuple' and isinstance(value, (tuple, list)) and len(value) == 2:
            return True
        return False


    @classmethod
    def choose_value_from_dialog(cls, value=None, parent=None):
        '''
        Open dialog to let user choose a value appropiate for current render override type.
        NOTE: You can either reimplement the default MSRS dialog to add other render override type
        support. Or reimplement this method to call your own separate dialog to handle other types.

        Args:
            value (object):
            parent (QWidget):

        Returns:
            accepted, value (tuple):
        '''
        from srnd_multi_shot_render_submitter.dialogs import render_override_set_value_dialog
        dialog_ui = render_override_set_value_dialog.RenderOverrideSetValueDialog(
            cls,
            value,
            parent=parent)
        dialog_code = dialog_ui.exec_()

        from Qt.QtWidgets import QDialog
        if dialog_code == QDialog.Accepted:
            return True, dialog_ui.get_value()
        else:
            return False, None

    # @classmethod
    # def choose_value_from_simple_dialog(
    #         cls,
    #         value=None,
    #         default_value=None,
    #         title=None,
    #         parent=None):
    #     '''
    #     Open simple dialog to let the user choose a value appopiate for current render override type.

    #     Args:
    #         parent (QWidget):

    #     Returns:
    #         value (object):
    #     '''
    #     from Qt.QtWidgets import QInputDialog

    #     title = str(title or str())
    #     if not title:
    #         title = 'Choose Value For Render Override'

    #     if cls.OVERRIDE_DESCRIPTION_FOR_UI:
    #         label= str(cls.OVERRIDE_DESCRIPTION_FOR_UI)
    #     else:
    #         label = 'Choose Value For <b>{}</b> Render Override'.format(cls.OVERRIDE_LABEL)
    #         label +=  20 * ' '

    #     # Add description of override
    #     description = cls.OVERRIDE_DESCRIPTION
    #     if description:
    #         label += '<br>Description: <b>{}</b>'.format(description)

    #     label += '<i>'
    #     if cls.OVERRIDE_CATEGORY:
    #         label += '<br>Override Category: <b>{}</b>'.format(cls.OVERRIDE_CATEGORY)
    #     if cls.AUTHOR:
    #         label += '<br>Override Author: <b>{}</b>'.format(cls.AUTHOR)
    #     if cls.AUTHOR_DEPARTMENT:
    #         department = cls.AUTHOR_DEPARTMENT.replace('&', '&&')
    #         label += '<br>Department: <b>{}</b>'.format(department)
    #     label += '<br>Id: <b>{}</b>'.format(cls.OVERRIDE_ID)
    #     label += '</i>'

    #     if cls.OVERRIDE_TYPE in ['int', 'float']:
    #         if value == None:
    #             if default_value == None:
    #                 value = cls.OVERRIDE_DEFAULT_VALUE
    #             else:
    #                 value = default_value
    #         min_value = cls.OVERRIDE_MIN_VALUE
    #         max_value = cls.OVERRIDE_MAX_VALUE
    #         if cls.OVERRIDE_TYPE == 'int':
    #             value, okay = QInputDialog.getInt(
    #                 parent,
    #                 title,
    #                 label,
    #                 value=value,
    #                 min=min_value,
    #                 max=max_value,
    #                 step=1)
    #         else:
    #             value, okay = QInputDialog.getDouble(
    #                 parent,
    #                 title,
    #                 label,
    #                 value=value,
    #                 min=min_value,
    #                 max=max_value)
    #                 # decimals=1)

    #     elif cls.OVERRIDE_TYPE == 'string':
    #             value, okay = QInputDialog.getText(
    #                 parent,
    #                 title,
    #                 label,
    #                 text=value)

    #     elif cls.OVERRIDE_TYPE == 'enum':
    #         from srnd_qt.ui_framework.dialogs import base_popup_dialog
    #         from Qt.QtWidgets import (QDialog, QComboBox, QLabel,
    #             QVBoxLayout, QHBoxLayout, QSizePolicy)
    #         from Qt.QtCore import Qt

    #         dialog = base_popup_dialog.BasePopupDialog(
    #             tool_name=title,
    #             icon_path=cls.OVERRIDE_ICON_PATH,
    #             window_size=(550, 275),
    #             description=label,
    #             description_by_title=False,
    #             parent=parent)
    #         layout = dialog.get_content_widget_layout()
    #         layout.setContentsMargins(8, 8, 8, 8)

    #         horizontal_layout = QHBoxLayout()
    #         horizontal_layout.addWidget(QLabel('Choose Override Value'))
    #         layout.addLayout(horizontal_layout)

    #         combo_box = QComboBox()
    #         combo_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    #         combo_box.addItems(cls.get_enum_options())
    #         horizontal_layout.addWidget(combo_box)

    #         # NOTE: Add long description and short name for each enum option (if available)
    #         descriptions = cls.get_enum_options_descriptions() or list()
    #         enum_options_short = cls.get_enum_options_short() or list()
    #         count = len(descriptions) or len(enum_options_short)
    #         for i in range(0, count, 1):
    #             tooltip = str()
    #             try:
    #                 description = descriptions[i]
    #                 if description:
    #                     tooltip += '<b>Description:</b> {}. '.format(description)
    #             except IndexError:
    #                 pass
    #             try:
    #                 label_short = enum_options_short[i]
    #                 if label_short:
    #                     tooltip += '<b>Short Label:</b> {}. '.format(label_short)
    #             except IndexError:
    #                 pass
    #             if tooltip:
    #                 combo_box.setItemData(i, tooltip, Qt.ToolTipRole)

    #         if value:
    #             import srnd_qt.base.utils
    #             srnd_qt.base.utils.combo_box_set_index_from_str(combo_box, str(value))

    #         layout.addStretch(100)

    #         dialog.build_okay_cancel_buttons()

    #         result = dialog.exec_()
    #         if result == QDialog.Rejected:
    #             return

    #         value = str(combo_box.currentText())

    #     elif cls.OVERRIDE_TYPE == 'tuple':
    #         value = (2048, 1050)

    #     return value


    ##########################################################################


    def get_view_display_value(self):
        '''
        Get a value to show in main MSRS view as very short value that takes up minimum width.

        Returns:
            display_str (str):
        '''
        display_str = str()
        if self.OVERRIDE_TYPE in ['int', 'float']:
            display_str = self.OVERRIDE_ACRONYM + str(self._value)
        elif self.OVERRIDE_TYPE == 'bool':
            if self._value:
                display_str = self.OVERRIDE_LABEL
            else:
                display_str = 'NOT ' + self.OVERRIDE_LABEL
        elif self.OVERRIDE_TYPE == 'enum':
            # NOTE: Returns the long enum option, if no short label
            enum_option_short = self.get_current_enum_option_short()
            display_str = self.OVERRIDE_ACRONYM + str(enum_option_short or str())
        elif self.OVERRIDE_TYPE == 'tuple' and isinstance(self._value, (tuple, list)) and len(self._value) == 2:
            display_str = self.OVERRIDE_ACRONYM + str(self._value[0]) + 'x' + str(self._value[1])
        elif self.OVERRIDE_ACRONYM:
            display_str = self.OVERRIDE_ACRONYM
        display_str = display_str or self.OVERRIDE_LABEL
        return display_str


    @classmethod
    def get_enum_options(cls):
        '''
        If override type is enum, return what the descriptive enum options are here.
        NOTE: This might require inspecting a database or other data source.

        Returns:
            enum_options (list):
        '''
        return list()


    @classmethod
    def get_enum_options_short(cls):
        '''
        If override type is enum, return what the abbrevation or short enum options are here.
        NOTE: This is what is shown in MSRS muilti shot view.

        Returns:
            enum_options_short (list):
        '''
        return list()


    @classmethod
    def get_enum_options_descriptions(cls):
        '''
        If override type is enum, optionally reimplement this method
        to return a description for each option.

        Returns:
            enum_options_descriptions (list):
        '''
        return list()


    def get_current_enum_option(self):
        '''
        Get the current enum option as longer label.

        Returns:
            current_enum_option (str):
        '''
        return self._value


    def get_current_enum_index(self):
        '''
        Get the current enum index.

        Returns:
            index (int): -1 if index not valid
        '''
        enum_options = self.get_enum_options()
        try:
            return enum_options.index(self._value)
        except IndexError:
            return -1


    def get_current_enum_option_short(self):
        '''
        Get the current enum option as short display value to display in MSRS view.
        NOTE: Returns the long enum if short display value not available.

        Returns:
            current_enum_option_short (str):
        '''
        enum_options_short = self.get_enum_options_short()
        # NOTE: If no short enum label implemented return long enum name
        if not enum_options_short:
            return self.get_current_enum_option()
        index = self.get_current_enum_index()
        try:
            return str(enum_options_short[index])
        except Exception:
            return self.get_current_enum_option()


    def get_current_enum_option_description(self):
        '''
        Get the current enum option as long description (if available).

        Returns:
            current_enum_option_short (str):
        '''
        enum_options_descriptions = self.get_enum_options_descriptions()
        if not enum_options_descriptions:
            return str()

        index = self.get_current_enum_index()
        try:
            return str(enum_options_descriptions[index])
        except IndexError:
            return str()


    def get_tuple_labels(self):
        '''
        If this render override is a tuple type, then return any labels for UI (if any).

        Returns:
            tuple_labels (tuple):
        '''
        return self.TUPLE_LABELS


    # def get_pass_for_env_item(self):
    #     '''
    #     Get the pass for env item that has this render override item.

    #     Returns:
    #         pass_for_env_item (RenderPassForEnvItem):

    #     '''
    #     return self._pass_for_env_item


    # def set_pass_for_env_item(self, pass_for_env_item):
    #     '''
    #     Set the pass for env item that has this render override item.

    #     Args:
    #         pass_for_env_item (RenderPassForEnvItem):

    #     '''
    #     if not pass_for_env_item or not hasattr(pass_for_env_item, 'is_pass_for_env_item'):
    #         msg = 'Must Specify Valid Pass For Env Item!'
    #         LOGGER.critical(msg)
    #         return
    #     if not pass_for_env_item.is_pass_for_env_item():
    #         msg = 'Invalid Pass For Env Item Specified: "{}"'.format(pass_for_env_item)
    #         LOGGER.critical(msg)
    #         return
    #     self._pass_for_env_item = pass_for_env_item


    ##########################################################################


    @classmethod
    def get_override_id(cls):
        '''
        Get the unique string identifier to represent this reimplemented override item.

        Returns:
            override_id (str):
        '''
        return cls.OVERRIDE_ID


    @classmethod
    def get_override_type(cls):
        '''
        Get the override data type, for example: "string" or "int"

        Returns:
            override_type (str):
        '''
        return cls.OVERRIDE_TYPE


    @classmethod
    def get_override_label(cls):
        '''
        Get the primary render override label which briefly suggests what this render override does.

        Returns:
            override_label (str):
        '''
        return cls.OVERRIDE_LABEL


    @classmethod
    def get_override_acronym(cls):
        '''
        Get the override acronym (if any) to display in the MSRS main view.

        Returns:
            override_acronym (str):
        '''
        return cls.OVERRIDE_ACRONYM


    @classmethod
    def get_override_category(cls):
        '''
        Get the render override category (if any)

        Returns:
            override_category (str):
        '''
        return cls.OVERRIDE_CATEGORY


    @classmethod
    def get_override_description(cls):
        '''
        Get a longer description of what this render override does.

        Returns:
            override_description (str):
        '''
        return cls.OVERRIDE_DESCRIPTION


    @classmethod
    def get_override_description_for_ui(cls):
        '''
        Get a description to display in popup dialog of what this render override does.

        Returns:
            override_description_for_ui (str):
        '''
        return cls.OVERRIDE_DESCRIPTION_FOR_UI


    @classmethod
    def get_override_colour(cls):
        '''
        Get override colour (if any):

        Returns:
            override_colour (tuple): RGB tuple
        '''
        return cls.OVERRIDE_COLOUR


    @classmethod
    def get_override_icon_path(cls):
        '''
        Get the override icon path (if any).

        Returns:
            override_icon_path (str):
        '''
        return cls.OVERRIDE_ICON_PATH


    @classmethod
    def get_use_override_icon_in_view(cls):
        '''
        Get whether to display the override icon or display label or current short enum value in view.

        Returns:
            use_override_icon_in_view (bool):
        '''
        return cls.USE_OVERRIDE_ICON_IN_VIEW


    @classmethod
    @abc.abstractmethod
    def in_supported_host_app(cls):
        '''
        Must implement whether this render override is in required host app.

        Returns:
            in_supported_host_app (bool):
        '''
        msg = 'Must Implement "in_supported_host_app"'
        raise NotImplementedError(msg)


    @classmethod
    def get_author(cls):
        '''
        Get the author of this render override.

        Returns:
            author (str):
        '''
        return cls.AUTHOR


    @classmethod
    def get_author_department(cls):
        '''
        Get the author department of this render override.

        Returns:
            author_department (str):
        '''
        return cls.AUTHOR_DEPARTMENT


    @classmethod
    def get_intended_for_projects(cls):
        '''
        Get a list of projects which this render override should only be exposed to.

        Returns:
            intended_for_projects (list):
        '''
        return cls.EXPOSED_FOR_PROJECTS or list()


    @classmethod
    def get_intended_for_users(cls):
        '''
        Get a list of users which this render override should only be exposed to.

        Returns:
            intended_for_users (list):
        '''
        return cls.EXPOSED_FOR_USERS or list()


    @classmethod
    def get_min_value(cls):
        '''
        Return the min value of int or float override item type.

        Returns:
            min_value (int): or float
        '''
        return cls.OVERRIDE_MIN_VALUE


    @classmethod
    def get_max_value(cls):
        '''
        Return the max value of int or float override item type.

        Returns:
            max_value (int): or float
        '''
        return cls.OVERRIDE_MAX_VALUE


    def __str__(self):
        '''
        Get human readable display label to show details about data object.

        Returns:
            msg (str):
        '''
        msg = 'RenderOverrideItem'
        msg += '->ID: "{}"'.format(self.OVERRIDE_ID)
        msg += '->Type: "{}"'.format(self.OVERRIDE_TYPE)
        msg += '->Label: "{}"'.format(self.OVERRIDE_LABEL)
        return msg


##############################################################################


# def register_plugin():
#     '''
#     Example of register this render override item.
#     NOTE: This abstract class isn't registered.

#     Returns:
#         render_override_item (RenderOverrideItem):
#     '''
#     return RenderOverrideItemAbstract