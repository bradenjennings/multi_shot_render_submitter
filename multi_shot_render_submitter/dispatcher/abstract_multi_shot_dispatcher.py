#!/usr/bin/env python


import abc
# import collections
import logging
import os
import re

from srnd_multi_shot_render_submitter import utils
from srnd_multi_shot_render_submitter.constants import Constants

constants = Constants()

logging.basicConfig()
LOGGER = logging.getLogger('dispatcher')
LOGGER.setLevel(logging.DEBUG)


##############################################################################


class AbstractMultiShotDispatcher(object):
    '''
    The core system to defer Multi Shot Job submission to a dispatching
    Job that runs on Plow. Each task of this constructed Job will be
    responsible for submitting one Environment.
    Note: Requires reimplementation and exposed as a dispatching plugin for a
    particular host app, via the env variable "SRND_MULTI_SHOT_DISPATCHER_PLUGINS".
    Note: This class may be instantiated to either initially build the deferred
    dispatcher Job for Plow. Or may be instantiated within a running
    dispatcher task on Plow, to build and execute a host app command.

    Args:
        session_location (str): file path or Hyref
        project (str): file path or hyref
        global_junk_box_id (str):
        tool_name (str):
        host_app (bool):
        debug_mode (bool):
    '''

    # The dispatcher system currently uses an Application
    # agnostic dispatching node.
    _NODE_PATH = 'srnd_multi_shot_render_submitter.nodes.'
    DISPATCHER_MODULE_PATH = str(_NODE_PATH) + 'MultiShotDispatcherNode'
    EMAIL_MODULE_PATH = str(_NODE_PATH) + 'MultiShotEmailNode'
    DISPATCHING_SERVICE_KEY = str()
    DISPATCHER_NAME = 'AbstractMultiShotDispatcher'

    __metaclass__ = abc.ABCMeta

    def __init__(
            self,
            session_location=None,
            project=None,
            global_junk_box_id=None,
            tool_name=None,
            host_app=None,
            debug_mode=False,
            **kwargs):
        super(AbstractMultiShotDispatcher, self).__init__()

        self.HOST_APP = host_app or constants.HOST_APP
        self.TOOL_NAME = tool_name or constants.TOOL_NAME

        self._session_location = session_location
        self._project = project
        self._global_junk_box_id = global_junk_box_id

        # Render targets
        self._environments_override = list()
        self._identifiers_override = list()
        self._render_nodes_override = list()

        # Global options
        self._global_shotsub_override = None
        self._global_job_identifier = str()
        self._global_note_override = str()
        self._auto_refresh_from_shotgun = True

        # Per render node options
        self._overrides_dict = dict()

        # Email details
        self._email_global_details = list()

        # Other
        self._multi_shot_render_submitter_version = 'srnd_multi_shot_render_submitter'
        self._host_app_version = str()
        self._use_current_env = False
        self._debug_mode = bool(debug_mode)

        # Tracking variables for Job setup and creation
        self._session = None
        self._graph = None
        self._plow_job_id = None
        self._environment_count = 0
        self._pass_counts_for_environments = dict()
        self._dispatcher_results = list()


    @classmethod
    def get_dispatcher_is_for_host_app(cls):
        '''
        Returns which app this dispatcher plugin is designed to be used with.

        Returns:
            host_app (str):
        '''
        return 'GEN'


    @classmethod
    def get_dispatcher_for_host_app(cls, host_app='GEN'):
        '''
        Get the required subclassed dispatcher object plugin for required host app.
        Choose the dispatcher algorithm strategically for host app.

        Args:
            host_app (str):

        Returns:
            dispatcher_object (AbstractMultiShotDispatcher): subclassed object
                for host app dispatching. exposed as a dispatcher plugin.
        '''
        plugin_info = SRND_MULTI_SHOT_DISPATCHER_PLUGINS.get(host_app.lower())
        if plugin_info:
            return plugin_info.get('class_object')


    @classmethod
    def get_dispatcher_instance_for_host_app(
            cls,
            host_app='GEN',
            debug_mode=False):
        '''
        Get the required subclassed dispatcher instance plugin for required host app.

        Args:
            host_app (str):
            debug_mode (bool):

        Returns:
            dispatcher_instance (AbstractMultiShotDispatcher): subclass instance
                for host app dispatching. exposed as a dispatcher plugin.
        '''
        dispatcher_object = AbstractMultiShotDispatcher.get_dispatcher_for_host_app(
            host_app)
        if dispatcher_object:
            return dispatcher_object(debug_mode=debug_mode)


    ##########################################################################
    # Job creation


    def _initialize_graph(
            self,
            use_current_env=False,
            run_local=False):
        '''
        Initialize the initial Job graph and session, before
        any nodes are added to it.

        Args:
            use_current_env (bool):
            run_local (bool):

        Returns:
            graph (kenobi.core.Graph):
        '''
        msg = 'Initialize Graph & Session For Multi Shot Submission'
        LOGGER.info(msg)

        # Clear any tracking variables from last submission
        self._session = None
        self._graph = None
        self._plow_job_id = None
        self._environment_count = 0

        from kenobi import core
        self._session = core.NodeFactory.sharedNodeFactory().createSession()
        self._session.setSessionType(core.SessionType.Plow)
        if use_current_env:
            self._session.setUseCurrentEnvironment(use_current_env)

        # Create graph
        self._graph = core.NodeFactory.sharedNodeFactory().createGraph()

        # kenobi_env = utils.apply_current_environment_to_graph(self._graph)

        if run_local:
            msg = 'Building Job For Local Submission'
            LOGGER.info(msg)
            self._graph.meta().setValueForKey('runLocal', True)

        return self._graph


    def create_dispatcher_job(self, submit=True):
        '''
        Build a Job containing N number of Environment/s to submit.
        Note: May be reimplemented by particular host app dispatcher if required,
        to specify more custom Job creation.
        Note: The initial expectation is this method does not need reimplementing
        for particular host app, it just creates the Agnostic node and sets required plugs.
        Note: Depending on the data setup for this object the Job Task names
        may include an expected pass counter or not.

        Args:
            submit (bool):

        Returns:
            submit, msg (tuple):
        '''
        # Must now have resolved environments to dispatch from
        if not self._environments_override:
            msg = 'NO RESOLVED ENVIRONMENT/S TO DISPATCH FROM!'
            LOGGER.critical(msg)
            return False, msg

        if not self._global_junk_box_id:
            from srnd_multi_shot_render_submitter import junkbox
            jbx = junkbox.JunkBox()
            self._global_junk_box_id = jbx.get_bucket_id_random()

        msg = 'CREATING DISPATCHER JOB FOR ENVIRONMENTS: "{}"'.format(self._environments_override)
        LOGGER.info(msg)

        ######################################################################

        # Extract session data from file path.
        multi_shot_data = dict()
        envs_data = list()
        if self._session_location:
            success, session_data = utils.extract_session_data(self._session_location)
            if not session_data:
                msg = 'Failed To Extract Session '
                msg += 'Data From: "{}". '.format(self._session_location)
                LOGGER.critical(msg)
                raise AttributeError(msg)
            multi_shot_data = session_data.get(
                constants.SESSION_KEY_MULTI_SHOT_DATA, dict())
            envs_data = multi_shot_data.get(
                constants.SESSION_KEY_ENVIRONMENTS, list())
            # Extract the global options if not already available from session data
            if not self._email_global_details and session_data:
                self._email_global_details = self.get_email_global_details_from_session_data(
                    session_data)

        ######################################################################
        # Formulate dispatcher Job name

        job_name_parts = ['{}MSRS'.format(self.HOST_APP.title())]
        # Include optional global job identifier in job name
        global_job_identifier = self.get_global_job_identifier()
        if global_job_identifier:
            global_job_identifier = global_job_identifier.replace(' ', str())
            job_name_parts.append(str(global_job_identifier))

        ######################################################################

        # Initialize graph and session (if not already available)
        if not all([self._session, self._graph]):
            self._initialize_graph(
                use_current_env=self._use_current_env)

        # Create a node to dispatch this environment
        email_node = self._graph.createNode(self.EMAIL_MODULE_PATH)

        msg = 'Setting Email Node Plug HostApp To: "{}". '.format(self.HOST_APP)
        msg += 'Type: "{}"'.format(type(self.HOST_APP))
        LOGGER.info(msg)
        email_node.findInput('HostApp').setValue(self.HOST_APP)

        multi_shot_version = self.get_multi_shot_render_submitter_version()
        msg = 'Setting Email Node '
        msg += 'Plug MultiShotSubmitterVersion To: "{}". '.format(multi_shot_version)
        msg += 'Type: "{}"'.format(type(multi_shot_version))
        LOGGER.info(msg)
        email_node.findInput('MultiShotSubmitterVersion').setValue(multi_shot_version)

        host_app_version = self.get_host_app_version()
        msg = 'Setting Email Node '
        msg += 'Plug HostAppVersion To: "{}". '.format(host_app_version)
        msg += 'Type: "{}"'.format(type(host_app_version))
        LOGGER.info(msg)
        email_node.findInput('HostAppVersion').setValue(host_app_version)

        self._debug_mode = bool(self._debug_mode)
        msg = 'Setting Email Node '
        msg += 'Plug DebugMode To: "{}". '.format(self._debug_mode)
        msg += 'Type: "{}"'.format(type(self._debug_mode))
        LOGGER.info(msg)
        email_node.findInput('DebugMode').setValue(self._debug_mode)

        global_junk_box_id = self.get_global_junk_box_id()
        msg = 'Setting Email Node '
        msg += 'Plug GlobalJunkBoxId To: "{}". '.format(global_junk_box_id)
        msg += 'Type: "{}"'.format(type(global_junk_box_id))
        LOGGER.info(msg)
        email_node.findInput('GlobalJunkBoxId').setValue(global_junk_box_id)

        msg = 'Setting Email Node '
        msg += 'Plug EmailGlobalDetails To: "{}". '.format(self._email_global_details)
        msg += 'Type: "{}"'.format(type(self._email_global_details))
        LOGGER.info(msg)
        email_node.findInput('EmailGlobalDetails').setValue(self._email_global_details)

        ######################################################################
        # Collect dispatcher Job attrs

        additional_job_attrs = dict()

        if self.HOST_APP:
            additional_job_attrs['host_app'] = str(self.HOST_APP)
        if host_app_version:
            additional_job_attrs['host_app_version'] = host_app_version
        if multi_shot_version:
            additional_job_attrs['submitter_pak_version'] = str(multi_shot_version)
        if self._project:
            additional_job_attrs['source_scene'] = str(self._project)
        if self._session_location:
            additional_job_attrs['session_path'] = str(self._session_location)
        if self._environments_override:
            additional_job_attrs['environments_to_dispatch'] = ', '.join(self._environments_override)
        if self._identifiers_override:
            additional_job_attrs['identifiers_override'] = ', '.join(self._identifiers_override)
        if self._render_nodes_override:
            additional_job_attrs['render_nodes_override'] = ', '.join(self._render_nodes_override)
        if self._global_note_override:
            additional_job_attrs['global_note_override'] = str(self._global_note_override)
        if self._global_job_identifier:
            additional_job_attrs['global_job_identifier'] = str(self._global_job_identifier)
        if self._global_junk_box_id:
            additional_job_attrs['global_junk_box_id'] = str(self._global_junk_box_id)
        if isinstance(self._global_shotsub_override, bool):
            additional_job_attrs['global_shotsub_identifier'] = bool(self._global_shotsub_override)

        ######################################################################

        import json
        import oz

        # Add a dispatcher task for each pre validated Environment
        self._environment_count = 0
        pass_count_all = 0
        # identifiers_to_dispatch = list()
        for environment in sorted(self._environments_override):
            # NOTE: This environment string may contain dash the job identifier or index number

            if not environment:
                msg = 'Invalid Null Environment For Submission: "{}". '.format(environment)
                msg += 'Type: "{}"'.format(type(environment))
                LOGGER.warning(msg)
                continue

            # Get the environment only (remove any index or optional job identifier)
            env_only = str(environment)
            if '-' in environment:
                env_only = environment.split('-')[0]

            # Validate the area is valid
            if not oz.Area.is_valid(env_only):
                msg = 'Environment Is Not Valid: "{}". Skipping Dispatch!'.format(env_only)
                LOGGER.warning(msg)
                continue

            # Get job identifier from overrides dict
            job_identifier = None
            env_info_dict = self._overrides_dict.get(environment)
            if env_info_dict and not job_identifier:
                job_identifier = env_info_dict.get(constants.SESSION_KEY_JOB_IDENTIFIER)

            identity_id = str()
            if env_info_dict:
                identity_id = env_info_dict.get('identity_id')

            # Otherwise get job identifier from session data
            env_data, env_index = (None, None)
            if envs_data:
                env_data, env_index = constants.get_env_data_from_envs_data(environment, envs_data)
                if not job_identifier and env_data:
                    job_identifier = env_data.get(constants.SESSION_KEY_JOB_IDENTIFIER)

            # Use pass count from all forced enabled render nodes
            pass_count = 0
            # Use cached pass count from earlier
            if self._pass_counts_for_environments:
                pass_count = self._pass_counts_for_environments.get(environment)
                # identifiers_to_dispatch.extend(self._identifiers_override)
            elif self._render_nodes_override or (env_data and isinstance(env_data, dict)):
                passes_data, node_names = (dict(), list())
                if self._render_nodes_override:
                    node_names = self._render_nodes_override
                elif env_data and isinstance(env_data, dict):
                    passes_data = env_data.get(constants.SESSION_KEY_PASSES, dict())
                    node_names = passes_data.keys()
                for node_name in node_names:
                    # Use session data to get if active to render or not.
                    # Otherwise all nodes as targets.
                    if passes_data and not self._render_nodes_override:
                        pass_data = passes_data.get(node_name)
                        if not pass_data:
                            continue
                        if not all([pass_data.get('enabled'), pass_data.get('queued')]):
                            continue
                    pass_count += 1

            # Must have pass count
            if not pass_count:
                msg = 'Renderable Count Is Unknown For Env: "{}". '.format(environment)
                msg += 'Must Specify Session Data Or Override '
                msg += 'The Render Nodes To Dispatch!'
                LOGGER.info(msg)
                continue

            msg = 'Building Dispatcher Task For Environment: "{}". '.format(environment)
            LOGGER.info(msg)

            # Create a node to dispatch this environment
            dispatcher_node = self._graph.createNode(self.DISPATCHER_MODULE_PATH)

            node_part_names = [environment[1:].replace('/', '_')]
            node_part_names.append('_'.join(job_name_parts))
            node_part_names.append('Dispatching')
            if job_identifier:
                node_part_names.append(str(job_identifier))
            if pass_count > 1:
                node_part_names.append('{}Passes'.format(pass_count))
            node_name = '_'.join(node_part_names)

            msg = 'Proposed Dispatcher Node Name Is: "{}"'.format(node_name)
            LOGGER.info(msg)

            dispatcher_node.setName(node_name)

            if self._project:
                msg = 'Setting dispatcher node plug: "{}". '.format(self._project)
                msg += 'Project to: "{}"'.format(type(self._project))
                LOGGER.info(msg)
                dispatcher_node.findInput('Project').setValue(self._project)

            if self._session_location:
                msg = 'Setting dispatcher node plug '
                msg += 'Session Location to: "{}". '.format(self._session_location)
                msg += 'Type: "{}"'.format(type(self._session_location))
                LOGGER.info(msg)
                dispatcher_node.findInput('Session').setValue(self._session_location)

            if environment:
                msg = 'Setting dispatcher node plug '
                msg += 'EnvironmentsToDispatchOverride to: "{}". '.format(environment)
                msg += 'Type: "{}"'.format(type(environment))
                LOGGER.info(msg)
                dispatcher_node.findInput('EnvironmentsToDispatchOverride').setValue(
                    [environment])

            if self._identifiers_override:
                msg = 'Setting dispatcher node plug '
                msg += 'PassForEnvIdentifiersOverride to: "{}". '.format(self._identifiers_override)
                msg += 'Type: "{}"'.format(type(self._identifiers_override))
                LOGGER.info(msg)
                dispatcher_node.findInput('PassForEnvIdentifiersOverride').setValue(
                    self._identifiers_override)

            if self._render_nodes_override:
                msg = 'Setting dispatcher node plug '
                msg += 'RenderNodesOverride to: "{}". '.format(self._render_nodes_override)
                msg += 'Type: "{}"'.format(type(self._render_nodes_override))
                LOGGER.info(msg)
                dispatcher_node.findInput('RenderNodesOverride').setValue(
                    self._render_nodes_override)

            if isinstance(self._global_shotsub_override, bool):
                msg = 'Setting dispatcher node plug '
                msg += 'GlobalShotsubOverride to: "{}". '.format(self._global_shotsub_override)
                msg += 'Type: "{}"'.format(type(self._global_shotsub_override))
                LOGGER.info(msg)
                dispatcher_node.findInput('GlobalShotsubOverride').setValue(
                    self._global_shotsub_override)

            if self._global_note_override:
                msg = 'Setting dispatcher node plug '
                msg += 'GlobalNoteOverride to: "{}". '.format(self._global_note_override)
                msg += 'Type: "{}"'.format(type(self._global_note_override))
                LOGGER.info(msg)
                dispatcher_node.findInput('GlobalNoteOverride').setValue(
                    self._global_note_override)

            if self._global_job_identifier:
                msg = 'Setting dispatcher node plug '
                msg += 'GlobalJobIdentifierOverride to: "{}". '.format(self._global_job_identifier)
                msg += 'Type: "{}"'.format(type(self._global_job_identifier))
                LOGGER.info(msg)
                dispatcher_node.findInput('GlobalJobIdentifierOverride').setValue(
                    self._global_job_identifier)

            if self._overrides_dict:
                msg = 'Setting dispatcher node plug '
                msg += 'OverridesDict to: "{}". '.format(self._overrides_dict)
                msg += 'Type: "{}"'.format(type(self._overrides_dict))
                LOGGER.info(msg)
                dispatcher_node.findInput('OverridesDict').setValue(
                    self._overrides_dict)

            if not self._auto_refresh_from_shotgun:
                skip_refresh_from_shotgun = True
                msg = 'Setting dispatcher node plug '
                msg += 'SkipRefreshProductionData to: "{}". '.format(skip_refresh_from_shotgun)
                msg += 'Type: "{}"'.format(type(skip_refresh_from_shotgun))
                LOGGER.info(msg)
                dispatcher_node.findInput('SkipRefreshProductionData').setValue(
                    skip_refresh_from_shotgun)

            dispatcher_node.findInput('HostApp').setValue(self.HOST_APP)
            dispatcher_node.findInput('DebugMode').setValue(bool(self._debug_mode))

            global_junk_box_id = self.get_global_junk_box_id()
            msg = 'Setting dispatcher node plug '
            msg += 'GlobalJunkBoxId to: "{}". '.format(global_junk_box_id)
            msg += 'Type: "{}"'.format(type(global_junk_box_id))
            LOGGER.info(msg)
            dispatcher_node.findInput('GlobalJunkBoxId').setValue(global_junk_box_id)

            meta = dispatcher_node.meta()
            if self.DISPATCHING_SERVICE_KEY:
                meta.setValueForKey('plowLayerService', str(self.DISPATCHING_SERVICE_KEY))
            _node_name = dispatcher_node.name()
            meta.setValueForKey('plowLayer', str(_node_name))

            additional_job_attrs['environments_to_dispatch'] = str(environment)

            if additional_job_attrs:
                meta.setValueForKey(
                    'plowLayerAttributes',
                    json.dumps(additional_job_attrs))

            self._environment_count += 1
            pass_count_all += pass_count

            dispatcher_node.po_DispatchResults.connect(email_node.pi_DispatchResults)

        # Must have environments to dispatch
        if not self._environment_count:
            msg = 'No environments to dispatch!'
            LOGGER.info(msg)
            return False, msg

        ######################################################################

        job_name_parts.append('Dispatching')
        if pass_count_all > 1:
            job_name_parts.append('{}Passes'.format(pass_count_all))
        if self._environment_count > 1:
            job_name_parts.append('For')
            job_name_parts.append('{}Environments'.format(self._environment_count))
        job_name = '_'.join(job_name_parts)
        job_name = job_name.replace('"', str()).replace("'", str())

        global_job_identifier = self.get_global_job_identifier()
        if global_job_identifier and isinstance(global_job_identifier, basestring):
            display_name = str(global_job_identifier)
        else:
            display_name = None

        msg = 'Proposed dispatcher job name is: "{}"'.format(job_name)
        LOGGER.info(msg)

        attrs, job_name = self.set_job_attrs(
            job_name=job_name,
            display_name=display_name,
            oz_area=os.getenv('OZ_CONTEXT'),
            additional_job_attrs=additional_job_attrs)

        ######################################################################

        msg = str()

        if submit:
            plow_job_id = self.submit_dispatcher_job()
            msg = 'Dispatched {} Environments & '.format(self._environment_count)
            msg += '{} Passes. Plow Job Id: "{}". '.format(pass_count_all, plow_job_id)
            LOGGER.info(msg)

        return True, msg


    def set_job_attrs(
            self,
            job_name=None,
            display_name=None,
            oz_area=os.getenv('OZ_CONTEXT'),
            additional_job_attrs=dict()):
        '''
        Set the Plow Job attributes for the dispatcher task.

        Args:
            job_name (str):
            display_name (str):
            oz_area (str):
            additional_job_attrs (dict): additional attrs to add to "managerJobAttributes"

        Returns:
            attrs, job_name (tuple):
        '''
        if not self._graph:
            msg = 'No Job Graph Available To Set Job Attributes For!'
            LOGGER.critical(msg)
            return False

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
            msg = 'Existing Dispatcher Job Attributes: "{}". '.format(attrs)
            msg += 'Type: "{}"'.format(type(attrs))
            LOGGER.critical(msg)

        # NOTE: All dispatcher tasks should get fastFrame priority
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
            attrs_to_update['displayName'] = str(display_name)
        elif job_name and isinstance(job_name, basestring):
            attrs_to_update['displayName'] = str(job_name)

        # Details about where dispatcher Job started
        user = os.getenv('USER')
        if user:
            attrs_to_update['dispatched_by_user'] = user
        host = os.getenv('HOST')
        if host:
            attrs_to_update['dispatched_by_host'] = host

        attrs.update(attrs_to_update)

        # Add Oz exact (if possible)
        import oz
        try:
            oz_exact = {'oz_exact': str(oz.Oz.from_env())}
            attrs.update(oz_exact)
        except oz.NotOzzedError:
            pass

        if additional_job_attrs:
            attrs.update(additional_job_attrs)

        # attrs_clean = dict()
        # for key, value in attrs.iteritems():
        #     attrs_clean[str(key)] = str(value)

        self._graph.meta().setValueForKey(
            'managerJobAttributes',
            json.dumps(attrs))
        self._graph.meta().setValueForKey('plowQuickLaunch', True)

        msg = 'Updated "managerJobAttributes" To: "{}"'.format(attrs)
        LOGGER.info(msg)

        if job_name and isinstance(job_name, basestring):
            job_name = str(job_name)
            self._graph.meta().setValueForKey('managerJobTitle', job_name)
            if self._session:
                self._session.setJobName(job_name)

        # self._graph.meta().setValueForKey('managerJobStatsKey', stats_key)

        return attrs, job_name


    def submit_dispatcher_job(self):
        '''
        Submit the dispatcher job now.

        Returns:
            plow_job_id (str):
        '''
        if not self._environment_count:
            msg = 'No Environments To Dispatch!'
            LOGGER.critical(msg)
            raise AttributeError(msg)

        if not all([self._graph, self._session]):
            msg = 'Must First Initialize The Job Graph And Session!'
            LOGGER.critical(msg)
            raise RuntimeError(msg)

        self._session.start(self._graph)
        self._plow_job_id = self._session.graph().meta().valueForKey('plowJobId')

        return self._plow_job_id


    def create_dispatcher_job_from_command_line(
            self,
            args_to_parse,
            host_app='GEN',
            host_app_version=None):
        '''
        Create a dispatcher job on Plow from the incoming command line arguments.

        Args:
            args_to_parse (list):
            host_app (str):
            host_app_version (str): optionally pass a sting identifier with the name
                of the host app version

        Returns:
            success, msg (bool):
        '''
        msg = 'PARSING COMMAND LINE ARGUMENTS:\n"{}"\n'.format(args_to_parse)
        LOGGER.warning(msg)

        # Build the generic command line interface (with additional non ui arguments) and parse
        from srnd_multi_shot_render_submitter.command_line import MultiShotRenderCommandLine
        multi_shot_command_line = MultiShotRenderCommandLine(host_app=host_app)
        parser, options_dict = multi_shot_command_line.build_command_line_interface(
            args_to_parse=args_to_parse,
            is_ui_context=False)

        ######################################################################

        msg = 'SETTING DISPATCHER OPTIONS FROM COLLECTED OPTIONS!'
        LOGGER.warning(msg)

        project = options_dict.get('project')
        session_location = options_dict.get('session')

        # Targets overrides
        environments_override = options_dict.get('environments')
        identifiers_override = options_dict.get('pass_for_env_identifiers_override')
        render_nodes_override = options_dict.get('render_nodes_override')

        # Global overrides
        global_shotsub_override = options_dict.get('global_shotsub_override', None)
        global_job_identifier = options_dict.get('global_job_identifier')
        global_note_override = options_dict.get('global_note_override')

        overrides_dict = self.resolve_per_render_node_overrides(options_dict)
        if overrides_dict:
            self.set_overrides_dict(overrides_dict)

        if project:
            self.set_project(project)

        if session_location:
            self.set_session_location(session_location)

        if environments_override:
            self.set_environments_override(environments_override)

        if identifiers_override:
            self.set_pass_for_env_identifiers_override(identifiers_override)

        if render_nodes_override:
            self.set_render_nodes_override(render_nodes_override)

        if global_job_identifier:
            self.set_global_job_identifier(global_job_identifier)

        if global_note_override:
            self.set_global_note_override(global_note_override)

        if isinstance(global_shotsub_override, bool):
            self.set_global_shotsub_override(global_shotsub_override)

        if host_app_version:
            self.set_host_app_version(host_app_version)

        multi_shot_version = utils.get_render_submitter_version(host_app=host_app)
        if multi_shot_version:
            self.set_multi_shot_render_submitter_version(multi_shot_version)

        ######################################################################

        msg = 'FINISHED SETTING DISPATCHER OPTIONS FROM COLLECTED OPTIONS!\n\n'
        LOGGER.warning(msg)

        # Now based on specified session or session of project, do final
        # resolve of all dispatcher options.
        self.validate_and_resolve_targets_in_session_data(session_location)

        ######################################################################

        # Optionally only list resolved values then exit
        show_validation_only = options_dict.get('show_validation_only')
        if show_validation_only:
            return False, msg

        ######################################################################

        # Build and submit the dispatcher job
        success, msg = self.create_dispatcher_job(submit=True)
        plow_job_id = self.get_plow_job_id_last_dispatched()

        msg = 'Create Dispatch Job Result: "{}". '.format(success)
        msg += 'Message: "{}". '.format(msg)
        msg += 'Plow Job Id: "{}". '.format(plow_job_id)
        LOGGER.info(msg)

        return success, msg


    @classmethod
    def resolve_per_render_node_overrides(cls, options_dict=None):
        '''
        Build overrides dict from options dict that pertain to per item overrides.

        Args:
            options_dict (dict): formulated for command line results.
                Note: only as subset of keys and values are actually render node overrides.

        Returns:
            overrides_dict (dict):
        '''
        if not options_dict:
            options_dict = dict() # collections.OrderedDict()

        frames_override = options_dict.get('frames_override', dict())
        version_override = options_dict.get('version_override', dict())
        shotsub_override = options_dict.get('shotsub_override', dict())
        note_override = options_dict.get('note_override', dict())
        job_identifier_override = options_dict.get('job_identifier_override', dict())

        from srnd_multi_shot_render_submitter.command_line import MultiShotRenderCommandLine

        overrides_dict = dict()

        for key, value in frames_override:
            if not MultiShotRenderCommandLine.validate_environment(key):
                msg = 'Environment Of Frames Override NOT Valid To Dispatch From: "{}"'.format(key)
                LOGGER.warning(msg)
                continue
            if key not in overrides_dict:
                overrides_dict[key] = dict()
            overrides_dict[key]['frame_range_override'] = value

        for key, value in version_override:
            if not MultiShotRenderCommandLine.validate_environment(key):
                msg = 'Environment Of Version Override NOT Valid To Dispatch From: "{}"'.format(key)
                LOGGER.warning(msg)
                continue
            if key not in overrides_dict:
                overrides_dict[key] = dict()
            overrides_dict[key]['version_override'] = value

        for key, value in shotsub_override:
            if not MultiShotRenderCommandLine.validate_environment(key):
                msg = 'Environment Of Shotsub Override NOT Valid To Dispatch From: "{}"'.format(key)
                LOGGER.warning(msg)
                continue
            if not value:
                continue
            if key not in overrides_dict:
                overrides_dict[key] = dict()
            post_task_details = dict()
            post_task_details['name'] = str(value)
            post_task_details['type'] = 'shotsub'
            overrides_dict[key]['post_tasks'] = post_task_details

        for sub_list in note_override:
            if not sub_list or not isinstance(sub_list, (list, tuple)):
                continue
            if len(sub_list) < 2:
                continue
            key = sub_list[0]
            if not MultiShotRenderCommandLine.validate_environment(key):
                msg = 'Environment Of Note Override NOT Valid To Dispatch From: "{}"'.format(key)
                LOGGER.warning(msg)
                continue
            # Join together all substring specified as separate nargs
            if len(sub_list) > 2:
                value = ' '.join(sub_list[1::])
            else:
                value = sub_list[-1]
            if key not in overrides_dict:
                overrides_dict[key] = dict()
            overrides_dict[key]['note_override'] = value

        for key, value in job_identifier_override:
            if constants.IDENTIFIER_JOINER in key:
                msg = 'Job Identifiers Can Only Be Specified For Environments! '
                msg += 'Skipping: "{}"'.format(key)
                LOGGER.warning(key)
                continue
            if not MultiShotRenderCommandLine.validate_environment(key):
                msg = 'Environment Of Job Identifier Override NOT Valid To Dispatch From: "{}"'.format(key)
                LOGGER.warning(msg)
                continue
            if key not in overrides_dict:
                overrides_dict[key] = dict()
            overrides_dict[key][constants.SESSION_KEY_JOB_IDENTIFIER] = value

        msg = 'Formulated Resolved Per Render Node Overrides:\n{}'.format(overrides_dict)
        LOGGER.info(msg)

        return overrides_dict


    ##########################################################################
    # Methods for when dispatcher is now running on Plow, and before host app opens


    @abc.abstractmethod
    def get_dispatch_command_for_host_app(self):
        '''
        Get a command which launches a host app and loads the session
        data, and then submits a Job to render Environment/s.
        Note: This is typically called from MultiShotDispatcherNode task on Plow.
        Note: Must be reimplemented to override abstract base interface.

        Returns:
            command_list (list):
        '''
        msg = 'GEN Multi Shot Render Submitter Cannot Build '
        msg += 'Deferred Dispatching Commands! '
        msg += 'No Host App Implementation Is Available!'
        raise NotImplementedError(msg)


    def get_gen_dispatch_command(self):
        '''
        Get a GEN dispatching command.
        Note: The shell command itself (arg 0), needs replacing
        with host app specific dispatcher.
        Note: Some per render node overrides in command line submission should
        be instead provided to MultiShotDispatcherNode via OverridesDict plug.
        '''
        command_list = ['srnd_multi_shot_render_submitterCL']

        if self._session_location and \
                isinstance(self._session_location, basestring):
            command_list.extend([
                '-session',
                '"{}"'.format(self._session_location)])

        if self._project and isinstance(self._project, basestring):
            # Add the project file path to command line (not hyref)
            project, msg = utils.get_hyref_default_location(
                self._project) or self._project
            command_list.extend([
                '-project',
                '"{}"'.format(project)])

        if self._global_junk_box_id and isinstance(self._global_junk_box_id, basestring):
            command_list.extend(['-globalJbxBucket', self._global_junk_box_id])

        # Provide all the targets via multi arguments

        if self._environments_override:
            command_list.append('-environments')
            command_list.extend(self._environments_override)

        if self._identifiers_override:
            command_list.append('-passForEnvIdentifiersOverride')
            command_list.extend(self._identifiers_override)

        if self._render_nodes_override:
            command_list.append('-renderNodesOverride')
            command_list.extend(self._render_nodes_override)

        if isinstance(self._global_shotsub_override, bool):
            command_list.extend([
                '-globalShotsubOverride',
                '"{}"'.format(int(self._global_shotsub_override))])

        if self._global_job_identifier and \
                isinstance(self._global_job_identifier, basestring):
            command_list.extend([
                '-globalJobIdentifierOverride',
                '"{}"'.format(self._global_job_identifier)])

        if self._global_note_override and \
                isinstance(self._global_note_override, basestring):
            command_list.extend([
                '-globalNoteOverride',
                '"{}"'.format(self._global_note_override)])

        if not self._auto_refresh_from_shotgun:
            command_list.append('--skipRefreshProductionData')

        if self._debug_mode:
            command_list.append('--debug')

        return command_list


    def dispatch(self):
        '''
        Start a submission for the currently desired session data,
        Environment/s and Render Node/s.
        Note: Calling dispatch will internally build the host app command, start
        the host app, load the session data, and do the submission.
        Note: This is typically called from MultiShotDispatcherNode task on Plow.
        Note: Must be reimplemented to override abstract base interface.

        Returns:
            return_code, dispatcher_results (tuple): bool and dict of dispatcher results
        '''
        self._dispatcher_results = list()

        dispatch_command = self.get_dispatch_command_for_host_app()

        # Check the required Multi Shot command for host app exists in environment
        command_exists = utils.check_shell_command_exists(dispatch_command[0])
        if not command_exists:
            msg = 'Command Not Available: {}. '.format(dispatch_command[0])
            LOGGER.info(msg)
            return

        # Get a JunkBox bucket id, to store dispatch results.
        from srnd_multi_shot_render_submitter import junkbox
        jbx = junkbox.JunkBox()
        bid = jbx.get_bucket_id_random()

        # Store the overrides dict in junkbox to be extracted in host app
        success = jbx.put_junkbox_data(
            bid,
            'overrides_dict',
            self._overrides_dict)

        dispatch_command.extend(['-jbxBucket', '"{}"'.format(bid)])

        command_str = ' '.join([str(arg) for arg in dispatch_command])
        msg = 'Formulated MSRS Dispatch Command: "{}". '.format(command_str)
        LOGGER.info(msg)

        msg = 'Command Argument List: "{}". '.format(dispatch_command)
        LOGGER.info(msg)

        return_code = utils.execute_shell_cmd(dispatch_command)
        print('Return Code: {}'.format(return_code))

        # Don't return dispatch results if return code is not 0
        if return_code != 0:
            msg = 'Process Failed With Return Code: "{}". '.format(return_code)
            msg += 'Command: "{}". '.format(dispatch_command)
            LOGGER.critical(msg)
            return return_code, list()

        # Extract the dispatch result from JunkBox key.
        self._dispatcher_results = jbx.get_junkbox_data(
            bid,
            jbx.DISPATCHER_JUNKBOX_KEY)

        return return_code, self._dispatcher_results


    def get_dispatcher_results(self):
        '''
        Get the dispatcher results, a list of dispatched
        Environment/s info dict/s.

        Returns:
            dispatcher_results (list):
        '''
        return self._dispatcher_results


    ##########################################################################
    # Session data


    def validate_and_resolve_targets_in_session_data(self, session_location=None):
        '''
        Resolve various options such as Environment/s to submit based
        on session data and any other provided Node override arguments.

        Args:
            session_location (str): file path or Hyref

        Returns:
            success (bool):
        '''
        msg = 'RESOLVING AND VALIDATING FINAL OPTIONS FOR SESSION DATA'
        LOGGER.info(msg)

        session_location = session_location or self._session_location

        # If session not specified, then try to get the session of project here.
        if not session_location and self._project:
            resource = utils.get_session_data_resource_of_project(self._project)
            if resource:
                session_location = resource.location
                msg = 'Derived Session Location From Project: "{}"'.format(session_location)
                LOGGER.info(msg)
                self.set_session_location(session_location)

        # Extract session data from session path now
        msg = 'Extracting Session Data From: "{}"'.format(session_location)
        LOGGER.info(msg)
        successs, session_data = utils.extract_session_data(session_location)

        # Derive project from session data (if not set)
        if not self._project:
            project = session_data.get('project')
            # Cast the project to filepath, if specified as hyref in session data
            if project and project.startswith(('hyref:', 'urn:')):
                project, msg = utils.get_hyref_default_location(
                    project,
                    as_file_path=True)
            if project:
                self._project = project
            msg = 'Derived project from session data: "{}". '.format(self._project)
            LOGGER.info(msg)

        done_msg = 'FINISHED RESOLVING AND VALIDATING FINAL OPTIONS FOR SESSION DATA\n\n'

        # TODO: Now validate all the target environments and pass for environment identifiers
        # against data in session data. To avoid creating more Plow tasks than required to submit Job.
        if not session_data:
            LOGGER.info(done_msg)
            return True

        ######################################################################

        multi_shot_data = session_data.get(constants.SESSION_KEY_MULTI_SHOT_DATA, dict())
        envs_data = multi_shot_data.get(constants.SESSION_KEY_ENVIRONMENTS, list())

        # Session has environments data, to check for renderable items
        if not envs_data:
            LOGGER.info(done_msg)
            return True

        msg = 'Looking In Session Data To Validate All Render Pass For Env Are Valid...'
        LOGGER.info(msg)

        environments_counter = dict()
        environments_resolved = set()
        identifiers_resolved = set()
        render_nodes_resolved = set()
        self._pass_counts_for_environments = dict()

        # Traverse all session data environments and validate all overrides are relevant.
        # NOTE: Filter out any overrides not valid for session data.
        for i, shot_data in enumerate(envs_data):
            # Must have shot / environment key
            environment = shot_data.get('environment')
            if not environment:
                continue

            # Count the number of times this environment has appeared
            if environment not in environments_counter.keys():
                environments_counter[environment] = 0
            environments_counter[environment] += 1

            # Get alternative string representations of this environment name
            env_index = environments_counter[environment]
            job_identifier = shot_data.get(constants.SESSION_KEY_JOB_IDENTIFIER)
            if job_identifier:
                env_nice_name = environment + '-' + str(job_identifier)
            else:
                env_nice_name = environment + '-' + str(env_index)

            # If explicit environment overrides specified then check if matches current session data environment.
            # NOTE: These environment overrides might be provided by the command line, and could include
            # the job identifier or environment index as part of the string.
            environment_found = True
            if self._environments_override:
                environment_found = environment in self._environments_override
                # Check if this session environment matches an alternative string representation in overrides
                if not environment_found and job_identifier:
                    _env_nice_name = environment + '-' + job_identifier
                    environment_found = _env_nice_name in self._environments_override
                if not environment_found:
                    _env_nice_name = environment + '-' + str(env_index)
                    environment_found = _env_nice_name in self._environments_override
                if environment_found:
                    # All specified environments should be rendered in the same proc
                    environments_resolved.add(environment)
                    # # NOTE: This would dispatch each same env in different procs
                    # environments_resolved.add(env_nice_name)

            msg = '->Looking At Session Data Environment: "{}". '.format(environment)
            msg = '->Nice Env Name Is: "{}". '.format(env_nice_name)
            if job_identifier:
                msg += 'Has Job Identifier: "{}". '.format(job_identifier)
            msg += 'Index: "{}"'.format(env_index)
            LOGGER.info(msg)

            item_full_names = shot_data.get(constants.SESSION_KEY_PASSES, dict()).keys()
            pass_count = len(item_full_names)

            # Count Queued and Enabled according to current session data.
            active_count = 0
            for item_full_name in item_full_names:
                pass_data = shot_data.get(constants.SESSION_KEY_PASSES, dict()).get(item_full_name)
                if not pass_data:
                    continue

                # Must be queued and enabled to count as renderable
                renderable = all([pass_data.get('enabled'), pass_data.get('queued')])

                # If identifiers override specified then check this identifier is in session data
                if self._identifiers_override:
                    identifier_found, identifier_nice_name = self.check_identifier_in_identifers(
                        environment, # raw environment name (without index or job identifier)
                        item_full_name, # the node / pass name to check in identifiers override
                        env_index=env_index, # the index of the environment to check if in identifiers override
                        job_identifier=job_identifier)
                    # Also cache the pass counts for the environment
                    if environment not in self._pass_counts_for_environments.keys():
                        self._pass_counts_for_environments[environment] = 0
                    # Specified identifier override matches current session data item
                    if identifier_found:
                        identifiers_resolved.add(identifier_nice_name)
                        # If no environment override specified then add env now, related to pass for env
                        if not self._environments_override:
                            environments_resolved.add(environment)
                        # Found another pass to dispatch for this environment
                        self._pass_counts_for_environments[environment] += 1
                # No identifier overrides specified, however pass is renderable according to session data
                elif renderable:
                    if environment not in self._pass_counts_for_environments.keys():
                        self._pass_counts_for_environments[environment] = 0
                    self._pass_counts_for_environments[environment] += 1
                    # If no environment override specified then add env now, related to pass for env
                    if not self._environments_override:
                        environments_resolved.add(environment)
                # Keep track of total renderable count
                if renderable:
                    active_count += 1

            msg = '->Environment Has {} Passes ({} Was Active)'.format(pass_count, active_count)
            LOGGER.info(msg)

            # Validate specified render nodes available in session data
            if self._render_nodes_override:
                render_node_names = multi_shot_data.get(constants.SESSION_KEY_RENDER_NODES, dict()).keys()
                for name in render_node_names:
                    if name in self._render_nodes_override:
                        render_nodes_resolved.add(name)

        environments_not_found = set(self._environments_override).difference(set(environments_resolved))
        if environments_not_found:
            msg = '->SOME ENVIRONMENTS NOT FOUND DURING SESSION CHECK: "{}"'.format(environments_not_found)
            LOGGER.warning(msg)

        identifiers_not_found = set(self._identifiers_override).difference(set(identifiers_resolved))
        if identifiers_not_found:
            msg = '->SOME IDENTIFIERS NOT FOUND DURING SESSION CHECK: "{}"'.format(identifiers_not_found)
            LOGGER.warning(msg)

        render_nodes_not_found = set(self._render_nodes_override).difference(set(render_nodes_resolved))
        if render_nodes_not_found:
            msg = '->SOME RENDER NODES NOT FOUND DURING SESSION CHECK: "{}"'.format(render_nodes_not_found)
            LOGGER.warning(msg)

        self._environments_override = list(environments_resolved or list())
        self._identifiers_override = list(identifiers_resolved or list())
        self._render_nodes_override = list(render_nodes_resolved or list())

        # Log all resolved values
        msg = 'RESOLVED ENVIRONMENTS OVERRIDES:\n'
        msg += '\n'.join(self.get_environments_override()) + '\n\n'
        LOGGER.info(msg)
        msg = 'RESOLVED PASS FOR ENV IDENTIFIERS OVERRIDES:\n'
        msg += '\n'.join(self.get_pass_for_env_identifiers_override()) + '\n\n'
        LOGGER.info(msg)
        msg = 'RESOLVED RENDER NODES OVERRIDES:\n'
        msg += '\n'.join(self.get_render_nodes_override()) + '\n\n'
        LOGGER.info(msg)

        ######################################################################

        LOGGER.info(done_msg)
        return True


    def get_email_global_details_from_session_data(self, session_data):
        '''
        Collect all the global email details from session data.

        Args:
            session_data (dict):

        Returns:
            email_details (list):
        '''
        email_details = list()

        source_project = session_data.get('project')
        detail_item = ('Source Project', str(source_project))
        email_details.append(detail_item)

        session_path = self._session_location
        detail_item = ('Auto Save Session Path', str(session_path))
        email_details.append(detail_item)

        additional_job_identifier = session_data.get('additional_job_identifier')
        if additional_job_identifier:
            detail_item = ('Additional Job Identifier', str(additional_job_identifier))
            email_details.append(detail_item)

        description_global = session_data.get('description_global')
        if description_global:
            detail_item = ('Overall Submission Description', str(description_global))
            email_details.append(detail_item)

        version_global_system = session_data.get('version_global_system')
        detail_item = ('Global Version System', str(version_global_system))
        email_details.append(detail_item)

        host_app_version = self.get_host_app_version()
        if host_app_version:
            label_str = '{} Version'.format(self.HOST_APP.title())
            detail_item = (label_str, str(host_app_version))
            email_details.append(detail_item)

        label_str = '{} Version'.format(self.TOOL_NAME)
        detail_item = (label_str, str(self._multi_shot_render_submitter_version))
        email_details.append(detail_item)

        # Also show version of base multi shot render submitter pak
        if 'GEN' not in self.TOOL_NAME:
            label_str = 'Multi Shot Render Submitter Version'.format(self.TOOL_NAME)
            version = utils.get_multi_shot_render_submitter_version()
            detail_item = (label_str, str(version))
            email_details.append(detail_item)

        return email_details


    def check_identifier_in_identifers(
            self,
            environment,
            item_full_name,
            env_index=None,
            job_identifier=None):
        '''
        Check if environment and node name / path are in current identifiers_override list.

        Args:
            environment (str): only the environment
            item_full_name (str): the full node name or path
            env_index (int): the index environment appears in session data
            job_identifier (str): the job identifier to check

        Returns:
            in_identifiers, identifier_nice_name (tuple):
        '''
        identifier_nice_name = environment + constants.IDENTIFIER_JOINER + item_full_name
        identifier_found = identifier_nice_name in self._identifiers_override
        if not identifier_found and isinstance(env_index, int):
            identifier_nice_name = environment + '-' + str(env_index) + constants.IDENTIFIER_JOINER + item_full_name
            identifier_found = identifier_nice_name in self._identifiers_override
        if not identifier_found and job_identifier:
            identifier_nice_name = environment + '-' + str(job_identifier) + constants.IDENTIFIER_JOINER + item_full_name
            identifier_found = identifier_nice_name in self._identifiers_override
        if identifier_found:
            return True, identifier_nice_name
        return False, identifier_nice_name


    ##########################################################################
    # Other getters and setters


    def get_session_location(self):
        return self._session_location


    def set_session_location(self, session_location):
        '''
        Set the session path that will be loaded once host app is opened.

        Args:
            session_location (str): file path or Hyref
        '''
        # Convert session location hyref to file path (if possible)
        if session_location.startswith(('hyref:', 'urn:')):
            session_location, msg = utils.get_hyref_default_location(session_location)
        msg = 'Setting session path to dispatch from to: "{}". '.format(session_location)
        msg += 'Value: "{}"'.format(type(session_location))
        LOGGER.info(msg)
        self._session_location = session_location


    def get_project(self):
        return self._project


    def set_project(self, project):
        '''
        Set the project that will be loaded once host app is opened.
        Note: If not specified, then the project in session data is used instead.

        Args:
            project (str): file path to project
        '''
        msg = 'Setting project to dispatch from to: "{}". '.format(project)
        msg += 'Value: "{}"'.format(type(project))
        LOGGER.info(msg)
        self._project = project


    def get_global_junk_box_id(self):
        return self._global_junk_box_id


    def set_global_junk_box_id(self, value):
        '''
        Set the global JunkBox Id to store Plow Job and Task id results.

        Args:
            value (str):
        '''
        msg = 'Setting global junkbox id to: "{}". '.format(value)
        msg += 'Value: "{}"'.format(type(value))
        LOGGER.info(msg)
        self._global_junk_box_id = value


    def get_environments_override(self):
        return self._environments_override


    def set_environments_override(self, environments_to_dispatch):
        '''
        Set the current override for Environment/s to dispatch for the next submission operation.

        Args:
            environments_to_dispatch (list):
        '''
        msg = 'Setting environment/s to dispatch to: "{}". '.format(environments_to_dispatch)
        msg += 'Value: "{}"'.format(type(environments_to_dispatch))
        LOGGER.info(msg)
        self._environments_override = environments_to_dispatch


    def get_render_nodes_override(self):
        return self._render_nodes_override


    def set_render_nodes_override(self, render_nodes):
        '''
        Optionally override which particular host app render nodes are
        rendered for every Environment. List of host app render node name/s,
        or full path/s list (depending on host app).
        Note: This overrides all queued and enabled states in session data.

        Args:
            render_nodes (list):
        '''
        msg = 'Setting render node/s to dispatch to: "{}". '.format(render_nodes)
        msg += 'Value: "{}"'.format(type(render_nodes))
        LOGGER.info(msg)
        self._render_nodes_override = render_nodes or list()


    def get_pass_for_env_identifiers_override(self):
        return self._identifiers_override


    def set_pass_for_env_identifiers_override(self, identifiers):
        '''
        When rendering from session data, optionally only rendering a subset
        of queued and enabled items from this specified mask list.
        Note: Items in session data set to unqueued or not enabled do not render either way.

        Args:
            identifiers (list):
        '''
        msg = 'Setting passes for environments to dispatch: "{}". '.format(identifiers)
        msg += 'Value: "{}"'.format(type(identifiers))
        LOGGER.info(msg)
        self._identifiers_override = identifiers or list()


    def set_email_global_details(self, email_global_details):
        '''
        List of global email details to include in
        collated email after all environment/s are dispatched.

        Args:
            email_global_details (list):
        '''
        self._email_global_details = email_global_details


    def get_multi_shot_render_submitter_version(self):
        return self._multi_shot_render_submitter_version


    def set_multi_shot_render_submitter_version(self, version):
        '''
        Get the Multi Shot Render submitter pak version for particular host app.
        Note: This just cached the value set from external provider.

        Args:
            version (str):
        '''
        msg = 'Multi Shot Version: "{}". '.format(version)
        msg += 'Type: "{}"'.format(type(version))
        LOGGER.info(msg)
        self._multi_shot_render_submitter_version = version


    def get_global_shotsub_override(self):
        return self._global_shotsub_override


    def set_global_shotsub_override(self, global_shotsub_override):
        '''
        Set whether every renderable should have Shotsub
        force enabled during submission or not. Otherwise session
        data value is used instead (or false if no session data).

        Args:
            global_shotsub_override (bool):
        '''
        msg = 'Shotsub global override: "{}". '.format(global_shotsub_override)
        msg += 'Type: "{}"'.format(type(global_shotsub_override))
        LOGGER.info(msg)
        self._global_shotsub_override = global_shotsub_override


    def get_global_job_identifier(self):
        return self._global_job_identifier


    def set_global_job_identifier(self, value):
        '''
        Optionally override global note that represents all tasks about to be submitted.

        Args:
            value (str):
        '''
        value = str(value or str())
        # NOTE: Remove any non alphanumeric characters
        value = re.sub(r'\W+', str(), value)
        msg = 'Set global job identifier override: "{}". '.format(value)
        msg += 'Type: "{}"'.format(type(value))
        LOGGER.info(msg)
        self._global_job_identifier = value


    def get_global_note_override(self):
        return self._global_note_override


    def set_global_note_override(self, global_note_override):
        '''
        Optionally override global note that represents all tasks about to be submitted.

        Args:
            global_note_override (str):
        '''
        msg = 'Set note global override: "{}". '.format(global_note_override)
        msg += 'Type: "{}"'.format(type(global_note_override))
        LOGGER.info(msg)
        self._global_note_override = global_note_override


    def get_overrides_dict(self):
        return self._overrides_dict


    def set_overrides_dict(self, overrides_dict):
        '''
        Optionally override global note that represents all tasks about to be submitted.

        Args:
            overrides_dict (str):
        '''
        msg = 'Set overrides dict: "{}". '.format(overrides_dict)
        msg += 'Type: "{}"'.format(type(overrides_dict))
        LOGGER.info(msg)
        self._overrides_dict = overrides_dict


    def get_host_app_version(self):
        return self._host_app_version


    def set_host_app_version(self, host_app_version):
        '''
        Set the host app version this Multi Shot Render Submitter is running in.
        Note: This just cached the value set from external provider.

        Args:
            ulti_shot_render_submitter_version (str):
        '''
        msg = 'Host app version: "{}". '.format(host_app_version)
        msg += 'Type: "{}"'.format(type(host_app_version))
        LOGGER.info(msg)
        self._host_app_version = host_app_version


    def get_plow_job_id_last_dispatched(self):
        '''
        Get the last Plow Job Id dispatched (if any).

        Returns:
            plow_job_id (str):
        '''
        return self._plow_job_id


    def get_auto_refresh_from_shotgun(self):
        '''
        Get whether to refresh production data in dispatcher task.

        Returns:
            auto_refresh_from_shotgun (bool):
        '''
        return self._auto_refresh_from_shotgun


    def set_auto_refresh_from_shotgun(self, value):
        '''
        Set whether to refresh production data in dispatcher task.

        Args:
            value (bool):
        '''
        value = bool(value)
        msg = 'Setting refresh from shotgun on submit: {}'.format(value)
        LOGGER.info(msg)
        self._auto_refresh_from_shotgun = value


