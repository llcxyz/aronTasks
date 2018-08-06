# coding:utf-8
import logging
import openerp
from hashlib import sha1
from inspect import getargspec
from celery import Task
from celery import Celery
from inspect import isfunction
from openerp.api import Environment
from openerp.modules.registry import Registry
from openerp.modules.registry import RegistryManager
from openerp import SUPERUSER_ID
from psycopg2 import IntegrityError

_logger = logging.getLogger('CeleryTask')
config = openerp.tools.config
celery_broker_url = openerp.tools.config['celery_broker_url']
celery_backend_url = openerp.tools.config['celery_backend_url']
from openerp import api

# from celery.contrib import rdb

app = Celery('odooAsyncTask', backend=celery_backend_url, broker=celery_broker_url)

celery_default_queue = openerp.tools.config.get('celery_default_queue', 'odoo-celery-task')

enable_celery_task = False
if 'enable_celery_task' in config.options and (config.options['enable_celery_task']
                                               or (config.options['enable_celery_task'] == 'True'
                                                   or config.options['enable_celery_task'] == 'true')):
    enable_celery_task = True


global init

init = False

class celeryTask(object):
    def __init__(self, *args, **kwargs):
        self.countdown = 0
        self.eta = None
        self.expires = None
        self.priority = 5
        self.model = False
        self.queue = celery_default_queue
        self.executor = False
        self.dbname = False
        self.max_retries = 100
        self.autoretry_for = (Exception, IntegrityError)

        self.origin_func = False

        self.name = False

        for arg, value in kwargs.items():
            setattr(self, arg, value)

        if not self.model:
            raise ValueError('params model required!')

        self.name = "%s.%s" % (self.model, self.name)
        self.task = False

        # app.register_task(self)

        # _logger.info("init celerTask[%s] " % self.name)

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        print('{0!r} failed: {1!r}'.format(task_id, exc))

    def run(self, *args, **kwargs):
        print "RUN RUN RUN !(args=%s, kwargs=%s" % (args, kwargs)

    def __call__(self, func, *args, **kwargs):

        self.name = self.name = "%s.%s" % (self.model, func.__name__)
        _logger.info("decorator func= %s " % func)

        token = sha1(self.name).hexdigest()

        # print "TOKEN= %s " % token

        def f_job(*args, **kwargs):
            # 无token 直接调用的.
            if not enable_celery_task:
                _logger.debug("celery disabled call %s direct" % func)
                return func(*args, **kwargs)

            new_func = args[0]

            if not self.origin_func:
                self.origin_func = func._orig if hasattr(func, "_orig") else func
            
            if not enable_celery_task:
                _logger.debug("celery disabled call %s direct" % self.origin_func)

                return self.origin_func(*args, **kwargs)

            if len(args) == 1 or args[-1] != token:
                # print 'Send Message to queue! args=%s, args_len= %s  token=%s ' % (args, len(args), token)
                _logger.debug("Send Message to MQ[queue=%s]" % self.queue)

                args += (token,)
                osv_object = self.model if self.model else args[0]._name
                argspecargs = tuple(getargspec(func).args) + (None,) * 4
                arglist = list(args)
                obj_ids = None
                if argspecargs[1] not in ('cr', 'cursor') and \
                        hasattr(func, '_api'):
                    cr, uid, context = args[0].env.cr, args[0].env.uid, \
                                       dict(args[0].env.context)
                    obj = arglist.pop(0)
                    api_name = func._api.__name__
                    if api_name == 'multi':
                        obj_ids = obj.ids
                    elif api_name == 'one':
                        obj_ids = [obj.id]
                    elif api_name == 'model':
                        obj_ids = obj.ids
                    kwargs['context'] = context
                else:
                    arglist.pop(0)  # Remove self
                    cr = arglist.pop(0)
                    uid = arglist.pop(0)
                    obj_ids = arglist.pop(0)
                    if kwargs.has_key('context'):
                        if not kwargs['context']:
                            kwargs['context'] = {}
                    else:
                        kwargs['context'] = {}

                dbname = cr.dbname if not self.dbname else self.dbname
                fname = func.__name__
                task_args = (dbname, uid, osv_object, fname)
                if obj_ids:
                    task_args += (obj_ids,)
                if arglist:
                    task_args += tuple(arglist)
                try:
                    exector = self.task

                    # 叠加调用任务.去掉上一次任务celeryTask跟踪.
                    if 'celeryTask' in context:
                        context.pop('celeryTask')

                    _logger.info("Send Message to Queue args=%s, kwargs=%s " % (task_args, kwargs))

                    celery_task = exector.apply_async(
                        args=task_args, kwargs=kwargs,
                        countdown=self.countdown, eta=self.eta,
                        expires=self.expires, priority=self.priority,
                        ignore_result=False,
                        queue=getattr(self, "queue", celery_default_queue))

                    _logger.info('Enqueued task %s.%s(%s) on celery with id %s'
                                 % (osv_object, fname, str(task_args),
                                    celery_task and celery_task.id))
                    return celery_task
                except Exception as exc:
                    if args[-1] == token:
                        args = args[:-1]
                    _logger.error(
                        'Celery enqueue task failed %s.%s '
                        'executing task now '
                        'Exception: %s' % (osv_object, fname, exc))

                    if 'context' in kwargs and not kwargs['context']:
                        kwargs.pop('context')
                    _logger.exception(exc)
                    if not self.dbname:
                        return self.origin_func(*args, **kwargs)
                    else:
                        raise exc

            else:
                new_func = args[0]
                _logger.debug('Execute f_job-> args=%s, kwargs=%s ' % (args, kwargs))

                if len(args) > 1 and args[-1] == token:
                    #_logger.debug(' token=%s, func=%s, func.orig = %s  func.name =%s, args=%s, kwargs=%s ' % (
                    #    token, new_func, self.origin_func,  args[0].__class__.__name__, args, kwargs))

                    args = list(args)
                    args.pop()
                    api_name = False
                    if hasattr(func, '_api'):
                        api_name = func._api.__name__

                    return self.executeOrm(api_name, *args, **kwargs)

                    # if callable(args[0]) and args[0].__class__.__name__ == 'f_job':
                    #     return self.executeOrm(*args, **kwargs)
                    # else:

                else:
                    raise ValueError("NOT SUPPORT")

        # 如果celeryTask 没启用.直接返回.f_job.

        if not enable_celery_task:
            _logger.info("celery disabled  %s " % func)
            return f_job

        self.task = app.task(f_job, bind=True, name=self.name, acks_late=True, autoretry_for=self.autoretry_for,
                             retry_kwargs={'max_retries': self.max_retries})

        app.register_task(self.task)

        _logger.info("create celeryTask[%s]  instance  = %s " % (self.name, self.task))

        f_job.AsyncResult = self.task.AsyncResult

        return f_job

    def executeOrm(self, api_name, task, dbname, uid, obj, method, *args, **kwargs):
        result = False
        _logger.debug("executeOrm self=%s,  task = %s ,dbname = %s ,uid= %s, obj=%s, method=%s, args=%s,"
                      "kwargs=%s" % (self, task, dbname, uid, obj, method, args, kwargs))

        # openerp.multi_process = True
        global init
        with Environment.manage():
            if not init:
                # 多进程间 不共享数据库连接.
                openerp.sql_db.close_all()
                init = True

            registry = RegistryManager.get(dbname)
            try:
                cr = registry.cursor()
                _logger.debug("Orm Cursor = %s  start " % cr)
                context = kwargs.pop('context') or {}
                # context['celeryTask'] = task
                env = Environment(cr, uid, context)
                model_method = False
                model = False

                obj_ids = []
                model_method = self.origin_func
                args = list(args)

                if not api_name:
                    model = registry[obj]
                    args.insert(0, uid)
                    args.insert(0, cr)
                    args.insert(0, model)
                    result = model_method(*args, **kwargs)

                else:
                    model = env[obj]
                    if api_name == 'model' or api_name == 'multi' or api_name == 'one':
                        obj_ids = args.pop(0)

                    recs = model.browse(obj_ids)

                    args.insert(0, recs)

                    result = model_method(*args, **kwargs)

                # rdb.set_trace()

                cr.commit()
            except Exception as exc:
                _logger.debug("Orm Cursor = %s  call %s.%s Exception " % (cr, model, model_method))
                cr.rollback()
                _logger.exception(exc)

                raise exc
                # print 'SELF.REQUEST= %s ' % self.request
                # try:
                #     raise self.retry(
                #         queue=self.request.delivery_info['routing_key'],
                #         exc=exc, countdown=(self.request.retries + 1) * 60,
                #         max_retries=100)
                # except Exception as retry_exc:
                #     raise retry_exc
            finally:
                _logger.debug("Orm Cursor = %s  end " % cr)
                cr.close()

        return result


