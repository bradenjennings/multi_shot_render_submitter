

import collections
import logging


from Qt.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout, QSizePolicy
from Qt.QtGui import (QCursor, QPainter, QBrush, QPen, QColor, 
    QFont, QFontMetrics)
from Qt.QtCore import Qt, Signal, QRect, QPointF


from srnd_multi_shot_render_submitter.constants import Constants
constants = Constants()

GRAPH_HEIGHT = 48
LABEL_HEIGHT = 66
OFF_HEIGHT = 28


class RenderEstimateWidget(QWidget):
    '''
    Widget to show render estimates and potential impact to available 
    render wall allocations for current project.

    Args:
        msrs_model (MultiShotRenderModel):
        render_summary_mode (str): current valid choices are "Graph", "Label", and "Off"
        show_shot_labels (bool): optionally show shot labels (where text fits)
        show_pass_indicators (bool):
    '''

    logMessage = Signal(str, int)
    selectEnvironmentsRequested = Signal(list)

    def __init__(
            self, 
            msrs_model, 
            render_summary_mode='Graph', 
            show_shot_labels=False,
            show_pass_indicators=False,
            parent=None):
        super(RenderEstimateWidget, self).__init__(parent=parent)

        self._msrs_model = msrs_model
        self._render_summary_mode = render_summary_mode or 'Graph'
        self._show_shot_labels = bool(show_shot_labels)
        self._show_pass_indicators = bool(show_pass_indicators)
        
        # Member to store per shot and pass details
        self._cached_estimates = dict()
        # Member to store QRect for each shot and pass
        self._cached_qrect_for_areas = dict()
        # Member to store current area under mouse (if any)
        self._highlighted_area = None
        
        # MSRS active items requires this percent of project allocation over night
        self._percent_required = 0
        # Percent of project allocation currently in use
        self._percent_used = 0
        # Percent of project allocation currently in use, plus allocation required by active MSRS items
        self._percent_total = 0

        self.setMouseTracking(True)
        self.setFixedHeight(GRAPH_HEIGHT)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)        

        vertical_layout = QVBoxLayout()
        vertical_layout.setContentsMargins(0, 0, 0, 0)
        vertical_layout.setSpacing(0)
        self.setLayout(vertical_layout)

        # Label to show at bottom of this widget
        self._label_summary = QLabel()
        self._label_summary.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        font = QFont()
        font.setFamily(constants.FONT_FAMILY)
        font.setPointSize(9)
        self._label_summary.setFont(font)
        vertical_layout.addStretch(100)
        vertical_layout.addWidget(self._label_summary)

        self._font_area = QFont()
        self._font_area.setPointSize(9)

        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._build_context_menu)            
    

    def set_render_summary_mode(self, mode='Graph'):
        '''
        Set render summary mode. Can be graph widget or label or off.

        Args:
            mode (str): current valid choices are "Graph", "Label", and "Off"
        '''
        if mode == self._render_summary_mode:
            return

        self._render_summary_mode = mode 
        msg = 'Set render summary mode: "{}"'.format(mode)
        self.logMessage.emit(msg, logging.INFO)

        _mode = self._render_summary_mode.lower()
        visible = _mode != 'off'
        graph_mode = _mode == 'graph'
        self._label_summary.setVisible(visible)

        if graph_mode:
            self.setFixedHeight(GRAPH_HEIGHT)
        elif visible:
            self.setFixedHeight(LABEL_HEIGHT)
        else:
            self.setFixedHeight(OFF_HEIGHT)

        self.update_estimate()

        # Write value back into preferences
        self._msrs_model.update_preference(
            'render_summary', 
            self._render_summary_mode)


    def set_show_shot_labels(self, value):
        '''
        Set whether to show shot labels in render estimate graph for expensive shots (where text fits).

        Args:
            value (bool):
        '''
        if value == self._show_shot_labels:
            return

        value = bool(value)
        self._show_shot_labels = value

        msg = 'Set show shot labels: "{}"'.format(value)
        self.logMessage.emit(msg, logging.INFO)

        self.update()

        # Write value back into preferences
        self._msrs_model.update_preference(
            'render_summary_graph_show_shot_labels', 
            self._show_shot_labels)


    def set_show_pass_indicator_lines(self, value):
        '''
        Set whether to show pass indicator lines in render estimate graph.

        Args:
            value (bool):
        '''
        if value == self._show_pass_indicators:
            return

        value = bool(value)
        self._show_pass_indicators = value

        msg = 'Set pass indicator lines: "{}"'.format(value)
        self.logMessage.emit(msg, logging.INFO)

        self.update_estimate()

        # Write value back into preferences
        self._msrs_model.update_preference(
            'render_summary_graph_show_pass_indicator_lines', 
            self._show_pass_indicators)


    def update_estimate(self, cached=True):
        '''
        Update the render estimates for all active environments and passes.

        Args:
            cached (bool):

        Returns:
            frame_count (int):
        '''
        _mode = self._render_summary_mode.lower()

        if _mode == 'off':
            self.update()
            return 0

        # Refresh the project and entire wall allocation details.
        if not cached:
            self._msrs_model.get_allocation(cached=False)
            self._msrs_model.get_allocation_wall(cached=False)

        # Optionally get basic text label overview, instead of full per shot graph 
        if _mode != 'graph':
            msg, _pass_count, _shot_count, frame_count = self._msrs_model.formulate_label_only_render_estimate()
            self._label_summary.setText(msg)
            self._label_summary.setToolTip(msg)
            self.update()
            return frame_count            

        msg = 'Updating render estimate widget...'
        self.logMessage.emit(msg, logging.INFO)

        allocation, allocation_used = self._msrs_model.get_allocation()
        percent_used = (allocation_used / float(allocation)) * 100
        # # Plow might return used more than available, so cap it to 100 percent
        # if percent_used > 100:
        #     percent_used = 100        
        pass_for_env_items = self._msrs_model.get_pass_for_env_items()

        # Reset cache
        self._cached_estimates = collections.OrderedDict()
        self._cached_qrect_for_areas = dict()
        
        # Total percent starts at projects in use percent
        self._percent_total = percent_used or 0
        # Percent required for active MSRS items
        self._percent_required = 0
        # Update percent used as int
        self._percent_used = int(percent_used)

        pass_count = 0
        est_passes = 0
        unknown = 0
        frame_count_total = 0
        hours_total = 0

        for pass_env_item in pass_for_env_items:
            if not pass_env_item.get_active():
                continue
            pass_count += 1

            environment_item = pass_env_item.get_environment_item()
            area = environment_item.get_oz_area()  
            if not area in self._cached_estimates.keys():
                self._cached_estimates[area] = dict()
                self._cached_estimates[area]['hours'] = 0
                self._cached_estimates[area]['percent'] = 0
                self._cached_estimates[area]['frame_count'] = 0
                self._cached_estimates[area]['passes'] = collections.OrderedDict()

            render_item = pass_env_item.get_source_render_item()
            # item_full_name = render_item.get_item_full_name()
            estimate = pass_env_item.get_render_estimate_average_frame()
            frame_count = pass_env_item.get_resolved_frames_count_queued()

            frame_count_total += frame_count

            # Full path to pass item (including environment index)
            item_full_name = pass_env_item.get_identifier(nice_env_name=True, prefer_jid=False)

            if estimate:              
                hours_pass = self._msrs_model.get_core_hours_from_estimate(estimate, frame_count)
                percent_pass = hours_pass / float(allocation)
                self._cached_estimates[area]['hours'] += hours_pass
                self._cached_estimates[area]['percent'] += percent_pass
                self._cached_estimates[area]['frame_count'] += frame_count

                value = float(percent_pass * 100)
                self._percent_total += value # includes allocations already used 
                self._percent_required += value # percent for active MSRS items only

                if self._show_pass_indicators:
                    pass_info = dict()
                    pass_info['hours'] = hours_pass
                    pass_info['percent'] = percent_pass
                    pass_info['frame_count'] = frame_count
                    self._cached_estimates[area]['passes'][item_full_name] = pass_info

                # Orange colour when beyond 100%
                if self._percent_total >= 100.0:
                    self._cached_estimates[area]['colour'] = colour = QColor(219, 158, 78)

                est_passes += 1
                hours_total += hours_pass
            else:
                unknown += 1

        shot_count = len(self._cached_estimates.keys())

        # Formulate summary text
        summary_text = '{} passes, {} shots, {} frames. '.format(pass_count, shot_count, frame_count_total)
        summary_text += '{} passes estimated and {} not estimated. '.format(est_passes, unknown)
        summary_text += '{}% total show allocation over night. '.format(int(self._percent_required))
        self._label_summary.setText(summary_text)

        # Tooltip can be longer 
        hours_total = round(hours_total, 2)
        summary_text += "estimated hours is {}.".format(hours_total)
        self._label_summary.setToolTip(summary_text)

        # msg = 'Estimates for areas: {}'.format(self._cached_estimates)
        # self.logMessage.emit(msg, logging.INFO)

        self.update()        

        return frame_count_total


    def get_area_and_pass_for_pos(self, pos=None):
        '''
        Get the oz area and full item name to pass for the QCursor position.

        Args:
            pos (QPoint):
        
        Returns:
            area, item_full_name (tuple): oz area and full path to particular item
        '''
        pos = pos or self.mapFromGlobal(QCursor.pos())
        for area in self._cached_qrect_for_areas.keys():
            qrect = self._cached_qrect_for_areas[area].get('value')
            if not qrect or not qrect.contains(pos):
                continue
            # Also check for pass within position
            item_full_name = None
            if self._show_pass_indicators:
                for _item_full_name in self._cached_qrect_for_areas[area].get('passes', dict()):
                    pass_rect = self._cached_qrect_for_areas[area]['passes'].get(_item_full_name)
                    if pass_rect and pass_rect.contains(pos):                
                        item_full_name = _item_full_name
            return area, item_full_name
        return None, None


    def _build_context_menu(self, show=True):
        '''
        Build QMenu for this widget.

        Args:
            show (bool):

        Returns:
            menu (QtGui.QMenu):
        '''
        from Qt.QtWidgets import QMenu
        import srnd_qt.base.utils

        menu = QMenu()

        _mode = self._render_summary_mode.lower()
        graph_mode = _mode == 'graph'
        label_mode = _mode == 'label'

        action = srnd_qt.base.utils.context_menu_add_menu_item(
            self, 
            'Show as graph',
            checked=graph_mode,
            checkable=True)
        action.toggled.connect(
            lambda *x: self.set_render_summary_mode(mode='Graph'))
        menu.addAction(action)

        action = srnd_qt.base.utils.context_menu_add_menu_item(
            self, 
            'Show as label only',
            checked=label_mode,
            checkable=True)
        action.toggled.connect(
            lambda *x: self.set_render_summary_mode(mode='Label'))
        menu.addAction(action)

        menu.addSeparator()

        if graph_mode:
            action = srnd_qt.base.utils.context_menu_add_menu_item(
                self, 
                'Show labels for expensive shots',
                checked=self._show_shot_labels,
                checkable=True)
            action.toggled.connect(self.set_show_shot_labels)
            menu.addAction(action)

            action = srnd_qt.base.utils.context_menu_add_menu_item(
                self, 
                'Show pass indicator lines',
                checked=self._show_pass_indicators,
                checkable=True)
            action.toggled.connect(self.set_show_pass_indicator_lines)
            menu.addAction(action)

            menu.addSeparator()

        msg = 'Refresh available allocation info'
        action = srnd_qt.base.utils.context_menu_add_menu_item(self, msg)
        action.triggered.connect(
            lambda *x: self.update_estimate(cached=False))
        menu.addAction(action)

        if show:
            pos = QCursor.pos()
            menu.exec_(pos)

        return menu


    ##########################################################################


    def mouseMoveEvent(self, event):
        '''
        Update tooltip for target area to show pertinent render estimate details.
        TODO: Could implement tooltip in eventFilter instead....
        '''
        allocation, allocation_used = self._msrs_model.get_allocation()

        pos = self.mapFromGlobal(QCursor.pos())
        area, item_full_name = self.get_area_and_pass_for_pos(pos=pos)

        # Formulate tooltip for particular shot and pass
        if area:
            hours_area = self._cached_estimates.get(area, dict()).get('hours', 0)
            if hours_area:
                try:
                    node_name = item_full_name.split('#')[-1]
                except Exception:
                    node_name = None
                
                # #6fb96f - green environment colour (unselected) 
                # #489b48 - green pass cell colour (unselected)
                # #aedadb - light blue render estimate colour
                # #b8ed5d - light green render estimate colour
                # <font color="#6fb96f" size="4">

                shot_frame_count = self._cached_estimates[area].get('frame_count', 0)
                percent_area = int((hours_area / float(allocation)) * 100)

                msg = '<b><font size="4">{}</font></b>'.format(area) 
                msg += '<br>Shot estimated core hours required: <b>{}</b>'.format(int(hours_area))
                msg += '<br>Shot show allocation required: <b>{}%</b>'.format(percent_area)
                msg += '<br>Shot frame count: <b>{}</b>'.format(shot_frame_count)  
                
                if self._show_pass_indicators:
                    msg += '<br>'
                    pass_rect = self._cached_qrect_for_areas[area]['passes'].get(item_full_name)
                    if pass_rect and pass_rect.contains(pos):
                        pass_info = self._cached_estimates[area].get('passes', dict()).get(item_full_name, 0)
                        hours_pass = pass_info.get('hours', 0)
                        percent_pass = pass_info.get('percent', 0)
                        pass_frame_count = pass_info.get('frame_count', 0)
                        percent_pass = int(percent_pass * 100)
                        msg += '<br>Pass: <b>{}</b>'.format(node_name)
                        msg += '<br>Pass estimated core hours required: <b>{}</b>'.format(int(hours_pass))
                        msg += '<br>Pass show allocation required: <b>{}%</b>'.format(percent_pass)                                 
                        msg += '<br>Pass frame count: <b>{}</b>'.format(pass_frame_count)  
                
                msg += '<br><br><b>LEFT CLICK TO SELECT IN MAIN MSRS VIEW</b>'
                self.setToolTip(msg)
                self._highlighted_area = area
                self.update()
                return  

        # Reset and trigger repaint for highlighted area if necessary
        had_highlighted_area = self._highlighted_area
        self._highlighted_area = None
        if had_highlighted_area:
            self.update()

        percent_of_wall = int((float(allocation) / self._msrs_model.get_allocation_wall()) * 100)

        # Formulate tooltip for overall project allocation (rather than particular shot or pass)
        msg = 'Show allocated core hours: <b>{}</b>'.format(int(allocation))
        msg += '<br>Show allocation: <b>{}%</b> of total wall'.format(percent_of_wall)
        msg += '<br>Show allocation used: <b>{}%</b>'.format(self._percent_used)
        msg += '<br>Show allocation required: <b>{}%</b>'.format(int(self._percent_required))
        self.setToolTip(msg)
    

    def mousePressEvent(self, event):
        '''
        Reimplemented to allow user to select environment by clicking render estimate area,

        Args:
            event (QEvent):
        '''
        if event.buttons() == Qt.LeftButton:
            area, item_full_name = self.get_area_and_pass_for_pos()
            if area and area.startswith('/'):
                # Prefer to select pass
                if item_full_name:
                    self.selectEnvironmentsRequested.emit([str(item_full_name)])
                # Otherwise select the environment
                elif area:
                    self.selectEnvironmentsRequested.emit([str(area)])
        QWidget.mousePressEvent(self, event)     


    def enterEvent(self, event):
        '''
        Reimplemented to set override cursor.
        '''
        QApplication.setOverrideCursor(Qt.PointingHandCursor)


    def leaveEvent(self, event):
        '''
        Reimplemented to set override cursor and remove highlights.
        '''
        QApplication.restoreOverrideCursor()
        self._highlighted_area = None
        self.update()


    def paintEvent(self, event):
        '''
        Reimplemented to paint render estimates for all active MSRS environments.

        Args:
            event (QtCore.QEvent)
        '''
        _mode = self._render_summary_mode.lower()
        if _mode != 'graph':
            QWidget.paintEvent(self, event)
            return

        allocation, allocation_used = self._msrs_model.get_allocation()

        percent_used_decimal = allocation_used / float(allocation)
        # # Plow might return used more than available, so cap it to 1.0
        # if percent_used_decimal > 1.0:
        #     percent_used_decimal = 1.0

        self._cached_qrect_for_areas = dict()

        painter = QPainter(self)
        painter.setRenderHint(QPainter.HighQualityAntialiasing)

        widget_width = self.width()
        widget_height = self.height()
        
        # Restrict height since label sits below it
        text_height_padding = 2
        label_height = self._label_summary.height() + text_height_padding
        widget_height -= label_height

        # Full width of graph is entire show allocation
        rect = event.rect()
        rect = rect.adjusted(0, 0, 0, -label_height)
        painter.fillRect(rect, QColor(130, 130, 130))

        # Calculate multiplier to normalize out of range 
        multiplier = 1
        if self._percent_total > 0:
            multiplier = 1.0 / float(self._percent_total / 100.0)
            if multiplier > 1.0:
                multiplier = 1
            
        x_pos = 0
        percent_total = 0

        # Show percent of show allocation already used
        used_width = int(percent_used_decimal * widget_width * multiplier)
        rect = QRect(0, 0, used_width, widget_height)
        area = 'Used'
        self._cached_qrect_for_areas[area] = dict()
        self._cached_qrect_for_areas[area]['value'] = rect
        self._cached_qrect_for_areas[area]['passes'] = dict()
        colour = QColor(180, 180, 180)
        painter.fillRect(rect, colour)
        pen = QPen()
        pen.setColor(QColor(0, 0, 0))
        painter.setPen(pen)                        
        self._font_area.setPointSize(9)
        painter.setFont(self._font_area)
        percent = int(percent_used_decimal * 100)
        display_value = 'Used {}%'.format(percent)
        width = QFontMetrics(self._font_area).width(display_value)
        if width < used_width:
            painter.drawText(QPointF(2, widget_height - 4), display_value)   
        percent_total += percent_used_decimal
        x_pos += used_width

        for a, area in enumerate(self._cached_estimates.keys()):
            area_dict = self._cached_estimates.get(area, dict())
            percent = area_dict.get('percent', 0)
            if not percent:
                continue
            
            percent_total += percent

            colour = area_dict.get('colour')
            if not colour:
                colour = QColor(175, 218, 219)

            # Shot area section
            section_width = int(percent * widget_width * multiplier)
            # rect = QRect(x_pos, 0, section_width, widget_height)
            rect = QRect(x_pos + 2, 0, section_width - 2, widget_height)
            self._cached_qrect_for_areas[area] = dict()
            self._cached_qrect_for_areas[area]['value'] = rect
            self._cached_qrect_for_areas[area]['passes'] = dict()
            if self._highlighted_area == area:
                colour = QColor(184, 238, 93)
            painter.fillRect(rect, colour)

            # # Shot area border
            # # if a % 2 == 0:
            # border_colour = QColor(185, 185, 185)
            # # else:
            # #     border_colour = QColor(150, 150, 150)
            # pen = QPen()
            # pen.setColor(border_colour)
            # pen.setWidth(2)
            # painter.setPen(pen)
            # rect_border = rect.adjusted(1, 1, -1, -1)
            # painter.drawRect(rect_border)

            # Area name (if space available)
            if self._show_shot_labels and section_width > 55:
                pen = QPen()
                pen.setColor(QColor(0, 0, 0))
                painter.setPen(pen)
                display_value = '/'.join(area.split('/')[-2:])
                if section_width < 85:
                    self._font_area.setPointSize(8)
                else:
                    self._font_area.setPointSize(9)
                painter.setFont(self._font_area)
                width = QFontMetrics(self._font_area).width(display_value)
                if width < int(section_width - 2):
                    painter.drawText(QPointF(x_pos + 2, widget_height - 4), display_value)   

            # Pass indicator lines
            if self._show_pass_indicators:
                pen = QPen()
                pen.setWidth(1)
                pen.setColor(QColor(140, 140, 140))
                painter.setPen(pen)
                pass_xpos = int(x_pos)
                item_full_names = self._cached_estimates[area].get('passes', dict()).keys()
                pass_count = len(item_full_names)
                for i, item_full_name in enumerate(item_full_names):
                    pass_info = self._cached_estimates[area]['passes'].get(item_full_name, 0)
                    percent_pass = pass_info.get('percent', 0)
                    pass_width = int(percent_pass * widget_width * multiplier)
                    if not pass_width:
                        continue
                    pass_rect = QRect(pass_xpos, 0, pass_width, widget_height)
                    self._cached_qrect_for_areas[area]['passes'][item_full_name] = pass_rect
                    if i == 0 or i == pass_count:
                        pass_xpos += pass_width
                        continue
                    painter.drawLine(pass_xpos, 0, pass_xpos, 7)
                    pass_xpos += pass_width

            x_pos += section_width  

        # Paint indicators when exceeed project allocation
        if self._percent_total > 100:
            line_xpos = int(widget_width * multiplier)
            pen = QPen()
            pen.setWidth(2)
            pen.setColor(QColor(255, 0, 0))
            pen.setStyle(Qt.CustomDashLine)
            pen.setDashPattern([1, 1])
            painter.setPen(pen)    
            painter.drawLine(line_xpos, 0, line_xpos, widget_height)    

            self._font_area.setPointSize(8)
            painter.setFont(self._font_area)

            display_value = '100%'
            width = QFontMetrics(self._font_area).width(display_value) 
            if (line_xpos + width + 6) < self.width():            
                painter.drawText(QPointF(line_xpos + 6, 10), display_value) 

        # else:
        #     painter.drawText(QPointF(line_xpos + 6, 10), 'Available {}%'.format()) 