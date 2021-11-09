

'''
This is part of a reusable framework for building applications
that require a multi shot rendering system.

Note: These base data objects are currently semi implemented or return
values, to allow the GEN Multi Shot Render Submitter to be opened as an
application, with limited functionality. All host app methods are not
properly implemented but return values. Other Multi Shot Render Submitter
implementations may choose to reimplement these base data objects directly,
since some of the default implementation can be reused.
With the understanding reimplementation is still required for
desired host app methods.

Note: In the near future the base nodes will inherit from a
fully abstract interface. In which case external reimplementations
may choose to instead use the abtract data nodes as the super
classes, rather than these current base nodes. For now the extra level
of inheritance isn't required or desired.
'''


import collections
import fileseq
import logging
import os
import re
import time
import traceback

from Qt.QtCore import Signal

from srnd_qt.ui_framework.models import base_tree_node

from srnd_multi_shot_render_submitter import production_info
from srnd_multi_shot_render_submitter import utils
from srnd_multi_shot_render_submitter.constants import Constants


# LOGGER = logging.getLogger(__name__)
# LOGGER.setLevel(logging.INFO)

constants = Constants()


#############################################################################


class BaseMultiShotItem(base_tree_node.BaseTreeNode):
    '''
    Base object of all MSRS data objects that also appear in MultiShotRenderModel.
    An object to store a name and all core MSRS states, such as queued and enabled state.
    NOTE: Includes methods which may be used to help implement the
    external MSRS model, among other use cases.

    Args:
        name (str):
        queued (bool):
        enabled (bool):
        node_type (str):
        icon_path (str):
        first_sibling (bool): if this abstract data Node is intended to be
            a sibling, pass in the first sibling, which manages all other siblings.
        identity_id (str): optional existing uuid number to reuse
        debug_mode (bool): whether this abstract data emits message signals upstream
        insertion_row (int): optionally choose the index this item is inserted under parent
        parent (object): optionally choose the parent data object at construction time
    '''

    logMessage = Signal(str, int)
    toggleProgressBarVisible = Signal(bool)
    updateLoadingBarFormat = Signal(int, str)

    def __init__(
            self,
            name=None,
            queued=True,
            enabled=True,
            node_type='BaseMultiShotItem',
            icon_path=None,
            first_sibling=None,
            identity_id=None,
            debug_mode=False,
            insertion_row=None,
            parent=None):
        super(BaseMultiShotItem, self).__init__(
            name=name,
            node_type=node_type,
            icon_path=icon_path,
            expanding_model=False,
            debug_mode=debug_mode,
            first_sibling=first_sibling,
            insertion_row=insertion_row,
            parent=parent)

        self._queued = queued
        self._enabled = enabled

        self._update_host_app = True
        self._is_selected_in_msrs = False

        self.derive_identity_id(identity_id=identity_id)


    def derive_identity_id(self, identity_id=None):
        '''
        Derive and set the identity id. Optionally pass in existing identity id.

        Args:
            identity_id (str):

        Returns:
            identity_id (str):
        '''
        if not identity_id:
            import uuid
            identity_id = str(uuid.uuid4())
        self._identity_id = str(identity_id)
        return self._identity_id


    def get_session_data(self):
        '''
        Gather the most generic session data for the base of any Multi Shot item.

        Returns:
            data (dict):
        '''
        data = dict()

        identity_id = self.get_identity_id()
        if not identity_id:
            identity_id = self.derive_identity_id()
        data['identity_id'] = str(identity_id)

        data['queued'] = bool(self.get_queued())
        data['enabled'] = bool(self.get_enabled())

        return data


    def apply_session_data(self, data=None, **kwargs):
        '''
        Apply most generic session data to the base of any Multi Shot item.

        Args:
            data (dict):

        Returns:
            sync_count (int):
        '''
        if not data or not isinstance(data, dict):
            return 0

        sync_count = 0

        identity_id = data.get('identity_id', str())
        if identity_id and isinstance(identity_id, basestring):
            self._identity_id = str(identity_id)
            sync_count += 1

        queued = data.get('queued')
        if isinstance(queued, bool):
            self.set_queued(queued)
            sync_count += 1

        enabled = data.get('enabled')
        if isinstance(enabled, bool):
            self.set_enabled(enabled)
            sync_count += 1

        return sync_count


    def get_root_item(self):
        '''
        Traverse up until get to the root item.

        Returns:
            root_item (RootMultiShotItem): or subclass of RootMultiShotItem
        '''
        parent = self.parent()
        if parent and hasattr(parent, 'get_root_item'):
            return parent.get_root_item()
        elif parent:
            return parent
        return self


    def get_identity_id(self):
        '''
        Get the identity uuid of this item.

        Returns:
            identity_id (str):
        '''
        return self._identity_id


    def get_queued(self):
        '''
        Get whether node is queued or not.
        Note: This is not a state that exists on host app node itself.

        Returns:
            queued (str):
        '''
        return self._queued


    def set_queued(self, queued):
        '''
        Set whether node is queued or not.
        Note: This is not a state that exists on host app node itself.

        Args:
            queued (str):
        '''
        if self._debug_mode:
            msg = '{}.set_queued(). '.format(self._node_type)
            msg += self._get_env_and_pass_name_message()
            msg += 'Value: {}'.format(queued)
            self.logMessage.emit(msg, logging.DEBUG)
        queued_changed = queued != self._queued
        self._queued = queued

        if self.is_pass_for_env_item() and queued_changed and self.get_active():
            if not self.get_resolved_frames_queued():
                self.resolve_frames()


    def get_enabled(self):
        '''
        Get whether node is enabled (not bypassed).

        Returns:
            enabled (str):
        '''
        return self._enabled


    def set_enabled(self, enabled):
        '''
        Set whether node is enabled (not bypassed).
        Requires reimplementation to toggle enabled this node in host app.

        Args:
            enabled (str):
        '''
        if self._debug_mode:
            msg = '{}.set_enabled(). '.format(self._node_type)
            msg += self._get_env_and_pass_name_message()
            msg += 'Value: {}'.format(enabled)
            self.logMessage.emit(msg, logging.DEBUG)
        enabled_changed = enabled != self._enabled
        self._enabled = enabled

        if self.is_pass_for_env_item() and enabled_changed and self.get_active():
            if not self.get_resolved_frames_queued():
                self.resolve_frames()


    def get_active(self):
        '''
        Get whether is active for render submission.

        Returns:
            active (bool):
        '''
        return self._queued and self._enabled


    def set_active(self, value):
        '''
        Set whether is active for render submission, by setting both
        queued and enabled to true.

        Returns:
            value (bool):
        '''
        value = bool(value)
        self._queued = value
        self._enabled = value


    def clear_overrides(self):
        '''
        No overrides at this level to clear in default implementation.
        '''
        return


    def copy_overrides(self):
        '''
        No overrides to copy at this level currently.

        Returns:
            overrides_dict (dict):
        '''
        return dict()


    def paste_overrides(self, overrides_dict=None):
        '''
        No overrides to paste at this level currently.

        Args:
            overrides_dict (dict):

        Returns:
            overrides_applied (int):
        '''
        if not overrides_dict:
            overrides_dict = dict()
        return 0


    def get_update_host_app(self):
        '''
        Is Clarisse updating when nodes are updated in model.

        Returns:
            update_host_app (str): name of Clarisse node
        '''
        return self._update_host_app


    def set_update_host_app(self, update_host_app, recursive=True):
        '''
        Set whether to make this node and all child nodes
        perform updates on host app data or not when values changed.

        Args:
            update_host_app (str):
            recursive (bool):
        '''
        if self._debug_mode:
            msg = '{}.set_update_host_app(). '.format(self._node_type)
            msg += self._get_env_and_pass_name_message()
            msg += 'Value: {}'.format(update_host_app)
            self.logMessage.emit(msg, logging.DEBUG)

        self._update_host_app = update_host_app

        if recursive:
            for node in self.children():
                node.set_update_host_app(
                    update_host_app,
                    recursive=True)


    def is_render_item(self):
        '''
        Return whether this item is a render item or not.
        Note: Subclasses should reimplement this.

        Returns:
            is_render_item (bool):
        '''
        return False


    def is_environment_item(self):
        '''
        Return whether this item is a environment item or not.
        Note: Subclasses should reimplement this.

        Returns:
            is_environment_item (bool):
        '''
        return False


    def is_pass_for_env_item(self):
        '''
        Return whether this item is a pass for env item or not.
        Note: Subclasses should reimplement this.

        Returns:
            is_pass_for_env_item (bool):
        '''
        return False


    def is_group_item(self):
        '''
        Return whether this item is a group item or not.
        Note: Subclasses should reimplement this.

        Returns:
            is_group_item (bool):
        '''
        return False


    def _get_env_and_pass_name_message(self, prefix=str()):
        '''
        Get a message about environment and pass name for
        this subclassed EnvironmentItem or RenderPassForEnvItem.

        Args:
            prefix (str):

        Returns:
            msg (str):
        '''
        try:
            if self.is_environment_item():
                msg = '{}Environment: "{}". '.format(prefix, self.get_oz_area())
            elif self.is_pass_for_env_item():
                environment_item = self.get_environment_item()
                render_item = self.get_source_render_item()
                msg = '{}Environment: "{}". '.format(prefix, environment_item.get_oz_area())
                msg = '{}Pass name: "{}". '.format(prefix, render_item.get_pass_name())
            else:
                msg = '{}Name: "{}". '.format(prefix, self._name)
        except Exception:
            msg = str()
        return msg


    def get_is_selected_in_msrs(self):
        '''
        Get whether this MSRS item is selected in multi shot view or not.
        NOTE: This is cached to this data object by the MSRS view.

        Returns:
            is_selected_in_msrs (bool):
        '''
        return self._is_selected_in_msrs


    def _set_is_selected_in_msrs(self, value):
        '''
        Set whether this MSRS item is selected in multi shot view or not.
        NOTE: This is cached to this data object by the MSRS view.

        Args:
            value (bool):
        '''
        self._is_selected_in_msrs = bool(value)


#############################################################################


class RenderItem(BaseMultiShotItem):
    '''
    A MSRS object representation of host app render node which stores
    the most interesting details such as node name or full path.

    Args:
        node_name (str): source generic Render node name
        item_full_name (str): full name to item (if applicable to host app).
            otherwise same as node name.
        pass_name (str):
        aov_names (list):
        render_category (str):
        camera_hyref (str):
        node_type (str):
        icon_path (str):
        identity_id (str): optional existing uuid number to reuse
        debug_mode (bool): whether this abstract data emits message signals upstream
    '''

    logMessage = Signal(str, int)
    toggleProgressBarVisible = Signal(bool)
    updateLoadingBarFormat = Signal(int, str)

    def __init__(
            self,
            node_name=None,
            item_full_name=None,
            pass_name=None,
            aov_names=None,
            render_category=None,
            camera_hyref=None,
            node_type='RenderItem',
            icon_path=None,
            identity_id=None,
            debug_mode=False,
            parent=None):

        kwargs = dict(locals())
        kwargs.pop('self')
        kwargs.pop('node_name')
        kwargs.pop('item_full_name')
        kwargs.pop('pass_name')
        kwargs.pop('aov_names')
        kwargs.pop('render_category')
        kwargs.pop('camera_hyref')
        kwargs['name'] = node_name

        super(RenderItem, self).__init__(**kwargs)

        self._pass_name = pass_name or node_name
        self._aov_names = aov_names
        self._render_category = render_category
        self._camera_hyref = camera_hyref
        self._item_full_name = item_full_name or node_name
        self._node_colour = None
        self._other_attrs = collections.OrderedDict()

        self._frames = str()
        self._explicit_version = 1

        self._renderable_count_for_render_node = 0
        self._render_node_resource_names = list()

        # NOTE: cached value used by headerData for font role, to help choose text size
        self._cached_width = None


    def get_session_data(self):
        '''
        Gather all session details for this render item or subclass.
        Reimplement this method to gather additional session data for subclassed items.

        Returns:
            data (dict):
        '''
        data = dict()

        identity_id = self.get_identity_id()
        if not identity_id:
            identity_id = self.derive_identity_id()
        data['identity_id'] = str(identity_id)

        enabled = self.get_enabled()
        data['enabled'] = str(enabled)

        pass_name = self.get_pass_name()
        data['pass_name'] = str(pass_name)

        node_colour = self.get_node_colour()
        if node_colour != None:
            data['node_colour'] = node_colour

        return data


    def apply_session_data(self, data=None, **kwargs):
        '''
        Apply session data to this render item or subclass.
        Reimplement this method to apply additional session data for subclassed items.

        Args:
            data (dict):

        Returns:
            sync_count (int):
        '''
        if not data or not isinstance(data, dict):
            return 0

        sync_count = BaseMultiShotItem.apply_session_data(self, data)

        # # NOTE: Keep already synced pass name from host app.
        # # Since this pass name is not currently editable via Multi Shot UI.
        # pass_name = data.get('pass_name')
        # if pass_name:
        #     self.set_pass_name(str(pass_name))

        node_colour = data.get('node_colour')
        if isinstance(node_colour, (tuple, list)) and len(node_colour) == 3:
            self.set_node_colour(node_colour)
        # NOTE: Support for loading node colour as a string tag name
        elif isinstance(node_colour, basestring):
            self.set_node_colour(str(node_colour or str()))

        sync_count += 1

        return sync_count


    def search_for_string(self, search_text):
        '''
        Search this render item data object for matching string.

        Args:
            search_text (str):

        Returns:
            found (bool):
        '''
        if not search_text:
            return False

        PASS_TOKENS = ('pass:')
        has_pass_tokens = search_text.startswith(PASS_TOKENS)
        if has_pass_tokens:
            search_text = search_text.split(':')[-1]

        if not search_text:
            return False

        node_name = str(self.get_node_name())
        pass_name =  str(self.get_pass_name())
        node_type =  str(self.get_node_type())
        check_values = [node_name, pass_name, node_type]
        item_full_name = str(self.get_item_full_name())

        if node_name != item_full_name:
            check_values.append(item_full_name)

        for check_value in check_values:
            result = re.findall(search_text, check_value, flags=re.IGNORECASE)
            if result:
                return True

        return False


    def sync_render_details(self, fast=True):
        '''
        Sync all details about this Render node from host application.
        Requires reimplementation for particular host app.

        Args:
            fast (bool): for some expensive sync operations, only perform when about to submit

        Returns:
            success (bool):
        '''
        return False


    def get_frames(self):
        '''
        Get the cached frames synced from host app render item (if any).

        Returns:
            frames (str):
        '''
        return self._frames


    def get_current_project_frame(self):
        '''
        Get the current host app project frame.
        TODO: Should be moved to a new Scene data object (with changes to Multi Shot API).
        Requires reimplementation for particular host app.

        Returns:
            frame (int):
        '''
        return None


    def get_current_project_version(self):
        '''
        Get the current host app project version (if any).
        TODO: Should be moved to a new Scene data object (with changes to Multi Shot API).
        Requires reimplementation for particular host app.

        Returns:
            version (int):
        '''
        return None


    def get_explicit_version(self):
        '''
        Get the cached explicit version synced from host app render item (if any).

        Returns:
            frames (str):
        '''
        return self._explicit_version


    def get_node_name(self):
        '''
        Get the node name this abstract data node points to
        for host app render node.

        Returns:
            node_name (str):
        '''
        return self.get_name()


    def set_node_name(self, node_name):
        '''
        Set the node name this abstract data node points to
        for host app render node.

        Args:
            node_name (str):
        '''
        self.set_name(node_name)


    def get_item_full_name(self):
        '''
        Get the full name to this RenderItem.

        Returns:
            item_full_name (str):
        '''
        return self._item_full_name


    def set_item_full_name(self, item_full_name):
        '''
        Set the full name to this RenderItem.

        Args:
            item_full_name (str):
        '''
        self._item_full_name = item_full_name


    def rename_node(self, new_node_name):
        '''
        Rename the host app node name of this Render item.

        Args:
            new_node_name (str):

        Returns:
            new_node_name (str):
        '''
        self._cached_width = None
        self.set_node_name(new_node_name)
        self.set_pass_name(new_node_name)
        return new_node_name


    def get_pass_name(self):
        '''
        Get the pass name of this Render item.

        Returns:
            pass_name (str):
        '''
        return self._pass_name


    def set_pass_name(self, pass_name):
        '''
        Set the pass name of host app node of this Render item.
        Requires reimplementation to set pass name for this node in host app.

        Args:
            pass_name (str):
        '''
        self._pass_name = pass_name


    def get_aov_names(self):
        '''
        Get any AOV names associated to this render pass for env.

        Returns:
            aov_names (list):
        '''
        return self._aov_names


    def set_aov_names(self, aov_names):
        '''
        Set any AOV names associated to this render pass for env.

        Args:
            aov_names (list):
        '''
        self._aov_names = aov_names


    def get_render_category(self):
        '''
        Get the render category in relation to the host app render node of this render item.

        Returns:
            render_category (str):
        '''
        return self._render_category


    def set_render_category(self, render_category):
        '''
        Set the render category in relation to the host app render node of this render item.

        Args:
            render_category (str):
        '''
        self._render_category = render_category


    def compute_camera_hyref(self):
        '''
        Compute and cache camera Hyref for this render item.
        Requires reimplementation.

        Returns:
            camera_hyref (str):
        '''
        # Must implement code to compute and cache camera Hyref here.
        return self._camera_hyref


    def get_camera_hyref(self):
        '''
        Get the camera hyref in relation to the host app camera node of this render item.

        Returns:
            camera_hyref (str):
        '''
        return self._camera_hyref


    def get_node_colour(self):
        '''
        Get the node colour.

        Returns:
            node_colour (list): RGB list of values between 0 and 1
        '''
        return self._node_colour


    def set_node_colour(self, colour):
        '''
        Set the node colour.
        Requires reimplementation to set this node color in host app.

        Args:
            colour (list): RGB list of values between 0 and 1
        '''
        if colour and isinstance(colour, (list, tuple)):
            self._node_colour = list(colour)
        else:
            self._node_colour = colour


    def get_render_node_resource_names(self):
        '''
        Get the cached available resource names to output path to Shotsub.

        Returns:
            value (list):
        '''
        return self._render_node_resource_names


    def get_other_attr(self, attr_name):
        '''
        Get some other arbitary extra attribute value
        this RenderItem is storing.

        Returns:
            value (object):
        '''
        return self._other_attrs.get(attr_name)


    def add_other_attr(self, key, value):
        '''
        Add a single other arbitary key to store on this RenderItem.

        Args:
            key (str):
            value (object):
        '''
        if not isinstance(key, str):
            msg = 'Key Must Be A String In Order To Add Attr Value!'
            raise AttributeError(msg)
        self._other_attrs[key] = value


    def get_other_attrs(self):
        '''
        Get mapping of all other arbitary extra attributes as key / values dict.

        Returns:
            other_attrs (dict):
        '''
        return self._other_attrs


    def set_other_attr(self, other_attrs):
        '''
        Set all other arbitary extra attributes this RenderItem is storing.

        Args:
            other_attrs (dict):
        '''
        if not isinstance(other_attrs, (dict, collections.OrderedDict)):
            msg = 'Must Provide A Dict Or OrderedDict For Other Attrs!'
            raise AttributeError(msg)
        self._other_attrs = other_attrs


    def get_node_in_host_app(self):
        '''
        Get the host app class this abstract node represents, assuming
        it still exists in current project.
        Requires reimplementation.

        Returns:
            class_object (object): returns the native host app class object (if any)
        '''
        return None


    def select_node_in_host_app(self):
        '''
        Select this Render node in host app.
        Requires reimplementation.

        Returns:
            success (bool):
        '''
        return False


    def get_is_selected_in_host_app(self):
        '''
        Check is this node selected in host app or not.
        Requires reimplementation.

        Returns:
            success (bool):
        '''
        return False


    def delete_node_in_host_app(self):
        '''
        Delete this Render node in host app.
        Note: This doesn't currently actually remove this node from data model.
        Requires reimplementation.

        Returns:
            success (bool):
        '''
        return False


    def _get_renderable_count_for_render_node(self):
        '''
        Get total number of current renderable passes, that are
        referring to this for this source RenderItem.
        Is a caching mechanism for summary details and custom paint events.
        '''
        return self._renderable_count_for_render_node


    def is_render_item(self):
        '''
        This method returns the type of node, so subclasses with possibly
        a different item type string, can still be identified as a
        node with specific functionality.

        Returns:
            is_render_item (bool):
        '''
        return True


    def __repr__(self):
        '''
        Get a string that enables the constuctor to run to initialize
        another identical instance of this class.

        Returns:
            msg (str):
        '''
        msg = '{}('.format(self._node_type)
        msg += '"{}", '.format(self.get_node_name())
        msg += 'pass_name="{}")'.format(self.get_pass_name())
        return msg


    def __str__(self):
        '''
        Get human readable display label to show details about data object.

        Returns:
            msg (str):
        '''
        msg = '{} For Host App '.format(self._node_type)
        msg += 'Node: "{}". '.format(self.get_node_name())
        msg += self._get_env_and_pass_name_message(prefix='\n->')
        return msg


#############################################################################


