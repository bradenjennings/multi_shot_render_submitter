

import os
import traceback

from Qt.QtWidgets import QWidget, QVBoxLayout
from Qt.QtCore import Signal, QSize


class ValidationSystemBase(QWidget):
    '''
    An adapter object to interact with different validation / preflight systems
    and associated UI, using a consistent generic interface.
    TODO: May want to convert this to abstract interface later on...

    Args:
        threaded (bool): use threading or not if the system support it
    '''

    logMessage = Signal(str, int)
    envValidationComplete = Signal(dict, bool, str)

    def __init__(self, threaded=True, parent=None):
        super(ValidationSystemBase, self).__init__(parent=parent)

        self._threaded = bool(threaded)
        self._is_interrupted = False
        self._validation_widget = None

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setLayout(layout)


    def build_validation_objects(self, environments=list(), nodes=list()):
        '''
        Build the validation / preflight system and widget (if any).
        Must be reimplemented to return build the host app specific validation objects.

        Args:
            environments (list):
            nodes (list): nodes to run validation / preflight on per environment

        Returns:
            validation_object (object):
                Note: Validation UI objects can be cached as private members.
        '''
        return


    def has_validation_system(self):
        '''
        Return whether a validation / preflight system is available.
        Must be reimplemented to return whether validation object is available.

        Returns:
            has_validation_system (bool):
        '''
        return False


    def get_validation_widget(self):
        '''
        Get the validation visual widget.

        Returns:
            validation_system (QWidget): or subclass
        '''
        return self._validation_widget


    def setup(self, environments=list(), nodes=list(), test=False):
        '''
        Request the preflight system to run validations,
        on a environment/s and particular nodes.

        Args:
            environments (list): list of oz areas
            nodes (list): list of host app render nodes
            test (bool): optionally include test / example validation data
        '''
        return


    def run_checks(self):
        '''
        Request the preflight system to run validations,
        on a single environment and particular nodes.
        Requires reimplementation for particular host app.
        '''
        return


    def get_critical_and_warning_count(self, oz_area=os.getenv('OZ_CONTEXT')):
        '''
        Get the critical and warning count from just run validation.

        Args:
            oz_area (str): which environment to get results from.

        Returns:
            critical_count, warning_count (tuple): two ints
        '''
        return 0, 0


    def filter_view_to_environments(self, environments=None):
        '''
        Filter the validation system view to particular environments.
        Requires reimplementation for particular host app.

        Args:
            environments (list):
        '''
        return


    def request_interrupt(self):
        '''
        Request an interrupt.
        Requires reimplementation to stop process.
        '''
        self._is_interrupted = True


    def is_interrupted(self):
        '''
        Whether validation was interrupted.
        Requires reimplementation for particular host app.

        Returns:
            is_interrupted (bool):
        '''
        return self._is_interrupted


    def sizeHint(self):
        '''
        Return initial suggested size for this widget
        '''
        return QSize(500, 500)