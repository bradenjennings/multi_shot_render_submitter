

import logging
import os
import traceback


logging.basicConfig()
LOGGER = logging.getLogger('render_overrides_manager')
LOGGER.setLevel(logging.DEBUG)


##############################################################################


class RenderOverridesManager(object):
    '''
    A render overrides items manager to collect and operate on all
    render overrides for required host application.
    NOTE: Is a singleton so all plugins can be loaded and shared as needed.

    Args:
        cached (bool): whether to return the previously cached render override
                item plugins or check for plugins again
        from_env_var (str): optionally override where to look for MSRS render
            overrides for particular host app, by providing environment variable.
        plugin_paths (list): if environment variable not provided, optionally look
            in this explicit list of paths
    '''

    __instance = None

    def __new__(
            cls,
            cached=True,
            from_env_var=None,
            plugin_paths=None):
        if RenderOverridesManager.__instance is None:
            RenderOverridesManager.__instance = object.__new__(cls)
            RenderOverridesManager.__instance._render_overrides_items_cached = list()
            RenderOverridesManager.__instance._from_env_var = from_env_var
            RenderOverridesManager.__instance._plugin_paths = list(plugin_paths or list())
        else:
            if from_env_var:
                RenderOverridesManager.__instance._from_env_var = from_env_var
            if plugin_paths:
                RenderOverridesManager.__instance._plugin_paths = list(plugin_paths or list())
        RenderOverridesManager.__instance.load_render_overrides_plugins(cached=cached)
        return RenderOverridesManager.__instance


    def load_render_overrides_plugins(self, cached=True):
        '''
        Check the MSRS from environment variable or explicit plugin
        paths for render overrides items and load.

        Args:
            cached (bool): whether to return the previously cached render override
                item plugins or check for plugins again

        Returns:
            render_overrides_items (collections.OrderedDict):
        '''
        # Return the cached render override item plugins map (if available)
        if cached and self._render_overrides_items_cached:
            return self._render_overrides_items_cached

        import sys

        # msg = 'Starting Register All MSRS Render Override Plugins...\n'
        # msg += 'From Env Var: "{}"'.format(self._from_env_var)
        # if self._plugin_paths:
        #     msg += '. Plugin Paths: "{}"'.format(self._plugin_paths)
        # LOGGER.info(msg)

        # EXCLUDE_FILES = ['__init__', 'abstract_multi_shot_dispatcher']

        project = os.getenv('FILM')
        user = os.getenv('USER')

        # Only load plugins from this directory
        THIS_FOLDER = os.path.dirname(__file__)

        # Load plugins from plugin directory or from default MSRS directory, or this folder
        PLUGINS_DIRECTORIES = list()
        if self._from_env_var:
            from_env_var = os.getenv(
                self._from_env_var,
                os.getenv('MSRS_RENDER_OVERRIDES', THIS_FOLDER))
            PLUGINS_DIRECTORIES.extend(from_env_var.split(':'))

        # Add any explicit plugin paths
        if self._plugin_paths:
            PLUGINS_DIRECTORIES.extend(self._plugin_paths)

        plugins_dict = dict()
        for plugins_directory in PLUGINS_DIRECTORIES:
            # msg = '->Checking Plugins Directory: "{}"'.format(plugins_directory)
            # LOGGER.info(msg)
            sys.path.insert(0, plugins_directory)
            for file_name in os.listdir(plugins_directory):
                file_name_no_ext, ext = os.path.splitext(file_name)
                if not ext == '.py':
                    continue
                # if ext == '.py' and file_name_no_ext not in EXCLUDE_FILES:
                file_path = os.path.join(plugins_directory, file_name)
                try:
                    module = __import__(file_name_no_ext)
                except Exception:
                    # msg = 'Failed To Load Plugin! '
                    # msg += 'Full Exception: "{}".'.format(traceback.format_exc())
                    # LOGGER.warning(msg)
                    continue
                if not hasattr(module, 'register_plugin'):
                    continue
                class_object = module.register_plugin()
                if class_object.in_supported_host_app():
                    override_id = class_object.get_override_id()
                    intended_for_projects = class_object.get_intended_for_projects()
                    if intended_for_projects and project not in intended_for_projects:
                        # msg = '->Plugin Load Skip Not Intended For Project: "{}"'.format(override_id)
                        # LOGGER.info(msg)
                        continue
                    intended_for_users = class_object.get_intended_for_users()
                    if intended_for_users and user not in intended_for_users:
                        # msg = '->Plugin Load Skip Not Intended For User: "{}"'.format(override_id)
                        # LOGGER.info(msg)
                        continue
                    plugins_dict[override_id] = dict()
                    plugins_dict[override_id]['class_object'] = class_object
                    plugins_dict[override_id]['module_path'] = file_path

                    override_label = class_object.get_override_label()
                    plugins_dict[override_id]['label'] = override_label

                    category = class_object.get_override_category()
                    if category:
                        plugins_dict[override_id]['category'] = category

                    override_type = class_object.get_override_type()
                    plugins_dict[override_id]['type'] = override_type

                    override_description = class_object.get_override_description()
                    if override_description:
                        plugins_dict[override_id]['description'] = override_description

                    author = class_object.get_author()
                    if author:
                        plugins_dict[override_id]['author'] = author

                    author_department = class_object.get_author_department()
                    if author_department:
                        plugins_dict[override_id]['author_department'] = author_department

                    icon_path = class_object.get_override_icon_path()
                    if icon_path:
                        plugins_dict[override_id]['icon_path'] = icon_path

            sys.path.pop(0)

        self._render_overrides_items_cached = plugins_dict

        # msg = 'Registered All MSRS Render Overrides Items '
        # msg += 'Plugins: "{}"\n\n'.format(self._render_overrides_items_cached)
        # LOGGER.info(msg)

        return self._render_overrides_items_cached


    def get_render_overrides_plugins(self):
        '''
        Get the previously loaded and cached render overrides plugins.

        Returns:
            render_overrides_items (collections.OrderedDict):
        '''
        if not self._render_overrides_items_cached:
            self.load_render_overrides_plugins(cached=False)
        return self._render_overrides_items_cached


    def get_render_overrides_plugins_ids(self):
        '''
        Get a list of loaded render overrides plugins ids.

        Returns:
            render_overrides_plugins_ids (list): list of string ids
        '''
        if not self._render_overrides_items_cached:
            self.load_render_overrides_plugins(cached=False)
        return self._render_overrides_items_cached.keys()


    def get_render_overrides_plugins_by_category(self, category):
        '''
        Get the previously loaded and cached render overrides plugins.

        Returns:
            render_overrides_items (collections.OrderedDict):
        '''
        if not category:
            return
        if not self._render_overrides_items_cached:
            self.load_render_overrides_plugins(cached=False)
        category = str(category)
        render_overrides_items = list()
        for override_id in self._render_overrides_items_cached.keys():
            class_object = self._render_overrides_items_cached[override_id].get('class_object')
            _category = self._render_overrides_items_cached[override_id].get('category')
            if class_object and _category == category:
                render_overrides_items.append(class_object)
        return render_overrides_items


    def get_render_override_details_by_id(self, override_id):
        '''
        Get details about particular render override object by id string.

        Args:
            override_id (str):

        Returns:
            render_override_item_details (dict):
        '''
        if not override_id:
            return
        if not self._render_overrides_items_cached:
            self.load_render_overrides_plugins(cached=False)
        return self._render_overrides_items_cached.get(override_id)


    def get_render_override_object_by_id(self, override_id):
        '''
        Get particular render override object by id string.

        Args:
            override_id (str):

        Returns:
            render_override_object (RenderOverrideItem): the render override object in uninstantiated state
        '''
        render_override_item_details = self.get_render_override_details_by_id(override_id)
        if render_override_item_details:
            return render_override_item_details.get('class_object')