##############################################################################
# Register all dispatcher plugins


def register_all_plugins():
    '''
    Register all the dispatcher plugins and store a key
    value mapping of available plugins for various host app.

    Returns:
        plugins_dict (dict):
    '''
    import sys

    msg = 'STARTING REGISTER OF MULTI SHOT DISPATCHER PLUGINS\n\n'
    LOGGER.debug(msg)

    # EXCLUDE_FILES = ['__init__', 'abstract_multi_shot_dispatcher']

    # Only load plugins from this directory
    THIS_FOLDER = os.path.dirname(__file__)

    # Load plugins from plugin directory
    PLUGINS_DIRECTORIES = os.getenv(
        'SRND_MULTI_SHOT_DISPATCHER_PLUGINS',
        THIS_FOLDER)

    plugins_dict = dict()
    for plugins_directory in PLUGINS_DIRECTORIES.split(':'):
        sys.path.insert(0, plugins_directory)
        for file_name in os.listdir(plugins_directory):
            file_name_no_ext, ext = os.path.splitext(file_name)
            if not ext == '.py':
                continue
            # if ext == '.py' and file_name_no_ext not in EXCLUDE_FILES:
            file_path = os.path.join(plugins_directory, file_name)
            try:
                module = __import__(file_name_no_ext)
            except ImportError as error:
                continue
            if not hasattr(module, 'register_plugin'):
                continue
            class_object = module.register_plugin()
            host_app = class_object.get_dispatcher_is_for_host_app().lower()
            plugins_dict[host_app] = dict()
            plugins_dict[host_app]['class_object'] = class_object
            plugins_dict[host_app]['module_path'] = file_path
        sys.path.pop(0)

    return plugins_dict


# Store an object to cache all the available multi shot dispatcher plugins
SRND_MULTI_SHOT_DISPATCHER_PLUGINS = register_all_plugins()