class OverrideBaseItem(BaseMultiShotItem):
    '''
    A MSRS object representation of core overrides which can have some
    basic overrides such as version and frame rule.
    Note: Is the base class for other MSRS items that require overrides such as
    an Environment and RenderPassForEnv item.

    Args:
        name (str):
        queued (bool):
        enabled (bool):
        overrides_dict (dict):
        version_override (str): override of version for env (None if not set)
        frame_range_override (str): override of pass for env frame range (None if not set)
        note_override (str): override of note (None if not set)
        node_type (str):
        icon_path (str):
        render_overrides_items (collections.OrderedDict):
            dict mapping of render override id to render override item that
            this render pass for env has
        first_sibling (bool): if this abstract data Node is intended to be
            a sibling, pass in the first sibling, which manages all other siblings.
        identity_id (str): optional existing uuid number to reuse
        debug_mode (bool): whether this abstract data emits message signals upstream
        insertion_row (int): optionally choose the index this item is inserted under parent
        parent (object): optionally choose the parent data object at construction time
    '''

    logMessage = Signal(str, int)
    toggleProgressBarVisible = Signal(bool)
    updateLoadingBarFormat = Signal(int, str)

    def __init__(
            self,
            name=None,
            queued=True,
            enabled=True,
            overrides_dict=None,
            version_override=None,
            frame_range_override=None,
            not_frame_range_override=None,
            note_override=None,
            node_type='RenderItem',
            icon_path=None,
            render_overrides_items=None,
            first_sibling=None,
            identity_id=None,
            debug_mode=False,
            insertion_row=None,
            parent=None):

        kwargs = dict(locals())
        kwargs.pop('self')
        kwargs.pop('render_overrides_items')
        kwargs.pop('overrides_dict')
        kwargs.pop('version_override')
        kwargs.pop('frame_range_override')
        kwargs.pop('not_frame_range_override')
        kwargs.pop('note_override')

        super(OverrideBaseItem, self).__init__(**kwargs)

        self._render_overrides_items = render_overrides_items or collections.OrderedDict()
        self._version_override = version_override

        self._frame_range_override = frame_range_override
        self._not_frame_range_override = not_frame_range_override

        self._frames_rule_important = False
        self._frames_rule_fml = False
        self._frames_rule_x1 = False
        self._frames_rule_x10 = False
        self._frames_rule_xn = None
        self._not_frames_rule_important = False
        self._not_frames_rule_fml = False
        self._not_frames_rule_x10 = False
        self._not_frames_rule_xn = None

        self._note_override = note_override
        self._note_override_submission = None
        self._wait_on = list()
        self._wait_on_plow_ids = list()
        self._colour = None

        self._post_tasks = list()
        self._dispatcher_plow_job_id = None


    def get_session_data(self, use_submit_note=False):
        '''
        Gather all session details for this override base item or subclass.
        Reimplement this method to gather additional session data for subclassed items.

        Args:
            use_submit_note (str):

        Returns:
            data (dict):
        '''
        # Gather identity id and active states from super class
        data = BaseMultiShotItem.get_session_data(self) or collections.OrderedDict()



        render_overrides_data = self.get_render_overrides_session_data()
        if render_overrides_data:
            data[constants.SESSION_KEY_RENDER_OVERRIDES_DATA] = render_overrides_data

        version_override = self.get_version_override()
        if version_override:
            data['version_override'] = version_override

        frame_range_override = self.get_frame_range_override()
        if frame_range_override:
            data['frame_range_override'] = frame_range_override

        not_frame_range_override = self.get_not_frame_range_override()
        if not_frame_range_override:
            data['not_frame_range_override'] = not_frame_range_override

        frames_rule_important = self.get_frames_rule_important()
        if frames_rule_important:
            data['frames_rule_important'] = bool(frames_rule_important)

        frames_rule_fml = self.get_frames_rule_fml()
        if frames_rule_fml:
            data['frames_rule_fml'] = bool(frames_rule_fml)

        frames_rule_x1 = self.get_frames_rule_x1()
        if frames_rule_x1:
            data['frames_rule_x1']  = bool(frames_rule_x1)

        frames_rule_x10 = self.get_frames_rule_x10()
        if frames_rule_x10:
            data['frames_rule_x10'] = bool(frames_rule_x10)

        frames_rule_xn = self.get_frames_rule_xn()
        if isinstance(frames_rule_xn, int):
            data['frames_rule_xn'] = frames_rule_xn

        not_frames_rule_important = self.get_not_frames_rule_important()
        if not_frames_rule_important:
            data['not_frames_rule_important']  = bool(not_frames_rule_important)

        not_frames_rule_fml = self.get_not_frames_rule_fml()
        if not_frames_rule_fml:
            data['not_frames_rule_fml']  = bool(not_frames_rule_fml)

        not_frames_rule_x10 = self.get_not_frames_rule_x10()
        if not_frames_rule_x10:
            data['not_frames_rule_x10'] = bool(not_frames_rule_x10)

        not_frames_rule_xn = self.get_not_frames_rule_xn()
        if isinstance(not_frames_rule_xn, int):
            data['not_frames_rule_xn'] = not_frames_rule_xn

        if use_submit_note:
            note_override = self.get_note_override_submission()
        else:
            note_override = self.get_note_override()
        if note_override:
            data['note_override'] = note_override

        wait_on = self.get_wait_on()
        if wait_on:
            data[constants.SESSION_KEY_WAIT_ON] = wait_on

        wait_on_plow_ids = self.get_wait_on_plow_ids()
        if wait_on_plow_ids:
            data[constants.SESSION_KEY_WAIT_ON_PLOW_IDS] = wait_on_plow_ids

        colour = self.get_colour()
        if colour:
            data[constants.SESSION_KEY_COLOUR] = colour

        post_tasks = self.get_post_tasks()
        if post_tasks:
            data['post_tasks'] = post_tasks

        dispatcher_plow_job_id = self.get_dispatcher_plow_job_id()
        if dispatcher_plow_job_id:
            data['dispatcher_plow_job_id'] = str(dispatcher_plow_job_id or str()) or None

        return data


    def apply_session_data(self, data=None, **kwargs):
        '''
        Apply session data to this environment item or subclass.
        Reimplement this method to apply additional session data for subclassed items.

        Args:
            data (dict):

        Returns:
            sync_count (int):
        '''
        if not data or not isinstance(data, dict):
            return 0

        sync_count = BaseMultiShotItem.apply_session_data(self, data)

        version_override = data.get('version_override', None)
        self.set_version_override(version_override)

        found_frame_rule = False
        found_not_frame_rule = False

        frame_range_override = data.get('frame_range_override', str())
        if frame_range_override:
            try:
                fileseq.FrameSet(frame_range_override)
                self.set_frame_range_override(frame_range_override)
                found_frame_rule = True
            except fileseq.ParseException as error:
                pass

        not_frame_range_override = data.get('not_frame_range_override', str())
        if not_frame_range_override:
            try:
                fileseq.FrameSet(not_frame_range_override)
                self.set_not_frame_range_override(not_frame_range_override)
                found_not_frame_rule = True
            except fileseq.ParseException as error:
                pass

        frames_rule_important = data.get('frames_rule_important')
        if frames_rule_important:
            self.set_frames_rule_important(True)
        # TODO: For backwards session compatible. To be removed soon
        elif not found_frame_rule and frame_range_override == 'Important':
            self.set_frames_rule_important(True)
            found_frame_rule = True

        frames_rule_fml = data.get('frames_rule_fml')
        if frames_rule_fml:
            self.set_frames_rule_fml(True)
        # TODO: For backwards session compatible. To be removed soon
        elif not found_frame_rule and frame_range_override == 'First Middle Last':
            self.set_frames_rule_fml(True)
            found_frame_rule = True

        frames_rule_x1 = data.get('frames_rule_x1')
        if frames_rule_x1:
            self.set_frames_rule_x1(True)
        # TODO: For backwards session compatible. To be removed soon
        elif not found_frame_rule and frame_range_override == 'X1':
            self.set_frames_rule_x1(True)
            found_frame_rule = True

        frames_rule_x10 = data.get('frames_rule_x10')
        if frames_rule_x10:
            self.set_frames_rule_x10(True)
        # TODO: For backwards session compatible. To be removed soon
        elif not found_frame_rule and frame_range_override == 'X10':
            self.set_frames_rule_x10(True)
            found_frame_rule = True

        frames_rule_xn = data.get('frames_rule_xn')
        if isinstance(frames_rule_xn, int):
            self.set_frames_rule_xn(frames_rule_xn)
        # TODO: For backwards session compatible. To be removed soon
        elif not found_frame_rule and frame_range_override.startswith('x'):
            try:
                self.set_frames_rule_xn(int(frame_range_override.split('x')[-1]))
                found_frame_rule = True
            except Exception:
                pass

        not_frames_rule_important = data.get('not_frames_rule_important')
        if not_frames_rule_important:
            self.set_not_frames_rule_important(True)

        not_frames_rule_fml = data.get('not_frames_rule_fml')
        if not_frames_rule_fml:
            self.set_not_frames_rule_fml(True)
        # TODO: For backwards session compatible. To be removed soon
        elif not found_not_frame_rule and not_frame_range_override == 'NOT First Middle Last':
            self.set_not_frames_rule_fml(True)
            found_not_frame_rule = True

        not_frames_rule_x10 = data.get('not_frames_rule_x10')
        if not_frames_rule_x10:
            self.set_not_frames_rule_x10(True)
        # TODO: For backwards session compatible. To be removed soon
        elif not found_not_frame_rule and not_frame_range_override == 'NOT x10':
            self.set_not_frames_rule_x10(True)
            found_not_frame_rule = True

        not_frames_rule_xn = data.get('not_frames_rule_xn')
        if isinstance(not_frames_rule_xn, int):
            self.set_not_frames_rule_xn(not_frames_rule_xn)
        # TODO: For backwards session compatible. To be removed soon
        elif not found_not_frame_rule and not_frame_range_override.startswith('x'):
            try:
                self.set_not_frames_rule_xn(int(not_frame_range_override.split('x')[-1]))
                found_not_frame_rule = True
            except Exception:
                pass

        note_override = data.get('note_override', None)
        self.set_note_override(note_override)

        wait_on = data.get(constants.SESSION_KEY_WAIT_ON, list())
        self.set_wait_on(wait_on)

        wait_on_plow_ids = data.get(constants.SESSION_KEY_WAIT_ON_PLOW_IDS, list())
        self.set_wait_on_plow_ids(wait_on_plow_ids)

        colour = data.get('colour', None)
        self.set_colour(colour)

        post_tasks = data.get('post_tasks', list())
        self.set_post_tasks(post_tasks)

        dispatcher_plow_job_id = data.get('dispatcher_plow_job_id', None)
        self.set_dispatcher_plow_job_id(dispatcher_plow_job_id)

        return sync_count


    def apply_render_overrides_session_data(self, render_overrides_data):
        '''
        Apply session data pertaining to render overrides to this override base item.

        Args:
            render_overrides_data (collections.OrderedDict):

        Returns:
            added_render_override_count (int):
        '''
        identifier = self.get_identifier()
        msg = 'Applying Render Overrides Session Data To Identifier: "{}". '.format(identifier)
        msg += 'Data: "{}"'.format(render_overrides_data)
        self.logMessage.emit(msg, logging.INFO)

        # NOTE: RenderOverridesManager is singleton and has already been instantiated
        # in regards to particular host app plugin path, so just get cached values.
        from srnd_multi_shot_render_submitter.render_overrides.render_overrides_manager import \
            RenderOverridesManager
        render_overrides_manager = RenderOverridesManager(cached=True)

        added_render_override_count = 0
        for override_id in render_overrides_data.keys():
            # The raw value extracted from json file
            value = render_overrides_data[override_id].get('value')
            if value == None:
                msg = 'No Value For Render Override Id: "{}"'.format(override_id)
                self.logMessage.emit(msg, logging.CRITICAL)
                continue

            # Check render override plugin object is available for id
            render_override_object = render_overrides_manager.get_render_override_object_by_id(override_id)
            if not render_override_object:
                msg = 'Failed To Get Render Override Object By Id: "{}"'.format(override_id)
                self.logMessage.emit(msg, logging.CRITICAL)
                continue

            # Deserialize the value according to render override for json file
            value = render_override_object.deserialize_value(value)
            if value == None:
                msg = 'Render Override Returned No Value After Desrialization: "{}". '.format(override_id)
                msg += 'Skipping Add Render Override! '
                msg += 'For: "{}"'.format(identifier)
                self.logMessage.emit(msg, logging.CRITICAL)
                continue

            # Validate the value is actually the expected type
            value_is_valid = render_override_object.validate_value(value)
            if not value_is_valid:
                msg = 'Render Override Has Illegal Value: "{}". '.format(override_id)
                msg += 'Skipping Add Render Override! '
                msg += 'For: "{}"'.format(identifier)
                self.logMessage.emit(msg, logging.CRITICAL)
                continue

            render_override_item = render_override_object(value=value)
            self.add_render_override_item(render_override_item)
            added_render_override_count += 1

        return added_render_override_count


    def get_render_overrides_session_data(self):
        '''
        Get session data pertaining to all current render override
        items of this override base item.

        Returns:
            render_overrides_data (collections.OrderedDict):
        '''
        identifier = self.get_identifier()
        render_overrides_data = collections.OrderedDict()
        render_overrides_items = self.get_render_overrides_items()
        for override_id in render_overrides_items.keys():
            render_override_item = render_overrides_items[override_id]
            override_id = render_override_item.get_override_id()
            value = render_override_item.get_value()
            # Serialize the value according to render override for json file
            value = render_override_item.serialize_value(value)
            if value == None:
                msg = 'Failed To Serialize Value: "{}". '.format(value)
                msg += 'For Render Override Id: "{}". '.format(override_id)
                msg += 'When Saving Session Data! Will Skip Serializing This Item! '
                msg += 'For: "{}"'.format(identifier)
                self.logMessage.emit(msg, logging.CRITICAL)
                continue
            render_overrides_data[override_id] = dict()
            render_overrides_data[override_id]['value'] = value
        identifier = self.get_identifier()
        # if render_overrides_data:
        #     msg = 'Gathered Render Overrides Session Data For Identifier: "{}". '.format(identifier)
        #     msg += 'Data: "{}"'.format(render_overrides_data)
        #     self.logMessage.emit(msg, logging.INFO)
        return render_overrides_data


    def validate_render_overrides(self):
        '''
        Validate all render overrides values of this override base item.

        Returns:
            changed_count (int): if any render overrides items were removed during validation
        '''
        identifier = self.get_identifier()
        render_overrides_items = self.get_render_overrides_items()
        if self._debug_mode:
            msg = 'Validating All Render Overrides For Identifier: "{}"'.format(identifier)
            self.logMessage.emit(msg, logging.INFO)
        changed_count = 0
        for override_id in render_overrides_items.keys():
            render_override_item = render_overrides_items[override_id]
            override_id = render_override_item.get_override_id()
            value = render_override_item.get_value()
            value_is_valid = render_override_item.validate_value(value)
            if not value_is_valid:
                msg = 'Value Not Valid For Render Override: "{}". '.format(value)
                msg += 'For Render Override Id: "{}". '.format(override_id)
                msg += 'Will Remove This Render Override Item! '
                msg += 'For: "{}"'.format(identifier)
                self.logMessage.emit(msg, logging.CRITICAL)
                success = self.remove_render_override_item_by_id(override_id)
                if success:
                    changed_count += 1
        return changed_count


    def search_for_string(self, search_text):
        '''
        Search this override base data object for matching string.

        Args:
            search_text (str):

        Returns:
            found (bool):
        '''
        if not search_text:
            return False

        # Search by UUID
        if search_text == self.get_identity_id():
            return True

        # Search for intersection of searched user frames with resolved frames
        FRAMES_TOKENS = ('frame:', 'frames:')
        has_frames_tokens = search_text.startswith(FRAMES_TOKENS)
        if self.is_pass_for_env_item() and has_frames_tokens:
            frames = search_text.split(':')[-1]
            if frames:
                resolved_frames_queued = self.get_resolved_frames_queued()
                try:
                    frameset_search = fileseq.FrameSet(str(frames))
                except fileseq.ParseException:
                    frameset_search = None
                if frameset_search and resolved_frames_queued:
                    try:
                        frameset_resolved = fileseq.FrameSet(str(resolved_frames_queued))
                    except fileseq.ParseException:
                        frameset_resolved = None
                    if frameset_resolved:
                        frameset_intersection = frameset_search.intersection(frameset_resolved)
                        if frameset_intersection:
                            return True
            else:
                return True

        # Search for user note
        NOTES_TOKENS = ('note:', 'notes:')
        has_note_token = search_text.startswith(NOTES_TOKENS)
        if has_note_token:
            _note_override = search_text.split(':')[-1]
            if _note_override:
                note_override = self.get_note_override()
                if _note_override and note_override:
                    found = str(_note_override).lower() in str(note_override).lower()
                    if found:
                        return True
            else:
                return True

        note_override = self.get_note_override()
        if note_override:
            found = re.findall(search_text, note_override)
            if found:
                return True

        return False


    def clear_overrides(self):
        '''
        Clear all overrides from this override base item.
        Reimplementyed method.
        '''
        # BaseMultiShotItem.clear_overrides(self)

        self._render_overrides_items = collections.OrderedDict()
        self._version_override = None

        self._frame_range_override = None
        self._not_frame_range_override = None

        self._frames_rule_important = False
        self._frames_rule_fml = False
        self._frames_rule_x1 = False
        self._frames_rule_x10 = False
        self._frames_rule_xn = None
        self._not_frames_rule_important = False
        self._not_frames_rule_fml = False
        self._not_frames_rule_x10 = False
        self._not_frames_rule_xn = None

        self._note_override = None
        self._note_override_submission = None
        self._wait_on = list()
        self._colour = None

        self._post_tasks = list()


    def clear_frame_overrides(self):
        '''
        Clear any frame overrides only.
        '''
        self._frame_range_override = None
        self._not_frame_range_override = None
        self._frames_rule_important = False
        self._frames_rule_fml = False
        self._frames_rule_x1 = False
        self._frames_rule_x10 = False
        self._frames_rule_xn = None
        self._not_frames_rule_important = False
        self._not_frames_rule_fml = False
        self._not_frames_rule_x10 = False
        self._not_frames_rule_xn = None


    def copy_overrides(self):
        '''
        Copy overrides as dictionary of details.
        Reimplemented method.

        Returns:
            overrides_dict (dict):
        '''
        # overrides_dict = BaseMultiShotItem.copy_overrides(self)

        overrides_dict = dict()

        # Collect session data to represent render overrides in isolation
        render_overrides_data = self.get_render_overrides_session_data()
        if render_overrides_data:
            overrides_dict['render_overrides_data'] = render_overrides_data

        if self._version_override:
            overrides_dict['version_override'] = self._version_override

        if self._frame_range_override:
            overrides_dict['frame_range_override'] = self._frame_range_override

        if self._not_frame_range_override:
            overrides_dict['not_frame_range_override'] = self._not_frame_range_override

        overrides_dict['frames_rule_important'] = bool(self._frames_rule_important)
        overrides_dict['frames_rule_fml'] = bool(self._frames_rule_fml)
        overrides_dict['frames_rule_x1'] = bool(self._frames_rule_x1)
        overrides_dict['frames_rule_x10'] = bool(self._frames_rule_x10)
        if self._frames_rule_xn:
            overrides_dict['frames_rule_xn'] = int(self._frames_rule_xn)

        overrides_dict['not_frames_rule_important'] = bool(self._not_frames_rule_important)
        overrides_dict['not_frames_rule_fml'] = bool(self._not_frames_rule_fml)
        overrides_dict['not_frames_rule_x10'] = bool(self._not_frames_rule_x10)
        if self._not_frames_rule_xn:
            overrides_dict['not_frames_rule_xn'] = int(self._not_frames_rule_xn)

        if self._wait_on:
            overrides_dict[constants.SESSION_KEY_WAIT_ON] = self._wait_on

        if self._note_override:
            overrides_dict['note_override'] = self._note_override

        if self._colour:
            overrides_dict['colour'] = self._colour

        if self._post_tasks:
            overrides_dict['post_tasks'] = self._post_tasks

        return overrides_dict


    def paste_overrides(self, overrides_dict=None):
        '''
        Paste overrides from dictionary of overrides details.

        Args:
            overrides_dict (dict):

        Returns:
            overrides_applied (int):
        '''
        # overrides_dict = BaseMultiShotItem.paste_overrides(self)

        if not overrides_dict:
            overrides_dict = dict()

        overrides_applied = 0

        if 'render_overrides_data' in overrides_dict.keys():
            overrides_applied += self.apply_render_overrides_session_data(
                overrides_dict['render_overrides_data'])

        if 'version_override' in overrides_dict.keys():
            self._version_override = overrides_dict.get('version_override')
            overrides_applied += 1

        if 'frame_range_override' in overrides_dict.keys():
            self._frame_range_override = overrides_dict.get('frame_range_override')
            overrides_applied += 1

        if 'not_frame_range_override' in overrides_dict.keys():
            self._not_frame_range_override = overrides_dict.get('not_frame_range_override')
            overrides_applied += 1

        if 'frames_rule_important' in overrides_dict.keys():
            self._frames_rule_important = bool(overrides_dict.get('frames_rule_important', False))
            overrides_applied += 1

        if 'frames_rule_fml' in overrides_dict.keys():
            self._frames_rule_fml = bool(overrides_dict.get('frames_rule_fml', False))
            overrides_applied += 1

        if 'frames_rule_x1' in overrides_dict.keys():
            self._frames_rule_x1 = bool(overrides_dict.get('frames_rule_x1', False))
            overrides_applied += 1

        if 'frames_rule_x10' in overrides_dict.keys():
            self._frames_rule_x10 = bool(overrides_dict.get('frames_rule_x10', False))
            overrides_applied += 1

        if 'frames_rule_xn' in overrides_dict.keys():
            frames_rule_xn = overrides_dict.get('frames_rule_xn')
            if isinstance(frames_rule_xn, int):
                self._frames_rule_xn = frames_rule_xn
                overrides_applied += 1

        if 'not_frames_rule_important' in overrides_dict.keys():
            self._not_frames_rule_important = bool(overrides_dict.get('not_frames_rule_important', False))
            overrides_applied += 1

        if 'not_frames_rule_fml' in overrides_dict.keys():
            self._not_frames_rule_fml = bool(overrides_dict.get('not_frames_rule_fml', False))
            overrides_applied += 1

        if 'not_frames_rule_x10' in overrides_dict.keys():
            self._not_frames_rule_x10 = bool(overrides_dict.get('not_frames_rule_x10', False))
            overrides_applied += 1

        if 'not_frames_rule_xn' in overrides_dict.keys():
            not_frames_rule_xn = overrides_dict.get('not_frames_rule_xn')
            if isinstance(not_frames_rule_xn, int):
                self._not_frames_rule_xn = not_frames_rule_xn
                overrides_applied += 1

        if constants.SESSION_KEY_WAIT_ON in overrides_dict.keys():
            self._wait_on = overrides_dict.get(constants.SESSION_KEY_WAIT_ON, list())
            overrides_applied += 1

        if 'note_override' in overrides_dict.keys():
            self._note_override = overrides_dict.get('note_override')
            overrides_applied += 1

        if 'colour' in overrides_dict.keys():
            self._colour = overrides_dict.get('colour')
            overrides_applied += 1

        if 'post_tasks' in overrides_dict.keys():
            self._post_tasks = overrides_dict.get('post_tasks')
            overrides_applied += 1

        msg = 'Successfully Pasted Overrides Count: {}. '.format(overrides_applied)
        msg += 'From Data: "{}"'.format(overrides_dict)
        self.logMessage.emit(msg, logging.DEBUG)

        return overrides_applied


    ##########################################################################
    # Render override items


    def set_render_overrides_items(self, value):
        '''
        Set dict mapping of render override id to render override items that this item has.

        Args:
            render_overrides_items (collections.OrderedDict):
        '''
        if not value:
            value = collections.OrderedDict()
        if self._debug_mode:
            identifier = self.get_identifier()
            msg = 'Setting Render Override Items To: "{}". '.format(value)
            msg += 'Identifier: "{}"'.format(identifier)
            self.logMessage.emit(msg, logging.DEBUG)
        self._render_overrides_items = value


    def get_render_overrides_items(
            self,
            include_from_env=False,
            auto_apply_only=False):
        '''
        Get dict mapping of render override id to render override items that this item has.

        Args:
            include_from_env (bool): whether to also check if the environment has render overrides
            auto_apply_only (bool): optionally only get render override items which are set to
                be auto applied on submission.

        Returns:
            render_overrides_items (collections.OrderedDict):
        '''
        render_overrides_items = self._render_overrides_items or dict()
        if self.is_pass_for_env_item() and include_from_env:
            environment_item = self.get_environment_item()
            if environment_item:
                render_overrides_env = environment_item.get_render_overrides_items()
                for override_id in render_overrides_env.keys():
                    if override_id not in render_overrides_items.keys():
                        render_overrides_items[override_id] = render_overrides_env[override_id]
        # Now optionally filter to overrides which are set to auto apply
        if auto_apply_only and render_overrides_items:
            _render_overrides_items = collections.OrderedDict()
            for override_id in render_overrides_items.keys():
                render_override_item = render_overrides_items[override_id]
                if not render_override_item.AUTO_APPLY_AT_SUBMIT:
                    # msg = 'Render Override Set To Not Auto Apply: "{}"'.format(override_id)
                    # self.logMessage.emit(msg, logging.WARNING)
                    continue
                _render_overrides_items[override_id] = render_overrides_items[override_id]
            render_overrides_items = _render_overrides_items
        return render_overrides_items


    def has_render_overrides(
            self,
            include_from_env=True,
            auto_apply_only=False):
        '''
        Get whether this item (or parent environment) has any render overrides to apply.

        Args:
            include_from_env (bool): whether to also check if the environment has render overrides

        Returns:
            has_render_overrides (bool):
        '''
        render_overrides_items = self.get_render_overrides_items(
            include_from_env=include_from_env,
            auto_apply_only=auto_apply_only)
        return bool(render_overrides_items)


    def add_render_override_item(self, render_override_item):
        '''
        Add render override item that this item references.

        Args:
            render_override_item (RenderOverrideItem):
        '''
        override_id = render_override_item.get_override_id()
        if self._debug_mode:
            msg = 'Adding Render Override Item With Id: "{}". '.format(override_id)
            msg += 'Item: "{}"'.format(render_override_item)
            self.logMessage.emit(msg, logging.DEBUG)
        self._render_overrides_items[override_id] = render_override_item


    def remove_render_override_item_by_id(self, override_id):
        '''
        Remove render override item that this item has by override id.

        Returns:
            success (bool):
        '''
        if override_id not in self._render_overrides_items.keys():
            return False
        if self._debug_mode:
            msg = 'Removing Render Override item By Id: "{}"'.format(override_id)
            if any([self.is_pass_for_env_item(), self.is_environment_item()]):
                identifier = self.get_identifier()
                msg += '. From: "{}"'.format(identifier)
            self.logMessage.emit(msg, logging.INFO)
        return bool(self._render_overrides_items.pop(override_id))


    def remove_all_render_override_items(self):
        '''
        Remove all render override items that this item has.

        Returns:
            removed_count (int):
        '''
        if self._render_overrides_items:
            removed_count = len(self._render_overrides_items)
            self._render_overrides_items = collections.OrderedDict()
            return removed_count
        return 0


    def get_render_overrides_items_ids(self):
        '''
        Get list of render override ids that this item has.

        Returns:
            render_overrides_items_ids (list):
        '''
        return self._render_overrides_items.keys()


    def get_render_override_by_id(self, render_override_id):
        '''
        Get render override item that this item might contain by override id.

        Args:
            render_override_id (RenderOverrideItem):
        '''
        if not render_override_id:
            return
        return self._render_overrides_items.get(render_override_id)


    def apply_render_overrides(self, override_ids=None):
        '''
        Apply any render overrides of this item to host app render nodes and project.

        Args:
            override_ids (list): optionally override which override ids should be applied

        Returns:
            applied_render_override_items (dict): mapping of render override items that should be later reverted
        '''
        if not override_ids:
            override_ids = list()

        identifier = self.get_identifier()

        if not self.has_render_overrides(include_from_env=True):
            # msg = 'No Render Overrides To Apply To '
            # msg += 'Identifier: "{}"'.format(identifier)
            # self.logMessage.emit(msg, logging.WARNING)
            return dict()

        if self.is_environment_item():
            msg = 'Apply Render Overrides Can Only Be Invoked For Render Pass For Env! '
            msg += 'Identifier: "{}"'.format(identifier)
            self.logMessage.emit(msg, logging.WARNING)
            return dict()

        render_item = self.get_source_render_item()
        if not render_item:
            msg = 'No Source RenderItem When Applying Render Overrides! '
            msg += 'Identifier: "{}"'.format(identifier)
            self.logMessage.emit(msg, logging.WARNING)
            return dict()

        item_full_name = render_item.get_item_full_name()
        render_node = render_item.get_node_in_host_app()
        if not render_node:
            msg = 'Failed To Get Host App Render Node When Applying Render Overrides! '
            msg += 'Identifier: "{}". '.format(identifier)
            msg += 'Host App Node: "{}"'.format(item_full_name)
            self.logMessage.emit(msg, logging.WARNING)
            return dict()

        render_overrides_items = self.get_render_overrides_items()

        # Merge any environment render overrides with pass render overrides
        environment_item = self.get_environment_item()
        render_overrides_items_env = environment_item.get_render_overrides_items()
        if render_overrides_items_env:
            # NOTE: RenderOverridesManager is singleton and has already been instantiated
            # in regards to particular host app plugin path, so just get cached values.
            from srnd_multi_shot_render_submitter.render_overrides.render_overrides_manager import \
                RenderOverridesManager
            render_overrides_manager = RenderOverridesManager(cached=True)
            for override_id in render_overrides_items_env.keys():
                if override_ids and override_id not in override_ids:
                    continue
                # Prefer to keep existing pass for env render override
                if override_id not in render_overrides_items.keys():
                    # Create a new render override object to cache values to
                    render_override_object = render_overrides_manager.get_render_override_object_by_id(
                        override_id)
                    if render_override_object:
                        # Copy the value of environment render override item
                        value = render_overrides_items_env[override_id].get_value()
                        render_overrides_items[override_id] = render_override_object(value=value)

        if self._debug_mode:
            msg = 'Applying Render Overrides To Identifier: "{}". '.format(identifier)
            msg += 'Host App Node: "{}". '.format(item_full_name)
            msg += 'Render Overrides: "{}"'.format(render_overrides_items)
            self.logMessage.emit(msg, logging.DEBUG)

        applied_render_override_items = collections.OrderedDict()
        for override_id in render_overrides_items.keys():
            # Optionally skip applying a subset of render overrides by id
            if override_ids and override_id not in override_ids:
                msg = 'Skipping Apply Render Override Id. Not Requested: "{}". '.format(override_id)
                msg += 'Identifier: "{}". '.format(identifier)
                msg += 'Host App Node: "{}"'.format(item_full_name)
                self.logMessage.emit(msg, logging.WARNING)
                continue
            render_override_item = render_overrides_items[override_id]
            if not render_override_item.AUTO_APPLY_AT_SUBMIT:
                msg = 'Skipping Apply Render Override Id For Now... '
                msg += 'Not Requested To Auto Apply: "{}". '.format(override_id)
                msg += 'Identifier: "{}". '.format(identifier)
                msg += 'Host App Node: "{}"'.format(item_full_name)
                self.logMessage.emit(msg, logging.WARNING)
                continue
            value = render_override_item.get_value()
            # Clear any cached values to ensure no dirty values
            render_override_item.clear_cached_values()
            try:
                success, result_msg = render_override_item.apply_render_override(
                    render_node,
                    self,
                    value)
            except Exception:
                success = False
                result_msg = 'Full Exception: "{}".'.format(traceback.format_exc())
            if success:
                msg = 'Successfully Applied Render Override By Id: "{}". '.format(override_id)
                msg += 'To Identifier: "{}". '.format(identifier)
                msg += 'Host App Node: "{}". '.format(item_full_name)
                msg += 'Value: "{}"'.format(value)
                if result_msg:
                    msg += '. Message: "{}". '.format(result_msg)
                self.logMessage.emit(msg, logging.INFO)
                applied_render_override_items[override_id] = render_override_item
            else:
                msg = 'Failed To Apply Render Override By Id: "{}". '.format(override_id)
                msg += 'To Identifier: "{}". '.format(identifier)
                msg += 'Host App Node: "{}". '.format(item_full_name)
                msg += 'Value: "{}"'.format(value)
                if result_msg:
                    msg += '. Message: "{}". '.format(result_msg)
                self.logMessage.emit(msg, logging.WARNING)

        return applied_render_override_items


    def revert_render_overrides(self, override_id_to_items=None):
        '''
        Revert any render overrides of this item to host app render nodes and project.

        Args:
            override_id_to_items (dict): optionally provide a mapping of override id to override item to revert

        Returns:
            reverted_override_ids (list): list of override ids that were successfully reverted
        '''
        if not override_id_to_items:
            override_id_to_items = dict()

        identifier = self.get_identifier()
        if self.is_environment_item():
            msg = 'Revert Render Overrides Can Only Be Invoked For Render Pass For Env! '
            msg += 'Identifier: "{}"'.format(identifier)
            self.logMessage.emit(msg, logging.WARNING)
            return list()

        render_item = self.get_source_render_item()
        if not render_item:
            msg = 'No Source RenderItem When Reverting Render Overrides! '
            msg += 'Identifier: "{}"'.format(identifier)
            self.logMessage.emit(msg, logging.WARNING)
            return list()

        item_full_name = render_item.get_item_full_name()
        render_node = render_item.get_node_in_host_app()
        if not render_node:
            msg = 'Failed To Get Host App Render Node When Reverting Render Overrides! '
            msg += 'Identifier: "{}". '.format(identifier)
            msg += 'Host App Node: "{}"'.format(item_full_name)
            self.logMessage.emit(msg, logging.WARNING)
            return list()

        render_overrides_items = override_id_to_items or self.get_render_overrides_items()

        reverted_override_ids = list()
        for override_id in reversed(render_overrides_items.keys()):
            # # Optionally skip reverting a subset of render overrides by id
            # if override_ids and override_id not in override_ids:
            #     msg = 'Skipping Revert Render Override Id. Not Requested: "{}". '.format(override_id)
            #     msg += 'Identifier: "{}". '.format(identifier)
            #     msg += 'Host App Node: "{}"'.format(item_full_name)
            #     self.logMessage.emit(msg, logging.WARNING)
            #     continue
            render_override_item = render_overrides_items[override_id]
            if not render_override_item.AUTO_APPLY_AT_SUBMIT:
                msg = 'Skipping Revert Render Override Id. Not Requested To Auto Apply: "{}". '.format(override_id)
                msg += 'Identifier: "{}". '.format(identifier)
                msg += 'Host App Node: "{}"'.format(item_full_name)
                self.logMessage.emit(msg, logging.WARNING)
                continue
            value = render_override_item.get_value()
            try:
                success, result_msg = render_override_item.revert_render_override(
                    render_node,
                    self)
            except Exception:
                success = False
                result_msg = 'Full Exception: "{}".'.format(traceback.format_exc())
            # Clear any cached values to ensure no dirty values
            render_override_item.clear_cached_values()
            if success:
                msg = 'Successfully Reverted Render Override By Id: "{}". '.format(override_id)
                msg += 'To Identifier: "{}". '.format(identifier)
                msg += 'Host App Node: "{}". '.format(item_full_name)
                msg += 'Value: "{}"'.format(value)
                if result_msg:
                    msg += '. Message: "{}". '.format(result_msg)
                self.logMessage.emit(msg, logging.INFO)
                reverted_override_ids.append(override_id)
            else:
                msg = 'Failed To Revert Render Override By Id: "{}". '.format(override_id)
                msg += 'To Identifier: "{}". '.format(identifier)
                msg += 'Host App Node: "{}". '.format(item_full_name)
                msg += 'Value: "{}"'.format(value)
                if result_msg:
                    msg += '. Message: "{}". '.format(result_msg)
                self.logMessage.emit(msg, logging.WARNING)

        return reverted_override_ids


    ##########################################################################


    def get_version_override(self):
        '''
        Get user override option for version (if any).

        Returns:
            version_override (str):
        '''
        return self._version_override


    def set_version_override(self, value):
        '''
        Set user override option for version (if any).

        Args:
            value (str):
        '''
        if self._debug_mode:
            msg = '{}.set_version_override(). '.format(self._node_type)
            msg += self._get_env_and_pass_name_message()
            msg += 'Value: {}'.format(value)
            self.logMessage.emit(msg, logging.DEBUG)
        if not value:
            self._version_override = None
        else:
            self._version_override = value


    ##########################################################################
    # Custom frame range overrides


    def get_frame_range_override(self):
        '''
        Get user custom frame range override (if any).

        Returns:
            frame_range_override (str): or None if no override
        '''
        return self._frame_range_override


    def set_frame_range_override(self, value):
        '''
        Set user custom frame range override (if any).

        Args:
            frame_range_override (str): or None if no override
        '''
        if self._debug_mode:
            msg = '{}.set_frame_range_override(). '.format(self._node_type)
            msg += self._get_env_and_pass_name_message()
            msg += 'Value: {}'.format(value)
            self.logMessage.emit(msg, logging.DEBUG)
        if not value:
            self._frame_range_override = None
        else:
            self._frame_range_override = str(value)


    def get_not_frame_range_override(self):
        '''
        Get user custom NOT frame range override (if any).

        Returns:
            not_frame_range_override (str): or None if no override
        '''
        return self._not_frame_range_override


    def set_not_frame_range_override(self, value):
        '''
        Set user custom NOT frame range override (if any).

        Args:
            value (str): or None if no override
        '''
        if self._debug_mode:
            msg = '{}.set_not_frame_range_override(). '.format(self._node_type)
            msg += self._get_env_and_pass_name_message()
            msg += 'Value: {}'.format(value)
            self.logMessage.emit(msg, logging.DEBUG)
        if not value:
            self._not_frame_range_override = None
        else:
            self._not_frame_range_override = str(value)


    ##########################################################################
    # Frame range rule overrides


    def get_frames_rule_important(self):
        return self._frames_rule_important

    def get_frames_rule_fml(self):
        return self._frames_rule_fml

    def get_frames_rule_x1(self):
        return self._frames_rule_x1

    def get_frames_rule_x10(self):
        return self._frames_rule_x10

    def get_frames_rule_xn(self):
        return self._frames_rule_xn

    def get_not_frames_rule_important(self):
        return self._not_frames_rule_important

    def get_not_frames_rule_fml(self):
        return self._not_frames_rule_fml

    def get_not_frames_rule_x10(self):
        return self._not_frames_rule_x10

    def get_not_frames_rule_xn(self):
        return self._not_frames_rule_xn

    def set_frames_rule_important(self, value):
        self._frames_rule_important = bool(value)

    def set_frames_rule_fml(self, value):
        self._frames_rule_fml = bool(value)

    def set_frames_rule_x1(self, value):
        self._frames_rule_x1 = bool(value)

    def set_frames_rule_x10(self, value):
        self._frames_rule_x10 = bool(value)

    def set_frames_rule_xn(self, value):
        if isinstance(value, int):
            self._frames_rule_xn = value
        else:
            self._frames_rule_xn = None

    def set_not_frames_rule_important(self, value):
        self._not_frames_rule_important = bool(value)

    def set_not_frames_rule_fml(self, value):
        self._not_frames_rule_fml = bool(value)

    def set_not_frames_rule_x10(self, value):
        self._not_frames_rule_x10 = bool(value)

    def set_not_frames_rule_xn(self, value):
        if isinstance(value, int):
            self._not_frames_rule_xn = value
        else:
            self._not_frames_rule_xn = None


    def _resolve_rule(self, frame_rule, frameset):
        '''
        Resolve a rule like FML, NOT FML, x10, NOT x10, and more for the frameset.

        Args:
            frame_rule (str): frames as string that can be parsed by FrameSet, or sequence rule etc
            frameset (fileseq.FrameSet): approved frameset

        Returns:
            frameset, resolved (tuple): fileseq.FrameSet of resolved frames
                and boolean of successfully resolved
        '''
        is_frame_rule = frame_rule in constants.OVERRIDES_FRAME_RULES
        is_frame_rule = is_frame_rule or frame_rule.startswith(('x', 'NOT x'))
        if not is_frame_rule:
            return frameset, True

        if self.is_pass_for_env_item():
            environment_item = self.get_environment_item()
        else:
            environment_item = self

        # Can be FML or NOT FML
        if constants.OVERRIDE_FRAMES_FML in frame_rule:
            frames_flat = list(frameset)
            # If no frames to resolve then just return original FrameSet
            if not frames_flat:
                return frameset, True
            # Add any specified FML frames
            fml_frames = set()
            if 'F' in frame_rule:
                fml_frames.add(str(frames_flat[0]))
            if 'M' in frame_rule:
                middle_frame = frames_flat[int(len(frames_flat) / 2.0)]
                fml_frames.add(str(middle_frame))
            if 'L' in frame_rule:
                fml_frames.add(str(frames_flat[-1]))
            frameset = fileseq.FrameSet(fml_frames)

        # Every N number of frames, or NOT every N number of frames
        elif frame_rule.startswith('x') or frame_rule.startswith('NOT x'):
            try:
                first, last = (frameset.start(), frameset.end())
                increment = frame_rule.split('x')[-1]
                frame_rule = '{}-{}x{}'.format(first, last, increment)
                frameset = fileseq.FrameSet(frame_rule)
            except Exception as error:
                msg = 'Failed To Formulate xN From: "{}". '.format(frameset)
                msg += 'Full Exception: "{}"'.format(traceback.format_exc())
                self.logMessage.emit(msg, logging. WARNING)

        elif frame_rule == constants.OVERRIDE_FRAMES_IMPORTANT:
            important_frames = environment_item.get_important_frames()
            if important_frames:
                frameset = fileseq.FrameSet(important_frames or str())

        elif frame_rule == constants.OVERRIDE_FRAMES_NOT_IMPORTANT:
            important_frames = environment_item.get_important_frames()
            if important_frames:
                frameset = frameset.difference(fileseq.FrameSet(important_frames or str()))
            else:
                return frameset, False

        return frameset, True


    ##########################################################################


    def get_note_override(self):
        '''
        Get the note override (if any).

        Returns:
            note_override (str):
        '''
        return self._note_override


    def set_note_override(self, value):
        '''
        Set the note override (if any).

        Args:
            value (str):
        '''
        if self._debug_mode:
            msg = '{}.set_note_override(). '.format(self._node_type)
            msg += self._get_env_and_pass_name_message()
            msg += 'Value: {}'.format(value)
            self.logMessage.emit(msg, logging.DEBUG)
        if not value:
            self._note_override = None
        else:
            self._note_override = str(value)


    def get_note_override_submission(self):
        '''
        Get the note override (if any) for the current submission.

        Returns:
            note_override_submission (str):
        '''
        return self._note_override_submission


    def set_note_override_submission(self, value):
        '''
        Set the note override (if any).

        Args:
            value (str):
        '''
        if self._debug_mode:
            msg = '{}.set_note_override_submission(). '.format(self._node_type)
            msg += self._get_env_and_pass_name_message()
            msg += 'Value: {}'.format(value)
            self.logMessage.emit(msg, logging.DEBUG)
        if not value:
            self._note_override_submission = None
        else:
            self._note_override_submission = str(value)


    def get_wait_on(self):
        '''
        Get current WAIT On multi shot item targets as list of UUIDs.

        Returns:
            value (list):
        '''
        return self._wait_on


    def set_wait_on(self, wait_on=None):
        '''
        Set WAIT On multi shot item targets by providing list of UUIDs.

        Args:
            value (list):
        '''
        if not wait_on:
            wait_on = list()
        if self._debug_mode:
            msg = '{}.set_wait_on(). '.format(self._node_type)
            msg += self._get_env_and_pass_name_message()
            msg += 'Value: {}'.format(wait_on)
            self.logMessage.emit(msg, logging.DEBUG)
        self._wait_on = list(set(wait_on))


    def get_wait_on_plow_ids(self):
        '''
        Get WAIT On Plow ids as a list of lists.

        Returns:
            wait_on_plow_ids (list):
        '''
        return self._wait_on_plow_ids


    def set_wait_on_plow_ids(self, wait_on_plow_ids=None):
        '''
        Set WAIT On Plow ids as a list of lists.
        Each list might contain a single Plow job Id as index 0,
        and optionally a Plow task id as index 1.

        Args:
            wait_on_plow_ids (list): list of lists where index 0 is Plow Job id,
                and index 1 is optionally a Plow task id.
        '''
        if not wait_on_plow_ids or not isinstance(wait_on_plow_ids, (tuple, list)):
            wait_on_plow_ids = list()
        if self._debug_mode:
            msg = '{}.set_wait_on_plow_ids(). '.format(self._node_type)
            msg += self._get_env_and_pass_name_message()
            msg += 'Value: {}'.format(wait_on_plow_ids)
            self.logMessage.emit(msg, logging.DEBUG)
        self._wait_on_plow_ids = list(wait_on_plow_ids)


    def get_colour(self):
        '''
        Get the optional colour (if any).

        Returns:
            value (list):
        '''
        return self._colour


    def set_colour(self, value):
        '''
        Set the optional colour (if any).

        Args:
            value (list):
        '''
        if not value:
            value = None
        if self._debug_mode:
            msg = '{}.set_colour(). '.format(self._node_type)
            msg += self._get_env_and_pass_name_message()
            msg += 'Value: {}'.format(value)
            self.logMessage.emit(msg, logging.DEBUG)
        self._colour  = value


    def get_post_tasks(self):
        '''
        Get the currently set post task/s (if any).

        Returns:
            post_tasks (list): list of post task name dict details
        '''
        return self._post_tasks


    def set_post_tasks(self, value):
        '''
        Set the currently set post task/s (if any).

        Args:
            value (list): list of post task name dict details
        '''
        if self._debug_mode:
            msg = '{}.set_post_tasks(). '.format(self._node_type)
            msg += self._get_env_and_pass_name_message()
            msg += 'Value: {}'.format(value)
            self.logMessage.emit(msg, logging.DEBUG)
        self._post_tasks = list()
        if value:
            for value_dict in value:
                # NOTE: Cast any OrderedDict to dict here.
                # Might be coming after session load.
                # Also cast unicode to regular string for display purposes.
                value_dict_clean = dict()
                for key, value in value_dict.iteritems():
                    value_dict_clean[str(key)] = value
                self._post_tasks.append(value_dict_clean) # dict(value_dict))
        print self._post_tasks


    def get_dispatcher_plow_job_id(self):
        '''
        Get the last dispatcher Job id for the last job launched from
        this item in dispatch mode.

        Returns:
            value (str):
        '''
        return self._dispatcher_plow_job_id


    def set_dispatcher_plow_job_id(self, plow_job_id):
        '''
        Set the last dispatcher Job id for the last job launched from
        this item in dispatch mode.

        Args:
            value (str):
        '''
        if self._debug_mode:
            msg = 'Setting Dispatcher Plow Job Id To: "{}". '.format(plow_job_id)
            msg += 'Identifier: "{}"'.format(self.get_identifier())
            self.logMessage.emit(msg, logging.INFO)
        self._dispatcher_plow_job_id = str(plow_job_id or str()) or None


    def get_overrides_tooltip(self):
        '''
        Get a tooltip for all core and render overrides.

        Returns:
            overrides_tooltip (str):
        '''
        overrides_tooltip = str()

        core_overrides_tooltip = self.get_core_overrides_tooltip()
        if core_overrides_tooltip:
            overrides_tooltip += '<br><b>OVERRIDES</b>'
            overrides_tooltip += '<ul>'
            overrides_tooltip +=  core_overrides_tooltip
            overrides_tooltip += '</ul>'

        render_overrides_tooltip = self.get_render_overrides_tooltip()
        if render_overrides_tooltip:
            overrides_tooltip += render_overrides_tooltip

        return overrides_tooltip


    def get_core_overrides_tooltip(self):
        '''
        Get a tooltip for this override base item, appropiate for all subclasses.

        Returns:
            msg (str): an HTML string of <li> bullet point tags
        '''
        # NOTE: This method currently is not reimplemented for environment item in particular
        job_identifier = None
        split_frame_ranges = False
        koba_shotsub = False
        if self.is_environment_item():
            job_identifier = self.get_job_identifier()
            split_frame_ranges = self.get_split_frame_ranges()
            koba_shotsub = self.get_koba_shotsub()

        msg = str()

        if any([
                self._version_override,
                self._frame_range_override,
                self._not_frame_range_override,
                self._frames_rule_important,
                self._frames_rule_fml,
                self._frames_rule_x1,
                self._frames_rule_x10,
                self._frames_rule_xn,
                self._not_frames_rule_important,
                self._not_frames_rule_fml,
                self._not_frames_rule_x10,
                self._not_frames_rule_xn,
                self._wait_on,
                self._post_tasks,
                self._note_override,
                job_identifier,
                split_frame_ranges,
                koba_shotsub]):

            if self._version_override:
                msg += '<li>Version override: <b>{}</b></li>'.format(self._version_override)

            if self._frame_range_override:
                msg += '<li>Custom frames: <b>{}</b></li>'.format(self._frame_range_override)

            if self._not_frame_range_override:
                msg += '<li>NOT custom frames: <b>{}</b></li>'.format(self._not_frame_range_override)

            if self._frames_rule_important:
                msg += '<li>Frame override: <b>"{}"</b></li>'.format(constants.OVERRIDE_FRAMES_IMPORTANT)

            if self._frames_rule_fml:
                msg += '<li>Frame override: <b>"{}"</b></li>'.format(constants.OVERRIDE_FRAMES_FML)

            if self._frames_rule_x1:
                msg += '<li>Frame override: <b>"{}"</b></li>'.format(constants.OVERRIDE_FRAMES_X1)

            if self._frames_rule_x10:
                msg += '<li>Frame override: <b>"{}"</b></li>'.format(constants.OVERRIDE_FRAMES_X10)

            if self._frames_rule_xn:
                msg += '<li>Frame override: <b>"{}"</b></li>'.format(constants.OVERRIDE_FRAMES_XCUSTOM)

            if self._not_frames_rule_important:
                msg += '<li>Frame override: <b>"{}"</b></li>'.format(constants.OVERRIDE_FRAMES_NOT_IMPORTANT)

            if self._not_frames_rule_fml:
                msg += '<li>Frame override: <b>"{}"</b></li>'.format(constants.OVERRIDE_FRAMES_NOT_FML)

            if self._not_frames_rule_x10:
                msg += '<li>Frame override: <b>"{}"</b></li>'.format(constants.OVERRIDE_FRAMES_NOT_X10)

            if self._not_frames_rule_xn:
                msg += '<li>Frame override: <b>"{}"</b></li>'.format(constants.OVERRIDE_FRAMES_NOT_XCUSTOM)

            if self._note_override:
                msg += '<li>Note: <b>{}</b></li>'.format(self._note_override)

            if self._wait_on:
                display_value = ', '.join(self._wait_on)
                msg += '<li>Depends on: <b>{}</b></li>'.format(display_value)

            if self._wait_on_plow_ids:
                msg += '<li>Depends on Plow: <b>{}</b></li>'.format(self._wait_on_plow_ids)

            if self._post_tasks:
                msg += '<li>Post task/s: <b>{}</b></li>'.format(self._post_tasks)

            if job_identifier:
                msg += '<li>Job identifier: <b>{}</b></li>'.format(job_identifier)

            if split_frame_ranges:
                msg += '<li>Split frame ranges: <b>{}</b></li>'.format(split_frame_ranges)

            if koba_shotsub:
                msg += '<li>Koba shotsub: <b>{}</b></li>'.format(koba_shotsub)

        return msg


    def get_render_overrides_tooltip(self):
        '''
        Get a tooltip for all render overrides of this item.

        Returns:
            tooltip (str): a complete HTML block about all render overrides.
        '''
        render_overrides_items = self.get_render_overrides_items()
        if not render_overrides_items:
            return str()
        msg = '<br><b>RENDER OVERRIDES</b>'
        msg += '<ul>'
        for override_id in render_overrides_items.keys():
            render_overrides_item = render_overrides_items[override_id]
            label = render_overrides_item.get_override_label()
            value = render_overrides_item.get_value()
            override_type = render_overrides_item.get_override_type()
            if isinstance(value, dict):
                msg += '<li>'
                msg += 'Render Override: <b>{}</b>. '.format(label)
                msg += 'Type: <b>{}</b>'.format(override_type)
                msg += '</li>'
                msg += '<ul>'
                for _key, _value in value.iteritems():
                    msg += '<li>Key: <b>{}</b>. Value: <b>{}</b></li>'.format(_key, _value)
                msg += '</ul>'
            else:
                msg += '<li>'
                msg += 'Render Override: <b>{}</b>. Value: <b>{}</b>. '.format(label, value)
                msg += 'Type: <b>{}</b>'.format(override_type)
                # msg += 'Id: <b>{}</b>. '.format(override_id)
                msg += '</li>'
        msg += '</ul>'
        return msg


    def __repr__(self):
        '''
        Get a string that enables the constuctor to run to initialize
        another identical instance of this class.

        Returns:
            msg (str):
        '''
        msg = '{}('.format(self._node_type)

        name = self._name
        if name:
            msg += '"{}", '.format(self._name)

        msg += 'queued="{}", '.format(self.get_queued())
        msg += 'enabled="{}", '.format(self.get_enabled())

        version_override = self.get_version_override()
        if version_override:
            msg += 'version_override="{}", '.format(version_override)

        frame_range_override = self.get_frame_range_override()
        if frame_range_override:
            msg += 'frame_range_override="{}", '.format(frame_range_override)

        not_frame_range_override = self.get_not_frame_range_override()
        if not_frame_range_override:
            msg += 'not_frame_range_override="{}", '.format(not_frame_range_override)

        note_override = self.get_note_override()
        if note_override:
            msg += 'note_override={})'.format(note_override)

        if self.is_environment_item():
            job_identifier = self.get_job_identifier()
            if job_identifier:
                msg += 'job_identifier={},'.format(job_identifier)

        return msg


    def __str__(self):
        '''
        Get human readable display label to show details about data object.

        Returns:
            msg (str):
        '''
        msg = str(self._node_type)
        msg += self._get_env_and_pass_name_message(prefix='\n->')
        msg += '\n->Queued: "{}". '.format(self.get_queued())
        msg += '\n->Enabled: "{}". '.format(self.get_enabled())

        version_override = self.get_version_override()
        if version_override:
            msg += '\n->Version Override: "{}". '.format(version_override)

        frame_range_override = self.get_frame_range_override()
        if frame_range_override:
            msg += '\n->Frame Range Override: "{}". '.format(frame_range_override)

        not_frame_range_override = self.get_not_frame_range_override()
        if not_frame_range_override:
            msg += '\n->NOT Frame Range Override: "{}". '.format(not_frame_range_override)

        note_override = self.get_note_override()
        if note_override:
            msg += '\n->Note Override: "{}". '.format(note_override)

        if self.is_environment_item():
            job_identifier = self.get_job_identifier()
            if job_identifier:
                msg += '\n->Job Identifier: "{}". '.format(job_identifier)

        return msg


