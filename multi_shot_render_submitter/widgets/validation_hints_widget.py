

from Qt.QtWidgets import QWidget
from Qt.QtGui import (QImage, QPainter, QPen, QColor, QFont, QFontMetrics)
from Qt.QtCore import (Qt, Signal, QRect, QRectF, QPoint)

from srnd_multi_shot_render_submitter.constants import Constants
constants = Constants()


##############################################################################


class ValidationHintsWidget(QWidget):
    '''
    A widget to hint critical and warnings issues.

    Args:
        critical_count (int):
        warning_count (int):
    '''

    validationHintsChanged = Signal(int, int)

    def __init__(
            self,
            critical_count=0,
            warning_count=0,
            parent=None):
        super(ValidationHintsWidget, self).__init__(parent=parent)
        self._critical_count = critical_count
        self._warning_count = warning_count

        self._pixmap_critical = None
        self._pixmap_warning = None

        # TODO: Should reimplement in the srnd_katana_render_submitter repo
        if constants.IN_KATANA:
            from UI4.Util import IconManager
            from wkatana.preflight import dialog
            self._pixmap_critical = IconManager.GetPixmap(dialog.SEVERE_ICON_PATH)
            self._pixmap_warning = IconManager.GetPixmap(dialog.WARNING_ICON_PATH)


    def set_validation_warning_counter(self, count):
        self._warning_count = count

    def set_validation_critical_counter(self, count):
        self._critical_count = count


    def paintEvent(self, event):
        '''
        Paint two squares (with rounded corners) with counter inside
        '''
        rect = event.rect()
        cell_width = rect.width()
        cell_height = rect.height()

        painter = QPainter(self)
        painter.setRenderHint(QPainter.HighQualityAntialiasing)

        pen = QPen()
        pen.setWidth(1)
        pen.setColor(QColor(255, 255, 255))

        font = QFont()
        font.setFamily('Bitstream Vera Sans')
        font.setBold(True)
        font.setPointSize(8)

        font_metrics = QFontMetrics(font, painter.device())

        HEIGHT = self.height()
        HALF_HEIGHT = int(HEIGHT / 2.0)
        SPACING = 10
        RECT_SOURCE_ICON = QRectF(0, 0, HEIGHT, HEIGHT)

        previous_width = 0
        if self._critical_count:
            if self._pixmap_critical:
                painter.setPen(Qt.NoPen)
                critical_str = str(self._critical_count)
                rect_icon = QRectF(0, 0, HEIGHT, HEIGHT)
                painter.drawPixmap(rect_icon, self._pixmap_critical, RECT_SOURCE_ICON)
                pen.setColor(QColor(255, 0, 0))
                painter.setPen(pen)
                width = font_metrics.width(critical_str)
                rect_icon.translate(QPoint(HALF_HEIGHT, 0))
                painter.drawText(
                    rect_icon,
                    Qt.AlignCenter,
                    critical_str)
                previous_width = rect_icon.bottomRight().x()
            else:
                painter.setPen(Qt.NoPen)
                critical_str = str(self._critical_count)
                width = font_metrics.width(critical_str) + 10
                height = self.height() - 4
                rect_critical = QRect(2, 2, width, height)
                painter.setBrush(QColor(255, 0, 0))
                painter.drawRect(rect_critical)
                # painter.drawRoundedRect(rect_critical, 8, 8)
                previous_width = int(width)
                painter.setPen(pen)
                painter.drawText(
                    rect_critical,
                    Qt.AlignCenter,
                    critical_str)

        if self._warning_count:
            if self._pixmap_warning:
                painter.setPen(Qt.NoPen)
                warning_str = str(self._warning_count)
                rect_icon = QRectF(previous_width, 0, HEIGHT, HEIGHT)
                painter.drawPixmap(rect_icon, self._pixmap_warning, RECT_SOURCE_ICON)
                pen.setColor(QColor(255, 165, 0))
                painter.setPen(pen)
                width = font_metrics.width(warning_str)
                rect_icon.translate(QPoint(HALF_HEIGHT, 0))
                painter.drawText(
                    rect_icon,
                    Qt.AlignCenter,
                    warning_str)
            else:
                painter.setPen(Qt.NoPen)
                warning_str = str(self._warning_count)
                width = font_metrics.width(warning_str) + 10
                height = self.height() - 4
                rect_warning = QRect(2 + previous_width + 5, 2, width, height)
                painter.setBrush(QColor(235, 150, 0))
                painter.drawRect(rect_warning)
                # painter.drawRoundedRect(rect_warning, 8, 8)
                painter.setPen(pen)
                painter.drawText(
                    rect_warning,
                    Qt.AlignCenter,
                    warning_str)