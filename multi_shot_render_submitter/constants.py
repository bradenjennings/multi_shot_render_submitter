

import logging
import os
import sys

from srnd_multi_shot_render_submitter import utils


LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)


##############################################################################
# In various host app constants


IN_KATANA = 'katana' in sys.executable
if IN_KATANA:
    from srnd_katana_render_submitter.multi_shot import katana_utils
    IN_KATANA_UI_MODE = katana_utils.get_in_katana_ui_mode()
else:
    IN_KATANA_UI_MODE = False

try:
    import ix
    IN_CLARISSE = True
    IN_CLARISSE_UI_MODE = ix.is_gui_application() # ix.is_interactive_application()
except Exception as error:
    IN_CLARISSE = False
    IN_CLARISSE_UI_MODE = False


##############################################################################


class Constants(object):
    '''
    A shared collection of Multi Shot Render Submitter constants,
    some of which depend on HOST_APP.
    Various constants are queried from external config file,
    the chosen constants file also depends on HOST_APP.
    Some parts of this might be reimplemented to provide
    different values for required host app.

    Note: Only one instance of this Singleton can exist
    for a given Multi Shot Render Submitter execution context.

    Note: If subclassing this Constants module, the subclass should
    be instantiated first when app open. So then instantiating this super
    Constants module again, it would then return the subclassed Constants.
    All client code can then call this class directly.

    Args:
        host_app (str):
    '''

    __instance = None


    def __new__(cls, host_app=str()):
        '''
        Return a shared instance of this Multi Shot Constants object.

        Args:
            host_app (str):
        '''
        if Constants.__instance is None:

            # Try to derive host app automatically, if not specified
            if not host_app:
                if IN_KATANA:
                    host_app = 'katana'
                elif IN_CLARISSE:
                    host_app = 'clarisse'
                else:
                    host_app = 'GEN'

            Constants.__instance = object.__new__(cls)
            Constants.__instance.HOST_APP = host_app
            Constants.__instance._set_all_constants()

        return Constants.__instance


    def get_host_app(self):
        '''
        Get the host app name.

        Returns:
            host_app (str):
        '''
        return self.HOST_APP


    def set_host_app(self, update_contants=True):
        '''
        Set the host app name.
        Some environment variables can now be optionally automatically updated.

        Args:
            host_app (str):
            update_contants (bool):
        '''
        self.HOST_APP = host_app
        if update_contants:
            self._set_all_constants()


    def _set_all_constants(self):
        '''
        Set all constants to default values, some of which depend on HOST_APP.
        Various constants are queried from external config file.
        '''
        self.TOOL_NAME = '{} Multi Shot Render Submitter'.format(self.HOST_APP.title())

        # Update name of wtpe config file based on host app name.
        # Located in directory: "/vol/wtpe/etc/config/site/"
        _app_config = str()
        if self.HOST_APP:
            _app_config = '{}_'.format(self.HOST_APP)
        # Branching should be avoided here, the design and interaction with this 
        # class will probably change soon, to make more sensible within framework...
        if self.HOST_APP =='katana':
            self.HOST_APP_DOCUMENT = 'katana scene'
            self.HOST_APP_RENDERABLES_LABEL = 'render nodes'
            self.HOST_APP_SERVICE_KEYS = ['katana_manuka']
        else:
            self.HOST_APP_DOCUMENT = 'project'
            self.HOST_APP_RENDERABLES_LABEL = 'layer items'
            self.HOST_APP_SERVICE_KEYS = ['clarisse']
        self.CONFIG_NAME = 'srnd_{}multi_shot_render_submitter'.format(_app_config)

        self.IDENTIFIER_JOINER = '#'

        ######################################################################
        # Primary session keys for important app agnostic data

        self.SESSION_KEY_MULTI_SHOT_DATA =  'multi_shot_data'
        self.SESSION_KEY_RENDER_NODES =  'render_nodes_data'
        self.SESSION_KEY_ENVIRONMENTS =  'environments_data'
        self.SESSION_KEY_PASSES =  'passes_for_env_data'
        self.SESSION_KEY_RENDER_OVERRIDES_DATA = 'render_overrides_data'
        self.SESSION_KEY_VISIBLE_ROWS = 'visible_rows_data'
        self.SESSION_KEY_ENVIRONMENT = 'environment'
        self.SESSION_KEY_JOB_IDENTIFIER = 'job_identifier'
        self.SESSION_KEY_WAIT_ON = 'wait_on_uuids'
        self.SESSION_KEY_WAIT_ON_PLOW_IDS = 'wait_on_plow_ids'
        self.SESSION_KEY_COLOUR = 'colour'
        self.SESSION_KEY_CURRENT_SELECTION = 'current_selection'
        self.SESSION_KEY_SELECTION_SETS = 'selection_sets'
        self.SESSION_KEY_RENDER_NODES_VIS_SETS = 'render_nodes_visibility_sets'
        self.SESSION_KEY_ENV_COLUMN_WIDTH = 'environments_column_width'

        ######################################################################
        # Get values from external config file and store as constant

        self.ADMIN_USERS = self.get_peconfig_value(
            'admin.admin_users',
            default=['bjennings'])

        ################
        # View constants

        self.HIDDEN_ITEMS_RENDERABLE = bool(self.get_peconfig_value(
            'view.hidden_items_renderable',
            default=False))
        self.GENERATE_EFFICIENT_THUMBNAILS_IN_THREAD = bool(self.get_peconfig_value(
            'view.generate_efficient_thumbnails_in_thread',
            default=True))

        #########################
        # Option toggle constants

        self.ALLOW_DELETE_FROM_COLUMN_HEADER = bool(self.get_peconfig_value(
            'options.allow_delete_from_column_header',
            default=True))
        self.ALLOW_RENAME_FROM_COLUMN_HEADER = bool(self.get_peconfig_value(
            'options.allow_rename_from_column_header',
            default=True))
        self.ALLOW_SET_COLOUR_FROM_COLUMN_HEADER = bool(self.get_peconfig_value(
            'options.allow_set_colour_from_column_header',
            default=True))
        self.ALLOW_TOGGLE_ENABLED_FROM_COLUMN_HEADER = bool(self.get_peconfig_value(
            'options.allow_toggle_enabled_from_column_header',
            default=True))
        self.ALLOW_RENDER_NODE_DROP = bool(self.get_peconfig_value(
            'options.allow_render_node_drop',
            default=True))
        self.EXPOSE_VALIDATION = bool(self.get_peconfig_value(
            'options.expose_validation',
            default=True))
        self.EXPOSE_CALLBACKS = bool(self.get_peconfig_value(
            'options.expose_callbacks',
            default=False))
        self.MENU_BAR_USE_HYREF_WIDGET = bool(self.get_peconfig_value(
            'options.menu_bar_use_hyref_widget',
            default=True))
        self.EXPOSE_UPDATE_OVERVIEW_BUTTON =  bool(self.get_peconfig_value(
            'options.expose_update_overview_button',
            default=True))
        self.EXPOSE_RENDER_ESTIMATE = bool(self.get_peconfig_value(
            'options.expose_render_estimate',
            default=True))
        self.PREFER_ESTIMATE_CORE_HOURS = bool(self.get_peconfig_value(
            'options.prefer_estimate_core_hours',
            default=True))            
        self.DISPATCH_DEFERRED = bool(self.get_peconfig_value(
            'options.dispatch_deferred',
            default=True))
        self.SNAPSHOT_BEFORE_DISPATCH = bool(self.get_peconfig_value(
            'options.snapshot_before_dispatch',
            default=True))
        self.EXPOSE_DISPATCH_DEFERRED = bool(self.get_peconfig_value(
            'options.expose_dispatch_deferred',
            default=True))
        self.LAUNCH_PAUSED = bool(self.get_peconfig_value(
            'options.launch_paused',
            default=False))
        self.LAUNCH_PAUSED_EXPIRES = int(self.get_peconfig_value(
            'options.launch_paused_expires',
            default=0))
        self.LAUNCH_ZERO_TIER = bool(self.get_peconfig_value(
            'options.launch_zero_tier',
            default=False))
        self.APPLY_RENDER_OVERRIDES = bool(self.get_peconfig_value(
            'options.apply_render_overrides',
            default=True))
        self.APPLY_DEPEDENCIES = bool(self.get_peconfig_value(
            'options.apply_dependencies',
            default=True))
        self.EXPOSE_SHOT_OVERRIDES = bool(self.get_peconfig_value(
            'options.expose_shot_overrides',
            default=True))
        self.EXPOSE_INTERACTIVE_RENDER = bool(self.get_peconfig_value(
            'options.expose_interactive_render',
            default=True))
        self.EXPOSE_SPLIT_FRAME_JOB = bool(self.get_peconfig_value(
            'options.expose_split_frame_job',
            default=True))
        # self.EXPOSE_DENOISE = bool(self.get_peconfig_value(
        #     'options.expose_denoise',
        #     default=False))
        # Check which version of Koba in environment
        # if not self.EXPOSE_DENOISE:
        self.EXPOSE_DENOISE = True
        # msg = 'Denoise Available For Koba: "{}"'.format(self.EXPOSE_DENOISE)
        # print(msg)
        if not self.EXPOSE_DENOISE:
            self.EXPOSE_DENOISE = bool(os.getenv('MSRS_EXPOSE_DENOISE'))

        self.LISTEN_TO_JOBS_FREQUENCY_DEFAULT = 25
        self.LISTEN_TO_JOBS_FREQUENCY_MIN = 3
        self.LISTEN_TO_JOBS_FREQUENCY_MAX = 999
        self.LISTEN_TO_JOBS = bool(self.get_peconfig_value(
            'options.listen_to_jobs',
            default=False))
        self.LISTEN_TO_JOBS_FREQUENCY = self.get_peconfig_value(
            'options.listen_to_jobs_frequency',
            default=self.LISTEN_TO_JOBS_FREQUENCY_DEFAULT)

        ######################
        # Validation constants

        self.FRAME_COUNT_HIGH = int(self.get_peconfig_value(
            'summary.frame_count_high',
            default=700))

        ######################################################################
        # Icon and font constants

        self.MULTI_SHOT_RENDER_SUBMITTER_ROOT = os.getenv(
            'SRND_MULTI_SHOT_RENDER_SUBMITTER_ROOT')
        self.ICONS_DIR = os.path.join(
            self.MULTI_SHOT_RENDER_SUBMITTER_ROOT,
            'icons')

        import srnd_qt.base.utils
        self.ICONS_DIR_QT = srnd_qt.base.utils.get_srnd_qt_icon_dir()

        self.FONT_FAMILY = 'Bitstream Vera Sans'

        ######################################################################
        # In various host app constants

        self.IN_KATANA = IN_KATANA
        self.IN_KATANA_UI_MODE = IN_KATANA_UI_MODE
        self.IN_CLARISSE = IN_CLARISSE
        self.IN_CLARISSE_UI_MODE = IN_CLARISSE_UI_MODE

        self.SYNC_RULES_ACTIVE = True
        self.SYNC_RULES_INCLUDE = list()
        self.SYNC_RULES_EXCLUDE = list()

        ##############################################################################
        # Sizes

        self.DETAILS_EDITOR_WIDTH = 360
        self.JOB_OPTIONS_EDITOR_WIDTH = 360
        self.LIGHTING_INFO_EDITOR_WIDTH = 560

        ##############################################################################
        # Colours

        self.HEADER_RENDERABLE_COLOUR = [112, 186, 112]
        self.CELL_RENDERABLE_COLOUR = [73, 155, 73]
        self.HEADER_BACKGROUND_COLOUR = [60, 60, 60]
        self.CELL_ENABLED_NOT_QUEUED_COLOUR = [80, 80, 80]
        self.CELL_DISABLED_COLOUR = [64, 64, 64]

        ##############################################################################
        # Presets / options

        self.DEFAULT_EMAIL_ADDITIONAL_USERS = [os.getenv('USER')]
        self.DEFAULT_GLOBAL_JOB_IDENTIFIER = str()
        self.DEFAULT_SEND_EMAIL = True
        self.DEFAULT_DESCRIPTION_GLOBAL = str()
        self.DEFAULT_SEND_SUMMARY_EMAIL_ON_SUBMIT = True

        ######################################################################
        # Overrides / rules

        self.OVERRIDES_RULE_TO_CATEGORY = dict()
        self.OVERRIDES_RULE_TO_FULLNAME = dict()

        ######################################################################
        # Overrides / rules for frames

        self.OVERRIDES_FRAME_RULES = list()

        self.OVERRIDE_FRAMES_X1 = 'x1'
        self.OVERRIDE_FRAMES_X1_LONG = 'Every frame'
        self.OVERRIDES_FRAME_RULES.append(self.OVERRIDE_FRAMES_X1)
        self.OVERRIDES_RULE_TO_CATEGORY[self.OVERRIDE_FRAMES_X1] = 'Frames'
        self.OVERRIDES_RULE_TO_FULLNAME[self.OVERRIDE_FRAMES_X1] = self.OVERRIDE_FRAMES_X1_LONG

        self.OVERRIDE_FRAMES_X10 = 'x10'
        self.OVERRIDE_FRAMES_X10_LONG = 'Every 10th frame'
        self.OVERRIDES_FRAME_RULES.append(self.OVERRIDE_FRAMES_X10)
        self.OVERRIDES_RULE_TO_CATEGORY[self.OVERRIDE_FRAMES_X10] = 'Frames'
        self.OVERRIDES_RULE_TO_FULLNAME[self.OVERRIDE_FRAMES_X10] = self.OVERRIDE_FRAMES_X10_LONG

        self.OVERRIDE_FRAMES_XCUSTOM = 'xN'
        self.OVERRIDE_FRAMES_XCUSTOM_LONG = 'Every Nth frame'
        self.OVERRIDES_FRAME_RULES.append(self.OVERRIDE_FRAMES_XCUSTOM)
        self.OVERRIDES_RULE_TO_CATEGORY[self.OVERRIDE_FRAMES_XCUSTOM] = 'Frames'
        self.OVERRIDES_RULE_TO_FULLNAME[self.OVERRIDE_FRAMES_XCUSTOM] = self.OVERRIDE_FRAMES_XCUSTOM_LONG

        self.OVERRIDE_FRAMES_FML = 'FML'
        self.OVERRIDE_FRAMES_FML_LONG = 'First/Middle/Last'
        self.OVERRIDES_FRAME_RULES.append(self.OVERRIDE_FRAMES_FML)
        self.OVERRIDES_RULE_TO_CATEGORY[self.OVERRIDE_FRAMES_FML] = 'Frames'
        self.OVERRIDES_RULE_TO_FULLNAME[self.OVERRIDE_FRAMES_FML] = self.OVERRIDE_FRAMES_FML_LONG

        self.OVERRIDE_FRAMES_CUSTOM = 'Custom frames'
        self.OVERRIDE_FRAMES_CUSTOM_LONG = 'Custom frames'
        self.OVERRIDES_RULE_TO_CATEGORY[self.OVERRIDE_FRAMES_CUSTOM] = 'Frames'
        self.OVERRIDES_RULE_TO_FULLNAME[self.OVERRIDE_FRAMES_CUSTOM] = 'Custom frames'

        self.OVERRIDE_FRAMES_NOT_FML = 'NOT FML'
        self.OVERRIDE_FRAMES_NOT_FML_LONG = 'Not First Middle Last'
        self.OVERRIDES_FRAME_RULES.append(self.OVERRIDE_FRAMES_NOT_FML)
        self.OVERRIDES_RULE_TO_CATEGORY[self.OVERRIDE_FRAMES_NOT_FML] = 'Frames'
        self.OVERRIDES_RULE_TO_FULLNAME[self.OVERRIDE_FRAMES_NOT_FML] = self.OVERRIDE_FRAMES_NOT_FML_LONG

        self.OVERRIDE_FRAMES_NOT_X10 = 'NOT x10'
        self.OVERRIDE_FRAMES_NOT_X10_LONG = 'Not every 10th frame'
        self.OVERRIDES_FRAME_RULES.append(self.OVERRIDE_FRAMES_NOT_X10)
        self.OVERRIDES_RULE_TO_CATEGORY[self.OVERRIDE_FRAMES_NOT_X10] = 'Frames'
        self.OVERRIDES_RULE_TO_FULLNAME[self.OVERRIDE_FRAMES_NOT_X10] = self.OVERRIDE_FRAMES_NOT_X10_LONG

        self.OVERRIDE_FRAMES_NOT_XCUSTOM = 'NOT xN'
        self.OVERRIDE_FRAMES_NOT_XCUSTOM_LONG = 'NOT every Nth frame'
        self.OVERRIDES_FRAME_RULES.append(self.OVERRIDE_FRAMES_NOT_XCUSTOM)
        self.OVERRIDES_RULE_TO_CATEGORY[self.OVERRIDE_FRAMES_NOT_XCUSTOM] = 'Frames'
        self.OVERRIDES_RULE_TO_FULLNAME[self.OVERRIDE_FRAMES_NOT_XCUSTOM] = self.OVERRIDE_FRAMES_XCUSTOM_LONG

        self.OVERRIDE_FRAMES_NOT_CUSTOM = 'Custom NOT frames'
        self.OVERRIDE_FRAMES_NOT_CUSTOM_LONG = 'Custom NOT frames'
        self.OVERRIDES_RULE_TO_CATEGORY[self.OVERRIDE_FRAMES_NOT_CUSTOM] = 'Frames'
        self.OVERRIDES_RULE_TO_FULLNAME[self.OVERRIDE_FRAMES_NOT_CUSTOM] = 'Custom NOT Frames'

        self.OVERRIDE_FRAMES_IMPORTANT = 'Important'
        self.OVERRIDE_FRAMES_IMPORTANT_LONG = 'Important frames for shot'
        self.OVERRIDES_RULE_TO_CATEGORY[self.OVERRIDE_FRAMES_IMPORTANT] = 'Frames'
        self.OVERRIDES_RULE_TO_FULLNAME[self.OVERRIDE_FRAMES_IMPORTANT] = self.OVERRIDE_FRAMES_IMPORTANT_LONG
        self.OVERRIDES_FRAME_RULES.append(self.OVERRIDE_FRAMES_IMPORTANT)

        self.OVERRIDE_FRAMES_NOT_IMPORTANT = 'NOT Important'
        self.OVERRIDE_FRAMES_NOT_IMPORTANT_LONG = 'NOT Important frames for shot'
        self.OVERRIDES_RULE_TO_CATEGORY[self.OVERRIDE_FRAMES_NOT_IMPORTANT] = 'Frames'
        self.OVERRIDES_RULE_TO_FULLNAME[self.OVERRIDE_FRAMES_NOT_IMPORTANT] = self.OVERRIDE_FRAMES_NOT_IMPORTANT_LONG
        self.OVERRIDES_FRAME_RULES.append(self.OVERRIDE_FRAMES_NOT_IMPORTANT)

        ######################################################################
        # Overrides / rules for versions

        self.OVERRIDES_VERSION_RULES = list()

        self.OVERRIDE_VERSION_CUSTOM = 'Custom version'
        self.OVERRIDE_VERSION_CUSTOM_LONG = 'Custom version'

        self.OVERRIDE_VERSION_VNEXT = 'V+'
        self.OVERRIDE_VERSION_VNEXT_LONG = 'Next version'
        self.OVERRIDES_VERSION_RULES.append(self.OVERRIDE_VERSION_VNEXT)
        self.OVERRIDES_RULE_TO_CATEGORY[self.OVERRIDE_VERSION_VNEXT] = 'Version'
        self.OVERRIDES_RULE_TO_FULLNAME[self.OVERRIDE_VERSION_VNEXT] = self.OVERRIDE_VERSION_VNEXT_LONG

        self.OVERRIDE_VERSION_VPASSESNEXT = 'VP+'
        self.OVERRIDE_VERSION_VPASSESNEXT_LONG = 'Next highest version of all passes'
        self.OVERRIDES_VERSION_RULES.append(self.OVERRIDE_VERSION_VPASSESNEXT)
        self.OVERRIDES_RULE_TO_CATEGORY[self.OVERRIDE_VERSION_VPASSESNEXT] = 'Version'
        self.OVERRIDES_RULE_TO_FULLNAME[self.OVERRIDE_VERSION_VPASSESNEXT] = self.OVERRIDE_VERSION_VPASSESNEXT_LONG

        # Other version constants
        self.DEFAULT_CG_VERSION_SYSTEM = 'VP+'
        self.CG_VERSION_SYSTEM_PASSES_NEXT = 'VP+'
        self.CG_VERSION_SYSTEM_PASS_NEXT = 'V+'
        self.CG_VERSION_SYSTEM_MATCH_SCENE = 'VS'
        self.CG_VERSION_SYSTEMS = [
            self.CG_VERSION_SYSTEM_PASSES_NEXT,
            self.CG_VERSION_SYSTEM_PASS_NEXT,
            self.CG_VERSION_SYSTEM_MATCH_SCENE]

        ######################################################################
        # Overrides / rules for other

        self.NOTE_ICON_PATH = os.path.join(
            self.ICONS_DIR,
            'nodeCommentActive20_hilite.png')
        self.WAIT_ICON_PATH = os.path.join(
            self.ICONS_DIR,
            'wait_20x20_s01.png')
        self.SPLIT_FRAMES_ICON_PATH = os.path.join(
            self.ICONS_DIR,
            'split_20x20_s01.png')

        self.OVERRIDE_NOTE = 'Note'
        self.OVERRIDE_NOTE_LONG = 'Note'
        self.OVERRIDES_RULE_TO_CATEGORY[self.OVERRIDE_NOTE] = 'MetaData'

        self.OVERRIDE_JOB_IDENTIFIER = 'Jid'
        self.OVERRIDE_JOB_IDENTIFIER_LONG = 'Job identifier to be included in submitted jobs'
        self.OVERRIDES_RULE_TO_CATEGORY[self.OVERRIDE_JOB_IDENTIFIER] = 'Job'

        self.OVERRIDE_SPLIT_FRAME_RANGES = 'SplitFrames'
        self.OVERRIDE_SPLIT_FRAME_RANGES_LONG = 'Whether to split frame ranges into split job'
        self.OVERRIDES_RULE_TO_CATEGORY[self.OVERRIDE_SPLIT_FRAME_RANGES] = 'Frames'

        self.OVERRIDE_WAIT = 'Wait'
        self.OVERRIDE_WAIT_LONG = 'WAIT'
        self.OVERRIDES_RULE_TO_CATEGORY[self.OVERRIDE_WAIT] = 'Job'

        ##############################################################################
        # Labels and tooltips

        self.TIME_TAKEN_MSG = 'Time Taken To "{}": {} Seconds'

        self.LABEL_SYNC = 'Rebuild passes'
        self.TOOLTIP_SYNC = 'Clear the existing synced data, then reload from '.format(self.HOST_APP_DOCUMENT)
        self.TOOLTIP_SYNC += 'available {} & output shots/assets'.format(self.HOST_APP_RENDERABLES_LABEL)

        tree = os.getenv('TREE') or 'shots'
        shot_or_variant = 'shot'
        seq_or_asset = 'sequence'
        if tree:
            shot_or_variant = tree.rstrip('s')
            if tree == 'assets':
                seq_or_asset = 'asset'
        self.LABEL_GET_ALL_ASSIGNED_SHOTS_FOR_PROJECT = 'Add assigned {}s from project'.format(shot_or_variant)
        self.LABEL_GET_ALL_ASSIGNED_SHOTS_FOR_SEQUENCE = 'Add assigned {}s from {}'.format(
            shot_or_variant, 
            seq_or_asset)
        self.LABEL_GET_ALL_SHOTS_FOR_SEQUENCE = 'Add current {}'.format(seq_or_asset)

        self.TOOLTIP_GLOBAL_JOB_IDENTIFIER = 'Set an optional string to include in all generated '
        self.TOOLTIP_GLOBAL_JOB_IDENTIFIER += 'job names for the next submission. '
        self.TOOLTIP_GLOBAL_JOB_IDENTIFIER += '<br>Note: Each shot / environment can optionally '
        self.TOOLTIP_GLOBAL_JOB_IDENTIFIER += 'have a unique job identifier (Right-click on shot to add).'

        self.TOOLTIP_DESCRIPTION_GLOBAL = 'Add optional global description which '
        self.TOOLTIP_DESCRIPTION_GLOBAL += 'applies to the overall next job submission. '

        self.TOOLTIP_SEND_EMAIL = 'Choose whether to include MSRS summary email on next submission or not.'

        ##############################################################################
        # Stylesheets

        self.STYLE_SHEET_LINE_EDIT_ORANGE = '''
QLineEdit {
color: rgb(255,204,51);
border-style: solid;
border-width: 1px;
border-color: rgb(255,204,51,80);}
'''

        _STYLESHEET_BORDER = '''
border-style: solid;
border-left-width: {0}px;
border-right-width: {1}px;
border-top-width: {2}px;
border-bottom-width: {3}px;
border-left-color: rgb(62, 62, 62);
border-right-color: rgb(62, 62, 62);
border-bottom-color: rgb(62, 62, 62);
'''

        self.STYLESHEET_FRAME_DETAILS_PANEL = 'QFrame#DetailsPanel {'
        self.STYLESHEET_FRAME_DETAILS_PANEL += 'background-color: rgb(52, 52, 52);'
        self.STYLESHEET_FRAME_DETAILS_PANEL += _STYLESHEET_BORDER.format(3, 3, 0, 3)
        self.STYLESHEET_FRAME_DETAILS_PANEL += '}'

        self.STYLESHEET_FRAME_DETAILS_PANEL_NO_BORDER = 'QFrame#DetailsPanel {'
        self.STYLESHEET_FRAME_DETAILS_PANEL_NO_BORDER += _STYLESHEET_BORDER.format(0, 0, 0, 0)
        self.STYLESHEET_FRAME_DETAILS_PANEL_NO_BORDER += '}'

        self.STYLESHEET_GROUPBOX_DETAILS_PANEL_BORDER = 'QGroupBox {'
        self.STYLESHEET_GROUPBOX_DETAILS_PANEL_BORDER += _STYLESHEET_BORDER.format(3, 3, 0, 3)
        self.STYLESHEET_GROUPBOX_DETAILS_PANEL_BORDER += '}'

        ##############################################################################
        # Setup fonts

        from Qt.QtGui import QFont

        self.PANEL_FONT_REGULAR = QFont()
        self.PANEL_FONT_REGULAR.setFamily(self.FONT_FAMILY)
        self.PANEL_FONT_REGULAR.setPointSize(9)

        self.PANEL_FONT_ITALIC = QFont()
        self.PANEL_FONT_ITALIC.setFamily(self.FONT_FAMILY)
        self.PANEL_FONT_ITALIC.setItalic(True)
        self.PANEL_FONT_ITALIC.setPointSize(9)


    ##############################################################################
    # Config file


    def get_config_path(self, config_name=None):
        '''
        Get the config file path for multi shot render submitter.

        Args:
            config_name (str):

        Returns:
            config_file_path (str):
        '''
        config_name = config_name or self.CONFIG_NAME
        from peconfig import WtConfigFile
        return WtConfigFile(application=config_name).config_file_name


    def get_peconfig_value(
            self,
            config_key,
            default=list(),
            config_name=None):
        '''
        Get config value for multi_shot_render_submitter.

        Args:
            config_key (str): key to get from config file
            default (list): default return value if key not found
            config_name (str):

        Returns:
            data (dict): Winstrumentation detailed logged
        '''
        config_name = config_name or self.CONFIG_NAME
        from peconfig import WtConfigKeyResolver
        config_resolver = WtConfigKeyResolver()
        return config_resolver.get_value_json(
            config_name + '.' + config_key,
            default=default)


    ##########################################################################


    def conform_session_data(self, session_data=None):
        '''
        Conform old multi shot environment data to new data structure.

        Args:
            session_data (dict): modify existing session data dict in place

        Returns:
            session_data (dict): the modified session data dictionary
        '''
        if not session_data:
            session_data = dict()
        multi_shot_data = session_data.get(self.SESSION_KEY_MULTI_SHOT_DATA, dict())
        environments_data = multi_shot_data.get(self.SESSION_KEY_ENVIRONMENTS)
        if isinstance(environments_data, dict):
            new_environments_data = list()
            for environment in sorted(environments_data.keys()):
                shot_data = dict()
                shot_data.update(environments_data[environment])
                shot_data[self.SESSION_KEY_ENVIRONMENT] = environment
                new_environments_data.append(shot_data)
            new_environments_data = list(new_environments_data or list())
            msg = 'Translated old multishot data to: "{}"'.format(new_environments_data)
            LOGGER.warning(msg)
            # Replace the multi shot environments data with list (instead of dict)
            session_data[self.SESSION_KEY_MULTI_SHOT_DATA][self.SESSION_KEY_ENVIRONMENTS] = new_environments_data
        return session_data


    def get_env_data_from_envs_data(self, find_env, envs_data=None):
        '''
        Extract the relevant sub dictionary of environment data, amongst environments data.
        Note: The find_env string might be an oz area only, or might include a dash
        then index number, or dash then optional job identifier.

        Args:
            find_env (str): environment to find in envs data.
                Note: Might end in dash then index, or dash then optional job identifier
            envs_data (list): all environments data to find environment data in.

        Returns:
            env_data, index (tuple):
        '''
        if not envs_data:
            envs_data = list()

        # Extract index and job identifier from environment (if any)
        index, job_identifier = (None, None)
        if '-' in find_env:
            extra_value = find_env.split('-')[-1]
            if extra_value and str(extra_value).isdigit():
                index = int(extra_value)
            elif extra_value:
                job_identifier = str(extra_value)

        # Find the environment data for env string
        environments_counter = dict()
        for i, env_data in enumerate(envs_data):
            if not isinstance(env_data, dict):
                continue

            # Must have environment string in env data
            environment = env_data.get(self.SESSION_KEY_ENVIRONMENT)
            if not environment:
                continue

            # If environment also includes job identifier or index
            if '-' in find_env and any([index, job_identifier]):
                env_job_identifier = env_data.get(self.SESSION_KEY_JOB_IDENTIFIER)
                # Count the number of times environment has already appeared
                if environment not in environments_counter.keys():
                    environments_counter[environment] = 0
                environments_counter[environment] += 1
                env_index = environments_counter[environment]
                if index == env_index:
                    return env_data, i
                # Check if specified job identifier matches
                elif job_identifier and \
                        env_data.get(self.SESSION_KEY_JOB_IDENTIFIER) == job_identifier:
                    return env_data, i

            # Found direct match
            if environment == find_env:
                return env_data, i

        return None, -1