#############################################################################


class GroupItem(BaseMultiShotItem):
    '''
    A MSRS object representation of a group with custom name.
    NOTE: Groups currently only contain Environment item/s.

    Args:
        group_name (str):
        identity_id (str): optional existing uuid number to reuse
        insertion_row (int): optionally choose the index this item is inserted under parent
        debug_mode (bool): whether this abstract data emits message signals upstream
    '''

    logMessage = Signal(str, int)

    def __init__(
            self,
            group_name,
            identity_id=None,
            insertion_row=None,
            debug_mode=False,
            parent=None):

        super(GroupItem, self).__init__(
            name=group_name,
            node_type='GroupItem',
            debug_mode=debug_mode,
            parent=parent)


    def get_group_name(self):
        return self.get_name()

    def set_group_name(self, name):
        self.set_name(name)

    def is_group_item(self):
        return True

    def get_environment_items(self):
        return self.children()


    def __repr__(self):
        '''
        Get a string that enables the constuctor to run to initialize
        another identical instance of this class.

        Returns:
            msg (str):
        '''
        msg = '{}('.format(self._node_type)
        msg += '"{}", '.format(self.get_group_name())
        msg += 'debug_mode="{}")'.format(self._debug_mode)
        return msg


    def __str__(self):
        '''
        Get human readable display label to show details about data object.

        Returns:
            msg (str):
        '''
        msg = '{} For Host App '.format(self._node_type)
        msg += 'Group Name: "{}". '.format(self.get_group_name())
        return msg


