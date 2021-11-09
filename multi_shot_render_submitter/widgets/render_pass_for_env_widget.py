

import collections
import os


from Qt.QtWidgets import QWidget, QSizePolicy
from Qt.QtGui import (QPainter, QBrush, QColor, QPen, QIcon,
    QFont, QFontMetrics, QPixmap)
from Qt.QtCore import (Qt, QRect, QRectF, QPoint, QSize, Signal)

from srnd_multi_shot_render_submitter.constants import Constants
constants = Constants()


##############################################################################
# Unique constants to this module


CELL_MARGINS = 3

STATUSWIDGET_DISPLAY_TEXT_START_HOFFSET = 4
STATUSWIDGET_HORIZONTAL_MARGINS = 3
STATUSWIDGET_VERTICAL_MARGINS = 3
STATUSWIDGET_STATUS_PADDING_H = 4
STATUSWIDGET_STATUS_PADDING_V = 3
STATUSWIDGET_STATUS_GAP_WIDTH = 3
STATUSWIDGET_STATUS_DOT_DOT = '..'
STATUSWIDGET_STATUS_DOT_DOT_WIDTH = 20
STATUSWIDGET_MINIMUM_WIDTH_BEFORE_COLLAPSE_ALL = 40
STATUSWIDGET_DISABLED_HINT_WIDTH = 8

PIXMAP_HEIGHT = 20
THUMBNAIL_HEIGHT = 46
FALLBACK_WIDTH = 160
FALLBACK_HEIGHT = 90

NAME_KEY = 'label'
CATEGORY_KEY = 'category'
COLOUR_KEY = 'colour'
PIXMAP_KEY = 'pixmap'
BOUNDS_KEY = 'rect'
SIZE_KEY = 'size'
MAX_CHARS = 14

ICONS_DIR = os.path.join(
    os.getenv('SRND_MULTI_SHOT_RENDER_SUBMITTER_ROOT', str()),
    'icons')
LOADING_GIF_PATH = os.path.join(ICONS_DIR, 'loading_18x18_s01.gif')


##############################################################################


