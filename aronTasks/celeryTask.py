# coding:utf-8
import sys

prj_base = "E:\\project2013\\clouderp\\platform\\myodoov9"
sys.path.append(prj_base)
import openerp

# openerp.tools.config.options['celery_broker_url'] = 'pyamqp://aron:aron@192.168.80.200//'
# openerp.tools.config.options['celery_backend_url'] = 'redis://192.168.80.200:6379/1'

import logging

from hashlib import sha1
from inspect import getargspec
from celery import Celery
from celery import Task

from inspect import isfunction
from openerp.api import Environment
from openerp.modules.registry import Registry
from openerp.modules.registry import RegistryManager
from openerp import SUPERUSER_ID
from psycopg2 import IntegrityError
import simplejson as json
from kombu.utils.encoding import safe_repr, safe_str

_logger = logging.getLogger('CeleryTask')
config = openerp.tools.config
# celery_broker_url = openerp.tools.config.get('celery_broker_url', "pyamqp://aron:aron@127.0.0.1//")
# celery_backend_url = openerp.tools.config.get('celery_backend_url', "redis://192.168.80.200:6379/1")

# from openerp import api

from celery.contrib import rdb

app = Celery('celeryTask')
app.config_from_object('celeryconfig')

celery_default_queue = openerp.tools.config.get('celery_default_queue', app.conf.task_default_queue)

enable_celery_task = app.conf.enable_celery_task
#
# if 'enable_celery_task' in config.options and (config.options['enable_celery_task']
#                                                or (config.options['enable_celery_task'] == 'True'
#                                                    or config.options['enable_celery_task'] == 'true')):
#     enable_celery_task = True

app_name = "odoo"
if hasattr(app.conf, "app_name"):
    app_name = app.conf.app_name

global init

init = False


from celery.worker.request import Request
class MyRequest(Request):
    'A minimal custom request to log failures and hard time limits.'

    def on_timeout(self, soft, timeout):
        super(MyRequest, self).on_timeout(soft, timeout)
        if not soft:
           _logger.warning(
               'A hard timeout was enforced for task %s',
               self.task.name
           )

    def on_failure(self, exc_info, send_failed_event=True, return_ok=False):
        super(MyRequest, self).on_failure(
            exc_info,
            send_failed_event=send_failed_event,
            return_ok=return_ok
        )
        _logger.warning(
            'Failure detected for task %s',
            self.task.name
        )
        print 'on_failure............'

    def on_retry(self, exc_info):
        ret = super(Request,self).on_retry(exc_info)
        print "on retry...."
        return ret


class aronBackGroundTask(Task):
    # Request = MyRequest

    # def run(self, *args, **kwargs):
    #     _logger.info("Running args=%s, kwargs=%s" % (args, kwargs))
    #     print("Task Running args=%s, kwargs=%s" % (args, kwargs))

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        print "Exxecut Failed : %s" % task_id
        print exc
        print args, kwargs, einfo
        db = args[0]
        err_msg = exc.message
        err_trace = safe_str(exc)

        sql = "update celery_task set state='fail', write_date=now() at time zone 'UTC', err_msg=%s, err_trace=%s where taskid = %s"
        # vals = {'state': 'fail', 'err_msg': err_msg, 'err_trace': err_trace}

        self.update_on_db(db, sql, [err_msg, err_trace, task_id])

    def on_success(self, retval, task_id, args, kwargs):
        print "Succcess return: %s:%s " % (task_id, retval)
        print args, kwargs
        db = args[0]
        # sql = "update celery_task set state='success', write_date=now() at time zone 'UTC' where taskid=%s"
        # vals = {'state': 'success'}
        sql = "delete from celery_task where taskid = %s"

        self.update_on_db(db, sql, [task_id])

    def after_return(self, status, retval, task_id, args, kwargs, einfo):
        print "After return: %s:%s " % (task_id, status)
        print retval, args, kwargs
        ret = json.dumps(retval)
        db = args[0]
        # vals = {'ret': ret}
        sql = "update celery_task set ret=%s where taskid=%s"
        self.update_on_db(db, sql, [ret, task_id])

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        print "Retry ...", exc, args, kwargs, einfo
        # rdb.set_trace()
        db = args[0]
        err_msg = exc.message
        err_trace = safe_str(exc)
        print 'einfo....'
        print einfo

        sql = "update celery_task set state='retrying', write_date= now() at time zone 'UTC'," \
              " err_msg=%s, err_trace=%s, cur_retry_cnt=cur_retry_cnt+1 where taskid = %s"
        # vals = {'state': 'retrying', 'err_msg': err_msg, 'err_trace': err_trace}

        self.update_on_db(db, sql, [err_msg, err_trace, task_id])

    def update_on_db(self, db,  sql, args):
        registry = RegistryManager.get(db)

        try:
            cr = registry.cursor()
            cr.execute(sql,args)
            cr.commit()

        finally:
            if cr:
                cr.close()