#############################################################################


class EnvironmentItem(OverrideBaseItem):
    '''
    A MSRS object representation of an Environment, which is a single scene / shot
    or asset / variant environment.

    Args:
        oz_area (str):
        queued (bool):
        enabled (bool):
        version_override (str): override of version for env (None if not set)
        not_frame_range_override (str):
        frame_range_override (str): override of pass for env frame range (None if not set)
        render_overrides_items (collections.OrderedDict):
            dict mapping of render override id to render override item that
            this render pass for env has
        node_type (str):
        icon_path (str):
        debug_mode (bool): whether this abstract data emits message signals upstream
        insertion_row (int): optionally choose the index this item is inserted under parent
        parent (object): optionally choose the parent data object at construction time
    '''

    logMessage = Signal(str, int)
    toggleProgressBarVisible = Signal(bool)
    updateLoadingBarFormat = Signal(int, str)

    def __init__(
            self,
            oz_area=os.getenv('OZ_CONTEXT'),
            queued=True,
            enabled=True,
            version_override=None,
            not_frame_range_override=None,
            frame_range_override=None,
            render_overrides_items=None,
            node_type='EnvironmentItem',
            icon_path=None,
            debug_mode=False,
            insertion_row=None,
            parent=None):

        kwargs = dict(locals())
        kwargs.pop('self')
        kwargs.pop('oz_area')
        kwargs['name'] = oz_area

        super(EnvironmentItem, self).__init__(**kwargs)

        self._job_identifier = None
        self._split_frame_ranges = False
        self._koba_shotsub = False

        self._frame_range = str()
        self._delivery_range = str()
        self._cut_range = str()
        self._important_frames = str()
        self._production_range_source = 'Delivery'
        self._production_data_last_refreshed = None
        self._frame_resolve_order_env_first = True

        self._delivery_format = str()
        self._editorial_shot_status = str()
        self._due_date = None
        self._thumbnail_path = str()

        self._graph = None
        self._session = None
        self._snapshot_hyref = None

        self._renderable_count_for_env = 0
        self._environment_index_cached = 0

        self._validation_warning_counter = 0
        self._validation_critical_counter = 0


    def set_area(
            self,
            area,
            sync_production_data=True,
            resolve_frames=True):
        '''
        Set the area of this Environment item.

        Args:
            area (str):
            sync_production_data (bool):
            resolve_frames (bool):
        '''
        self.set_name(area)

        if sync_production_data:
            self.sync_production_data()

        if resolve_frames:
            # Resolve Environment frames
            self.resolve_frames()
            # Resolve each pass frames
            pass_env_items = self.get_pass_for_env_items()
            for pass_env_item in pass_env_items:
                pass_env_item.resolve_frames()


    def get_session_data(self, use_submit_note=False):
        '''
        Gather all session details for this environment item or subclass.
        Reimplement this method to gather additional session data for subclassed items.

        Args:
            use_submit_note (str):

        Returns:
            data (dict):
        '''
        # Gather identity id and active states from super class.
        # Also gather all generic overrides for either env or pass for env.
        data = OverrideBaseItem.get_session_data(
            self,
            use_submit_note=use_submit_note) or collections.OrderedDict()

        # Add environment specific data
        data['group_name'] = str(self.get_group_name())

        job_identifier = self.get_job_identifier()
        if job_identifier:
            data[constants.SESSION_KEY_JOB_IDENTIFIER] = str(job_identifier or str()) or None

        split_frame_ranges = self.get_split_frame_ranges()
        if split_frame_ranges:
            data['split_frame_ranges'] = bool(split_frame_ranges)

        koba_shotsub = self.get_koba_shotsub()
        if koba_shotsub:
            data['koba_shotsub'] = bool(koba_shotsub)

        # Get production data
        value = self.get_frame_range()
        if value:
            data['frame_range'] = value
        value =  self.get_delivery_range()
        if value:
            data['delivery_range'] = value
        value = self.get_cut_range()
        if value:
            data['cut_range'] = value
        value = self.get_important_frames()
        if value:
            data['important_frames'] = value
        value = self.get_production_data_last_refreshed()
        if value:
            data['production_data_last_refreshed'] = value

        # Frames options
        value = self.get_production_range_source()
        if value:
            data['production_range_source'] = str(value or str()) or None

        value = self.get_frame_resolve_order_env_first()
        data['frame_resolve_order_env_first'] = bool(value)

        ##################################################################

        data[constants.SESSION_KEY_PASSES] = dict()
        data[constants.SESSION_KEY_ENVIRONMENT] = self.get_oz_area()

        return data


    def apply_session_data(self, data=None, apply_production_data=False, **kwargs):
        '''
        Apply session data to this environment item or subclass.
        Reimplement this method to apply additional session data for subclassed items.

        Args:
            data (dict):
            apply_production_data (bool): whether to apply production data from session data (if available).
                otherwise leave this environment on currently synced data.

        Returns:
            sync_count (int):
        '''
        if not data or not isinstance(data, dict):
            return 0

        sync_count = OverrideBaseItem.apply_session_data(self, data)

        job_identifier = data.get('job_identifier', None)
        self.set_job_identifier(job_identifier)

        split_frame_ranges = data.get('split_frame_ranges', False)
        self.set_split_frame_ranges(split_frame_ranges)

        koba_shotsub = data.get('koba_shotsub', False)
        self.set_koba_shotsub(koba_shotsub)

        # Apply production data
        if apply_production_data:
            value = data.get('frame_range')
            if value:
                self._frame_range = str(value)
            value = data.get('delivery_range')
            if value:
                self._delivery_range = str(value)
            value = data.get('cut_range')
            if value:
                self._cut_range = str(value)
            value = data.get('important_frames')
            if value:
                self._important_frames = str(value)
            value = data.get('production_data_last_refreshed')
            if value:
                self._production_data_last_refreshed = str(value)

        # Frames options
        value = data.get('production_range_source', 'Delivery')
        self.set_production_range_source(value)

        value = data.get('frame_resolve_order_env_first', True)
        self.set_frame_resolve_order_env_first(bool(value))

        sync_count += 1

        return sync_count


    def copy_overrides(self):
        '''
        Copy overrides as dictionary of details.
        Reimplemted method.

        Returns:
            overrides_dict (dict):
        '''
        overrides_dict = OverrideBaseItem.copy_overrides(self) or dict()

        if self._job_identifier:
            overrides_dict[constants.SESSION_KEY_JOB_IDENTIFIER] = self._job_identifier

        overrides_dict['split_frame_ranges'] = self._split_frame_ranges

        overrides_dict['frame_resolve_order_env_first'] = self._frame_resolve_order_env_first

        overrides_dict['koba_shotsub'] = self._koba_shotsub

        return overrides_dict


    def paste_overrides(self, overrides_dict=None):
        '''
        Paste overrides from dictionary of overrides details.

        Args:
            overrides_dict (dict):

        Returns:
            overrides_applied (int):
        '''
        if not overrides_dict:
            overrides_dict = dict()

        overrides_applied = OverrideBaseItem.paste_overrides(self, overrides_dict) or 0

        if constants.SESSION_KEY_JOB_IDENTIFIER in overrides_dict.keys():
            self._job_identifier = overrides_dict.get(constants.SESSION_KEY_JOB_IDENTIFIER)
            overrides_applied += 1

        if 'split_frame_ranges' in overrides_dict.keys():
            self._split_frame_ranges = overrides_dict.get('split_frame_ranges', False)
            overrides_applied += 1

        if 'frame_resolve_order_env_first' in overrides_dict.keys():
            self._frame_resolve_order_env_first = overrides_dict.get(
                'frame_resolve_order_env_first', True)
            overrides_applied += 1

        if 'koba_shotsub' in overrides_dict.keys():
            self._koba_shotsub = overrides_dict.get('koba_shotsub', False)
            overrides_applied += 1

        msg = 'Successfully Pasted Overrides Count: {}. '.format(overrides_applied)
        msg += 'From Data: "{}"'.format(overrides_dict)
        self.logMessage.emit(msg, logging.DEBUG)

        return overrides_applied


    def clear_overrides(self):
        '''
        Clear all overrides from this environment item.
        Reimplemented method.
        '''
        OverrideBaseItem.clear_overrides(self)
        self._job_identifier = None
        self._split_frame_ranges = False
        self._koba_shotsub = False


    def resolve_frames(
            self,
            frame_range=None,
            current_frame_only=False):
        '''
        Resolve frames for this environment item.

        Args:
            frame_range (str): optionally override what frames to resolve environment rules against
            current_frame_only (bool): ignore frame range overrides and only render current project frame

        Returns:
            pass_frameset (fileseq.FrameSet):
        '''
        production_range = self.get_production_frame_range()
        shot_frame_override = self.get_frame_range_override()
        frame_range = shot_frame_override or frame_range or production_range or str()
        try:
            frameset =  fileseq.FrameSet(frame_range)
        except fileseq.ParseException:
            frameset =  fileseq.FrameSet(list())

        # msg = 'Shot Frame Range To Resolve Rules Against: "{}".'.format(frameset)
        # self.logMessage.emit(msg, logging.WARNING)

        ######################################################################

        add_frame_sets = list()
        remove_frame_sets = list()

        frames_rule_important = self.get_frames_rule_important()
        if frames_rule_important:
            _frameset, success = self._resolve_rule(constants.OVERRIDE_FRAMES_IMPORTANT, frameset)
            if _frameset and success:
                add_frame_sets.append(_frameset)

        frames_rule_fml = self.get_frames_rule_fml()
        if frames_rule_fml:
            _frameset, success = self._resolve_rule(constants.OVERRIDE_FRAMES_FML, frameset)
            if _frameset and success:
                add_frame_sets.append(_frameset)

        frames_rule_x1 = self.get_frames_rule_x1()
        if frames_rule_x1:
            _frameset, success = self._resolve_rule(constants.OVERRIDE_FRAMES_X1, frameset)
            if _frameset and success:
                add_frame_sets.append(_frameset)

        frames_rule_x10 = self.get_frames_rule_x10()
        if frames_rule_x10:
            _frameset, success = self._resolve_rule(constants.OVERRIDE_FRAMES_X10, frameset)
            if _frameset and success:
                add_frame_sets.append(_frameset)

        frames_rule_xn = self.get_frames_rule_xn()
        if frames_rule_xn:
            _frameset, success = self._resolve_rule('x{}'.format(frames_rule_xn), frameset)
            if _frameset and success:
                add_frame_sets.append(_frameset)

        not_frames_rule_important = self.get_not_frames_rule_important()
        if not_frames_rule_important:
            _frameset, success = self._resolve_rule(constants.OVERRIDE_FRAMES_NOT_IMPORTANT, frameset)
            if _frameset and success:
                remove_frame_sets.append(_frameset)

        not_frames_rule_fml =  self.get_not_frames_rule_fml()
        if not_frames_rule_fml:
            _frameset, success = self._resolve_rule(constants.OVERRIDE_FRAMES_NOT_FML, frameset)
            if _frameset and success:
                remove_frame_sets.append(_frameset)

        not_frames_rule_x10 =  self.get_not_frames_rule_x10()
        if not_frames_rule_x10:
            _frameset, success = self._resolve_rule(constants.OVERRIDE_FRAMES_NOT_X10, frameset)
            if _frameset and success:
                remove_frame_sets.append(_frameset)

        not_frames_rule_xn = self.get_not_frames_rule_xn()
        if not_frames_rule_xn:
            _frameset, success = self._resolve_rule('NOT x{}'.format(not_frames_rule_xn), frameset)
            if _frameset and success:
                remove_frame_sets.append(_frameset)

        if add_frame_sets:
            env_frameset = fileseq.FrameSet(list())
            for _frameset in add_frame_sets:
                env_frameset = env_frameset.union(_frameset)
        else:
            env_frameset = frameset
        for _frameset in remove_frame_sets:
            env_frameset = env_frameset.difference(_frameset)

        # Now remove any environment explicit NOT custom frames
        not_frame_override = self.get_not_frame_range_override()
        if not_frame_override:
            try:
                env_frameset = env_frameset.difference(fileseq.FrameSet(not_frame_override))
            except fileseq.ParseException as error:
                pass

        # msg = 'Environment Resolved FrameSet: "{}"'.format(env_frameset)
        # self.logMessage.emit(msg, logging.WARNING)

        return env_frameset


    def copy_production_data(self, env_item):
        '''
        Copy the production data from another EnvironmentItem.

        Args:
            env_item (EnvironmentItem):
        '''
        self._frame_range = env_item._frame_range
        self._delivery_range = env_item._delivery_range
        self._cut_range = env_item._cut_range
        self._important_frames = env_item._important_frames
        self._delivery_format = env_item._delivery_format
        self._editorial_shot_status = env_item._editorial_shot_status
        self._due_date = env_item._due_date
        self._thumbnail_path = env_item._thumbnail_path
        self._production_range_source = env_item._production_range_source
        self._production_data_last_refreshed = env_item._production_data_last_refreshed

        source = env_item.get_environment_name_nice()
        target = self.get_environment_name_nice()

        if self._debug_mode:
            msg = 'Copied Production Data From: "{}". '.format(source)
            msg += 'To: "{}"'.format(target)
            self.logMessage.emit(msg, logging.DEBUG)


    def get_oz_area(self):
        '''
        Get the environment of this item.
        TODO: Should be refactored to get_environment.

        Returns:
            oz_area (str):
        '''
        return str(self.get_name() or str())


    def get_scene_shot_area(self):
        '''
        Get the scene shot of environment only.

        Returns:
            scene_shot_area (str):
        '''
        try:
            context_split = self.get_name().split('/')
            return '/'.join(context_split[-2:])
        except Exception as error:
            # Fallback to returning environment as is
            return self.get_name()


    def get_context(self, area=None):
        '''
        Get a context mapping for this environment as formulated by oz API.

        Args:
            area (str): only specify to check a different environment than that of this item

        Returns:
            context (dict):
                NOTE: Returns upper case keys of FILM, TREE, SCENE, SHOT.
                NOTE: returns shots or assets tree with same SCENE and SHOT keys.
        '''
        area = area or self.get_oz_area()
        from oz import utils
        try:
            return utils.get_project_area_details(area)
        except Exception:
            return dict()


    def set_oz_area(self, oz_area):
        '''
        Set the environment of this item.
        TODO: Should be refactored to set_environment.

        Args:
            oz_area (str):
        '''
        self.set_name(oz_area)


    def get_environment_name_nice(
            self,
            environment=None,
            job_identifier=None,
            env_index=0,
            prefer_jid=True):
        '''
        Get the environment as a nice name.

        Args:
            environment (str): only specify if want to use different value than on item
            job_identifier (str): only specify if want to use different value than on item
            env_index (int): only specify if want to use different value than on item
            prefer_jid (str): include the job identifier (if any defined)
                for this environment item, otherwise include the environment index, if this
                item is appearing for the Nth time.

        Returns:
            environment_nice_name (str):
        '''
        environment = environment or self.get_oz_area()
        environment_nice = str(environment)
        job_identifier = job_identifier or self.get_job_identifier()
        env_index = env_index or self._get_cached_environment_index()
        if job_identifier and prefer_jid:
            environment_nice = environment + '-' + str(job_identifier)
        # Only include the index if Nth version of same environment
        elif (env_index and isinstance(env_index, int)): # and env_index > 1:
            environment_nice = environment + '-' + str(env_index)
        return environment_nice


    def get_group_name(self):
        '''
        Get the parent group name (if any).

        Returns:
            group_name (str):
        '''
        parent = self.parent()
        if parent and parent.is_group_item():
            return parent.get_group_name()
        return str()


    def get_all_wait_on(self, must_be_active=False):
        '''
        Get a list of all WAIT on for the environment and each pass.

        Args:
            must_be_active (bool):

        Returns:
            wait_on_all (list):
        '''
        wait_on_all = self._wait_on or list()
        for pass_env_item in self.get_pass_for_env_items():
            if must_be_active and not pass_env_item.get_active():
                continue
            wait_on_all.extend(pass_env_item.get_wait_on() or list())
        return wait_on_all


    def get_all_wait_on_plow_ids(self):
        '''
        Get a list of all WAIT on Plow ids for the environment and each pass.

        Returns:
            wait_on_all (list):
        '''
        wait_on_plow_ids = self._wait_on_plow_ids or list()
        for pass_env_item in self.get_pass_for_env_items():
            wait_on_plow_ids.extend(pass_env_item.get_wait_on_plow_ids() or list())
        return wait_on_plow_ids


    def get_production_range_source(self):
        '''
        Get which production range type should be used to resolve frame rules against.

        Retuns:
            production_range_source (str):
        '''
        return self._production_range_source


    def set_production_range_source(
            self,
            production_range_source='Delivery'):
        '''
        Set which production range type should be used to resolve frame rules against.

        Args:
            production_range_source (str): current valid choices
                are: ["Cut", "Delivery", "FrameRange", "Important"]
        '''
        self._production_range_source = str(production_range_source)


    def get_production_data_last_refreshed(self):
        '''
        Get production data last refreshed as string.

        Returns:
            datetime_str (str):
        '''
        return self._production_data_last_refreshed


    def get_production_data_last_refreshed_since_now(self, datetime_str=None):
        '''
        Get production data last refreshed as string.

        Args:
            datetime_str (str): datetime as string

        Returns:
            datetime_str (str):
        '''
        datetime_str = datetime_str or self._production_data_last_refreshed
        from dateutil import parser
        try:
            dt_before = parser.parse(datetime_str)
            return utils.get_time_stamp(dt_before, include_time_of_day=True)
        except Exception:
            return str()


    def get_frame_resolve_order_env_first(self):
        '''
        Get whether to resolve the environment frames before the pass frames or vice versa.

        Retuns:
            value (str):
        '''
        return self._frame_resolve_order_env_first


    def set_frame_resolve_order_env_first(self, value):
        '''
        Set whether to resolve the environment frames before the pass frames or vice versa.

        Args:
            value (bool):
        '''
        self._frame_resolve_order_env_first = bool(value)


    def get_production_frame_range(self, source=None):
        '''
        Get the production frame range based on currently chosen source.

        Args:
            source (str): which preferred production frame range to get.
                If not provided then use users preferred choice.

        Returns:
            frame_range (str):
        '''
        source = source or self.get_production_range_source()
        production_range = None
        if 'Cut' in source:
            production_range = self.get_cut_range()
        elif 'Delivery' in source:
            production_range = self.get_delivery_range()
        elif 'Important' in source:
            production_range = self.get_important_frames()
        elif 'FrameRange' in source:
            production_range = self.get_frame_range()
        # Otherwise fallback to the first available production range type
        if not production_range:
            production_range = self.get_cut_range()
        if not production_range:
            production_range = self.get_delivery_range()
        if not production_range:
            production_range = self.get_frame_range()
        if not production_range:
            production_range = self.get_important_frames()
        return production_range


    def get_job_identifier(self):
        '''
        Get the optional job identifier (if any).

        Returns:
            job_identifier (str):
        '''
        return self._job_identifier


    def set_job_identifier(self, value):
        '''
        Set the optional job identifier (if any).

        Args:
            value (str):
        '''
        if self._debug_mode:
            msg = '{}.set_job_identifier(). '.format(self._node_type)
            msg += self._get_env_and_pass_name_message()
            msg += 'Value: {}'.format(value)
            self.logMessage.emit(msg, logging.DEBUG)
        if not value:
            self._job_identifier = None
        else:
            value = str(value or str())
            # NOTE: Remove any non alphanumeric characters
            value = re.sub(r'\W+', str(), value)
            self._job_identifier = str(value)


    def get_split_frame_ranges(self):
        '''
        Get whether this Environment should be submitted in split frame Jobs or not.

        Returns:
            value (bool):
        '''
        return self._split_frame_ranges


    def get_split_frame_to_job_type_list(self, current_frame_only=False):
        '''
        Get all the split frame ranges for this Environment item.

        Args:
            current_frame_only (bool): ignore frame range overrides and only render current project frame

        Returns:
            value (list): split into multiple jobs
                based on given job_types and RenderPass types.
                List of tuples: [(frame_range, job_type)]
                Example: [('1-3', 'fastFrame'), ('1-10', 'normal')]
        '''
        value = list()

        env_frameset = self.resolve_frames(
            current_frame_only=current_frame_only)

        if self.get_frames_rule_fml():
            _frameset, resolved = self._resolve_rule(constants.OVERRIDE_FRAMES_FML, env_frameset)
            if resolved and _frameset:
                job_type = (str(_frameset), 'fastFrame')
                value.append(job_type)

        if self.get_frames_rule_x10():
            _frameset, resolved = self._resolve_rule(constants.OVERRIDE_FRAMES_X10, env_frameset)
            if resolved and _frameset:
                job_type = (str(_frameset), 'x10')
                value.append(job_type)

        if self.get_frames_rule_xn():
            frames_rule_xn =  self.get_frames_rule_xn()
            xn_label = 'x{}'.format(frames_rule_xn)
            _frameset, resolved = self._resolve_rule(xn_label, env_frameset)
            if resolved and _frameset:
                job_type = (str(_frameset), xn_label)
                value.append(job_type)

        if self.get_frames_rule_x1():
            _frameset, resolved = self._resolve_rule(constants.OVERRIDE_FRAMES_X1, env_frameset)
            if resolved and _frameset:
                job_type = (str(_frameset), 'x1')
                value.append(job_type)

        return value


    def get_split_frame_to_job_type(self, current_frame_only=False):
        '''
        Get all the split frame ranges for this Environment item.

        Args:
            current_frame_only (bool): ignore frame range overrides and only render current project frame

        Returns:
            display_value (str):
        '''
        value = self.get_split_frame_to_job_type_list(current_frame_only) or list()
        labels = list()
        for frame_range, job_type in value:
            label = '{} ({})'.format(frame_range, job_type)
            labels.append(label)
        return ', '.join(labels)


    def set_split_frame_ranges(self, value):
        '''
        Set whether this Environment should be submitted in split frame Jobs or not.

        Args:
            value (bool):
        '''
        if self._debug_mode:
            msg = '{}.set_split_frame_ranges(). '.format(self._node_type)
            msg += self._get_env_and_pass_name_message()
            msg += 'Value: {}'.format(value)
            self.logMessage.emit(msg, logging.DEBUG)
        self._split_frame_ranges = bool(value)


    def get_koba_shotsub(self):
        '''
        Get whether to perform Koba shotsub or not if assembly also
        defined at Environment level.

        Returns:
            value (bool):
        '''
        return self._koba_shotsub


    def set_koba_shotsub(self, value):
        '''
        Set whether to perform Koba shotsub or not if assembly also
        defined at Environment level.

        Args:
            value (bool):
        '''
        if self._debug_mode:
            msg = '{}.set_koba_shotsub(). '.format(self._node_type)
            msg += self._get_env_and_pass_name_message()
            msg += 'Value: {}'.format(value)
            self.logMessage.emit(msg, logging.DEBUG)
        self._koba_shotsub = bool(value)


    def update_environment_in_host_app(self, session_path=None):
        '''
        Update the environment in the host application.
        Requires reimplementation.

        Args:
            session_path (str):

        Returns:
            success (bool):
        '''
        return True


    def render_passes_for_environment(
            self,
            oz_area=None,
            pass_env_items=None,
            snapshot=None,
            job_name=str(),
            global_job_identifier=None,
            interactive=False,
            session_path=str(),
            local=False,
            current_frame_only=False,
            launch_paused=False,
            launch_zero_tier=False,
            note=str(),
            update_environment=False,
            **kwargs):
        '''
        Render the specified PassForEnvItems (or subclasses) for this oz area.

        Args:
            oz_area (str):
            pass_env_items (list): list of RenderPassForEnvItem/s (or subclasses)
            snapshot (str): optionally reuse an existing project snapshot for this submission,
                if it makes sense to do so.
                NOTE: This is intended to allow split jobs for various frame rules, for the same
                env and target pass versions.
            job_name (str):
            global_job_identifier (str): already included in job name
            interactive (bool):
            local (bool): True will dispatch the job to your localhost. Defaults to false.
            current_frame_only (bool): ignore frame range overrides and only render current project frame
            session_path (str): path to session data to auto append to optional shotsub notes
            note (str):
            update_environment (bool): optionally perform any update that
                prepares the environment for rendering all passes.

        Returns:
            success, collected_details_dict (tuple):
        '''
        if not pass_env_items:
            pass_env_items = list()
        oz_area = oz_area or self.get_oz_area()
        self._graph, self._session = (None, None)
        return False, dict()


    def set_job_attrs(
            self,
            job_name=None,
            display_name=None,
            oz_area=os.getenv('OZ_CONTEXT'),
            job_frame_set=None,
            interactive=False,
            additional_job_attrs=dict()):
        '''
        Set the Plow Job attributes for this EnvironmentItem which is
        being submitted to Plow as a single Job.

        Args:
            job_name (str):
            display_name (str):
            oz_area (str):
            job_frame_set (fileseq.FrameSet):
            interactive (bool):
            additional_job_attrs (dict): additional attrs to add to "managerJobAttributes"

        Returns:
            attr, job_name (tuple):
        '''
        if not self._graph:
            msg = 'No Job Graph Available To Set Job Attributes For!'
            self.logMessage.emit(msg, logging.CRITICAL)
            return False, job_name

        if job_name and isinstance(job_name, basestring):
            job_name = str(job_name)
        else:
            job_name = None

        import json

        attrs = self._graph.meta().valueForKey('managerJobAttributes') or dict()
        if attrs:
            attrs = json.loads(attrs)
        else:
            attrs = dict()

        if attrs:
            msg = 'Existing Dispatcher Job Attributes: "{}"'.format(attrs)
            msg += 'Type: "{}"'.format(type(attrs))
            self.logMessage.emit(msg, logging.INFO)

        frame_range_extents_count = 0
        if job_frame_set:
            try:
                job_frame_set = fileseq.FrameSet(str(job_frame_set))
                frame_range_extents_count = len(job_frame_set)
            except fileseq.ParseException:
                msg = 'Failed To Parse Job Frame Set: "{}". '.format(job_frame_set)
                msg += 'Full Exception: "{}".'.format(traceback.format_exc())
                job_frame_set = None

        msg = 'Frame Range Extents Count: "{}"'.format(frame_range_extents_count)
        self.logMessage.emit(msg, logging.INFO)

        if interactive:
            attrs.update({'jobType': 'interactive', 'interactive': True})
            if isinstance(job_name, basestring):
                job_name += '_INTERACTIVE'
        elif frame_range_extents_count > 0 and frame_range_extents_count <= 3:
            attrs.update({'jobType': 'fastFrame'})
            if isinstance(job_name, basestring):
                job_name += '_FASTFRAME'

        oz_area = oz_area or self.get_oz_area() or os.getenv('OZ_CONTEXT')
        oz_components = oz_area.split('/')
        shot = oz_components.pop()
        scene = oz_components.pop()
        tree = oz_components.pop()
        film = oz_components.pop()

        # NOTE: Setting Job attrs to be similar to those provided by wKatana
        attrs_to_update = {
            'film_tree_scene_shot': '_'.join([film, tree, scene, shot]),
            'film_tree_scene': '_'.join([film, tree, scene]),
            'film_tree': '_'.join([film, tree]),
            'film_scene_shot': '_'.join([film, scene, shot]),
            'tree_scene_shot': '_'.join([tree, scene, shot]),
            'scene_shot': '_'.join([scene, shot])}

        if display_name and isinstance(display_name, basestring):
            attrs_to_update['displayName'] = display_name
        elif job_name and isinstance(job_name, basestring):
            attrs_to_update['displayName'] = job_name

        attrs.update(attrs_to_update)

        # Add Oz exact (if possible)
        import oz
        try:
            oz_exact = {'oz_exact': str(oz.Oz.from_env())}
            attrs.update(oz_exact)
        except oz.NotOzzedError:
            pass

        if isinstance(job_frame_set, fileseq.FrameSet):
            attrs.update({'frameRange': str(job_frame_set)})

        if additional_job_attrs:
            attrs.update(additional_job_attrs)

        # attrs_clean = dict()
        # for key, value in attrs.iteritems():
        #     attrs_clean[str(key)] = str(value)

        self._graph.meta().setValueForKey('managerJobAttributes', json.dumps(attrs))
        self._graph.meta().setValueForKey('plowQuickLaunch', True)

        msg = 'Updated "managerJobAttributes" To: "{}"'.format(attrs)
        self.logMessage.emit(msg, logging.INFO)

        if job_name and isinstance(job_name, basestring):
            job_name = str(job_name)
            self._graph.meta().setValueForKey('managerJobTitle', job_name)
            if self._session:
                self._session.setJobName(job_name)

        return attrs, job_name


    def add_koba_assembly_for_env_to_graph(
            self,
            assembly_name,
            ignore_shot_overrides=False,
            graph=None):
        '''
        Add Koba assembly Kenobi node to Job graph for entire shot passes to render.

        Args:
            assembly_name (str): if not specified then use currently chosen assembly of this environment
            ignore_shot_overrides (bool):
            graph (kenobi.core.Graph): if not specified then use current graph (during submission)

        Returns:
            koba_node (kenobi.base.Node):
        '''
        environment = self.get_oz_area()

        ######################################################################
        # Validation

        graph = graph or self._graph
        if not self._graph:
            msg = 'No Job Graph Available To Build Koba Assembly For!'
            self.logMessage.emit(msg, logging.WARNING)
            return

        if not assembly_name:
            msg = 'No Koba Assembly To Add For Environment: "{}"'.format(environment)
            self.logMessage.emit(msg, logging.WARNING)
            return

        # NOTE: It's only possible for the Multi Shot UI to pass a valid assembly name at this point.
        # TODO: May later want to verify assembly name here, in case other API calls this.

        ######################################################################
        # Gather plug values

        job_identifier = self.get_job_identifier()
        koba_shotsub = self.get_koba_shotsub()

        node_name_parts = [environment[1:].replace('/', '_')]
        node_name_parts.append('Koba')
        node_name_parts.append(assembly_name)
        if job_identifier:
            node_name_parts.append(job_identifier)
        node_name = '_'.join(node_name_parts)

        frame_range = self.get_environment_frame_range_extent()

        description_parts = list()
        note_override_submission = self.get_note_override_submission() or self.get_note_override() or str()
        koba_note = "Koba Assembly: {}".format(assembly_name)
        if note_override_submission:
            description_parts.append(note_override_submission)
            description_parts.append(koba_note)
        else:
            msg = 'Submitted from {}'.format(constants.TOOL_NAME)
            description_parts.append(msg)
            description_parts.append(koba_note)
        description = '. '.join(description_parts)

        # Convert oz area to film/scene/shot for Koba.
        # NOTE: Koba currently doesn't support tree, it's always "shots".
        from srnd_multi_shot_render_submitter import koba_helper
        context_dict = koba_helper.formulate_context_map_from_environment(environment)
        # context_dict = self.get_context()
        project = context_dict.get('PROJECT')
        tree = 'shots'
        scene = context_dict.get('SCENE')
        shot = context_dict.get('SHOT')
        koba_context_str = '/'.join([project, scene, shot])

        msg = 'Koba Assembly To Add To Job Graph: "{}". '.format(assembly_name)
        msg += 'Environment: "{}"'.format(environment)
        self.logMessage.emit(msg, logging.INFO)

        msg = 'Koba Context: "{}"'.format(koba_context_str)
        self.logMessage.emit(msg, logging.INFO)

        msg = 'Koba Frame Range: "{}"'.format(frame_range)
        self.logMessage.emit(msg, logging.INFO)

        msg = 'Koba Description: "{}"'.format(description)
        self.logMessage.emit(msg, logging.INFO)

        msg = 'Koba Shotsub: "{}"'.format(koba_shotsub)
        self.logMessage.emit(msg, logging.INFO)

        msg = 'Ignore Shot Overrides: "{}"'.format(ignore_shot_overrides)
        self.logMessage.emit(msg, logging.INFO)

        ######################################################################
        # Set plug values

        koba_node = graph.createNode('koba.nodes.KobaCL')
        koba_node.setName(node_name)

        # Specific assembly name for Koba process
        koba_node.findInput('AssemblyName').setValue(str(assembly_name))

        if ignore_shot_overrides:
            ignore_override_plug = koba_node.findInput('IgnoreOverride')
            if ignore_override_plug:
                ignore_override_plug.setValue(True)
                msg = 'Set KobaCL Node IgnoreOverride Plug To True! '
                self.logMessage.emit(msg, logging.WARNING)
            else:
                msg = 'IgnoreOverride Plug Does Not Exist On KobaCL Node! '
                msg += 'Use The Latest Koba Pak!'
                self.logMessage.emit(msg, logging.WARNING)

        # # Dictionary of arguments to form {nodename{knobname:value}}
        # arguments = dict()
        # koba_node.findInput('Arguments').setValue(arguments)

        # film/scene/shot
        koba_node.findInput('Context').setValue(str(koba_context_str))

        # Optional frame range flag, if not given use 'smartRange' feature in Koba
        koba_node.findInput('FrameRange').setValue(str(frame_range))

        # String to tag the Hydra version with
        koba_node.findInput('HydraTag').setValue('latest')

        # Koba render/chunk size
        koba_node.findInput('Chunk').setValue(1)

        # Koba write node version number override
        koba_node.findInput('VersionNumber').setValue(0)

        # Plow Job name override
        koba_node.findInput('JobName').setValue(str(node_name))

        # # Element name if any
        # koba_node.findInput('ElementName').setValue(str())

        # # Plow koba jobType attribute
        # koba_node.findInput('KobaTask').setValue(str())

        # Description for each published assembly or of Shotsub note
        koba_node.findInput('Description').setValue(str(description))

        # Submit render using multi slot
        # koba_node.findInput('MultiSlots').setValue(False)

        # Atributes dictionary to pass on to outputs
        # koba_node.findInput('Attributes').setValue(dict())

        # Set assembly to stereo views when resolving
        # koba_node.findInput('Stereo').setValue(False)

        # Set off shotsub after render
        koba_node.findInput('Shotsub').setValue(bool(koba_shotsub))

        # # Turn on debugging for this node
        # koba_node.findInput('Debug').setValue(True)

        # # NOTE: If need to make the generated Job also dependent on another Job.
        # koba_node.job_id = plow_job_id

        import srnd_pipeline.kenobi.environment
        try:
            srnd_pipeline.kenobi.environment.setup_kenobi_environment(
                koba_node,
                project,
                tree,
                scene,
                shot,
                ep_name='nuke',
                use_ep=True)
        except Exception:
            msg = 'Failed To Setup Koba Environment: "{}". '.format(context_dict)
            msg += 'For Koba Node: "{}". '.format(koba_node)
            msg += 'Full Exception: "{}".'.format(traceback.format_exc())
            self.logMessage.emit(msg, logging.WARNING)

        return koba_node


    def post_environment_render(self):
        '''
        After an Environments desired RenderPassForEnv item/s was
        submitted for rendering, perform any optional post render tasks.

        Returns:
            success, msg (tuple)
        '''
        msg = 'No Post Environment Render Tasks To Perform!'
        self.logMessage.emit(msg, logging.WARNING)
        return True, msg


    def check_frame_range_in_custom_range(
            self,
            frame_range,
            custom_frame_range,
            valid_if_not_custom_frames=False):
        '''
        Check the custom frame range is within the approved frame range.

        Args:
            frame_range (str):
            custom_frame_range (str):
            valid_if_not_custom_frames (bool): if custom frame provided is actually
                a frame range rule like FML, then return True, instead of
                checking custom frames in approved range.

        Returns:
            in_frame_range, custom_frame_count (tuple):
        '''
        # Check custom frame is not a frame rule like FML
        if custom_frame_range and valid_if_not_custom_frames:
            try:
                custom_frame_range = str(fileseq.FrameSet(custom_frame_range))
            except fileseq.ParseException as error:
                return True, 0

        # Parse approved range
        cut_frameset = None
        try:
            cut_frameset = fileseq.FrameSet(frame_range)
        except fileseq.ParseException as error:
            msg = 'Failed To Parse Approved Frames: "{}"'.format(frame_range)
            # msg += 'Full Exception: "{}".'.format(traceback.format_exc())
            self.logMessage.emit(msg, logging.WARNING)

        # Try to parse custom frame range
        custom_frameset = None
        try:
            custom_frameset = fileseq.FrameSet(custom_frame_range)
        except fileseq.ParseException as error:
            msg = 'Failed To Parse Custom Frames: "{}"'.format(custom_frame_range)
            # msg += 'Full Exception: "{}".'.format(traceback.format_exc())
            self.logMessage.emit(msg, logging.WARNING)

        # Check custom range in approved range
        if cut_frameset and custom_frameset:
            if custom_frameset.issubset(cut_frameset):
                return True, len(custom_frameset)
            else:
                # msg = 'Custom Frames: "{}". '.format(custom_frame_range)
                # msg += 'Not In Cut Range: "{}".'.format(cut_frameset)
                # self.logMessage.emit(msg, logging.WARNING)
                return False, len(custom_frameset)

        return False, 0


    def sync_production_data(self, shot_object=None):
        '''
        Gather production data for this environment node using Pericsope2.

        Args:
            shot_object (persicope2.Shot): optionally use the specified Shot or Asset object

        Returns:
            success, shot_object (bool):
        '''
        oz_area = self.get_oz_area()
        nice_env_name = self.get_environment_name_nice()

        self._cut_range = None
        self._delivery_range = None
        self._frame_range = None
        self._important_frames = str()
        self._editorial_shot_status = str()
        self._due_date = str()

        from datetime import datetime
        self._production_data_last_refreshed = str(datetime.now())

        shot_object = shot_object or production_info.get_shot_for_environment(oz_area)
        if not shot_object:
            return False, shot_object

        try:
            cut_frame_in = shot_object.cut_frame_in
            cut_frame_out = shot_object.cut_frame_out
            if isinstance(cut_frame_in, (int, float)) and \
                    isinstance(cut_frame_out, (int, float)):
                cut_range = '{}-{}'.format(int(cut_frame_in), int(cut_frame_out))
                self._cut_range = str(fileseq.FrameSet(cut_range or str()))
        except Exception as error:
            msg = 'Failed to sync "cut_frame_in" or out for env: "{}". '.format(nice_env_name)
            msg += 'Full exception: "{}".'.format(traceback.format_exc())
            self.logMessage.emit(msg, logging.WARNING)

        try:
            delivery_range = str(shot_object.delivery_range or str()).replace(' ', str())
            self._delivery_range = str(fileseq.FrameSet(delivery_range or str()))
        except Exception as error:
            msg = 'Failed to sync "delivery_range" for env: "{}". '.format(nice_env_name)
            msg += 'Full exception: "{}".'.format(traceback.format_exc())
            self.logMessage.emit(msg, logging.WARNING)

        try:
            frame_range_in = shot_object.frame_range_in
            frame_range_out = shot_object.frame_range_out
            if isinstance(frame_range_in, (int, float)) and \
                    isinstance(frame_range_out, (int, float)):
                frame_range = '{}-{}'.format(int(frame_range_in), int(frame_range_out))
                self._frame_range = str(fileseq.FrameSet(frame_range or str()))
        except Exception as error:
            msg = 'Failed to sync "frame_range" for env: "{}". '.format(nice_env_name)
            msg += 'Full exception: "{}".'.format(traceback.format_exc())
            self.logMessage.emit(msg, logging.WARNING)

        self._important_frames = str()
        try:
            important_frames = str(shot_object.important_frames or str()).replace(' ', str())
            self._important_frames = str(fileseq.FrameSet(important_frames or str()))
        except Exception as error:
            msg = 'Failed to sync "important_frames" for env: "{}". '.format(nice_env_name)
            msg += 'Full exception: "{}".'.format(traceback.format_exc())
            self.logMessage.emit(msg, logging.WARNING)

        self._delivery_format = str()
        try:
            self._delivery_format = str(shot_object.delivery_format.full_name)
        except Exception as error:
            msg = 'Failed to sync "delivery_format.full_name" for env: "{}". '.format(nice_env_name)
            msg += 'Full exception: "{}".'.format(traceback.format_exc())
            self.logMessage.emit(msg, logging.WARNING)

        self._editorial_shot_status = str()
        try:
            self._editorial_shot_status = str(shot_object.editorial_shot_status)
        except Exception as error:
            msg = 'Failed to sync "editorial_shot_status" for env: "{}". '.format(nice_env_name)
            msg += 'Full exception: "{}".'.format(traceback.format_exc())
            self.logMessage.emit(msg, logging.WARNING)

        self._due_date = str()
        try:
            due_date_datetime = shot_object.desired_date
            # NOTE: "desired_date" = The date the shot is desired to be finished by.
            # NOTE: "creative_approval_date" = The date the Director has approved this shot.
            # NOTE: "final_date" = The date the shot was last set to a final status.
            # NOTE: "first_look_date" = The first look date of the shot
            self._due_date = str(utils.get_time_stamp(due_date_datetime))
        except Exception as error:
            msg = 'Failed to sync "desired_date" for env: "{}". '.format(nice_env_name)
            msg += 'Full exception: "{}".'.format(traceback.format_exc())
            self.logMessage.emit(msg, logging.WARNING)

        msg = 'Finished sync production data: "{}"'.format(nice_env_name)
        self.logMessage.emit(msg, logging.INFO)

        return True, shot_object


    def cache_production_data_as_previous(self):
        '''
        Cache the current production data of this environment item as previous.
        NOTE: Currently only the summary dialog uses this method.

        Returns:
            data (dict):
        '''
        self._previous_production_data = dict()
        self._previous_production_data['production_frame_range'] = self.get_production_frame_range()
        self._previous_production_data['production_data_last_refreshed'] = self._production_data_last_refreshed
        return self._previous_production_data


    def get_previous_production_data(self):
        '''
        Get mapping of previous production data before resolve all is executed.

        Returns:
            previous_production_data (dict):
        '''
        try:
            return self._previous_production_data or dict()
        except AttributeError:
            return dict()


    def get_previous_production_frame_range(self):
        '''
        Get the previous production frame range before resolve all is executed.

        Returns:
            production_frame_range (str):
        '''
        data = self.get_previous_production_data() or dict()
        return data.get('production_frame_range')


    def cache_production_data_changed(self):
        '''
        Check last cached production data against current production data and store cache of details.
        '''
        try:
            self._previous_production_data
        except AttributeError:
            return
        production_frame_range = self._previous_production_data.get('production_frame_range')
        self._production_frame_range_changed = production_frame_range != self.get_production_frame_range()


    def get_production_data_changed(self):
        '''
        After summary dialog is opened check whether the production data changed or not (after resolve all).

        Returns:
            production_frame_range_changed (bool):
        '''
        try:
            return self._production_frame_range_changed
        except AttributeError:
            return False


    def get_snapshot_hyref(self):
        '''
        Get the last snapshot scene hyref, created during submission.

        Returns:
            value (str):
        '''
        return self._snapshot_hyref


    def set_snapshot_hyref(self, value):
        '''
        Cache the snapshot hyref on this environment item.

        Args:
            value (str):
        '''
        if value:
            msg = 'Cache Environment Snapshot Hyref: "{}". '.format(value)
            msg += 'For Environment: "{}"'.format(self.get_oz_area())
            self.logMessage.emit(msg, logging.INFO)
        self._snapshot_hyref = value


    def get_hash_pass_versions(self, pass_env_items=None):
        '''
        Get hash data as mapping of host app render node name to hash data.
        NOTE: This might be used to calculate which same environments have same target
        pass versions, therefore the render snapshot could be reused between environments.

        Args:
            pass_env_items (list): list of explicit pass for env items to get hashed data for,
                otherwise get data from all active items.

        Returns:
            pass_for_env_hash_data (dict): mapping of host app render node full path to hash data
        '''
        pass_env_items = pass_env_items or self.siblings()
        pass_for_env_hash_data = dict()
        for pass_env_item in pass_env_items:
            if not pass_env_item.get_active():
                continue
            render_item = pass_env_item.get_source_render_item()
            item_full_name = render_item.get_item_full_name()
            version_number = pass_env_item.get_resolved_version_number()
            if version_number:
                hash_data = [version_number]
                if pass_env_item.has_render_overrides(include_from_env=True):
                    render_overrides_items = pass_env_item.get_render_overrides_items() or dict()
                    hash_data.extend(render_overrides_items.keys())
                    values = [_item.get_value() for _item in render_overrides_items.values()]
                    if values:
                        hash_data.extend(values)
                    # Merge any environment render overrides with pass render overrides
                    environment_item = pass_env_item.get_environment_item()
                    render_overrides_items_env = environment_item.get_render_overrides_items() or dict()
                    hash_data.extend(render_overrides_items_env.keys())
                    values = [_item.get_value() for _item in render_overrides_items_env.values()]
                    if values:
                        hash_data.extend(values)
                pass_for_env_hash_data[item_full_name] = hash_data
        return pass_for_env_hash_data


    ##########################################################################
    # Cached production data (from last Sync production data)


    def get_frame_range(self):
        return self._frame_range

    def get_delivery_range(self):
        return self._delivery_range

    def get_cut_range(self):
        return self._cut_range

    def get_important_frames(self):
        return self._important_frames

    def get_delivery_format(self):
        return self._delivery_format

    def get_editorial_shot_status(self):
        return self._editorial_shot_status

    def get_due_date(self):
        return self._due_date

    def get_thumbnail_path(self):
        return self._thumbnail_path

    def set_thumbnail_path(self, value):
        self._thumbnail_path = str()
        if value and os.path.isfile(str(value)):
            self._thumbnail_path = str(value)


    def derive_and_cache_shot_thumbnail_path(
            self,
            oz_area=None,
            shot_object=None,
            animated=False,
            cached=True):
        '''
        Derive the shot environment Shotsub thumbnail.

        Args:
            oz_area (str):
            shot_object (persicope2.Shot): optionally use the specified Shot or Asset object
            animated (bool): get animated gif otherwise static jpg
            cached (bool):

        Returns:
            thumbnail_path (str):
        '''
        thumbnail_path = self.get_thumbnail_path()
        if cached and thumbnail_path:
            return thumbnail_path
        environment = oz_area or self.get_oz_area()
        thumbnail_path = production_info.get_shotsub_thumbnail_path_for_environment(
            environment,
            shot_object=shot_object,
            animated=animated)
        if self._debug_mode:
            msg = 'Derived thumbnail path: "{}". '.format(thumbnail_path)
            msg += 'For environment: "{}"'.format(environment)
            self.logMessage.emit(msg, logging.INFO)
        self.set_thumbnail_path(thumbnail_path)
        return thumbnail_path


    ##########################################################################


    def search_for_string(self, search_text):
        '''
        Search this environment data object for matching string.

        Args:
            search_text (str):

        Returns:
            found (bool):
        '''
        found = re.findall(search_text, self.get_oz_area(), flags=re.IGNORECASE)
        if found:
            return True

        found = re.findall(search_text, self.get_environment_name_nice())
        if found:
            return True

        # Search for matching oz area first
        ENVIRONMENT_TOKENS = ('env:', 'area:', 'environment:', 'shot:')
        has_environment_token = search_text.startswith(ENVIRONMENT_TOKENS)
        # job_identifier = self.get_job_identifier()
        if has_environment_token:#and any([oz_area, job_identifier]):
            _oz_area = search_text.split(':')[-1]
            if _oz_area:
                found = re.findall(_oz_area, self.get_oz_area(), flags=re.IGNORECASE)
                if not found:
                    found = re.findall(_oz_area, self.get_environment_name_nice())
                if found:
                    return True
            else:
                return True

        # Search for job identifier
        JOB_IDENTIFIER_TOKEN = 'job:'
        has_job_identifier_token = search_text.startswith(JOB_IDENTIFIER_TOKEN)
        job_identifier = self.get_job_identifier()
        if has_job_identifier_token and job_identifier:
            _job_identifier = search_text.split(':')[-1]
            if _job_identifier:
                found = re.findall(_job_identifier, job_identifier, flags=re.IGNORECASE)
                if found:
                    return True
            else:
                return True

        # Call super class to search for the string (search for matching frames)
        found = OverrideBaseItem.search_for_string(self, search_text)
        if found:
            return True

        return False


    def _get_renderable_count_for_env(self):
        '''
        Get total number of current renderable passes for this
        EnvironmentItem that are both enabled and queued.
        Is a caching mechanism for summary details and custom paint events.
        '''
        return self._renderable_count_for_env


    def _get_cached_environment_index(self):
        return self._environment_index_cached


    def _set_cached_environment_index(self, index):
        self._environment_index_cached = index


    def get_pass_for_env_items(self, active_only=False):
        '''
        Get all the render pass for env items of this environment, and optionally
        only the active items.

        Args:
            active_only (bool):

        Returns:
            pass_for_env_items (list):
        '''
        if not active_only:
            return self.siblings()
        active_pass_for_env_items = list()
        for pass_env_item in self.siblings():
            if pass_env_item.get_active():
                active_pass_for_env_items.append(pass_env_item)
        return active_pass_for_env_items


    def get_pass_for_env_items_being_dispatched(self):
        '''
        Get only the render pass for env items currently being dispatched of this environment.

        Returns:
            pass_for_env_items (list):
        '''
        pass_for_env_items = list()
        for pass_for_env_item in self.siblings():
            if pass_for_env_item.get_is_being_dispatched():
                pass_for_env_items.append(pass_for_env_item)
        return pass_for_env_items


    def get_renderable_nodes_in_host_app(self, pass_env_items=None):
        '''
        Get all the queued and enabled source Render nodes
        for this EnvironmentItem.

        Args:
            pass_env_items (list): list of PassForEnvItems to filter nodes list to

        Returns:
            render_nodes (list): list of native host app Render node objects
        '''
        render_nodes = list()
        for pass_for_env_item in self.get_pass_for_env_items():
            if pass_env_items and pass_for_env_item not in pass_env_items:
                continue
            render_item = pass_for_env_item.get_source_render_item()
            if not render_item:
                continue
            render_node = render_item.get_node_in_host_app()
            if not render_node:
                msg = 'Failed To Find Render Node In Host App For Item '
                msg += 'Identifier: "{}"'.format(pass_for_env_item.get_identifier())
                self.logMessage.emit(msg, logging.WARNING)
                continue
            render_nodes.append(render_node)
        return render_nodes


    def get_pass_for_env_by_full_name(self, item_full_name):
        '''
        Get the sibling RenderPassForEnvItem (or subclass), of this
        EnvironmentItem, with a particular node name (if any).

        Args:
            item_full_name (str):

        Returns:
            render_pass_for_env (RenderPassForEnvItem):
        '''
        for pass_for_env_item in self.get_pass_for_env_items():
            render_item = pass_for_env_item.get_source_render_item()
            if render_item and render_item.get_item_full_name() == item_full_name:
                return pass_for_env_item


    def get_environment_frame_range_extent(self, resolve_frames=True):
        '''
        Get the frame range extent for an Environment / Shot.
        Which includes all queued and enabled render pass for env
        resolved frame ranges combined.

        Args:
            resolve_frames (bool): whether to resolve the frames for each
                render pass for env, or use last cached resolved frames.

        Returns:
            frame_range (fileseq.FrameSet):
        '''
        frame_set_env_extent = fileseq.FrameSet(str())
        for pass_env_item in self.get_pass_for_env_items():
            # Skip resolving queued and unqueued items
            if not pass_env_item.get_active():
                continue
            # Resolve the frames again
            if resolve_frames:
                frame_set = pass_env_item.resolve_frames()
            # Use last cached resolved frames
            else:
                try:
                    frame_set = fileseq.FrameSet(pass_env_item.get_resolved_frames_enabled())
                except fileseq.ParseException as error:
                    frame_set = pass_env_item.resolve_frames()
            # Union frame extents together
            if frame_set:
                frame_set_env_extent = frame_set_env_extent.union(frame_set)
        return frame_set_env_extent


    def is_environment_item(self):
        '''
        This method returns the type of node, so subclasses with possibly
        a different item type string, can still be identified as a
        node with specific functionality.

        Returns:
            is_environment_item (bool):
        '''
        return True


    def get_identifier(self, *args, **kwargs):
        '''
        Return the oz area, as an identifier.

        Args:
            joiner (str):

        Returns:
            identifier (str):
        '''
        return self.get_oz_area()


    ##########################################################################
    # Validation


    def get_validation_warning_counter(self):
        return self._validation_warning_counter

    def set_validation_warning_counter(self, count):
        self._validation_warning_counter = count

    def get_validation_critical_counter(self):
        return self._validation_critical_counter

    def set_validation_critical_counter(self, count):
        self._validation_critical_counter = count


