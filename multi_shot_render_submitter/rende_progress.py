

import logging
import time
import traceback


from Qt.QtCore import QThread, Signal


LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.DEBUG)


class CollectRenderProgressThread(QThread):
    '''
    Collect the render progress for all previously launched MSRS jobs.

    Args:
        frequency (int): in seconds
    '''

    collectedResults = Signal(dict)

    def __init__(self, frequency=25, parent=None):
        super(CollectRenderProgressThread, self).__init__(parent)
        self._listening = False
        self._frequency = frequency
        self._details_to_collect = dict()
        self._last_results = dict()


    def set_frequency(self, value):
        '''
        Set how often to collect render progress for previously launched MSRS jobs.

        Args:
            frequency (int): in seconds
        '''
        self._frequency = int(value)


    def get_frequency(self):
        '''
        Get how often to collect render progress for previously launched MSRS jobs.

        Returns:
            frequency (int): in seconds
        '''
        return self._frequency


    def set_details_to_collect(self, details_to_collect):
        '''
        Set dict mapping which contains details of all previously launched MSRS jobs.
        This source information is used to check on Plow Render Jobs and
        Layers for render progress.

        Args:
            details_to_collect (dict):
        '''
        if not details_to_collect:
            details_to_collect = dict()
        self._details_to_collect = details_to_collect


    def get_details_to_collect(self):
        '''
        Get current details to collect map.

        Returns:
            details_to_collect (dict):
        '''
        return self._details_to_collect or dict()


    def get_last_results(self):
        '''
        Get the results of the last checked render progress for previously launched MSRS jobs.

        Returns:
            last_results (dict):
        '''
        return self._last_results


    def start_listening(self):
        '''
        Request that listening to Jobs and collecting data should be started.
        '''
        was_listening = self._listening
        self._listening = True
        # Request thread to start if not already running
        if not self.isRunning():
            self.start()


    def stop_listening(self):
        '''
        Request that listening to Jobs and collecting data should be stopped as soon as possible.
        '''
        # Clear last results
        self._last_results = dict()
        # Stop listening as soon as possible
        self._listening = False


    def run(self):
        '''
        Start collecting render progress for multiple previously launched MSRS jobs.
        '''
        self._listening = True
        collected_results = dict()
        counter = 0
        while True:
            # time.sleep(self._frequency)

            if not self._listening:
                # Clear last results
                self._last_results = dict()
                # msg = 'Request To Stop Listening And Collecting '
                # msg += 'Render Progress Data. Exiting Thread...'
                # LOGGER.debug(msg)
                break

            # msg = 'Collecting Render Progress. '
            # msg += 'From Details: "{}". '.format(self._details_to_collect)
            # msg += 'Counter: "{}"'.format(counter)
            # LOGGER.debug(msg)

            if self._details_to_collect:
                self._last_results = self.collect_render_progress()
            else:
                self._last_results = dict()
            self.collectedResults.emit(self._last_results)
            counter += 1

            time.sleep(self._frequency)

        # msg = 'Thread Done. So Exiting....'
        # LOGGER.debug(msg)


    def collect_render_progress(self):
        '''
        Collect render progress for previously launched MSRS jobs.

        Returns:
            results (dict):
        '''
        results = dict()

        import plow

        job_for_uuid = dict()
        for msrs_uuid in self._details_to_collect.keys():
            details = self._details_to_collect[msrs_uuid]
            dispatcher_plow_job_id = details.get('dispatcher_plow_job_id')
            plow_job_id = details.get('plow_job_id')
            plow_layer_id = details.get('plow_layer_id')

            # Collect percent for dispatched jobs
            if dispatcher_plow_job_id:
                plow_job_id = None
                plow_layer_id = None
                # Get all Layers of dispatcher Job
                try:
                    if msrs_uuid in job_for_uuid.keys():
                        job = job_for_uuid[msrs_uuid]
                    else:
                        job = plow.get_job(dispatcher_plow_job_id)
                        job_for_uuid[msrs_uuid] = job
                    layers = job.get_layers()
                except Exception:
                    layers = list()
                if not layers:
                    continue
                # Gather all dispatcher results for all Layers of dispatcher Job
                for layer in layers:
                    try:
                        _results_by_uuid = eval(layer.attrs.get('dispatcher_results_by_uuid'))
                    except Exception:
                        _results_by_uuid = dict()
                    if _results_by_uuid and isinstance(_results_by_uuid, dict):
                        for _msrs_uuid in _results_by_uuid.keys():
                            if _msrs_uuid not in results:
                                results[_msrs_uuid] = dict()
                            _plow_job_id = _results_by_uuid[_msrs_uuid].get('plow_job_id')
                            if _plow_job_id:
                                results[_msrs_uuid]['plow_job_id'] = _plow_job_id
                            _plow_layer_id = _results_by_uuid[_msrs_uuid].get('plow_layer_id')
                            if _plow_layer_id:
                                results[_msrs_uuid]['plow_layer_id'] = _plow_layer_id
                # Check the render progress or Layer
                plow_layer_id = results.get(msrs_uuid, dict()).get('plow_layer_id')
                if not plow_layer_id:
                    continue
                try:
                    layer = job.get_layers(id=plow_layer_id)
                except Exception:
                    layer = None
                if not layer:
                    continue
                # Store the percent for msrs Pass uuid
                results[msrs_uuid]['percent'] = self._get_progress_of_layer(layer)

            # Collect percent for non dispatched jobs
            elif all([plow_job_id, plow_layer_id]):
                try:
                    if msrs_uuid in job_for_uuid.keys():
                        job = job_for_uuid[msrs_uuid]
                    else:
                        job = plow.get_job(plow_job_id)
                        job_for_uuid[msrs_uuid] = job
                    layers = job.get_layers(id=plow_layer_id)
                    layer = layers[0]
                except Exception:
                    layer = None
                if not layer:
                    continue
                results[msrs_uuid] = dict()
                results[msrs_uuid]['percent'] = self._get_progress_of_layer(layer)

        return results


    @classmethod
    def _get_progress_of_layer(cls, layer):
        '''
        Get progress of Plow Layer.

        Args:
            layer (Plow.layer.Layer):

        Returns:
            percent (int):
        '''
        try:
            tasks = layer.get_tasks() or list()
        except Exception:
            msg = 'Failed To Get Tasks Of Layer: "{}". '.format(layer)
            msg += 'Full Exception: "{}".'.format(traceback.format_exc())
            LOGGER.warning(msg)
            return 0
        task_count = len(tasks)
        progress_list = list()
        for task in tasks:
            try:
                progress_list.append(int(task.stats.progress))
            except Exception:
                progress_list.append(0)
        percent = 0
        if task_count:
            percent = int(sum(progress_list) / task_count)
        return percent