class RenderPassForEnvWidget(QWidget):
    '''
    A widget which represents a render pass for env, or the environment itself.
    Note: It is desired to cache as little as possible on this widget, since it
    can be created a large number of times in a hierarchical tree view.

    Args:
        display_label (str):
        queued (bool):
        enabled (bool):
        is_pass (bool):
        include_thumbnail (bool):
        thumbnail_path (str):
        thumbnail_qmovie (QMovie):
        background_colour (tuple): optionally choose background colour of this widget when active
        debug_mode (bool):
    '''

    queuedToggled = Signal(bool)
    enabledToggled = Signal(bool)

    def __init__(
            self,
            display_label=str(),
            queued=True,
            enabled=True,
            is_pass=True,
            include_thumbnail=False,
            thumbnail_path=None,
            thumbnail_qmovie=None,
            debug_mode=False,
            parent=None):
        super(RenderPassForEnvWidget, self).__init__(parent=parent)

        self._horizontal_layout = None

        self._is_pass = bool(is_pass)
        self._has_renderables = True
        self._is_selected = False
        self._is_processing = False
        self._process_msg = str()
        self._render_progress = None

        if not self._is_pass:
            self._display_label = str(display_label or str())
            self._queued = bool(queued)
            self._enabled = bool(enabled)
            if include_thumbnail:
                self._create_shotsub_thumbnail(
                    thumbnail_qmovie=thumbnail_qmovie,
                    thumbnail_path=thumbnail_path)

        # NOTE: Cache minimal details for applied overrides for paint event.
        self._overrides = collections.OrderedDict()

        self._view = self.parent().parent()


    ##########################################################################
    # Build widget and any children


    def _create_layout(self):
        '''
        Create a layout for this widget on demand.
        '''
        if not self._horizontal_layout:
            from Qt.QtWidgets import QHBoxLayout
            self._horizontal_layout = QHBoxLayout()
            self._horizontal_layout.setContentsMargins(0, 0, 0, 0)
            self.setLayout(self._horizontal_layout)
            self._horizontal_layout.addStretch(100)


    def _create_shotsub_thumbnail(
            self,
            thumbnail_qmovie=None,
            thumbnail_path=None):
        '''
        Create shotsub thumbnail child widget for this widget on demand.

        Args:
            thumbnail_qmovie (QMovie):
            thumbnail_path (str):
        '''
        self._create_layout()
        from Qt.QtWidgets import QLabel
        self._label_for_thumbnail_movie = QLabel(parent=self)
        stylesheet = 'padding: 2px 2px 2px 2px;background-color: black'
        self._label_for_thumbnail_movie.setStyleSheet(stylesheet)
        self._horizontal_layout.addWidget(self._label_for_thumbnail_movie)
        self.set_thumbnail_movie(
            thumbnail_qmovie=thumbnail_qmovie,
            thumbnail_path=thumbnail_path)


    def set_thumbnail_movie(
            self,
            thumbnail_qmovie=None,
            thumbnail_path=None):
        '''
        Set the thumbnail for the child QLabel to an existing
        QMovie, or generate a new QMovie for the qgiven thumbnail path.

        Args:
            thumbnail_qmovie (QMovie):
            thumbnail_path (QMovie):
        '''
        widget = self.get_thumbnail_movie_container_widget()
        if not widget:
            return
        from Qt.QtGui import QMovie
        if thumbnail_qmovie and isinstance(thumbnail_qmovie, QMovie):
            widget.setMovie(thumbnail_qmovie)
            widget.setFixedSize(thumbnail_qmovie.scaledSize())
            if thumbnail_qmovie.state() == QMovie.NotRunning:
                thumbnail_qmovie.start()
        elif thumbnail_path:
            is_gif = thumbnail_path.endswith('.gif')
            if is_gif:
                thumbnail_qmovie = QMovie(thumbnail_path)
                thumbnail_qmovie.jumpToFrame(0)
                rect = thumbnail_qmovie.frameRect()
            else:
                pixmap = QPixmap(thumbnail_path)
                rect = pixmap.rect()

            aspect =  float(rect.width() or FALLBACK_WIDTH) / (rect.height() or FALLBACK_HEIGHT)
            _thumbnail_width = (THUMBNAIL_HEIGHT - 2) * aspect
            _thumbnail_height = THUMBNAIL_HEIGHT - 2
            size = QSize(_thumbnail_width, _thumbnail_height)
                
            if is_gif:
                thumbnail_qmovie.setScaledSize(size)
                widget.setMovie(thumbnail_qmovie)
                widget.setFixedSize(thumbnail_qmovie.scaledSize())
                thumbnail_qmovie.setCacheMode(QMovie.CacheAll)
                thumbnail_qmovie.setSpeed(100)
                thumbnail_qmovie.start()
            else:
                pixmap = pixmap.scaledToHeight(_thumbnail_height, Qt.SmoothTransformation)
                widget.setPixmap(pixmap)                                
        else:
            aspect = 1.77
            height = THUMBNAIL_HEIGHT - 2
            width = (THUMBNAIL_HEIGHT * aspect) - 2
            widget.setFixedSize(width, height)


    def get_thumbnail_movie_container_widget(self):
        '''
        Get the container widget which thumbnail QMovie will be applied to.

        Returns:
            label (QLabel):
        '''
        if hasattr(self, '_label_for_thumbnail_movie'):
            return self._label_for_thumbnail_movie


    ##########################################################################


    def add_override(
            self,
            key,
            label=str(),
            max_chars=MAX_CHARS,
            category=str(),
            colour=None,
            icon=None):
        '''
        Add an override by key to this render pass for env widget.

        Args:
            key (str):
            label (str):
            max_chars (int):
            category (str):
            colour (QColor):
            icon (QIcon):

        Returns:
            override_info (dict): information about the override just added
        '''
        if not key or not isinstance(key, basestring):
            return
        key = str(key)
        self._overrides[key] = dict()
        if label and isinstance(label, basestring):
            self._overrides[key][NAME_KEY] = str(label)
        elif len(key) > max_chars:
            # Truncate the diplay text within this method (avoiding excess method calls)
            truncated_name = self._compute_truncated_display_name(
                key,
                max_chars=max_chars)
            if truncated_name != key:
                self._overrides[key][NAME_KEY] = truncated_name
        if category and isinstance(category, basestring):
            self._overrides[key][CATEGORY_KEY] = str(category)
        if isinstance(colour, QColor):
            self._overrides[key][COLOUR_KEY] = colour
        if isinstance(icon, QIcon):
            self._overrides[key][PIXMAP_KEY] = icon
        return self._overrides.get(key)


    def remove_override(self, key):
        '''
        Remove the override with key (if previously added)
        from this render pass for env widget.

        Args:
            key (str):

        Returns:
            override_info (dict): the override info just removed.
                Or return None if not availble to remove.
        '''
        if not key or not isinstance(key, basestring):
            return
        key = str(key)
        if self._overrides.get(key):
            return self._overrides.pop(key)


    def has_override(self, key):
        '''
        Check whether override by key has been added.

        Args:
            key (str):

        Returns:
            has_override (bool):
        '''
        return bool(self._overrides.get(key))


    def update_overrides_from_item(self, item=None, model=None):
        '''
        Cache states of MSRS data object on to widget, and also
        formulate a new mapping of all overrides details that require painting.

        Args:
            item (OverrideBaseItem): render pass for env or environment item
            model (MultiShotRenderModel): pass the model in case some specific
                configuration options needs to be queried.

        Returns:
            overrides (dict): the overrides details just cached on to this widget
        '''
        frame_range_override = None
        not_frame_range_override = None
        frames_rule_important = None
        frames_rule_fml = None
        frames_rule_x1 = None
        frames_rule_x10 = None
        frames_rule_xn = None
        not_frames_rule_important = None
        not_frames_rule_fml = None
        not_frames_rule_x10 = None
        not_frames_rule_xn = None
        version_override = None
        note_override = None
        wait_on = None
        wait_on_plow_ids = None
        colour = None
        job_identifier = None
        split_frame_ranges = None

        ######################################################################
        # Get values from MSRS data object

        if item:
            is_environment_item = item.is_environment_item()
            environment_item = item if is_environment_item else item.get_environment_item()

            frame_range_override = item.get_frame_range_override()
            not_frame_range_override = item.get_not_frame_range_override()
            frames_rule_important = item.get_frames_rule_important()
            frames_rule_fml = item.get_frames_rule_fml()
            frames_rule_x1 = item.get_frames_rule_x1()
            frames_rule_x10 = item.get_frames_rule_x10()
            frames_rule_xn = item.get_frames_rule_xn()
            not_frames_rule_important = item.get_not_frames_rule_important()
            not_frames_rule_fml = item.get_not_frames_rule_fml()
            not_frames_rule_x10 = item.get_not_frames_rule_x10()
            not_frames_rule_xn = item.get_not_frames_rule_xn()
            version_override = item.get_version_override()
            note_override = item.get_note_override()
            wait_on = item.get_wait_on()
            wait_on_plow_ids = item.get_wait_on_plow_ids()
            colour = item.get_colour()
            is_selected = item.get_is_selected_in_msrs()

            self._colour = colour
            self._is_selected = bool(is_selected)

            if is_environment_item:
                job_identifier = item.get_job_identifier()
                split_frame_ranges = item.get_split_frame_ranges()
                # Update display label
                if model:
                    if model.get_show_full_environments():
                        self._display_label = item.get_oz_area()
                    else:
                        self._display_label = item.get_scene_shot_area()
                # Force environment to look unqueued if no active passes to render
                has_renderables = bool(environment_item._get_renderable_count_for_env())
                self.set_has_renderables(has_renderables)
            else:
                self._queued = bool(item.get_queued())
                self._enabled = bool(item.get_enabled())
                self._render_progress = item.get_render_progress()

        ######################################################################
        # Now formulate a cache of overrides which are to be painted and have cached bounds

        # NOTE: Formulating all overrides manually here at once,
        # rather than calling add_override multiple times.

        # self.clear_all_overrides()
        self._overrides = collections.OrderedDict()

        if version_override:
            self._overrides['Version'] = dict()
            if version_override and isinstance(version_override, int):
                self._overrides['Version'][NAME_KEY] = 'v{}'.format(version_override)
            else:
                self._overrides['Version'][NAME_KEY] = str(version_override)
            # key = 'Version'
            # self.add_override(key, label=NAME_KEY)

        if frame_range_override:
            frame_range_override = self._compute_truncated_display_name(frame_range_override)
            self._overrides[constants.OVERRIDE_FRAMES_CUSTOM] = dict()
            self._overrides[constants.OVERRIDE_FRAMES_CUSTOM][NAME_KEY] = frame_range_override

        if not_frame_range_override:
            not_frame_range_override = self._compute_truncated_display_name(
                not_frame_range_override)
            if not not_frame_range_override.startswith('NOT'):
                not_frame_range_override = 'NOT ' + not_frame_range_override
            self._overrides[constants.OVERRIDE_FRAMES_NOT_CUSTOM] = dict()
            self._overrides[constants.OVERRIDE_FRAMES_NOT_CUSTOM][NAME_KEY] = not_frame_range_override
            self._overrides[constants.OVERRIDE_FRAMES_NOT_CUSTOM][COLOUR_KEY] = self._view.get_override_standard_not_colour()

        if frames_rule_important:
            self._overrides[constants.OVERRIDE_FRAMES_IMPORTANT] = dict()

        if frames_rule_fml:
            self._overrides[constants.OVERRIDE_FRAMES_FML] = dict()

        if frames_rule_x1:
            self._overrides[constants.OVERRIDE_FRAMES_X1] = dict()

        if frames_rule_x10:
            self._overrides[constants.OVERRIDE_FRAMES_X10] = dict()

        if frames_rule_xn:
            self._overrides[constants.OVERRIDE_FRAMES_XCUSTOM] = dict()
            self._overrides[constants.OVERRIDE_FRAMES_XCUSTOM][NAME_KEY] = 'x{}'.format(frames_rule_xn)

        if not_frames_rule_important:
            self._overrides[constants.OVERRIDE_FRAMES_NOT_IMPORTANT] = dict()
            self._overrides[constants.OVERRIDE_FRAMES_NOT_IMPORTANT][COLOUR_KEY] = self._view.get_override_standard_not_colour()

        if not_frames_rule_fml:
            self._overrides[constants.OVERRIDE_FRAMES_NOT_FML] = dict()
            self._overrides[constants.OVERRIDE_FRAMES_NOT_FML][COLOUR_KEY] = self._view.get_override_standard_not_colour()

        if not_frames_rule_x10:
            self._overrides[constants.OVERRIDE_FRAMES_NOT_X10] = dict()
            self._overrides[constants.OVERRIDE_FRAMES_NOT_X10][COLOUR_KEY] = self._view.get_override_standard_not_colour()

        if not_frames_rule_xn:
            self._overrides[constants.OVERRIDE_FRAMES_NOT_XCUSTOM] = dict()
            self._overrides[constants.OVERRIDE_FRAMES_NOT_XCUSTOM][NAME_KEY] = 'NOT x{}'.format(not_frames_rule_xn)
            self._overrides[constants.OVERRIDE_FRAMES_NOT_XCUSTOM][COLOUR_KEY] = self._view.get_override_standard_not_colour()

        if split_frame_ranges:
            self._overrides[constants.OVERRIDE_SPLIT_FRAME_RANGES] = dict()
            self._overrides[constants.OVERRIDE_SPLIT_FRAME_RANGES][NAME_KEY] = 'Note'
            self._overrides[constants.OVERRIDE_SPLIT_FRAME_RANGES][PIXMAP_KEY] = QPixmap(constants.SPLIT_FRAMES_ICON_PATH)

        if note_override:
            self._overrides[constants.OVERRIDE_NOTE] = dict()
            self._overrides[constants.OVERRIDE_NOTE][NAME_KEY] = 'Note'
            self._overrides[constants.OVERRIDE_NOTE][PIXMAP_KEY] = QPixmap(constants.NOTE_ICON_PATH)

        if job_identifier:
            self._overrides[constants.OVERRIDE_JOB_IDENTIFIER] = dict()
            self._overrides[constants.OVERRIDE_JOB_IDENTIFIER][NAME_KEY] = job_identifier
            self._overrides[constants.OVERRIDE_JOB_IDENTIFIER][COLOUR_KEY] = self._view.get_job_override_colour()

        if any([wait_on, wait_on_plow_ids]):
            self._overrides[constants.OVERRIDE_WAIT] = dict()
            self._overrides[constants.OVERRIDE_WAIT][NAME_KEY] = 'WAIT'
            self._overrides[constants.OVERRIDE_WAIT][PIXMAP_KEY] = QPixmap(constants.WAIT_ICON_PATH)

        ######################################################################
        # Also get render overrides details which are to be painted and have cached bounds

        if item:
            render_override_statuses = self.update_render_overrides_from_item(item)
            if render_override_statuses:
                self._overrides.update(render_override_statuses)

        return self._overrides


    @classmethod
    def get_session_key_for_override(cls, override_key):
        '''
        For core overrides the key is typically used to store the display label.
        To avoid caching any extra data.
        So this method can be used to get the actual override id, which
        is also the MSRS session key.
        NOTE: Render overrides always use the override id as key.

        Args:
            override_key (str): override display label / key of this widget

        Returns:
            session_key (str): MSRS stores the override in session data with this key
        '''
        # TODO: Use the constants module to get key in the future..
        # Not all details are in constants yet...
        session_key = None
        if override_key == constants.OVERRIDE_FRAMES_CUSTOM:
            session_key = 'frame_range_override'
        elif override_key == constants.OVERRIDE_FRAMES_IMPORTANT:
            session_key = 'frames_rule_important'
        elif override_key == constants.OVERRIDE_FRAMES_FML:
            session_key = 'frames_rule_fml'
        elif override_key == constants.OVERRIDE_FRAMES_X1:
            session_key = 'frames_rule_x1'
        elif override_key == constants.OVERRIDE_FRAMES_X10:
            session_key = 'frames_rule_x10'
        elif override_key == constants.OVERRIDE_FRAMES_XCUSTOM:
            session_key = 'frames_rule_xn'
        elif override_key == constants.OVERRIDE_FRAMES_NOT_CUSTOM:
            session_key = 'not_frame_range_override'
        elif override_key == constants.OVERRIDE_FRAMES_NOT_IMPORTANT:
            session_key = 'not_frames_rule_important'
        elif override_key == constants.OVERRIDE_FRAMES_NOT_FML:
            session_key = 'not_frames_rule_fml'
        elif override_key == constants.OVERRIDE_FRAMES_NOT_X10:
            session_key = 'not_frames_rule_x10'
        elif override_key == constants.OVERRIDE_FRAMES_NOT_XCUSTOM:
            session_key = 'not_frames_rule_xn'
        elif override_key == constants.OVERRIDE_NOTE:
            session_key = 'note_override'
        elif override_key == constants.OVERRIDE_NOTE:
            session_key = 'note_override'
        elif override_key == constants.OVERRIDE_WAIT:
            session_key = constants.SESSION_KEY_WAIT_ON
        elif override_key == constants.OVERRIDE_JOB_IDENTIFIER:
            session_key = 'job_identifier'
        elif override_key == constants.OVERRIDE_SPLIT_FRAME_RANGES:
            session_key = 'split_frame_ranges'
        elif override_key == 'Version':
            session_key = 'version_override'
        elif override_key == 'MSRS_Colour':
            session_key = 'colour'
        # NOTE: Return the existing override key for render overrides
        return session_key or override_key


    def update_render_overrides_from_item(self, item):
        '''
        Collect all render override statuses and cache on this widget

        Args:
            item (OverrideBaseItem): render pass for env or environment item subclass

        Returns:
            render_override_statuses (collections.OrderedDict()):
        '''
        if not any([item.is_environment_item(), item.is_pass_for_env_item()]):
            return list()


        render_overrides_items = item.get_render_overrides_items()

        # NOTE: All overrides are placed and painted from right to left, so reverse order of render overrides
        render_override_statuses = collections.OrderedDict()
        for override_id in reversed(render_overrides_items.keys()):
            render_override_item = render_overrides_items[override_id]
            # override_label = render_override_item.get_override_label()
            # override_type = render_override_item.get_override_type()
            override_icon_path = render_override_item.get_override_icon_path()
            use_override_icon_in_view = render_override_item.get_use_override_icon_in_view()
            display_str = render_override_item.get_view_display_value()

            render_override_statuses[override_id] = dict()
            render_override_statuses[override_id][NAME_KEY] = display_str
            if use_override_icon_in_view and override_icon_path and os.path.isfile(override_icon_path):
                render_override_statuses[override_id][PIXMAP_KEY] = QPixmap(override_icon_path)

            override_colour = render_override_item.get_override_colour()
            if override_colour and isinstance(override_colour, (tuple, list)) and len(override_colour) == 3:
                render_override_statuses[override_id][COLOUR_KEY] = list(override_colour)
            else:
                render_override_statuses[override_id][COLOUR_KEY] = self._view.get_render_override_standard_colour()

        return render_override_statuses


    def clear_all_overrides(self):
        '''
        Clear all overrides at once.
        NOTE: This doesn't reset the states of this widget.
        '''
        self._overrides = collections.OrderedDict()


    def get_all_overrides_infos(self):
        '''
        Get the complete overrides info details as dictionary mapping of
        override key to each override info.

        Returns:
            overrides (collections.OrderedDict):
                mapping of override key to each override info
        '''
        return self._overrides


    def get_override_info(self, key):
        '''
        Get the override info dictionary for the key (if previously added).

        Args:
            key (str):

        Returns:
            override_info (dict): information about the override if found.
        '''
        if not key or not isinstance(key, basestring):
            return
        return self._overrides.get(str(key))


    def get_all_overrides_by_category(self, category_name):
        '''
        Get the override info dictionary for the target override
        display text (if previously added).

        Args:
            category_name (str): if blank string is provided then
                get all override details with no category set

        Returns:
            overrides_list (list): list of overrides info dictionaries
        '''
        if not category_name or not isinstance(category_name, basestring):
            return
        category_name = str(category_name)
        overrides_list = list()
        for key in self._overrides.keys():
            override_info = self._overrides[key]
            if override_info.get(CATEGORY_KEY) == category_name:
                overrides_list.append(override_info)
        return overrides_list


    def _get_override_info_at_qpoint(self, qpoint):
        '''
        Traverse over overrides infos and cached QRect objects,
        and test for intersection with QPoint.

        Args:
            qpoint (QPoint):

        Returns:
            override_id, overrides_info (tuple): the override id ,
                and override info found by intersection (if any)
        '''
        for override_id in self._overrides.keys():
            rect = self._overrides[override_id].get(BOUNDS_KEY)
            if rect and rect.contains(qpoint):
                return override_id, self._overrides[override_id]
        return None, dict()


    def _destroy_cached_transform_info(self):
        '''
        Destroy any cached transform info from last paint event that might
        be queried by other methods later on.
        '''
        for key in self._overrides.keys():
            if SIZE_KEY in self._overrides[key].keys():
                self._overrides[key].pop(SIZE_KEY)
            if BOUNDS_KEY in self._overrides[key].keys():
                self._overrides[key].pop(BOUNDS_KEY)


    ##########################################################################


    @classmethod
    def _compute_truncated_display_name(cls, frame_rule, max_chars=MAX_CHARS):
        '''
        Shorten the frame range if to long.

        Args:
            frame_rule (str):
            max_chars (int):

        Returns:
            short_frame_rule (str):
        '''
        if 'First' in frame_rule:
            frame_rule = 'FML'
        elif 'Important' in frame_rule:
            frame_rule = 'Important'
        elif len(frame_rule) > max_chars:
            frame_rule = frame_rule[:max_chars] + '..'
        return frame_rule


    def _modify_font_for_status_str(self, font, display_text, rect_width, count):
        '''
        Scale a QFont up or down depending on display text, QRect, and total override count.

        Args:
            font (QFont):
            display_text (str):
            rect_width (int):
            count (int):
        '''
        character_count = len(display_text)
        if rect_width > 175:
            font.setPointSize(9)
        elif rect_width > 150:
            font.setPointSize(8)
        elif character_count > 9 and count >= 3:
            font.setPointSize(7)
        elif character_count < 4:
            font.setPointSize(9)
        else:
            font.setPointSize(8)
        return font


    ##########################################################################
    # Cell states


    def get_queued(self):
        '''
        Get whether render pass for env is queued or not.

        Returns:
            queued (str):
        '''
        if self._is_pass:
            return self._queued
        return True


    def set_queued(self, queued):
        '''
        Set whether render pass for env is queued or not.

        Args:
            queued (str):
        '''
        if self._is_pass:
            self._queued = bool(queued)


    def get_enabled(self):
        '''
        Get whether render pass for env is enabled or not.

        Returns:
            enabled (str):
        '''
        if self._is_pass:
            return self._enabled
        return True


    def set_enabled(self, enabled):
        '''
        Set whether render pass for env is enabled or not.

        Args:
            enabled (str):
        '''
        if self._is_pass:
            self._enabled = bool(enabled)


    def get_display_label(self):
        '''
        Get the display label if this widget is for environment item.

        Returns:
            value (bool):
        '''
        if not self._is_pass:
            return self._display_label
        return str()


    def set_display_label(self, value):
        '''
        Set the display label if this widget is for environment item.

        Args:
            value (bool):
        '''
        if not self._is_pass:
            self._display_label = str(value or str())

    def set_is_selected(self, value):
        '''
        Set whether this widget is selected or not, which changes the paint event.

        Args:
            value (bool):
        '''
        self._is_selected = bool(value)


    def set_has_renderables(self, value):
        '''
        Set whether this widget is queued and enabled, or some of the child passes are.

        Args:
            value (bool):
        '''
        self._has_renderables = bool(value)
        self._queued = bool(self._has_renderables)


    def set_is_processing(self, value):
        '''
        Set this widget to processing state so it can be painted differently.

        Args:
            value (bool):
        '''
        self._is_processing = bool(value)


    def set_process_msg(self, msg='Processing...'):
        '''
        Set a message to display in this widget during MSRS submission.

        Args:
            msg (str):
        '''
        self._process_msg = str(msg or str())


    def has_shotsub_thumnail(self):
        '''
        Return whether this widget has a child widget containing a
        Shotsub thumbnail QMovie.

        Returns:
            has_shotsub_thumnail (bool):
        '''
        if not self._is_pass:
            return hasattr(self, '_label_for_thumbnail_movie')
        return False


    def get_render_progress(self):
        '''
        Get the current render progress percent (if any).
        If None then the render progress is not shown on the left of this widget.

        Returns:
            render_progress (int):
        '''
        return self._render_progress


    def get_colour(self):
        '''
        Get a colour to display as a notch within left corner of this widget (if any).

        Returns:
            colour (list): RGB list
        '''
        return self._colour

    ##########################################################################


    def paintEvent(self, event):
        '''
        Paint the background with some padding.

        Args:
            event (QtCore.QEvent):
        '''
        # Destroy any cached transform info from last paint event.
        self._destroy_cached_transform_info()

        rect = event.rect()
        # NOTE: This paint event rect is intersected with the visible viewport.
        # Therefore for columns on the edge of the screen, this would cause the
        # internal overrides to be drawn in the reduced rectangle space.
        # So force the rect to be resized from the left edge, to the size of this widget,
        rect.setWidth(self.width())
        if self.has_shotsub_thumnail():
            # width = self._label_for_thumbnail_movie.width()
            # if width:
            rect = rect.adjusted(0, 0, -self._label_for_thumbnail_movie.width() - 4, 0)
        rect_width = rect.width()

        ######################################################################
        # TODO This part can be cached in future between paint operations

        is_queued = self.get_queued()
        is_enabled = self.get_enabled()

        # Paint red cell background when processing and have process message
        if self._is_processing and self._process_msg:
            colour = [255, 50, 50]
        else:
            if not self._is_pass:
                if self._has_renderables:
                    background_colour = self._view.get_environment_colour()
                    colour = list(background_colour) # constants.HEADER_RENDERABLE_COLOUR
                else:
                    unqueued_colour = self._view.get_unqueued_colour()
                    colour = list(unqueued_colour) # constants.CELL_ENABLED_NOT_QUEUED_COLOUR)                    
                if self._is_selected:
                    if self._has_renderables:
                        colour[0] *= 1.15
                        colour[2] *= 1.15                        
                    else:
                        colour[0] *= 1.6
                        colour[1] *= 1.6
                        colour[2] *= 1.6                           
            else:
                if is_enabled:
                    if is_queued:
                        background_colour = self._view.get_pass_colour()
                        colour = list(background_colour) # constants.CELL_RENDERABLE_COLOUR
                    else:
                        unqueued_colour = self._view.get_unqueued_colour()
                        colour = list(unqueued_colour) # constants.CELL_ENABLED_NOT_QUEUED_COLOUR)
                else:
                    unqueued_colour = self._view.get_pass_disabled_colour()
                    colour = list(unqueued_colour) # constants.CELL_DISABLED_COLOUR)
                if self._is_selected:
                    colour[0] *= 1.6
                    if not all([is_queued, is_enabled]):
                        colour[1] *= 1.6
                    colour[2] *= 1.6

        ######################################################################

        # NOTE: Make transparent cells for testing
        # colour.append(100)

        # limit to rgb 255 range
        colour = [255 if c > 255 else c for c in colour]
        cell_qcolor = QColor.fromRgb(*colour)
        # cell_qcolor = QColor(*colour)

        painter = QPainter(self)
        # NOTE: this draw a nice sharp white line around cell, otherwise it looks blurry with normal Antialiasing
        painter.setRenderHint(QPainter.HighQualityAntialiasing)

        # Paint the background colour of entre cell
        background_rect = rect.adjusted(
            CELL_MARGINS,
            CELL_MARGINS,
            -CELL_MARGINS,
            -CELL_MARGINS)
        painter.fillRect(background_rect, cell_qcolor)

        # Draw a red outline when processing and no processing message
        if self._is_processing and not self._process_msg:
            pen = QPen()
            pen.setWidth(3)
            colour = [200, 30, 30] # [255, 0, 0]
            pen.setColor(QColor(*colour))
            painter.setPen(pen)
            painter.drawRect(background_rect)

        # Paint outline if selected
        elif self._is_selected:
            pen = QPen()
            pen.setWidth(1)
            colour = [255, 255, 255]
            pen.setColor(QColor(*colour))
            painter.setPen(pen)
            painter.drawRect(background_rect)

        display_label_offset = 0
        override_colour = self.get_colour()
        if override_colour and not self._is_processing:
            pen = QPen()
            pen.setWidth(3)
            value = list(override_colour)
            if all([is_queued, is_enabled]):
                multiplier = 255
            else:
                multiplier = 127
            value[0] = int(override_colour[0] * multiplier)
            value[1] = int(override_colour[1] * multiplier)
            value[2] = int(override_colour[2] * multiplier)
            colour_rect = QRect(background_rect)
            colour_rect.setWidth(STATUSWIDGET_DISABLED_HINT_WIDTH)
            painter.fillRect(colour_rect, QColor(*value))
            display_label_offset += STATUSWIDGET_DISABLED_HINT_WIDTH

        # Paint a disabled line
        if not is_enabled and not self._is_processing:
            rect_disabled_hint = QRect(background_rect)
            rect_disabled_hint.translate(
                rect_disabled_hint.width() - STATUSWIDGET_DISABLED_HINT_WIDTH,
                0)
            rect_disabled_hint.setWidth(STATUSWIDGET_DISABLED_HINT_WIDTH)

            pen = QPen()
            pen.setWidth(2)
            pen.setColor(QColor(255, 0, 0))
            painter.setPen(pen)
            painter.drawLine(
                rect_disabled_hint.topLeft(),
                rect_disabled_hint.bottomRight())
            painter.drawLine(
                rect_disabled_hint.bottomLeft(),
                rect_disabled_hint.topRight())

        # Paint a display label
        rect_display_text = None
        display_label_width = 0
        display_label = self.get_display_label()
        if display_label or self._is_processing:
            cell_width = rect.width()
            cell_height = rect.height()

            display_label = display_label

            font = QFont()
            # font.setStyleStrategy(QFont.PreferDevice)
            font.setFamily(constants.FONT_FAMILY)
            font.setBold(True)

            # Paint the processing message (if available)
            if self._is_processing and self._process_msg:
                font.setPointSize(9)
                display_label = self._process_msg
            elif display_label.count('/') > 1:
                font.setPointSize(9)
                font.setBold(True)
            else:
                font.setPointSize(11)
                font.setBold(True)
            painter.setFont(font)

            font_metrics = QFontMetrics(font, painter.device())
            display_label_width = font_metrics.width(display_label)
            display_label_height = font_metrics.height()

            pen = QPen()
            if self._is_processing:
                colour = QColor(255, 255, 255)
            else:
                colour = QColor(0, 0, 0)
            pen.setColor(colour)
            painter.setPen(pen)

            rect_display_text = QRect(
                STATUSWIDGET_DISPLAY_TEXT_START_HOFFSET + display_label_offset,
                STATUSWIDGET_DISPLAY_TEXT_START_HOFFSET,
                display_label_width,
                display_label_height)

            painter.drawText(
                rect_display_text,
                Qt.AlignCenter,
                display_label)

            # # Debug drawing
            # painter.setBrush(QColor(255, 0, 0))
            # painter.drawRoundedRect(rect_display_text, 0, 0)

        # Do not draw overrides when processing and have process message
        if self._is_processing and self._process_msg:
            painter.end()
            return

        # Paint any active overrides (only for enabled items)
        if self._overrides and is_enabled:
            cell_width = rect.width()
            cell_height = rect.height()
            start_x_pos = cell_width - (STATUSWIDGET_HORIZONTAL_MARGINS * 2)
            start_y_pos = cell_height - (STATUSWIDGET_VERTICAL_MARGINS * 2)

            font = QFont()
            font.setFamily(constants.FONT_FAMILY)
            font.setBold(True)
            painter.setFont(font)

            ##################################################################
            # Count and sum up widths of all required overrides to paint

            count = len(self._overrides)
            widths = list()
            for key in self._overrides.keys():
                short_name = self._overrides[key].get(NAME_KEY) or key
                pixmap = self._overrides[key].get(PIXMAP_KEY)
                width, height = (0, PIXMAP_HEIGHT)
                if isinstance(pixmap, QPixmap) and not pixmap.isNull():
                    width, height = (PIXMAP_HEIGHT, PIXMAP_HEIGHT)
                elif short_name:
                    font = self._modify_font_for_status_str(
                        font,
                        short_name,
                        rect_width,
                        count)
                    painter.setFont(font)
                    font_metrics = QFontMetrics(font, painter.device())
                    width += font_metrics.width(short_name) + STATUSWIDGET_STATUS_PADDING_H
                    height = font_metrics.height() + STATUSWIDGET_STATUS_PADDING_V
                self._overrides[key][SIZE_KEY] = (width, height)
                widths.append(width)

            # Bounds for all overrides
            overrides_total_width = sum(widths) + (STATUSWIDGET_STATUS_GAP_WIDTH * count)
            rect_all_overrides = QRect(
                start_x_pos - overrides_total_width,
                start_y_pos - height,
                overrides_total_width,
                height)

            # When statuses not all fit in available space, add a dot dot dot status
            intercepts = rect_display_text and rect_display_text.intersects(rect_all_overrides)
            if not rect.contains(rect_all_overrides) or intercepts:
                override_info = dict()
                override_info[NAME_KEY] = STATUSWIDGET_STATUS_DOT_DOT
                override_info[SIZE_KEY] = (
                    STATUSWIDGET_STATUS_DOT_DOT_WIDTH,
                    STATUSWIDGET_STATUS_DOT_DOT_WIDTH)
                _overrides_to_paint = collections.OrderedDict()
                _overrides_to_paint[STATUSWIDGET_STATUS_DOT_DOT] = override_info
                # Add all other overrides after this special status
                for key in self._overrides.keys():
                    _overrides_to_paint[key] = self._overrides[key]
                # _overrides_to_paint.update(self._overrides)
                overrides_to_paint = _overrides_to_paint
            else:
                overrides_to_paint = self._overrides

            ##################################################################

            pen = QPen()

            offset = 0
            count = len(overrides_to_paint)
            for key in overrides_to_paint.keys():
                short_name = overrides_to_paint[key].get(NAME_KEY) or key

                width = STATUSWIDGET_STATUS_DOT_DOT_WIDTH
                height = STATUSWIDGET_STATUS_DOT_DOT_WIDTH
                collapse_all = (rect_width - display_label_width) < STATUSWIDGET_MINIMUM_WIDTH_BEFORE_COLLAPSE_ALL
                if collapse_all:
                    short_name = '..'
                else:
                    width, height = overrides_to_paint[key].get(SIZE_KEY, (width, height))

                rect_for_status = QRect(
                    start_x_pos - width + offset,
                    start_y_pos - height,
                    width,
                    height)

                if not background_rect.contains(rect_for_status):
                    continue

                if rect_display_text and rect_display_text.intersects(rect_for_status):
                    continue

                if key in self._overrides:
                    self._overrides[key][BOUNDS_KEY] = rect_for_status

                pixmap = overrides_to_paint[key].get(PIXMAP_KEY)
                if isinstance(pixmap, QPixmap) and not pixmap.isNull():
                    rect_icon = QRect(0, 0, width, height)
                    if not is_queued:
                        painter.setOpacity(0.4)
                    painter.drawPixmap(
                        rect_for_status,
                        pixmap,
                        rect_icon)
                    if not is_queued:
                        painter.setOpacity(1.0)

                elif short_name:
                    colour = overrides_to_paint[key].get(
                        COLOUR_KEY, 
                        self._view.get_override_standard_colour())
                    if not is_queued or not self._has_renderables:
                        colour = [c * 0.4 for c in colour]
                    brush = QBrush(QColor(*colour))
                    painter.setBrush(brush)
                    painter.setPen(Qt.NoPen)
                    painter.drawRoundedRect(rect_for_status, 4, 4)

                    if is_queued:
                        pen.setColor(QColor(0, 0, 0))
                    else:
                        pen.setColor(QColor(40, 40, 40))
                    painter.setPen(pen)

                    font = self._modify_font_for_status_str(
                        font,
                        short_name,
                        rect_width,
                        count)
                    painter.setFont(font)
                    painter.drawText(
                        rect_for_status,
                        Qt.AlignCenter,
                        short_name)

                offset -= width + STATUSWIDGET_STATUS_GAP_WIDTH

                if collapse_all:
                    break

        if is_enabled and self._render_progress != None:

            circle_padding = 4
            circle_diameter = 18
            rect_circle = QRect(
                circle_padding,
                circle_padding,
                circle_diameter,
                circle_diameter)
            painter.setBrush(QBrush(QColor(255, 0, 0)))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(rect_circle)

            font = QFont()
            font.setFamily(constants.FONT_FAMILY)
            font.setPointSize(6)
            font.setBold(True)
            painter.setFont(font)

            pen = QPen()
            pen.setColor(QColor(255, 255, 255))
            painter.setPen(pen)

            painter.drawText(
                rect_circle,
                Qt.AlignCenter,
                str(self._render_progress))

        # # Debugging drawing
        # painter.setBrush(QColor(0, 255, 0, 50))
        # painter.drawRoundedRect(rect_all_overrides, 0, 0)

        painter.end()


    def mousePressEvent(self, event):
        '''
        Override mouse press event, so middle click can toggle queued mode.
        '''
        if event.button() == Qt.MiddleButton and self._is_pass and self.get_enabled():
            is_queued = self.get_queued()
            self.set_queued(not is_queued)
            self.queuedToggled.emit(is_queued)
            self.update()
        event.ignore()


    def mouseReleaseEvent(self, event):
        event.ignore()

    def mouseMoveEvent(self, event):
        event.ignore()