#############################################################################


class RenderPassForEnvItem(OverrideBaseItem):
    '''
    A MSRS object representation of an render pass for particular environment.
    NOTE: This render pass item can have multiple render override items, and
    has a reference to the source render item, and the environment.

    Args:
        queued (bool):
        enabled (bool):
        overrides_dict (dict):
        version_override (str): override of version for env (None if not set)
        frame_range_override (str): override of pass for env frame range (None if not set)
        icon_path (str):
        render_overrides_items (collections.OrderedDict):
            dict mapping of render override id to render override item that
            this render pass for env has
        source_render_item (RenderItem): abstract node representing
            the source render node (for no particular environment).
            Note: The source render nodes are the columns.
        first_sibling (object): pass in the first sibling abstract node of Environment type.
            the first sibling Environment node is on column 0, where all other siblings
            are on every other column.
        debug_mode (bool): whether this abstract data emits message signals upstream
    '''

    logMessage = Signal(str, int)
    toggleProgressBarVisible = Signal(bool)
    updateLoadingBarFormat = Signal(int, str)

    def __init__(
            self,
            queued=True,
            enabled=True,
            overrides_dict=None,
            version_override=None,
            frame_range_override=None,
            node_type='RenderPassForEnvItem',
            icon_path=None,
            render_overrides_items=None,
            source_render_item=None,
            first_sibling=None,
            debug_mode=False,
            parent=None):

        kwargs = dict(locals())
        kwargs.pop('self')
        kwargs.pop('source_render_item')

        super(RenderPassForEnvItem, self).__init__(**kwargs)

        self._plow_job_id_last = None
        self._plow_layer_id_last = None
        self._plow_task_id_last = None
        self._render_estimate_average_frame = None

        self._source_render_item = source_render_item

        self._resolved_version_number = None
        self._resolved_version_system = None
        self._resolved_version_already_registered = False

        self._resolved_frames_enabled = str()
        self._resolved_frames_enabled_count = 0
        self._resolved_frames_queued = str()
        self._resolved_frames_queued_count = 0

        self._time_to_setup_render = 0
        self._kenobi_render_node = None
        self._is_being_dispatched = False
        self._render_progress = None

        if overrides_dict and isinstance(overrides_dict, dict):
            self.paste_overrides(overrides_dict)


    def copy_resolved_values(self, pass_env_item):
        '''
        Copy the resolved values from another pass for env item.

        Args:
            pass_env_item (RenderPassForEnvItem):
        '''
        self._resolved_frames_enabled = pass_env_item._resolved_frames_enabled
        self._resolved_frames_enabled_count = pass_env_item._resolved_frames_enabled_count
        self._resolved_frames_queued = pass_env_item._resolved_frames_queued
        self._resolved_frames_queued_count = pass_env_item._resolved_frames_queued_count
        self._resolved_version_number = pass_env_item._resolved_version_number
        self._resolved_version_system = pass_env_item._resolved_version_system
        self._render_estimate_average_frame = pass_env_item._render_estimate_average_frame
        self._render_progress = pass_env_item._render_progress
        # self._plow_job_id_last = pass_env_item._plow_job_id_last
        # self._plow_layer_id_last = pass_env_item._plow_layer_id_last
        # self._plow_task_id_last = pass_env_item._plow_task_id_last


    def get_session_data(self, use_submit_note=False):
        '''
        Gather all session details for this RenderPassForEnv or subclass.
        Reimplement this method to gather additional session data for subclassed items.

        Args:
            use_submit_note (bool):

        Returns:
            data (dict):
        '''
        # Gather identity id and active states from super class.
        # Also gather all generic overrides for either env or pass for env.
        data = OverrideBaseItem.get_session_data(
            self,
            use_submit_note=use_submit_note) or collections.OrderedDict()

        # Add pass for env specific data
        render_item = self.get_source_render_item()
        if not render_item:
            msg = 'No Associated Render Item For: "{}". '.format(self)
            self.logMessage.emit(msg, logging.WARNING)

        if render_item:
            data['pass_name'] = str(render_item.get_pass_name() or str())

        is_being_dispatched = self.get_is_being_dispatched()
        if is_being_dispatched:
            data['is_being_dispatched'] = bool(is_being_dispatched)

        plow_job_id_last = self.get_plow_job_id_last()
        if plow_job_id_last:
            data['plow_job_id_last'] = plow_job_id_last

        plow_layer_id_last = self.get_plow_layer_id_last()
        if plow_layer_id_last:
            data['plow_layer_id_last'] = plow_layer_id_last

        return data


    def apply_session_data(self, data=None, **kwargs):
        '''
        Apply session data to this render pass for env.
        Reimplement this method to apply additional session data for subclassed items.

        Args:
            data (dict):

        Returns:
            sync_count (int):
        '''
        if not data or not isinstance(data, dict):
            return 0

        sync_count = OverrideBaseItem.apply_session_data(self, data)

        version_override = data.get('version_override', None)
        self.set_version_override(version_override)

        found_frame_rule = False
        found_not_frame_rule = False

        frame_range_override = data.get('frame_range_override', None)
        if frame_range_override not in constants.OVERRIDES_FRAME_RULES:
            self.set_frame_range_override(frame_range_override)
            found_frame_rule = True

        not_frame_range_override = data.get('not_frame_range_override', None)
        if not_frame_range_override not in constants.OVERRIDES_FRAME_RULES:
            self.set_not_frame_range_override(not_frame_range_override)
            found_not_frame_rule = True

        frames_rule_important = data.get('frames_rule_important')
        if frames_rule_important:
            self.set_frames_rule_important(True)
        # TODO: For backwards session compatible. To be removed soon
        elif not found_frame_rule and frame_range_override == 'Important':
            self.set_frames_rule_important(True)
            found_frame_rule = True

        frames_rule_fml = data.get('frames_rule_fml')
        if frames_rule_fml:
            self.set_frames_rule_fml(True)
        # TODO: For backwards session compatible. To be removed soon
        elif not found_frame_rule and frame_range_override == 'First Middle Last':
            self.set_frames_rule_fml(True)
            found_frame_rule = True

        frames_rule_x1 = data.get('frames_rule_x1')
        if frames_rule_x1:
            self.set_frames_rule_x1(True)
        # TODO: For backwards session compatible. To be removed soon
        elif not found_frame_rule and frame_range_override == 'X1':
            self.set_frames_rule_x1(True)
            found_frame_rule = True

        frames_rule_x10 = data.get('frames_rule_x10')
        if frames_rule_x10:
            self.set_frames_rule_x10(True)
        # TODO: For backwards session compatible. To be removed soon
        elif not found_frame_rule and frame_range_override == 'X10':
            self.set_frames_rule_x10(True)
            found_frame_rule = True

        frames_rule_xn = data.get('frames_rule_xn')
        if isinstance(frames_rule_xn, int):
            self.set_frames_rule_xn(frames_rule_xn)
        # TODO: For backwards session compatible. To be removed soon
        elif not found_frame_rule and frame_range_override.startswith('x'):
            try:
                self.set_frames_rule_xn(int(frame_range_override.split('x')[-1]))
                found_frame_rule = True
            except Exception:
                pass

        not_frames_rule_important = data.get('not_frames_rule_important')
        if not_frames_rule_important:
            self.set_not_frames_rule_important(True)

        not_frames_rule_fml = data.get('not_frames_rule_fml')
        if not_frames_rule_fml:
            self.set_not_frames_rule_fml(True)
        # TODO: For backwards session compatible. To be removed soon
        elif not found_not_frame_rule and not_frame_range_override == 'NOT First Middle Last':
            self.set_not_frames_rule_fml(True)
            found_not_frame_rule = True

        not_frames_rule_x10 = data.get('not_frames_rule_x10')
        if not_frames_rule_x10:
            self.set_not_frames_rule_x10(True)
        # TODO: For backwards session compatible. To be removed soon
        elif not found_not_frame_rule and not_frame_range_override == 'NOT x10':
            self.set_not_frames_rule_x10(True)
            found_not_frame_rule = True

        not_frames_rule_xn = data.get('not_frames_rule_xn')
        if isinstance(not_frames_rule_xn, int):
            self.set_not_frames_rule_xn(not_frames_rule_xn)
        # TODO: For backwards session compatible. To be removed soon
        elif not found_not_frame_rule and not_frame_range_override.startswith('x'):
            try:
                self.set_not_frames_rule_xn(int(not_frame_range_override.split('x')[-1]))
                found_not_frame_rule = True
            except Exception:
                pass

        note_override = data.get('note_override', None)
        self.set_note_override(note_override)

        wait_on = data.get(constants.SESSION_KEY_WAIT_ON, list())
        self.set_wait_on(wait_on)

        colour = data.get('colour', list())
        self.set_colour(colour)

        post_tasks = data.get('post_tasks', list())
        self.set_post_tasks(post_tasks)

        is_being_dispatched = data.get('is_being_dispatched', None)
        if is_being_dispatched and isinstance(is_being_dispatched, bool):
            self.set_is_being_dispatched(True)

        plow_job_id_last = data.get('plow_job_id_last', None)
        self.set_plow_job_id_last(plow_job_id_last)

        plow_layer_id_last = data.get('plow_layer_id_last', None)
        self.set_plow_layer_id_last(plow_layer_id_last)

        sync_count += 1

        return sync_count


    def search_for_string(self, search_text):
        '''
        Search this render pass for env data object for matching string.

        Args:
            search_text (str):

        Returns:
            found (bool):
        '''
        # Search the source render item for string match
        render_item = self.get_source_render_item()
        if render_item:
            found = render_item.search_for_string(search_text)
            if found:
                return True

        # Call super class to search for the string (search for matching frames)
        found = OverrideBaseItem.search_for_string(self, search_text)
        if found:
            return True

        return False


    def get_source_render_item(self):
        '''
        Get the source abstract Render node (if any).
        This source Render nodes is for no particular environment, and
        relates to available columns.

        Returns:
            source_render_item (RenderItem):
        '''
        return self._source_render_item


    def get_node_name(self):
        '''
        Get the node name for source render item.

        Returns:
            node_name (str):
        '''
        render_item = self.get_source_render_item()
        if render_item:
            return render_item.get_node_name()


    def get_pass_name(self):
        '''
        Get the pass name for source render item.

        Returns:
            pass_name (str):
        '''
        render_item = self.get_source_render_item()
        if render_item:
            return render_item.get_pass_name()


    def get_version_override(self):
        '''
        Get user override option for version (if any).

        Returns:
            version_override (str):
        '''
        return self._version_override


    def set_version_override(self, value):
        '''
        Set user override option for version (if any).

        Args:
            value (str):
        '''
        if self._debug_mode:
            msg = '{}.set_version_override(). '.format(self._node_type)
            msg += self._get_env_and_pass_name_message()
            msg += 'Value: {}'.format(value)
            self.logMessage.emit(msg, logging.DEBUG)
        if not value:
            self._version_override = None
        else:
            self._version_override = value


    def get_frame_range_override(self):
        '''
        Get user override option for frame range (if any).

        Returns:
            frame_range_override (str): or None if no override
        '''
        return self._frame_range_override


    def set_frame_range_override(self, value):
        '''
        Set user override option for frame range (if any).

        Args:
            value (str): or None if no override
        '''
        if self._debug_mode:
            msg = '{}.set_frame_range_override(). '.format(self._node_type)
            msg += self._get_env_and_pass_name_message()
            msg += 'Value: {}'.format(value)
            self.logMessage.emit(msg, logging.DEBUG)
        if not value:
            self._frame_range_override = None
        else:
            self._frame_range_override = str(value)


    def get_plow_job_id_last(self):
        '''
        Get the last launched Plow Job id of the current pass for env item (if any).

        Returns:
            plow_job_id_last (str):
        '''
        return self._plow_job_id_last


    def set_plow_job_id_last(self, value):
        '''
        Set the last launched Plow Job id of the current pass for env item.

        Args:
            value (str):
        '''
        if self._debug_mode:
            msg = '{}.set_plow_job_id_last(). '.format(self._node_type)
            msg += self._get_env_and_pass_name_message()
            msg += 'Value: {}'.format(value)
            self.logMessage.emit(msg, logging.DEBUG)
        self._plow_job_id_last = value


    def get_plow_layer_id_last(self):
        '''
        Get the last launched Plow Layer id of the current pass for env item (if any).

        Returns:
            plow_layer_id_last (str):
        '''
        return self._plow_layer_id_last


    def set_plow_layer_id_last(self, value):
        '''
        Set the last launched Plow Layer id of the current pass for env item.

        Args:
            value (str):
        '''
        if self._debug_mode:
            msg = '{}.set_plow_layer_id_last(). '.format(self._node_type)
            msg += self._get_env_and_pass_name_message()
            msg += 'Value: {}'.format(value)
            self.logMessage.emit(msg, logging.DEBUG)
        self._plow_layer_id_last = value


    def get_plow_task_ids_last(self):
        '''
        Get the last launched Plow Task ids of the current pass for env item (if any).

        Returns:
            plow_job_id_last (list):
        '''
        return self._plow_task_id_last


    def set_plow_task_ids_last(self, value):
        '''
        Set the last launched Plow Task ids of the current pass for env item.

        Args:
            value (list):
        '''
        if self._debug_mode:
            msg = '{}.set_plow_task_ids_last(). '.format(self._node_type)
            msg += self._get_env_and_pass_name_message()
            msg += 'Value: {}'.format(value)
            self.logMessage.emit(msg, logging.DEBUG)
        self._plow_task_id_last = value


    def get_render_estimate_average_frame(self):
        '''
        Get the cached average time in took to render this render pass for env last time (if available).

        Returns:
            value (float): if 0 then value is invalid and hasn't been computed
        '''
        return self._render_estimate_average_frame


    def set_render_estimate_average_frame(self, value):
        '''
        Set the cached average time in took to render this render pass for env last time

        Returns:
            value (float): if 0 then value is invalid and hasn't been computed
        '''
        if self._debug_mode:
            msg = '{}.set_render_estimate_average_frame(). '.format(self._node_type)
            msg += self._get_env_and_pass_name_message()
            msg += 'Value: {}'.format(value)
            self.logMessage.emit(msg, logging.DEBUG)
        self._render_estimate_average_frame = value


    def get_render_estimate_core_hours(self, estimate_per_frame=None, frame_count=None):
        '''
        Get the estimated core hours to render N number of frames, given an average time per frame.

        Args:
            estimate_per_frame (float): if not provided then use value cached on this item
            frame_count (int): if not provided then use value cached on this item

        Returns:
            core_hours (float):
        '''
        estimate_per_frame = estimate_per_frame or self._render_estimate_average_frame
        frame_count = frame_count or self.get_resolved_frames_count_queued()
        estimate_total = estimate_per_frame * frame_count
        seconds = estimate_total / 1000.0
        minutes = seconds / 60.0
        hours = minutes / 60.0
        core_hours = round(hours, 2)
        return core_hours


    def is_pass_for_env_item(self):
        '''
        This method returns the type of node, so subclasses with possibly
        a different item type string, can still be identified as a
        node with specific functionality.

        Returns:
            is_pass_for_env_item (bool):
        '''
        return True


    def get_environment_item(self):
        '''
        Get the environment item for this render pass for env item.

        Returns:
            environment_item (EnvironmentItem):
        '''
        return self.get_first_sibling()


    def get_identifier(
            self,
            nice_env_name=False,
            prefer_jid=True):
        '''
        Splice the environment and pass name into a
        single string, that will be unique for a single cell.
        TODO: Possibly include the index number or optional job identifier in index.
        Note: Currently these extra parts of the identifier are built and queried elsehwhere.

        Args:
            nice_env_name (bool):
            prefer_jid (str): prefer including the Job identifier in nice env name,
                otherwise use env index

        Returns:
            identifier (str):
        '''
        environment_item = self.get_environment_item()
        render_item = self.get_source_render_item()
        if all([environment_item, render_item]):
            if nice_env_name:
                environment_name = environment_item.get_environment_name_nice(
                    prefer_jid=prefer_jid)
            else:
                environment_name = environment_item.get_oz_area()
            item_full_name = render_item.get_item_full_name()
            identifier = environment_name + constants.IDENTIFIER_JOINER + item_full_name
            return constants.IDENTIFIER_JOINER.join([environment_name, item_full_name])
        return str()


    @classmethod
    def _update_renderable_count_for_index(
            cls,
            qmodelindex,
            renderable_offset=0,
            update_environment=True):
        '''
        Update the caching for a render pass for env item, given a
        QModelIndex that points to the item.

        Args:
            qmodelindex (QModelIndex):
            renderable_offset (int): number of renderabes to add or remove from cached value
            update_environment (bool):
        '''
        item = qmodelindex.internalPointer()
        model = qmodelindex.model()

        if item.is_pass_for_env_item():
            render_item = item.get_source_render_item()
            render_item._renderable_count_for_render_node += renderable_offset
            if render_item._renderable_count_for_render_node < 0:
                render_item._renderable_count_for_render_node = 0
            environment_item = item.get_environment_item()
        elif item.is_environment_item():
            environment_item = item
        else:
            return

        environment_item._renderable_count_for_env += renderable_offset
        if environment_item._renderable_count_for_env < 0:
            environment_item._renderable_count_for_env = 0

        # Optionally update column 0, EnvironmentItem styling after chaging renderable count.
        # Once EnvironmentItem has either 0 or 1 items, and
        # queued or enabled just modified, then update hint on column 0.
        if update_environment and environment_item._renderable_count_for_env in [0, 1]:
            qmodelindex_to_update = qmodelindex.sibling(qmodelindex.row(), 0)
            environment_item =  qmodelindex_to_update.internalPointer()
            has_renderables = bool(environment_item._renderable_count_for_env)
            # NOTE: Update to show environment is renderable hints
            model.environmentHasRenderables.emit(
                qmodelindex_to_update,
                has_renderables)


    ##########################################################################
    # Environment per pass overrides


    def resolve_frames(self, current_frame_only=False):
        '''
        Resolve frames for this render pass for env item.

        Args:
            current_frame_only (bool): ignore frame range overrides and only render current project frame

        Returns:
            pass_frameset (fileseq.FrameSet):
        '''
        # Reset cached frame counters for other external purposes
        self._resolved_frames_enabled = str()
        self._resolved_frames_enabled_count = 0
        self._resolved_frames_queued = str()
        self._resolved_frames_queued_count = 0

        enabled = self.get_active()

        # If not enabled then no frames are renderable
        if not enabled:
            return fileseq.FrameSet(str())

        pass_frame_override = self.get_frame_range_override()

        queued = self.get_queued()
        environment_item = self.get_environment_item()

        if not environment_item.is_environment_item():
            return

        production_frame_range = environment_item.get_production_frame_range()
        shot_frame_override = environment_item.get_frame_range_override()

        render_item = self.get_source_render_item()
        current_project_frame = render_item.get_current_project_frame()
        has_current_project_frame = isinstance(current_project_frame, (int, float))

        # Resolve frame rules
        pass_frameset = None
        if not current_frame_only or not has_current_project_frame:

            # Resolve environment frame overrides first
            frame_resolve_order_env_first = environment_item.get_frame_resolve_order_env_first()
            if frame_resolve_order_env_first:
                env_frameset = environment_item.resolve_frames()
                frame_range = pass_frame_override or str(env_frameset) or str()
            # Otherwise pass frame range overrides are resolved against
            # production range (ignoring environment overrides for now).
            else:
                try:
                    frame_range = pass_frame_override or shot_frame_override or production_frame_range or '1'
                    env_frameset = fileseq.FrameSet(frame_range)
                except Exception:
                    env_frameset = fileseq.FrameSet(list())
                frame_range = str(env_frameset)

            # The initial frame range to calulate pass frame overrides against
            try:
                frameset =  fileseq.FrameSet(frame_range)
            except fileseq.ParseException as error:
                frameset =  fileseq.FrameSet(list())

            # msg = 'Pass Frame Range To Resolve Rules Against: "{}".'.format(frameset)
            # self.logMessage.emit(msg, logging.WARNING)

            add_frame_sets = list()
            remove_frame_sets = list()

            frames_rule_important = self.get_frames_rule_important()
            if frames_rule_important:
                _frameset, success = self._resolve_rule(constants.OVERRIDE_FRAMES_IMPORTANT, frameset)
                if _frameset and success:
                    add_frame_sets.append(_frameset)

            frames_rule_fml = self.get_frames_rule_fml()
            if frames_rule_fml:
                _frameset, success = self._resolve_rule(constants.OVERRIDE_FRAMES_FML, frameset)
                if _frameset and success:
                    add_frame_sets.append(_frameset)

            frames_rule_x1 = self.get_frames_rule_x1()
            if frames_rule_x1:
                _frameset, success = self._resolve_rule(constants.OVERRIDE_FRAMES_X1, frameset)
                if _frameset and success:
                    add_frame_sets.append(_frameset)

            frames_rule_x10 = self.get_frames_rule_x10()
            if frames_rule_x10:
                _frameset, success = self._resolve_rule(constants.OVERRIDE_FRAMES_X10, frameset)
                if _frameset and success:
                    add_frame_sets.append(_frameset)

            frames_rule_xn = self.get_frames_rule_xn()
            if frames_rule_xn:
                _frameset, success = self._resolve_rule('x{}'.format(frames_rule_xn), frameset)
                if _frameset and success:
                    add_frame_sets.append(_frameset)

            not_frames_rule_important = self.get_not_frames_rule_important()
            if not_frames_rule_important:
                _frameset, success = self._resolve_rule(constants.OVERRIDE_FRAMES_NOT_IMPORTANT, frameset)
                if _frameset and success:
                    remove_frame_sets.append(_frameset)

            not_frames_rule_fml =  self.get_not_frames_rule_fml()
            if not_frames_rule_fml:
                _frameset, success = self._resolve_rule(constants.OVERRIDE_FRAMES_NOT_FML, frameset)
                if _frameset and success:
                    remove_frame_sets.append(_frameset)

            not_frames_rule_x10 =  self.get_not_frames_rule_x10()
            if not_frames_rule_x10:
                _frameset, success = self._resolve_rule(constants.OVERRIDE_FRAMES_NOT_X10, frameset)
                if _frameset and success:
                    remove_frame_sets.append(_frameset)

            not_frames_rule_xn = self.get_not_frames_rule_xn()
            if not_frames_rule_xn:
                _frameset, success = self._resolve_rule('NOT x{}'.format(not_frames_rule_xn), frameset)
                if _frameset and success:
                    remove_frame_sets.append(_frameset)

            if add_frame_sets:
                pass_frameset = fileseq.FrameSet(list())
                for _frameset in add_frame_sets:
                    pass_frameset = pass_frameset.union(_frameset)
            else:
                pass_frameset = frameset
            for _frameset in remove_frame_sets:
                pass_frameset = pass_frameset.difference(_frameset)

            # Now remove any pass explicit NOT custom frames
            not_frame_override = self.get_not_frame_range_override()
            if not_frame_override:
                try:
                    pass_frameset = pass_frameset.difference(fileseq.FrameSet(not_frame_override))
                except fileseq.ParseException as error:
                    pass

            # When resolving environment last, the pass frames must intersect resolved environment frames
            if not frame_resolve_order_env_first and pass_frameset:
                env_frameset = environment_item.resolve_frames()
                if env_frameset:
                    pass_frameset = env_frameset.intersection(pass_frameset)

        # Only render current host app project frame
        elif current_frame_only and has_current_project_frame:
            try:
                pass_frameset = fileseq.FrameSet(int(current_project_frame))
            except fileseq.ParseException as error:
                pass_frameset = None

        # msg = 'Pass Resolved FrameSet: "{}"'.format(pass_frameset)
        # self.logMessage.emit(msg, logging.WARNING)

        ######################################################################

        # Must now have valid frameset with frames
        if not pass_frameset:
            return None

        count = len(pass_frameset)
        frames_resolved_str = str(pass_frameset)
        self._resolved_frames_enabled = frames_resolved_str
        self._resolved_frames_enabled_count = count
        if queued:
            self._resolved_frames_queued = frames_resolved_str
            self._resolved_frames_queued_count = count
        return pass_frameset


    def get_resolved_frames_enabled(self):
        '''
        Get the total resolved frames string (but possibly not queued).

        Returns:
            frames_str (str):
        '''
        return self._resolved_frames_enabled


    def get_resolved_frames_count_enabled(self):
        '''
        Get the total number of enabled frames (but possibly not queued).

        Returns:
            frame_count (int):
        '''
        return self._resolved_frames_enabled_count


    def get_resolved_frames_queued(self):
        '''
        Get the total resolved frames string (but possibly not queued).

        Returns:
            frames_str (str):
        '''
        return self._resolved_frames_queued


    def get_resolved_frames_count_queued(self):
        '''
        Get the total number of queued and enabled frames.

        Returns:
            frame_count (int):
        '''
        return self._resolved_frames_queued_count



    def get_frame_range_tooltip(self, show_production_range=True):
        '''
        Get a frame range tooltip to represent the current resolved
        frames for this pass for env item, compared to approved frames.

        Args:
            show_production_range (bool):

        Returns:
            tooltip, range_issue (tuple):
        '''
        frames_str = self.get_resolved_frames_queued()
        if not frames_str:
            return str(), True

        range_issue = False
        environment_item = self.get_environment_item()

        msg = 'Resolved frames: <b>{}</b>. ' .format(frames_str)
        production_frame_range = environment_item.get_production_frame_range()
        in_production_range, custom_frame_count = environment_item.check_frame_range_in_custom_range(
            production_frame_range,
            frames_str)
        if in_production_range:
            fc = '<font color="#000000">'
        else:
            fc = '<font color="#FF0000">'
            range_issue = True
        msg += 'In chosen production range: '
        msg += '{}<b>{}</b></font>'.format(fc, in_production_range)
        if custom_frame_count:
            if custom_frame_count > constants.FRAME_COUNT_HIGH:
                fc = '<font color="#FF0000">'
                msg += '<br>Frame count is high: '
                msg += '{}<b>{}</b></font>. ' .format(fc, custom_frame_count)
                range_issue = True

        if show_production_range:
            msg += '<br>Chosen production range: <b>{}</b>. ' .format(production_frame_range)

        return msg, range_issue


    def resolve_version(
            self,
            version_system=None,
            source_project_version=None,
            cache_values=False,
            collapse_version_overrides=False):
        '''
        Resolve the version of the pass for env item on demand and cache the result.
        Note: Pass in explcit version system name to preview a different result.

        Args:
            version_system (str):
            source_project_version (int):
            cache_values (bool): whether to store the resolved cg version as private
                member on each render pass for env or not.
            collapse_version_overrides (bool): whether to collapse dynamic version overrides to explicit

        Returns:
            resolved_version_number (int):
        '''
        # Reset cached version data
        self._resolved_version_system = None
        self._resolved_version_number = None
        self._resolved_version_already_registered = False

        resolved_version_system = version_system or str(self._resolve_version_system())
        resolved_version_number = None
        ver_already_registered = False

        environment_item = self.get_environment_item()
        oz_area = environment_item.get_oz_area()
        render_item = self.get_source_render_item()
        pass_name = render_item.get_pass_name()

        project_version = source_project_version or render_item.get_current_project_version()
        has_project_version = isinstance(project_version, int) and bool(project_version)
        is_version_match_scene = resolved_version_system == constants.CG_VERSION_SYSTEM_MATCH_SCENE

        # Custom version is picked
        if resolved_version_system.isdigit():
            resolved_version_number = int(resolved_version_system)
            # Check if explicit version is already registered
            output_image_path, version_number, ver_already_registered = utils.compute_cg_output_path(
                pass_name,
                environment=oz_area,
                render_type='beauty',
                use_auto_cg_version=False,
                version=resolved_version_number)

        # Get the next highest version of this pass (for V+ and VP+).
        # NOTE: For VP+ external code applies the max version of shot to pass items.
        # NOTE: Global version isn't considered at this point.
        elif resolved_version_system in [
                constants.CG_VERSION_SYSTEM_PASSES_NEXT,
                constants.CG_VERSION_SYSTEM_PASS_NEXT] or not has_project_version:
            output_image_path, version_number, ver_already_registered = utils.compute_cg_output_path(
                pass_name,
                environment=oz_area,
                render_type='beauty',
                use_auto_cg_version=True)
            if version_number:
                resolved_version_number = int(version_number)

        # Use current project version for resolved cg version
        elif is_version_match_scene and has_project_version:
            resolved_version_number = int(project_version)
            # Check if explicit version is already registered
            output_image_path, version_number, ver_already_registered = utils.compute_cg_output_path(
                pass_name,
                environment=oz_area,
                render_type='beauty',
                use_auto_cg_version=False,
                version=resolved_version_number)
            if version_number:
                resolved_version_number = int(version_number)

        # Cache the resolved values as private members.
        # NOTE: The resolved version can be queried with get_resolved_version_number.
        if cache_values:
            self._resolved_version_number = resolved_version_number
            self._resolved_version_already_registered = bool(ver_already_registered)

        # NOTE: Collapse dynamic version overrides currently only happens just before generate jobs.
        # This might be deferred to dispatcher Job.
        if collapse_version_overrides:
            # If pass has dynamic version override (or inherits it),
            # then collapse to explicit version override during render submission.
            # NOTE: The original per pass version overrides are cached
            # and reverted during the multi shot render submission process.
            version_override = self.get_version_override()
            if not isinstance(version_override, int) and resolved_version_number:
                self.set_version_override(resolved_version_number)

        return resolved_version_number


    def _resolve_version_system(self):
        '''
        Only resolve the version system.

        Returns:
            version_system (str):
        '''
        environment_item = self.get_environment_item()
        root_item = environment_item.get_root_item()

        global_version = root_item.get_version_global_system()
        shot_version = environment_item.get_version_override()
        pass_version = self.get_version_override()

        resolved_version_system = pass_version or shot_version or global_version
        if resolved_version_system and isinstance(resolved_version_system, basestring):
            resolved_version_system = resolved_version_system.lstrip('v')

        self._resolved_version_system = resolved_version_system

        return self._resolved_version_system


    def get_resolved_version_number(self):
        '''
        Get the last resolved cg version number from cache (if any).
        NOTE: When submitting via multi_shot_render dynamic version overrides are
        temporarily collapsed to explicit cg version overrides. In which
        case get_version_override would return the same result during submission.

        Returns:
            version_number (int):
        '''
        return self._resolved_version_number


    def set_resolved_version_number(self, resolved_version_number):
        '''
        Cache resolved cg version number (if any).
        NOTE: When submitting via multi_shot_render dynamic version overrides are
        temporarily collapsed to explicit cg version overrides. In which
        case get_version_override would return the same result during submission.

        Args:
            version_number (int):
        '''
        self._resolved_version_number = resolved_version_number


    def get_resolved_version_system(self):
        '''
        Get the last resolved version system string (if any).
        Resolve version is called on demand, and this caches that result.

        Returns:
            resolved_version_system (str):
        '''
        resolved_version_system = str(self._resolved_version_system or str())
        if not resolved_version_system:
            return None
        elif resolved_version_system.isdigit():
            return int(resolved_version_system)
        elif resolved_version_system:
            resolved_version_system = resolved_version_system.lstrip('v')
        return resolved_version_system


    def get_resolved_version_already_registered(self):
        '''
        Get whether the last resolved version number has already been
        registered before (from previously cached value).

        Returns:
            resolved_version_already_registered (bool):
        '''
        return self._resolved_version_already_registered


    ##########################################################################
    # Render from single Render node


    def render_pass_for_env(
            self,
            oz_area=None,
            snapshot=None,
            job_name=str(),
            job_description=str(),
            global_job_identifier=None,
            **kwargs):
        '''
        Render a single Render node / pass, for this Environment.
        Note: Normally all passes for an environment are launched as a
        single job, this will create a Job with only one Pass to render.

        Args:
            oz_area (str):
            snapshot (str): optionally reuse an existing project snapshot for this submission,
                if it makes sense to do so.
                NOTE: This is intended to allow split jobs for various frame rules, for the same
                env and target pass versions.
            job_name (str):
            job_description (str):
            global_job_identifier (str): already included in job name

        Returns:
            success, collected_details_dict (tuple):
        '''
        environment_item = self.get_environment_item()
        if not environment_item:
            msg = 'Render Pass Has No Environment! Cannot Render!'
            return False, dict()

        # First perform any required setup on the render pass
        self.setup_render_pass_for_env(update_environment=True)

        return environment_item.render_passes_for_environment(
            oz_area=oz_area,
            pass_env_items=[self],
            snapshot=snapshot,
            job_name=job_name,
            job_description=job_description,
            global_job_identifier=global_job_identifier,
            update_environment=False) # Environment already updated in Pass setup


    def set_kenobi_render_node(self, node):
        '''
        Set the cached pointer to the Kenobi render node that is created during submission.
        Note: This pointer is automatically cleaned up after submission completes.
        TODO: Actually not cleaned up yet...

        Args:
            node (kenobi.base.Node): subclass of Kenobi base node
        '''
        identifier = self.get_identifier()
        msg = 'Setting Cached Kenobi Render Node For: "{}". '.format(identifier)
        msg += 'Node: "{}"'.format(node)
        self.logMessage.emit(msg, logging.WARNING)
        self._kenobi_render_node = node


    def get_kenobi_render_node(self):
        '''
        Get the cached pointer to the Kenobi render node that is created during submission.
        Note: This pointer is automatically cleaned up after submission completes.

        Returns:
            node (kenobi.base.Node): subclass of Kenobi base node
        '''
        return self._kenobi_render_node


    def clear_kenobi_render_node(self):
        '''
        Clear cached pointer to Kenobi render node that was created during submission.
        TODO: Call this after submission to clear temp pointer...
        '''
        self._kenobi_render_node = None


    def setup_render_pass_for_env(
            self,
            update_environment=True):
        '''
        Setup a single Render node / pass, for a paricular Environment.

        Args:
            update_environment (bool): optionally perform any update that
                prepares the environment for rendering all passes.

        Returns:
            success, msg (tuple):
        '''
        # Clear existing cached values
        self._time_to_setup_render = 0
        self._kenobi_render_node = None

        time_start = time.time()

        # Implement render setup / submission logic here

        self._time_to_setup_render = int(time.time() - time_start)

        msg = 'No Implemented Render Pass For Env '
        msg += 'Setup To Perform: "{}"'.format(self.get_identifier())
        self.logMessage.emit(msg, logging.WARNING)

        return True, msg


    def add_shotsub_tasks_to_graph(
            self,
            graph,
            hyref,
            resource_name=None,
            department='shots',
            session_path=str()):
        '''
        Add Shotsub Kenobi post task node/s for this render pass for env item.
        TODO: To be later moved to MultiShotJob object...

        Args:
            graph (kenobi.core.Graph): the Kenobi graph to create the shotsub node/s inside
            hyref (str): cg location to shotsub
            resource_name (str): optionally limit which shotsub task/s to add. otherwise
                all post task/s of "shotsub" type are added.
            department (str):
            session_path (str): path to session data to auto append to optional shotsub notes

        Returns:
            shotsub_nodes (list): list of kenobi.core.Shotsub
        '''
        render_item = self.get_source_render_item()
        render_node_name = render_item.get_node_name()
        identifier = self.get_identifier()
        post_tasks = self.get_post_tasks()
        is_anamorphic = render_item.get_other_attr('anamorphic')

        notes = self.get_note_override_submission() or self.get_note_override() or str()

        # Add automatically generated notes
        if session_path:
            notes += '<br>Autosave Path: <b>"{}"</b>'.format(session_path)

        if not post_tasks:
            msg = 'Pass identifier: "{}". '.format(identifier)
            msg += 'has no post tasks to add.'
            self.logMessage.emit(msg, logging.WARNING)
            return list()

        # Get hyref from location
        from srnd_multi_shot_render_submitter import utils
        hyref = str(hyref or str())
        if hyref and not hyref.startswith(('hyref:', 'urn:')) or os.path.isfile(hyref):
            hyref, msg = utils.get_hyref_for_location(hyref)
        if not hyref:
            msg = 'Must have registered hyref to add shotsub. '
            msg += 'Skipping adding shotsub for:  "{}"'.format(identifier)
            self.logMessage.emit(msg, logging.WARNING)
            return list()

        shotsub_nodes = list()
        for post_task_details in post_tasks:
            if post_task_details.get('type') != 'shotsub':
                continue
            _resource_name = post_task_details.get('name')

            # Optionally limit shotsub to certain resource name
            if resource_name and _resource_name != resource_name:
                continue

            if _resource_name == 'primary':
                _resource_name = 'beauty'

            if _resource_name:
                pass_description = '{}: {}'.format(render_node_name, _resource_name)
            else:
                pass_description = render_node_name

            resource_location, msg = utils.get_hyref_default_location(
                hyref,
                as_file_path=True,
                resource_name=_resource_name)

            msg = 'Shotsub resource to add to job graph: "{}". '.format(_resource_name)
            msg += 'Identifier: "{}". '.format(identifier)
            msg += 'Hyref: "{}". '.format(hyref)
            msg += 'Resource location: "{}". '.format(resource_location)
            msg += 'Notes: "{}". '.format(notes)
            self.logMessage.emit(msg, logging.INFO)

            shotsub_node = graph.createGraph('shotsub.BunkerGraph') # 'default.ShotsubNode')
            default_node_name = 'Shotsub_{}_{}'.format(render_node_name, _resource_name)
            shotsub_node.setName(default_node_name)

            # env = shotsub_node.createEnvironment()
            # env.setContext(film, tree, scene, shot)
            # env.setMods( ['bunker_kenobi-0.0.5'] )

            shotsub_node.findInput('sequence').setValue(resource_location)

            frames_str = str(self.get_resolved_frames_queued() or str())

            args_dict = dict()

            # SHOTRND-5261 - If resolved frames results in a very verbose frame string
            # that cannot be further simplified with FrameSet, then let the Shotsub node
            # get the frames from sequence on disk when the Task runs on Plow.
            # NOTE: This might be because the user used some complex frame skipping logic, and
            # split the render across two jobs. The in between frames might have already
            # been rendered in the other job. Therefore making the frames in file sequence
            # a continual set of frames, and making for a small frame string.
            # NOTE: Shotgun API has a limit of 255 characters for frame range string.
            # Otherwise this error would be raised: "value too long for type character varying(255)".
            # NOTE: The ticket SHOTRND-5262 will make this situation less likely by improving
            # how shotsub is performed across multiple jobs that target the same cg versions.
            if frames_str and len(frames_str) < 255:
                args_dict['framerange'] = frames_str
            else:
                msg = 'Shotsub framerange to long for Shotgun!. '
                msg += 'Will skip providing it for now, and will let this be '
                msg += 'resolved when task runs from files on disc....'
                self.logMessage.emit(msg, logging.WARNING)

            environment_item = self.get_environment_item()
            args_dict['oz_context'] = environment_item.get_oz_area()

            # Bunker supports both these arguments
            if pass_description:
                args_dict['description'] = str(pass_description)

            if notes and isinstance(notes, basestring):
                args_dict['notes'] = str(notes)

            if department and isinstance(department, str):
                args_dict['dept'] = str(department)

            if isinstance(is_anamorphic, bool):
                args_dict['anamorphic'] = bool(is_anamorphic)

            args_dict['force'] = True
            shotsub_node.findInput('args').setValue(args_dict)

            msg = 'Built Shotsub Node: "{}". '.format(shotsub_node)
            msg += 'With Extra Args: "{}"'.format(args_dict)
            self.logMessage.emit(msg, logging.INFO)

            shotsub_nodes.append(shotsub_node)

        return shotsub_nodes


    def add_denoise_tasks_to_graph(
            self,
            graph,
            hyref,
            preset_name=None):
        '''
        Add denoise post task/s for this render pass for env item.
        TODO: To be later moved to MultiShotJob object...

        Args:
            graph (kenobi.core.Graph): the Kenobi graph to create the shotsub node/s inside
            hyref (str): cg location to shotsub
            preset_name (str): optionally limit which denoise preset name/s to add. otherwise
                all post task/s of "denoise" type are added.

        Returns:
            denoise_graphs (list):
        '''
        render_item = self.get_source_render_item()
        render_node_name = render_item.get_node_name()
        identifier = self.get_identifier()
        post_tasks = self.get_post_tasks()

        if not post_tasks:
            msg = 'Pass Identifier: "{}". '.format(identifier)
            msg += 'Has No Denoise Post Task/s To Add!'
            self.logMessage.emit(msg, logging.WARNING)
            return list()

        # Get hyref from location
        from srnd_multi_shot_render_submitter import utils
        hyref = str(hyref or str())
        if hyref and not hyref.startswith(('hyref:', 'urn:')) or os.path.isfile(hyref):
            hyref, msg = utils.get_hyref_for_location(hyref)
        if not hyref:
            msg = 'Must Have Registered Hyref To Add Denoise Graph. '
            msg += 'Skipping Adding Denoise For:  "{}"'.format(identifier)
            self.logMessage.emit(msg, logging.WARNING)
            return list()

        is_stereo = utils.get_cg_version_is_stereo(hyref)

        # Get camera Hyref via MSRS render item (if implemented)
        cam_hyref = render_item.compute_camera_hyref()
        # Otherwise get camera Hyref from cginput resource
        cam_hyref = cam_hyref or utils.get_cg_version_camera_hyref(hyref) or None
        if cam_hyref:
            msg = 'Camera Hyref In Relation To Denoise: "{}"'.format(cam_hyref)
            self.logMessage.emit(msg, logging.INFO)

        environment_item = self.get_environment_item()
        oz_area = environment_item.get_oz_area()
        area = oz_area.replace('/', '_').lstrip('_')
        context_dict = environment_item.get_context()

        project = context_dict.get('FILM')
        tree = context_dict.get('TREE')
        scene = context_dict.get('SCENE')
        shot = context_dict.get('SHOT')

        from koba import database
        presets = database.get_denoise_presets(
            project=project,
            include_weta=True) or dict()
        if not presets:
            msg = 'No Denoise Presets For Project: "{}". '.format(project)
            msg += 'Skipping Adding Denoise For:  "{}"'.format(identifier)
            self.logMessage.emit(msg, logging.WARNING)
            return list()

        from koba.command_line import denoiser_k

        denoise_graphs = list()
        for post_task_details in post_tasks:
            if post_task_details.get('type') != 'denoise':
                continue
            _preset_name = post_task_details.get('name')
            # if not _preset_name:
            #     continue

            # Optionally limit denoise to certain preset name
            if preset_name and _preset_name != preset_name:
                continue

            msg = 'Denoise Preset Name To Add To Job Graph: "{}". '.format(_preset_name)
            msg += 'Identifier: "{}"'.format(identifier)
            self.logMessage.emit(msg, logging.INFO)

            # Prepare settings and call LaunchDenoiseProcess.execute
            # in same manner as koba.katana.denoise.launch.
            settings = list()
            if _preset_name in presets:
                preset_data = presets.get(_preset_name)
            else:
                preset_data = presets.get('default')
            if not preset_data:
                msg = 'No Denoise Settings Were Found Skipping: "{}". '.format(hyref)
                msg += 'Preset Name: "{}"'.format(_preset_name)
                self.logMessage.emit(msg, logging.WARNING)
                continue

            frames = self.get_resolved_frames_queued()
            try:
                frame_count = len(fileseq.FrameSet(frames))
            except Exception:
                frame_count = 0
            if frame_count <= 1:
                msg = 'Skipping Denoise! Requires More Frames! '
                msg += 'Preset Name: "{}"'.format(_preset_name)
                self.logMessage.emit(msg, logging.WARNING)
                continue

            preset_data['hyref'] = hyref
            preset_data['frames'] = frames
            settings.append(preset_data)

            msg = 'Denoise Settings: "{}"'.format(settings)
            self.logMessage.emit(msg, logging.WARNING)

            try:
                denoiser = denoiser_k.LaunchDenoiseProcess()
                denoiser.execute(
                    settings=settings,
                    cam_hyref=cam_hyref, # argument requires koba version >= 1.9.34
                    is_stereo=is_stereo, # argument requires koba version >= 1.9.34
                    chunk=1, # argument requires koba version >= 1.9.34
                    submit=False, # argument requires koba version >= 1.9.34
                    ignore_validation=True) # argument requires koba version >= 1.9.34
            except Exception:
                # Allow submission to continue if denoise setup fails, but log as issue
                denoiser = None
                msg = 'Failed to build or execute denoise setup task for project: "{}". '.format(project)
                msg += 'Full exception: "{}"'.format(traceback.format_exc())
                self.logMessage.emit(msg, logging.CRITICAL)
            if not denoiser:
                continue

            if not denoiser.graphs:
                msg = 'Failed to build any denoise kenobi graphs for project: "{}". '.format(project)
                msg += 'Preset name: "{}"'.format(_preset_name)
                self.logMessage.emit(msg, logging.WARNING)
                continue

            for denoise_graph in denoiser.graphs:
                graph_name = 'DenoiseGraph_{}_{}'.format(render_node_name, _preset_name)
                denoise_graph.setName(graph_name)
                denoise_graph.setParent(graph)
                if not denoise_graph.findInput('Wait'):
                    denoise_graph.createInput('Wait', str())
                denoise_graph.expand()
                for denoise_node in denoise_graph.nodes():
                    if not denoise_node.findInput('Wait'):
                        denoise_node.createInput('Wait', str())
                    denoise_graph.pi_Wait.connect(denoise_node.pi_Wait)
                    node_name = denoise_node.name()
                    node_name += '_{}_{}'.format(render_node_name, _preset_name)
                    denoise_node.setName(node_name)
                denoise_graphs.append(denoise_graph)

        return denoise_graphs


    def get_is_being_dispatched(self):
        '''
        Check if this render pass for env is currently being dispatched.

        Returns:
            is_being_dispatched (bool):
        '''
        return self._is_being_dispatched


    def set_is_being_dispatched(self, value):
        '''
        Set an indication that this render pass for env is currently being dispatched.

        Args:
            value (bool):
        '''
        value = bool(value)
        if self._debug_mode:
            identifier = self.get_identifier(nice_env_name=True)
            msg = 'Set Is Being Dispatched: "{}". To: "{}"'.format(identifier, value)
            self.logMessage.emit(msg, logging.WARNING)
        self._is_being_dispatched = value


    def get_render_progress(self):
        '''
        Get the last cached render progress from previously launched Plow Job
        for this render pass for env item.

        Returns:
            value (str):
        '''
        return self._render_progress


    def set_render_progress(self, value):
        '''
        Set the last cached render progress from previously launched Plow Job
        for this render pass for env item.

        Args:
            value (str):
        '''
        # if self._debug_mode:
        #     msg = '{}.set_render_progress(). '.format(self._node_type)
        #     msg += self._get_env_and_pass_name_message()
        #     msg += 'Value: {}'.format(value)
        #     self.logMessage.emit(msg, logging.DEBUG)
        self._render_progress = value


    def get_time_to_setup_render(self):
        '''
        Get the time it took to setup a single Render pass for an Environment.

        Returns:
            time_to_setup_render (int):
        '''
        return self._time_to_setup_render