class celeryTask(Task):
    def __init__(self, *args, **kwargs):
        self.countdown = 0
        self.eta = None
        self.expires = None
        self.priority = 5
        self.model = False
        self.queue = celery_default_queue
        self.executor = False
        self.dbname = False
        self.max_retries = 500
        self.autoretry_for = (Exception, IntegrityError)
        self.ignore_result = True
        self.origin_func = False
        self.app_name = app_name
        self.name = False
        self.persist = True
        self.desc = False

        # 如果不使用aronBackGroundTask将不在数据库内记录状态.

        self.baseTask = None

        for arg, value in kwargs.items():
            setattr(self, arg, value)

        if not self.model:
            raise ValueError('params model required!')

        self.name = "%s[%s].%s" % (self.app_name, self.model, self.name)

        self.task = False

        # app.register_task(self)

        # _logger.info("init celerTask[%s] " % self.name)

    def __call__(self, func, *args, **kwargs):

        self.name = "%s[%s].%s" % (self.app_name, self.model, func.__name__)
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
                cursor = None  # 保存任务的 cursor.
                if argspecargs[1] not in ('cr', 'cursor') and hasattr(func, '_api') and hasattr(args[0], "env"):
                    cr, uid, context = args[0].env.cr, args[0].env.uid, dict(args[0].env.context)
                    cursor = cr
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
                    cursor = cr
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

                exector = self.executor if self.executor else self.task

                target_queue = getattr(self, "queue", celery_default_queue)

                try:

                    # 叠加调用任务.去掉上一次任务celeryTask跟踪.
                    if 'celeryTask' in kwargs['context']:
                        context.pop('celeryTask')

                    _logger.info("Send Message to Queue[%s] args=%s, kwargs=%s " % (target_queue, task_args, kwargs))

                    celery_task = exector.apply_async(
                        args=task_args, kwargs=kwargs,
                        countdown=self.countdown, eta=self.eta,
                        expires=self.expires, priority=self.priority,
                        ignore_result=self.ignore_result,
                        queue=target_queue)

                    _logger.info('Enqueued task %s.%s(%s) on celery with id %s'
                                 % (osv_object, fname, str(task_args),
                                    celery_task and celery_task.id))
                    if self.baseTask:
                        self.save_pending_task(cursor, celery_task.id, dbname, self.name, self.desc, target_queue,
                                               task_args, kwargs)

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
                    if not dbname:
                        return self.origin_func(*args, **kwargs)
                    else:
                        raise exc

            else:
                new_func = args[0]
                _logger.debug('Execute f_job-> args=%s, kwargs=%s ' % (args, kwargs))

                if len(args) > 1 and args[-1] == token:
                    # _logger.debug(' token=%s, func=%s, func.orig = %s  func.name =%s, args=%s, kwargs=%s ' % (
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

        self.task = app.task(f_job, bind=True, name=self.name, base=self.baseTask, acks_late=True,
                             autoretry_for=self.autoretry_for,
                             ignore_result=self.ignore_result,
                             retry_kwargs={'max_retries': self.max_retries}, default_retry_delay=60, retry_backoff=True)

        self.task.on_retry = aronBackGroundTask.on_retry
        self.task.on_success = aronBackGroundTask.on_success
        self.task.on_failure = aronBackGroundTask.on_failure

        app.register_task(self.task)

        _logger.info("create celeryTask[%s]  instance  = %s " % (self.name, self.task))

        f_job.AsyncResult = self.task.AsyncResult

        return f_job

    def save_pending_task(self, cr, task_id, task_db, task_name, task_desc, task_queue, args, kwargs):

        cr.execute("insert into celery_task(create_date,taskid, db, name, queue, \"desc\", args, kwargs,state)"
                   " values(now() at time zone 'UTC', %s,%s,%s,%s,%s,%s,%s,%s)", [task_id, task_db, task_name, task_queue,
                                                        task_desc, json.dumps(args), json.dumps(kwargs), 'pending'])

    def executeOrm(self, api_name, task, dbname, uid, obj, method, *args, **kwargs):
        result = False
        _logger.debug("executeOrm self=%s,  task = %s ,dbname = %s ,uid= %s, obj=%s, method=%s, args=%s,"
                      "kwargs=%s" % (self, task, dbname, uid, obj, method, args, kwargs))

        # openerp.multi_process = True
        # rdb.set_trace()
        uid = SUPERUSER_ID
        global init
        with Environment.manage():
            if not init:
                # 多进程间 不共享数据库连接.
                openerp.sql_db.close_all()
                init = True

            registry = RegistryManager.get(dbname)
            model_method = False
            model = False

            try:
                cr = registry.cursor()
                _logger.debug("Orm Cursor = %s  start " % cr)
                context = kwargs.pop('context') if 'context' in kwargs else {}
                #context['celeryTask'] = task
                # rdb.set_trace()
                env = Environment(cr, uid, context)
                obj_ids = []
                model_method = self.origin_func
                args = list(args)
                print 'api_name= %s ' % api_name
                # rdb.set_trace()
                if not api_name:
                    model = registry[obj]
                    args.insert(0, uid)
                    args.insert(0, cr)
                    args.insert(0, model)
                    print 'call %s ' % model_method
                    result = model_method(*args, **kwargs)

                else:
                    model = env[obj]
                    if api_name == 'model' or api_name == 'multi' or api_name == 'one':
                        if args:
                            obj_ids = args.pop(0)
                    if obj_ids:
                        recs = model.browse(obj_ids)
                    else:
                        recs = model

                    args.insert(0, recs)

                    result = model_method(*args, **kwargs)

                cr.commit()

            except Exception as exc:
                _logger.debug("Orm Cursor = %s  call %s.%s Exception " % (cr, model, model_method))
                cr.rollback()
                _logger.exception(exc)
                # rdb.set_trace()

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
                # _logger.debug("Orm Cursor = %s  end " % cr)
                cr.close()

        return result
