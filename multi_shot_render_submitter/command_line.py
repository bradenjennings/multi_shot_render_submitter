

# import collections
import logging
import os
import traceback

from Qt.QtCore import QObject, Signal

from srnd_multi_shot_render_submitter.constants import Constants
constants = Constants()


logging.basicConfig()
LOGGER = logging.getLogger('command_line')
# LOGGER.setLevel(logging.DEBUG)


##############################################################################


class MultiShotRenderCommandLine(QObject):
    '''
    A command line interface for both the deferred dispatching system,
    and the Submitter user interface.
    Note: Some commands are made to be applicable only for the user
    interface or dispatching system.
    Note: Depending on UI or dispatching context some command line
    descriptions are modified to be more explicit.

    Args:
        host_app (str): name of host app that command line is being built for.
            if not specified is derived from reimplemented
            Constants Singleton object.
    '''

    logMessage = Signal(str, int)

    def __init__(self, host_app=None, parent=None):
        super(MultiShotRenderCommandLine, self).__init__(parent=parent)

        self.HOST_APP = host_app or constants.HOST_APP


    def build_command_line_interface(
            self,
            args_to_parse=None,
            force_args=False,
            is_ui_context=True,
            command_title=None):
        '''
        Build the GEN command line options for Multi Shot Render Submitter UI,
        or for the dispather task.
        May be reimplemented to provide additional arguments for particular host app.

        Args:
            args_to_parse (list): optionally override the sys.argv args
                to parse using argparser
            force_args (bool): optionally force parsing potentially an empty arg list,
                to prevent the default system args be parsed.
            is_ui_context (bool): whether the command line interface is being built
                for the Submitter UI context, otherwise the dispatcher context.
            command_title (str): optionally override the command title.

        Returns:
            parser, options_dict (tuple): a tuple of the argparse.Namespace and parsed args in dict
        '''
        msg = 'BUILDING COMMAND LINE INTERFACE FOR HOST APP: "{}". '.format(self.HOST_APP)
        msg += 'FOR UI CONTEXT: "{}"'.format(is_ui_context)
        LOGGER.info(msg)

        import argparse
        import sys

        # Default command title for UI or dispatcher mode (if not provided)
        if not command_title:
            command_title = 'srnd {} Multi Shot Render '.format(self.HOST_APP.title())
            # command_title = constants.TOOL_NAME
            if is_ui_context:
                command_title += 'Submitter (UI Startup Commands)'
            else:
                command_title += 'Dispatcher Commands'
            command_title += ' - Help'

        parser = argparse.ArgumentParser(description=command_title)

        ##########################################################################

        if is_ui_context:
            msg = 'Optionally Load A Project On Startup. '
            msg += 'Project Should Be Specified As Hyref. '
        else:
            msg = 'Optionally Override The Project To Dispatch. Otherwise '
            msg += 'Use The Project Specified In Session Data. '
        parser.add_argument(
            '-project',
            action='store',
            default=None,
            help=msg)

        if is_ui_context:
            msg = 'Load A Session Hyref Or File Path On Startup. Choosing This '
            msg += 'Will Disregard Any Specified Project File.'
        else:
            msg = 'The Session To Load And Dispatch From. '
            msg += 'Note: Use The -environments Argument To Override Which Subset '
            msg += 'Of Environment/s Should Be Dispatched.'
        parser.add_argument(
            '-session',
            action='store',
            default=None,
            help=msg)

        if is_ui_context:
            msg = 'Optionally Specify Multiple Environments To Add On Startup. '
        else:
            msg = 'Optionally Override Which Subset Of Environment/s To Submit '
            msg += 'In This Dispatcher Task. Otherwise Will Render All '
            msg += 'Environment/s With Queued Items In Session Data, '
            msg += 'Or All Environments Of Pass For Env Identifiers. '
        msg += 'Note: Specify Multiple Oz Contexts After "-environments" Argument Like This: '
        msg += '-environments project/tree/scene/shotA project/tree/scene/shotB'
        parser.add_argument(
            '-environments',
            nargs='+',
            help=msg)

        if is_ui_context:
            msg = 'Optionally Override The Project Shot Assignments Should Later '
            msg += 'Be Queried And Populated From. '
            parser.add_argument(
                '-shotAssignmentsProject',
                action='store',
                default=None,
                help=msg)

            msg = 'Optionally Override The User Shot Assignments Should Later '
            msg += 'Be Queried And Populated From. '
            parser.add_argument(
                '-shotAssignmentsUser',
                action='store',
                default=None,
                help=msg)

        # Only valid for CL command line dispatch tool
        if not is_ui_context:
            msg = 'Optionally Only Render A Subset Of Items From This Specified Identifier List. '
            msg += 'An Identifier Is A String Of "$OZ_CONTEXT#$RENDERABLE_NODE_NAME". '
            msg += 'Note: Node Name Might Instead Be Full Path To Item Depending On Host App. '
            msg += 'Note: Targets Specified Will Be Set To Queued And Enabled, Unspecified '
            msg += 'Targets Will be Set To Unqueued, And Will Not Render. '
            parser.add_argument(
                '-passForEnvIdentifiersOverride',
                nargs='+',
                help=msg)

            msg = 'Optionally Override Which Particular Host App Render Nodes Are '
            msg += 'Rendered For Every Environment. List Of Host App Render Node '
            msg += 'Name/s, Or Full Path/s List (Depending On Host App). '
            msg += 'Note: Unqueued Or Disabled Items In Session Data (If Any) '
            msg += 'Will Be Automatically Toggled To Renderable. '
            msg += 'Note: If This Option Is In Use, An Item Can Still Be Rendered '
            msg += 'That Does Not Appear In The List, If It Appears In '
            msg += 'PassForEnvIdentifiersOverride List. '
            msg += 'Note: This Option May Be Useful If No Session Data Is Available '
            msg += 'To Submit From. But You Know The Names Or Render Nodes To Dispatch. '
            parser.add_argument(
                '-renderNodesOverride',
                nargs='+',
                help=msg)

            msg = 'Optionally Force Override Shotsub State To Enabled Or Disabled '
            msg += 'For All Renderables. '
            parser.add_argument(
                '-globalShotsubOverride',
                type=int,
                default=None,
                help=msg)

            msg = 'Optionally Override Global Note That Represents All Tasks '
            msg += 'About To Be Submitted. '
            parser.add_argument(
                '-globalNoteOverride',
                nargs='+',
                help=msg)

            msg = 'Optionally Include A Global Identifier String As Part '
            msg += 'Of Job Name For Dispatcher Job.'
            parser.add_argument(
                '-globalJobIdentifierOverride',
                nargs='+',
                help=msg)

            msg = 'Optionally Apply Specific Frames Or Frames Rule Override To An Environment Or Render Pass For Env. '
            msg += 'Note: This Argument Can Be Specified Multiple Times For Different Targets. '
            msg += 'Note: Specify The Environment Or Render Pass For Env Identifier And Then Frames Or Frame Rule. '
            msg += 'Usage Example: \'-framesOverride /e/n/v/a "1-20x3" -framesOverride /e/n/v/b#RenderNodeB "FML"\''
            parser.add_argument(
                '-framesOverride',
                nargs=2,
                metavar=('node_name','frames'),
                action='append',
                help=msg)

            msg = 'Optionally Apply Specific Custom Version Or Version Rule Override To An Environment Or Render Pass For Env. '
            msg += 'Note: This Argument Can Be Specified Multiple Times For Different Targets. '
            msg += 'Note: Specify The Environment Or Render Pass For Env Identifier And Then Version Or Version Rule. '
            msg += 'Usage Example: \'-versionOverride /e/n/v/a "1-20x3" -versionOverride /e/n/v/b#RenderNodeB "FML"\''
            parser.add_argument(
                '-versionOverride',
                nargs=2,
                metavar=('node_name','version'),
                action='append',
                help=msg)

            msg = 'Optionally Apply Specific Note Override To An Environment Or Render Pass For Env. '
            msg += 'Note: This Argument Can Be Specified Multiple Times For Different Targets. '
            msg += 'Note: Specify The Environment Or Render Pass For Env Identifier And Then A Note. '
            msg += 'Usage Example: \'-noteOverride /e/n/v/a "Note For Env A" -noteOverride /e/n/v/b#RenderNodeB "Note For env b and render node b"\''
            parser.add_argument(
                '-noteOverride',
                nargs='+',
                # nargs=2,
                metavar=('node_name','note'),
                action='append',
                help=msg)

            msg = 'Optionally Set Whether To Shotsub Or Not To A Render Pass For Env. '
            msg += 'Note: This Argument Can Be Specified Multiple Times For Different Targets. '
            msg += 'Note: Specify The Environment Or Render Pass For Env Identifier And Then 0 Or 1. '
            msg += 'Usage Example: \'-shotsubOverride /e/n/v/a 0 -shotsubOverride /e/n/v/b#RenderNodeB 1\''
            parser.add_argument(
                '-shotsubOverride',
                nargs=2,
                metavar=('node_name','shotsub'),
                action='append',
                help=msg)

            msg = 'Optionally Apply Specific Job Identifier Override To An Environment. '
            msg += 'Note: This Argument Can Be Specified Multiple Times For Different Targets. '
            msg += 'Note: Specify The Environment And Then A Job Identifier. '
            msg += 'Usage Example: \'-jobIdentifierOverride /e/n/v/a "MyJobId" -jobIdentifierOverride /e/n/v/b "5sJob"\''
            parser.add_argument(
                '-jobIdentifierOverride',
                nargs=2,
                metavar=('node_name','jobIdentifier'),
                action='append',
                help=msg)

            msg = 'When --dispatch Is Enabled Optionally Query And List All The '
            msg += 'Resolved Values Only (Dispatch Will Be Skipped).'
            parser.add_argument(
                '--showValidationOnly',
                action='store_true',
                help=msg)

            msg = 'Whether to dispatch all environment/s as separate tasks '
            msg += 'on plow. Otherwise submit all environment/s using local '
            msg += 'machine in one task.'
            parser.add_argument(
                '--dispatch',
                action='store_true',
                help=msg)

            msg = 'Note: This argument should not be provided by user. '
            msg += 'Instead the argument is used internally to '
            msg += 'Cache host app dispatch results.'
            parser.add_argument(
                '-jbxBucket',
                action='store',
                default=None,
                help=msg)


            msg = 'Note: This argument should not be provided by user. '
            msg += 'Instead the argument is used internally to '
            msg += 'Cache job and task ids between all dispatcher results.'
            parser.add_argument(
                '-globalJbxBucket',
                action='store',
                default=None,
                help=msg)

            msg = 'Optionally skip refreshing production data in dispatcher task.'
            parser.add_argument(
                '--skipRefreshProductionData',
                action='store_true',
                help=msg)

        if is_ui_context:
            msg = 'Debug mode shows more verbose info in log panel'
        else:
            msg = 'Debug mode shows more verbose info while dispatching'
        parser.add_argument(
            '--debug',
            action='store_true',
            help=msg)

        # Parse from particular args, or optionally from empty arg list
        if args_to_parse or force_args:
            args = parser.parse_args(args_to_parse)
        # Parse from default sys args
        else:
            args = parser.parse_args()

        ##########################################################################

        import oz

        options_dict = dict() # collections.OrderedDict()

        # If project hyref specified verify it now
        if args.project:
            project = self._cleanup_command_line_string(args.project)
            import srnd_multi_shot_render_submitter.utils
            location, msg = srnd_multi_shot_render_submitter.utils.get_hyref_default_location(
                project,
                as_file_path=True)
            if location:
                options_dict['project'] = str(project)
                msg = 'Specified Project To Load. '
                msg += 'Value: "{}". Type: "{}"'.format(project, type(project))
                LOGGER.info(msg)

        # Optionally open a session on startup
        if args.session:
            session_location = self._cleanup_command_line_string(args.session)
            options_dict['session'] = session_location
            msg = 'Specified Session. '
            msg += 'Value: "{}". Type: "{}"'.format(session_location, type(session_location))
            LOGGER.info(msg)

        if is_ui_context:
            # Optionally open a session on startup
            if args.shotAssignmentsProject:
                shot_project = self._cleanup_command_line_string(
                    args.shotAssignmentsProject)
                options_dict['shot_assignments_project'] = shot_project
                msg = 'Specified Film (For Later Deriving Shot Assignments). '
                msg += 'Value: "{}". Type: "{}"'.format(shot_project, type(shot_project))
                LOGGER.info(msg)

            # Optionally open a session on startup
            if args.shotAssignmentsUser:
                shot_user = self._cleanup_command_line_string(
                    args.shotAssignmentsUser)
                options_dict['shot_assignments_user'] = shot_user
                msg = 'Specified User (For Later Deriving Shot Assignments). '
                msg += 'Value: "{}". Type: "{}"'.format(shot_user, type(shot_user))
                LOGGER.info(msg)
        else:
            # Validated all the specified pass for environments have valid oz areas
            if args.passForEnvIdentifiersOverride:
                msg = 'Validating Pass For Environments '
                msg += 'Identifiers Overrides: "{}"'.format(args.passForEnvIdentifiersOverride)
                LOGGER.warning(msg)
                identifiers = list()
                for identifier in args.passForEnvIdentifiersOverride:
                    # Validate expected separator between environment and render node name
                    if constants.IDENTIFIER_JOINER not in identifier:
                        msg = 'Pass For Env Identifier Must Have Hash Separating '
                        msg += 'Environment And Pass Name: "{}"'.format(identifier)
                        LOGGER.warning(msg)
                        continue
                    # Validate identifier has valid environment
                    environment = identifier.split(constants.IDENTIFIER_JOINER)[0]
                    is_valid = self.validate_environment(environment)
                    if not is_valid:
                        msg = 'Environment Of Identifier NOT Valid To Dispatch From: "{}". '.format(identifier)
                        msg += 'Env: "{}"'.format(environment)
                        LOGGER.warning(msg)
                        continue
                    # Validate identifier has render node name
                    render_node_name = identifier.split(constants.IDENTIFIER_JOINER)[-1]
                    if not render_node_name:
                        msg = 'Must Specify Identifier As Environment Then Hash '
                        msg += 'Then Render Node Name. Skipping Add Identifier! '
                        msg += 'Value: "{}". Type: "{}"'.format(identifier, type(identifier))
                        LOGGER.warning(msg)
                        continue
                    msg = 'Environment Of Identifier Is Valid To Dispatch From: "{}"'.format(environment)
                    LOGGER.warning(msg)
                    identifiers.append(identifier)
                if identifiers:
                    options_dict['pass_for_env_identifiers_override'] = identifiers
                    msg = 'Specified Valid Pass For Env Identifiers: "{}". '.format(identifiers)
                    msg += 'Value: "{}". Type: "{}"'.format(identifiers, type(identifiers))
                    LOGGER.info(msg)

            if args.renderNodesOverride:
                render_nodes = args.renderNodesOverride
                options_dict['render_nodes_override'] = render_nodes
                msg = 'Specified Override List Of Render Node/s To Dispatch '
                msg += 'For Every Environment. '
                msg += 'Value: "{}". Type: "{}"'.format(render_nodes, type(render_nodes))
                LOGGER.info(msg)

            ##################################################################
            # Global options

            if isinstance(args.globalShotsubOverride, (int, bool)):
                global_shotsub_override = bool(args.globalShotsubOverride)
                options_dict['global_shotsub_override'] = global_shotsub_override
                msg = 'Specified Global Shotsub Override.  '
                msg += 'Value: "{}". Type: "{}"'.format(global_shotsub_override, type(global_shotsub_override))
                LOGGER.info(msg)

            if args.globalNoteOverride:
                description = args.globalNoteOverride or list()
                description = ' '.join(description)
                # description = self._cleanup_command_line_string(description)
                options_dict['global_note_override'] = description
                msg = 'Specified Global Note Override.  '
                msg += 'Value: "{}". Type: "{}"'.format(description, type(description))
                LOGGER.info(msg)

            if args.globalJobIdentifierOverride:
                global_job_identifier = args.globalJobIdentifierOverride or list()
                global_job_identifier = ' '.join(global_job_identifier)
                global_job_identifier = self._cleanup_command_line_string(global_job_identifier)
                options_dict['global_job_identifier'] = global_job_identifier
                msg = 'Specified Global Job Identifier Override. '
                msg += 'Value: "{}". Type: "{}"'.format(global_job_identifier, type(global_job_identifier))
                LOGGER.info(msg)

            ##################################################################
            # Per render node overrides

            if args.framesOverride:
                frames_override = args.framesOverride
                options_dict['frames_override'] = frames_override
                msg = 'Specified Frames Override.  '
                msg += 'Value: "{}". Type: "{}"'.format(frames_override, type(frames_override))
                LOGGER.info(msg)

            if args.versionOverride:
                version_override = args.versionOverride
                options_dict['version_override'] = version_override
                msg = 'Specified Version Override.  '
                msg += 'Value: "{}". Type: "{}"'.format(version_override, type(version_override))
                LOGGER.info(msg)

            if args.noteOverride:
                note_override = args.noteOverride
                options_dict['note_override'] = note_override
                msg = 'Specified Note Override.  '
                msg += 'Value: "{}". Type: "{}"'.format(note_override, type(note_override))
                LOGGER.info(msg)

            if args.shotsubOverride:
                shotsub_override = args.shotsubOverride
                options_dict['shotsub_override'] = shotsub_override
                msg = 'Specified Shotsub Override.  '
                msg += 'Value: "{}". Type: "{}"'.format(shotsub_override, type(shotsub_override))
                LOGGER.info(msg)

            if args.jobIdentifierOverride:
                job_identifier_override = args.jobIdentifierOverride
                options_dict['job_identifier_override'] = job_identifier_override
                msg = 'Specified Job Identifier Override.  '
                msg += 'Value: "{}". Type: "{}"'.format(job_identifier_override, type(job_identifier_override))
                LOGGER.info(msg)

            ##################################################################
            # Other

            if args.showValidationOnly:
                show_validation_only = True
                options_dict['show_validation_only'] = show_validation_only
                msg = 'Specified To List Environments From Session Data Rather That Dispatch.  '
                msg += 'Value: "{}". Type: "{}"'.format(show_validation_only, type(show_validation_only))
                LOGGER.info(msg)

            if args.jbxBucket:
                jbx_bucket = self._cleanup_command_line_string(args.jbxBucket)
                options_dict['jbx_bucket'] = jbx_bucket
                msg = 'Specified JunkBox Bucket To Cache Dispatch Results.  '
                msg += 'Value: "{}". Type: "{}"'.format(jbx_bucket, type(jbx_bucket))
                LOGGER.info(msg)

            if args.globalJbxBucket:
                global_jbx_bucket = self._cleanup_command_line_string(args.globalJbxBucket)
                options_dict['global_jbx_bucket'] = global_jbx_bucket
                msg = 'Specified Global JunkBox Bucket To Cache Dispatch Job And Task Id Results.  '
                msg += 'Value: "{}". Type: "{}"'.format(global_jbx_bucket, type(global_jbx_bucket))
                LOGGER.info(msg)

            options_dict['auto_refresh_from_shotgun'] = not bool(args.skipRefreshProductionData)

        # Validate all the specified environments (which may include index or
        # job identifier token), are actually valid oz areas.
        if args.environments:
            msg = 'Validating Environments: "{}"'.format(args.environments)
            LOGGER.warning(msg)
            validated_environments = list()
            for environment in args.environments:
                is_valid = self.validate_environment(environment)
                if is_valid:
                    validated_environments.append(environment)
                    msg = 'Environment Is Valid To Dispatch From: "{}"'.format(environment)
                    LOGGER.info(msg)
                else:
                    msg = 'Environment NOT Valid To Dispatch From: "{}"'.format(environment)
                    LOGGER.warning(msg)
            if validated_environments:
                options_dict['environments'] = validated_environments
                msg = 'Specified Valid Environments: "{}". '.format(validated_environments)
                LOGGER.info(msg)

        options_dict['debug_mode'] = bool(args.debug)
        if args.debug:
            msg = 'Debug mode enabled'
            LOGGER.info(msg)
            msg = 'Collected options dict: "{}"'.format(options_dict)
            LOGGER.info(msg)

        msg = 'FINISHED COLLECTING OPTIONS FROM COMMAND LINE\n\n'
        LOGGER.info(msg)

        return parser, options_dict


    @classmethod
    def _cleanup_command_line_string(cls, command_str):
        '''
        Remove any extra quotes from command line values.

        Args:
            command_str (str):
        '''
        return str(command_str).replace('"', str()).replace("'", str())


    @classmethod
    def validate_environment(cls, environment=os.getenv('OZ_CONTEXT')):
        '''
        Validate a single environment specified in the command line.
        Note: The environment in command line might include an additional index
        or job identifier, this needs to be stripped when checking oz area is valid.

        Args:
            environment (str):

        Returns:
            is_valid (bool):
        '''
        environment = str(environment or str())

        # If validating render pass for environment identifier, validate only rhe environment here
        if constants.IDENTIFIER_JOINER in environment:
            environment = environment.split(constants.IDENTIFIER_JOINER)[0]

        import oz
        # If index or job identifier is included in environment then only validate the area.
        # NOTE: The index or job identifier specified is later checked when session data is available.
        if '-' in environment:
            environment = environment.split('-')[0]
        # Validate the environment without the extra index or job identifier token
        if not environment or not oz.Area.is_valid(environment):
            # msg = 'Environment NOT Valid To Dispatch From: "{}"'.format(environment)
            # LOGGER.warning(msg)
            return False
        # msg = 'Environment Is Valid To Dispatch From: "{}"'.format(environment)
        # LOGGER.info(msg)
        return True