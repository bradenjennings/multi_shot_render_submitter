

import abc


class AbstractMultiShotFactory(object):
    '''
    An abstract factory to instantiate various reimplemented objects via factory methods.
    Reimplement this object to return a family of related objects which are intended
    to be used for particular host application.
    '''

    __metaclass__ = abc.ABCMeta

    def __init__(self):
        super(AbstractMultiShotFactory, self).__init__()


    @abc.abstractmethod
    def get_group_item_object(self):
        '''
        Must be reimplemented to return a Multi Shot group item (subclassed from GroupItem).

        Returns:
            group_item (GroupItem):
        '''
        raise NotImplementedError


    @abc.abstractmethod
    def get_environment_item_object(self):
        '''
        Must be reimplemented to return a Multi Shot environment item (subclassed from EnvironmentItem).

        Returns:
            environment_item (EnvironmentItem):
        '''
        raise NotImplementedError


    @abc.abstractmethod
    def get_render_item_object(self):
        '''
        Must be reimplemented to return a Multi Shot render item (subclassed from RenderItem).

        Returns:
            render_item (RenderItem):
        '''
        raise NotImplementedError


    @abc.abstractmethod
    def get_pass_for_env_item_object(self):
        '''
        Must be reimplemented to return a Multi Shot pass for env item (subclassed from RenderPassForEnvItem).

        Returns:
            render_pass_for_env (RenderPassForEnvItem):
        '''
        raise NotImplementedError


    @abc.abstractmethod
    def get_multi_shot_view_object(self):
        '''
        Must be reimplemented to return a Multi Shot view (subclassed from MultiShotRenderView).

        Returns:
            view (MultiShotRenderView):
        '''
        raise NotImplementedError


    @abc.abstractmethod
    def get_multi_shot_model_object(self):
        '''
        Must be reimplemented to return a Multi Shot model (subclassed from MultiShotRenderModel).

        Returns:
            model (MultiShotRenderModel):
        '''
        raise NotImplementedError


    @abc.abstractmethod
    def get_summary_model_object(self):
        '''
        Must be reimplemented to return a Multi Shot summary model (subclassed from SummaryModel).

        Returns:
            summary_model (SummaryModel):
        '''
        raise NotImplementedError


    @abc.abstractmethod
    def get_multi_shot_delegates_object(self):
        '''
        Must be reimplemented to return a Multi Shot render delegates (subclassed from MultiShotRenderDelegates).

        Returns:
            delegate (MultiShotRenderDelegates):
        '''
        raise NotImplementedError


    @abc.abstractmethod
    def get_job_options_widget_object(self):
        '''
        Get the GEN Multi Shot job options widget as uninstantiated object.

        Returns:
            job_options_widget (JobOptionsWidget):
        '''
        raise NotImplementedError


    @abc.abstractmethod
    def get_spash_intro_object(self):
        '''
        Must be reimplemented to return a Multi Shot splash intro widget (subclassed from SplashIntroWidget).

        Returns:
            splash_intro_widget (SplashIntroWidget):
        '''
        raise NotImplementedError


##############################################################################


from srnd_multi_shot_render_submitter.models import data_objects


class MultiShotFactory(AbstractMultiShotFactory):
    '''
    A factory to build GEN multi shot render submitter objects.
    NOTE: This class may be reimplemented again to return the tailored host app specific subclasses of objects.
    NOTE: Thus allowing the GEN multi shot base objects to be used, where no tailored class is required.
    '''

    def __init__(self):
        super(MultiShotFactory, self).__init__()


    @classmethod
    def get_group_item_object(cls):
        '''
        Get the GEN Multi Shot group item as uninstantiated object.

        Returns:
            group_item (GroupItem):
        '''
        return data_objects.GroupItem


    @classmethod
    def get_environment_item_object(cls):
        '''
        Get the GEN Multi Shot environment item as uninstantiated object.

        Returns:
            environment_item (EnvironmentItem):
        '''
        return data_objects.EnvironmentItem


    @classmethod
    def get_render_item_object(cls):
        '''
        Get the GEN Multi Shot render item as uninstantiated object.

        Returns:
            render_item (RenderItem):
        '''
        return data_objects.RenderItem


    @classmethod
    def get_pass_for_env_item_object(cls):
        '''
        Get the GEN Multi Shot render pass for env item as uninstantiated object.

        Returns:
            pass_for_env_item (RenderPassForEnvItem):
        '''
        return data_objects.RenderPassForEnvItem


    @classmethod
    def get_multi_shot_view_object(cls):
        '''
        Get the GEN multi shot view object in uninstantiated state.

        Returns:
            view (MultiShotRenderView): or subclass
        '''
        from srnd_multi_shot_render_submitter.views import multi_shot_render_view
        return multi_shot_render_view.MultiShotRenderView


    @classmethod
    def get_multi_shot_model_object(cls):
        '''
        Get the GEN multi shot model object in uninstantiated state.

        Returns:
            model (MultiShotRenderModel): or subclass
        '''
        from srnd_multi_shot_render_submitter.models import multi_shot_render_model
        return multi_shot_render_model.MultiShotRenderModel


    @classmethod
    def get_summary_model_object(cls):
        '''
        Get the GEN Multi Shot summary model as uninstantiated object.

        Returns:
            summary_model (SummaryModel):
        '''
        from srnd_multi_shot_render_submitter.models import summary_model
        return summary_model.SummaryModel


    @classmethod
    def get_render_overrides_manager_object(cls):
        '''
        Get the GEN render overrides manager object in uninstantiated state.

        Returns:
            render_overrides_item_manager (RenderOverridesManager):
        '''
        from srnd_multi_shot_render_submitter.render_overrides import render_overrides_manager
        return render_overrides_manager.RenderOverridesManager


    @classmethod
    def get_scheduler_operations_object(cls):
        '''
        Get uninstantiated scheduler operations object.
        NOTE: This might return a GEN scheduler operations in the future.

        Returns:
            scheduler_operations_object (SchedulerOperations):
        '''
        from srnd_multi_shot_render_submitter import plow_scheduler_operations
        return plow_scheduler_operations.PlowSchedulerOperations


    @classmethod
    def get_multi_shot_delegates_object(cls):
        '''
        Get the GEN multi shot delegates object in uninstantiated state.

        Returns:
            delegate (MultiShotRenderDelegates):
        '''
        from srnd_multi_shot_render_submitter.delegates import multi_shot_render_delegates
        return multi_shot_render_delegates.MultiShotRenderDelegates


    @classmethod
    def get_job_options_widget_object(cls):
        '''
        Get the GEN Multi Shot job options widget as uninstantiated object.

        Returns:
            job_options_widget (JobOptionsWidget):
        '''
        from srnd_multi_shot_render_submitter.widgets import job_options_widget
        return job_options_widget.JobOptionsWidget


    @classmethod
    def get_spash_intro_object(cls):
        '''
        Get the GEN Multi Shot splash intro widget as uninstantiated object.

        Returns:
            splash_intro_widget (SplashIntroWidget): or subclass
        '''
        from srnd_qt.ui_framework.widgets import splash_intro_widget
        return splash_intro_widget.SplashIntroWidget