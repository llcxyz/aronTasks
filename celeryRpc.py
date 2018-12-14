#coding:utf-8
import sys
prj_base = "E:\\project2013\\clouderp\\platform\\myodoov9"
sys.path.append(prj_base)

import openerp
import logging
from celery import Celery
from psycopg2 import IntegrityError
from hashlib import sha1

# app_name = openerp.tools.config.get("app_name", "odoo")

celery_default_queue = openerp.tools.config.get('celery_default_queue', 'odoo-celery-task')
celery_broker_url = openerp.tools.config.get('celery_broker_url', "pyamqp://aron:aron@192.168.80.200//")
celery_backend_url = openerp.tools.config.get('celery_backend_url', "redis://192.168.80.200:6379/1")

app = Celery('odooRpcTask', backend=celery_backend_url, broker=celery_broker_url)


_logger = logging.getLogger(__name__)


class modelRpcStub(object):
    def __init__(self, db, model, **kwargs):
        self.db = db
        self.model = model
        self.countdown = 0
        self.eta = None
        self.uid = 1
        self.expires = None
        self.priority = 5
        self.queue = celery_default_queue
        self.max_retries = 100
        self.autoretry_for = (Exception, IntegrityError)
        self.timeout = 5
        self.tasks = {}
        for arg, value in kwargs.items():
            setattr(self, arg, value)

    def __getattr__(self, name, *args, **kwargs):
        if name == '__call__':
            return super(modelRpcStub, self).__getattr__(name, *args, **kwargs)

        return self.create_celery_task(name)

    def create_celery_task(self, name):
        name = "%s.%s" % (self.model, name)

        def f_job(*args, **kwargs):
            task, func = self.tasks[name]
            token = sha1(name).hexdigest()

            task_args = [self.db, self.uid, self.model, name]
            task_args += args
            task_args += [token]

            asResult = task.apply_async(
                args=task_args, kwargs=kwargs,
                countdown=self.countdown, eta=self.eta,
                expires=self.expires, priority=self.priority,
                ignore_result=False,
                queue=getattr(self, "queue", celery_default_queue))

            return asResult.get(timeout=self.timeout)

        if name in self.tasks:
            task, func = self.tasks[name]
            return func

        else:
            task = app.task(f_job, bind=True, name=name, acks_late=True, autoretry_for=self.autoretry_for,
                            retry_kwargs={'max_retries': self.max_retries}, default_retry_delay=60,
                            retry_backoff=True)

            app.register_task(task)

            _logger.info("create celeryTask[%s]  instance  = %s " % (name, task))

            f_job.AsyncResult = task.AsyncResult
            self.tasks[name] = (task, f_job)
            return f_job


class celeryRpc:
    def __init__(self, db, **kwargs):
        self.db = db
        self.kwargs = kwargs

    def env(self, model):
        return modelRpcStub(self.db, model, **self.kwargs)


if __name__ == "__main__":
    enable_celery_task = True
    api = celeryRpc("campus", queue="campus.tasks.orm").env("campus.api")
    for i in range(0,10000):
        r= api.on_new_product(i)
    print r



