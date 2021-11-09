

import logging
import time
import traceback


from Qt.QtCore import QThread, Signal


THUMBNAIL_HEIGHT = 46
FALLBACK_WIDTH = 160
FALLBACK_HEIGHT = 90

LOGGER = logging.getLogger(__name__)
# LOGGER.setLevel(logging.INFO)


class ThumbnailPrepThread(QThread):
    '''
    Given a mapping of string identifiers to thumbnail file paths
    resize the thumbnails and make more efficient for displaying
    in a UI where many QMovies might play at once.

    Args:
        height (int): height to resize temp thumbnails to
        every_nth_frame (int): skip every nth frame of animation.
            if 0 include all frames.
    '''

    # Emits mapping of string identifier to resized file paths
    thumbnailsGenerated = Signal(dict)
    # Emits string identifier to resized file path
    thumbnailGenerated = Signal(str, str)

    def __init__(
            self,
            height=THUMBNAIL_HEIGHT,
            every_nth_frame=6,
            batch_emit=True,
            parent=None):
        super(ThumbnailPrepThread, self).__init__(parent)
        self._thumbnails_request = dict()
        self._thumbnails_results = dict()
        self._height = int(height)
        self._every_nth_frame = int(every_nth_frame or 0)
        self._batch_emit = bool(batch_emit)
        self._stop_requested = False


    def add_thumbnails_request(
            self,
            thumbnails_request_resize,
            auto_start=True):
        '''
        Add additional thumbnails to resize to queue.

        Args:
            thumbnails_request_resize (dict):
            auto_start (bool):
        '''
        for identifier in thumbnails_request_resize.keys():
            if identifier not in self._thumbnails_request:
                self._thumbnails_request[identifier] = thumbnails_request_resize[identifier]
        if auto_start and not self.isRunning():
            self.start()


    def get_resized_thumbnails_results(self):
        '''
        Get all the cached resized thumbnails results so far.

        Returns:
            thumbnails_results (dict):
        '''
        return self._thumbnails_results


    def get_resized_thumbnail_from_results(self, identifier):
        '''
        Get the file path of a resized thumbnail from results (if any).

        Args:
            identifier (str):

        Returns:
            file_path (str):
        '''
        identifier = str(identifier or str())
        return self._thumbnails_results.get(identifier)


    def stop_prepare_thumbnails(self):
        '''
        Request that this thumbnail prep thread stop as soon as possible.
        '''
        self._stop_requested = True


    def run(self):
        '''
        Start prep of thumbnails queue.
        '''
        self._stop_requested = False

        # Mapping of thumbnails generated only in this run
        thumbnails_results = dict()

        while self._thumbnails_request:
            if self._stop_requested:
                break

            identifiers = dict(self._thumbnails_request)
            for identifier in identifiers:
                if self._stop_requested:
                    break

                resized_thumbnail_path = self.get_resized_thumbnail_from_results(identifier)
                if resized_thumbnail_path:
                    self._thumbnails_results[identifier] = resized_thumbnail_path
                    thumbnails_results[identifier] = resized_thumbnail_path
                    if identifier in self._thumbnails_request:
                        del self._thumbnails_request[identifier]
                    continue

                thumbnail_path = self._thumbnails_request.get(identifier)
                if not thumbnail_path:
                    if identifier in self._thumbnails_request:
                        del self._thumbnails_request[identifier]
                    continue

                resized_thumbnail_path = resize_gif(
                    identifier,
                    thumbnail_path,
                    height=self._height,
                    every_nth_frame=self._every_nth_frame)

                self._thumbnails_results[identifier] = resized_thumbnail_path
                thumbnails_results[identifier] = resized_thumbnail_path

                if identifier in self._thumbnails_request:
                    del self._thumbnails_request[identifier]
                if not self._batch_emit:
                    self.thumbnailGenerated.emit(identifier, resized_thumbnail_path)

        # Reset the thumbnails requests
        self._thumbnails_request = dict()

        # Emit only the thumbnails generated in this run
        if self._batch_emit:
            self.thumbnailsGenerated.emit(thumbnails_results)

        # msg = 'Thread Done. So Exiting....'
        # LOGGER.debug(msg)


##############################################################################


def resize_gif(
        identifier,
        thumbnail_path,
        height=THUMBNAIL_HEIGHT,
        every_nth_frame=6):
    '''
    Resize a gif to new height and save into temp directory

    Args:
        identifier (str):
        thumbnail_path (str):
        height (int):
        every_nth_frame (int):

    Returns:
        resized_thumbnail_path (str):
    '''
    # msg = 'Prep Thumbnail For Identifier: "{}". '.format(identifier)
    # msg += 'Path: "{}". '.format(thumbnail_path)
    # msg += 'Requested Height: "{}"'.format(height)
    # LOGGER.info(msg)

    try:
        # Read the Image
        from PIL import Image, ImageSequence
        image = Image.open(thumbnail_path)
        current_width, current_height = image.size
        # No need to resize thumbnail if already below or equal desired height
        if current_height <= height:
            return thumbnail_path

        multiplier = height / float(current_height)
        width = int(float(current_width) * multiplier)
        size = int(width), int(height)
        # Get sequence iterator
        frames = ImageSequence.Iterator(image)

    except Exception:
        image = None
        # msg = 'Failed To Read Thumbnail: "{}". '.format(thumbnail_path)
        # msg += 'Will Skip Prep More Efficent Thumbnail! '
        # msg += 'Full Exception: "{}".'.format(traceback.format_exc())
        # LOGGER.warning(msg)
        return

    def thumbnails(frames, size, every_nth_frame=6):
        thumbnails = list()
        for i, frame in enumerate(frames):
            if every_nth_frame and bool(i % every_nth_frame):
                continue
            thumbnail = frame.copy()
            thumbnail.thumbnail(size)
            thumbnails.append(thumbnail)
        return thumbnails

    # Get thumbnails frames
    frames = thumbnails(
        frames,
        size,
        every_nth_frame=every_nth_frame)
    if not frames:
        return

    prefix = 'MSRS_thumbnail' + str(identifier).replace('/', '_') + '_'

    import tempfile
    _file = tempfile.NamedTemporaryFile(
        delete=False,
        prefix=prefix,
        suffix='.gif')
    _file.close()
    resized_thumbnail_path = _file.name

    # Save new resized thumbnails
    try:
        frame = frames[0]
        frame.info = image.info # copy sequence info
        frame.save(
            resized_thumbnail_path,
            save_all=True,
            append_images=list(frames))
    except Exception:
        # msg = 'Failed To Save New Thumbnail To: "{}". '.format(resized_thumbnail_path)
        # msg += 'Full Exception: "{}".'.format(traceback.format_exc())
        # LOGGER.warning(msg)
        return

    # msg = 'Finished Generating Efficent Thumbnail: "{}"'.format(resized_thumbnail_path)
    # LOGGER.info(msg)

    return resized_thumbnail_path