

import logging
import os


from Qt.QtWidgets import (QWidget, QFrame, QTextEdit, QLineEdit,
    QCheckBox, QSpinBox, QLabel,
    QVBoxLayout, QGridLayout, QSizePolicy)
from Qt.QtGui import QRegExpValidator
from Qt.QtCore import QSize, Signal, QRegExp

from srnd_qt.ui_framework.widgets import (
    completor_email_widget,
    group_box_collapsible)

from srnd_multi_shot_render_submitter.constants import Constants
constants = Constants()


ICONS_DIR = os.path.join(
    os.getenv('SRND_MULTI_SHOT_RENDER_SUBMITTER_ROOT', str()),
    'icons')
# SRND_QT_ROOT = os.getenv('SRND_QT_ROOT')
# SRND_QT_ICONS_DIR = os.path.join(SRND_QT_ROOT, 'res', 'icons')


##############################################################################


class JobOptionsWidget(QFrame):
    '''
    A widget to contain all Multi Shot Render Submitter Job options.
    '''

    logMessage = Signal(str, int)

    def __init__(self, parent=None):
        super(JobOptionsWidget, self).__init__(parent)

        self.setObjectName('DetailsPanel')

        self._session_options_widget = None

        self._vertical_layout_main = QVBoxLayout()
        self._vertical_layout_main.setContentsMargins(5, 5, 5, 5)
        self._vertical_layout_main.setSpacing(0)
        self.setLayout(self._vertical_layout_main)
        self.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding)

        self._build_main_options()

        self._vertical_layout_main.addSpacing(15)

        # self._build_save_session_options()

        self._vertical_layout_main.addStretch(100)

        # TODO: Later improve global styling system and reimplement
        # in srnd_katana_render_submitter repo
        if constants.IN_KATANA_UI_MODE:
            self.setStyleSheet(constants.STYLESHEET_FRAME_DETAILS_PANEL)
        else:
            self.setStyleSheet(constants.STYLESHEET_FRAME_DETAILS_PANEL_NO_BORDER)


    def _build_main_options(self):
        '''
        Build the main option widgets of Job options.
        '''
        self._layout_main_job_options = QGridLayout()
        self._layout_main_job_options.setContentsMargins(0, 0, 0, 0)
        self._layout_main_job_options.setSpacing(3)
        self._layout_main_job_options.setColumnStretch(1, 100)

        self._vertical_layout_main.addLayout(self._layout_main_job_options)

        msg = 'Either Submit The Job/s Now In The Current Application '
        msg += 'Context, Or Start A Job On The Wall Which Will Dispatch '
        msg += 'All The Required Environment/s In Separate Tasks. '

        msg += '<br><br><i>Note: Submitting Many Environment/s In The Current Application '
        msg += 'Context May Take A Long Time, Because All Environment Setup, '
        msg += 'Allocations, Product Registration Needs To Run Up Front.</i>'

        row = 0
        column = 0

        label_str = 'Dispatch on plow'
        self._checkBox_dispatch_deferred = QCheckBox(label_str)
        self._checkBox_dispatch_deferred.setToolTip(msg)
        self._checkBox_dispatch_deferred.setChecked(True)
        self._layout_main_job_options.addWidget(
            self._checkBox_dispatch_deferred, row, column, 1, 1)
        self._checkBox_dispatch_deferred.setVisible(
            constants.EXPOSE_DISPATCH_DEFERRED)
        column += 1

        msg = 'When <b>Dispatch On Plow</b> Is Enabled, Optionally Snapshot '
        msg += 'The Current Project Before Starting The Dispatch Job. '

        # msg += '<br><br><i>Note: If Render Overrides Are Available And '
        # msg += '<b>Apply Render Overrides</b> Is Enabled, Then The Project '
        # msg += 'Is Always Snapshot Despite This Option, Since It Varies From Current State.</i>'

        msg += '<br><br><i>Note: Enabling This Option Will Increase The '
        msg += 'Time It Takes For The Dispatch Job To Be Created In Plow.</i>'

        msg += '<br><br><i>Note: Only Disable This Option If The Current '
        msg += 'Project Isn\'t Likely To Be Saved Again, With Removed '
        msg += 'Renderables In The Next Short While. Otherwise the Dispatcher '
        msg += 'Job On The Wall May Access The Project The User Just Saved Again, '
        msg += 'And Not Be Able To Successfully Dispatch A Particular Renderable.</i>'

        label_str = 'Snapshot before'
        self._checkBox_snapshot_before_dispatch = QCheckBox(label_str)
        self._checkBox_snapshot_before_dispatch.setToolTip(msg)
        self._checkBox_snapshot_before_dispatch.setChecked(True)
        self._layout_main_job_options.addWidget(
            self._checkBox_snapshot_before_dispatch, row, column, 1, 1)
        self._checkBox_snapshot_before_dispatch.setVisible(
            constants.EXPOSE_DISPATCH_DEFERRED)
        row += 1

        self._checkBox_dispatch_deferred.toggled.connect(
            self._checkBox_snapshot_before_dispatch.setEnabled)

        column = 0

        label_str = 'Launch jobs paused'
        msg = 'Whether To Launch All Jobs PAUSED Or Not.'
        self._checkBox_launch_paused = QCheckBox(label_str)
        self._checkBox_launch_paused.setToolTip(msg)
        self._checkBox_launch_paused.setChecked(False)
        self._layout_main_job_options.addWidget(
            self._checkBox_launch_paused, row, column, 1, 1)
        column += 1

        msg = 'If Launching Jobs PAUSED Then Optionally Specify When To Expire '
        msg += 'The Paused State And Start Rendering. '
        msg += '<br><i>Note: If The Value Is Kept As Default Of {}, '.format(
            constants.LAUNCH_PAUSED_EXPIRES)
        msg += 'Then No Expire Time Is Specified To Plow Job.</i>'
        self._spinBox_launch_paused_expire = QSpinBox()
        self._spinBox_launch_paused_expire.setToolTip(msg)
        self._spinBox_launch_paused_expire.setMinimum(0)
        self._spinBox_launch_paused_expire.setMaximum(99999)
        self._spinBox_launch_paused_expire.setValue(constants.LAUNCH_PAUSED_EXPIRES)
        self._spinBox_launch_paused_expire.setSuffix(' min')
        self._spinBox_launch_paused_expire.setEnabled(False)
        self._spinBox_launch_paused_expire.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Expanding)
        self._layout_main_job_options.addWidget(
            self._spinBox_launch_paused_expire, row, column, 1, 1)
        row += 1

        self._checkBox_launch_paused.toggled.connect(
            self._spinBox_launch_paused_expire.setEnabled)

        column = 0

        label_str = 'Launch zero tier'
        msg = 'Whether To Apply managerJobAttributes "customTier" To "Zero"'
        self._checkBox_launch_zero_tier = QCheckBox(label_str)
        self._checkBox_launch_zero_tier.setToolTip(msg)
        self._checkBox_launch_zero_tier.setChecked(False)
        self._layout_main_job_options.addWidget(
            self._checkBox_launch_zero_tier, row, column, 1, 1)
        row += 1

        label_str = 'Apply dependencies'
        msg = 'Optionally Apply Any Defined WAIT On Dependencies Or Not When Submitting Job/s. '
        msg += '<br><i>Note: Some Job/s Will Automatically Remain PAUSED Until '
        msg += 'All Depedendices Are Finished Being Applied, And Then Be Auto Unpaused.</i>'
        self._checkBox_apply_dependencies = QCheckBox(label_str)
        self._checkBox_apply_dependencies.setToolTip(msg)
        self._checkBox_apply_dependencies.setChecked(True)
        self._layout_main_job_options.addWidget(
            self._checkBox_apply_dependencies, row, column, 1, 1)
        column += 1

        label_str = 'Apply render overrides'
        msg = 'Whether To Apply Any Render Overrides To Host App Project When Submitting (If Any). '
        msg += '<br><i>Note: Render Overrides Are Typically Shown In Light Blue Colour In MSRS View.</i>'
        self._checkBox_apply_render_overrides = QCheckBox(label_str)
        self._checkBox_apply_render_overrides.setToolTip(msg)
        self._checkBox_apply_render_overrides.setChecked(True)
        self._layout_main_job_options.addWidget(
            self._checkBox_apply_render_overrides, row, column, 1, 1)
        row += 1

        ######################################################################

        self._vertical_layout_main.addSpacing(10)

        grid_layout = QGridLayout()
        grid_layout.setContentsMargins(0, 0, 0, 0)
        grid_layout.setSpacing(3)
        self._vertical_layout_main.addLayout(grid_layout)
        row = 0

        # Add widget to pick additional email recipients
        label = QLabel('Email users')
        label.setFont(constants.PANEL_FONT_REGULAR)
        grid_layout.addWidget(label, row, 0)
        self._lineEdit_email_additional_users = completor_email_widget.EmailCompletorWidget(
            default_entries=constants.DEFAULT_EMAIL_ADDITIONAL_USERS,
            include_label=False)
        grid_layout.addWidget(
            self._lineEdit_email_additional_users, row, 1)
        row += 1

        # Add optional extra job identifier widget
        label = QLabel('Global job\nidentifier')
        label.setFont(constants.PANEL_FONT_REGULAR)
        grid_layout.addWidget(label, row, 0)
        self._lineEdit_additional_job_identifier = QLineEdit()
        validator = QRegExpValidator()
        validator.setRegExp(QRegExp('[A-Za-z0-9_]+'))
        self._lineEdit_additional_job_identifier.setValidator(validator)

        grid_layout.addWidget(
            self._lineEdit_additional_job_identifier, row, 1)
        row += 1

        # Add optional global description wudget
        label = QLabel('Global submit\ncomment')
        label.setFont(constants.PANEL_FONT_REGULAR)
        grid_layout.addWidget(label, row, 0)
        self._textEdit_global_submit_description = QTextEdit()
        self._textEdit_global_submit_description.setAcceptRichText(False)
        self._textEdit_global_submit_description.setFixedHeight(60)
        grid_layout.addWidget(
            self._textEdit_global_submit_description, row, 1)
        row += 1

        self._checkbox_send_email = QCheckBox('Send summary email')
        self._checkbox_send_email.setChecked(True)
        grid_layout.addWidget(self._checkbox_send_email, row, 0)
        row += 1


    def get_content_widget_layout(self):
        '''
        Get this MultiShotDetailsWidget main layout.

        Returns:
            horizontal_layout (QVBoxLayout):
        '''
        return self._vertical_layout_main


    def sizeHint(self):
        '''
        Return the size this widget should be.
        '''
        return QSize(constants.JOB_OPTIONS_EDITOR_WIDTH, 140)


    def get_layout_main_job_options(self):
        return self._layout_main_job_options

    def get_email_additional_users_widget(self):
        return self._lineEdit_email_additional_users

    def get_global_submit_description_widget(self):
        return self._textEdit_global_submit_description

    def get_send_summary_email_on_submit(self):
        return self._checkbox_send_email

    def get_global_job_identifier_widget(self):
        return self._lineEdit_additional_job_identifier

    def get_dispatch_deferred_widget(self):
        return self._checkBox_dispatch_deferred

    def get_snapshot_before_dispatch_widget(self):
        return self._checkBox_snapshot_before_dispatch

    def get_launch_paused_widget(self):
        return self._checkBox_launch_paused

    def get_launch_paused_expires_widget(self):
        return self._spinBox_launch_paused_expire

    def get_launch_zero_tier_widget(self):
        return self._checkBox_launch_zero_tier

    def get_apply_render_overrides_widget(self):
        return self._checkBox_apply_render_overrides

    def get_apply_dependencies_widget(self):
        return self._checkBox_apply_dependencies