##############################################################################


class RootMultiShotItem(base_tree_node.BaseTreeNode):
    '''
    The root MSRS data object that appears in MultiShotRenderModel.

    Args:
        version_global_system (str):
        show_full_environments (bool):
        debug_mode (bool): whether this abstract data emits message signals upstream
    '''

    logMessage = Signal(str, int)
    toggleProgressBarVisible = Signal(bool)
    updateLoadingBarFormat = Signal(int, str)

    def __init__(
            self,
            version_global_system=constants.DEFAULT_CG_VERSION_SYSTEM,
            show_full_environments=False,
            debug_mode=False,
            parent=None):
        super(RootMultiShotItem, self).__init__(
            node_type='RootMultiShotItem',
            expanding_model=False,
            debug_mode=debug_mode,
            parent=parent)

        self._version_global_system = version_global_system
        self._show_full_environments = show_full_environments


    def get_root_item(self):
        return self

    def is_group_item(self):
        return False


    def get_version_global_system(self):
        '''
        Get the global version system like "V+" or "VP+", or
        a particular custom version int.

        Returns:
            version_global_system (str): or int if custom version
        '''
        version_global_system = str(self._version_global_system).lstrip('v')
        if version_global_system.isdigit():
            return int(version_global_system)
        return version_global_system


    def set_version_global_system(self, version_global_system):
        '''
        Set any optional global description to describe the next
        Plow Job submission.

        Returns:
            version_global_system (str):
        '''
        version_global_system = str(version_global_system).lstrip('v')

        if not version_global_system:
            version_global_system = constants.DEFAULT_CG_VERSION_SYSTEM

        if version_global_system.isdigit():
            version_global_system =  int(version_global_system)
        elif version_global_system not in constants.CG_VERSION_SYSTEMS:
            version_global_system = constants.DEFAULT_CG_VERSION_SYSTEM

        # Value didn't actually change
        if version_global_system == self._version_global_system:
            return version_global_system

        if self._debug_mode:
            msg = 'Setting Global Version System For Next '
            msg += 'Submission To: {}'.format(version_global_system)
            self.logMessage.emit(msg, logging.DEBUG)

        self._version_global_system = version_global_system

        return version_global_system


    def set_show_full_environments(self, show_full_environments):
        '''
        Set show full environment or not.

        Args:
            show_full_environments (bool):
        '''
        self._show_full_environments = show_full_environments

        if self._debug_mode:
            msg = 'Setting Display Mode Show Full '
            msg += 'Environments To: {}'.format(show_full_environments)
            self.logMessage.emit(msg, logging.DEBUG)


    def get_show_full_environments(self):
        '''
        Get show full environment or not.

        Returns:
            show_full_environments (bool):
        '''
        return self._show_full_environments