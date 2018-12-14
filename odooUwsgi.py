# coding:utf-8

import logging
import urlparse
import os
import uwsgi
import sys
import werkzeug
import ConfigParser

from uwsgidecorators import *

_logger = logging.getLogger(__name__)

uwsgi_conf = {}

# sys.meta_path.insert(0, uwsgi.SymbolsImporter())


if 'ext-package' in uwsgi.opt:
    print 'Try to loading core ext-package ', uwsgi.opt['ext-package']
    core_base = uwsgi.opt['ext-package'].split(";")
    for pkg in core_base:
        sys.path.append(pkg)

import openerp
from openerp.service.wsgi_server import application_unproxied
from openerp.service.server import load_server_wide_modules

from odooUtils import connection_info_for
from odooUtils import odoo_cron_polling_job
from odooUtils import load_database_config
from odooUtils import odoo_preload_registry

from odooUtils import DATABASES

from celeryTask import app


# 替换
openerp.sql_db.connection_info_for = connection_info_for


def v9_load_conf():
    """
    载入配置.
    """

    print "*" * 60
    for opt in uwsgi.opt:
        print "\t%s=%s" % (opt, uwsgi.opt[opt])
        print "\t\tAPP CONFIG:%s=%s" % (opt, uwsgi.opt[opt])
        openerp.tools.config.options[opt] = uwsgi.opt[opt]
        uwsgi_conf[opt] = uwsgi.opt[opt]

    print "*" * 60


def config_db_list():
    load_database_config()
    if not DATABASES:
        load_database_config()

    return DATABASES.keys()


def db_list():
    if openerp.tools.config['db_name']:
        db_names = openerp.tools.config['db_name'].split(',')
    else:
        db_names = openerp.service.db.list_dbs(True)
        db_names = filter(lambda x: x.endswith(".xunjiexidi.com"), db_names)
    return db_names


def cron_works(signum):
    """
    execute  cron for v7
    """

    db_names = db_list()
    print 'cron load dblist: %s '% db_names

    for db in db_names:
        odoo_cron_polling_job(db)


@app.task(name="odoo.cron.dispatch")
def celery_odoo_cron_dispatch():
    print "WARNING.THIS SHOULD NOT BE APPEAR!!, ODOO TIMER MAY NOT WORK!"


def celery_cron_trigger(signum):
    "Execute "
    print "trigger odoo celery timer"
    celery_odoo_cron_dispatch.apply_async()

app_name = uwsgi.opt['app_name']


def v9_init():
    import openerp
    server_wide_modules = openerp.tools.config['server_wide_modules'].split(",")
    print 'server wide modules', server_wide_modules
    openerp.conf.server_wide_modules = server_wide_modules

    if 'multi' in uwsgi_conf and uwsgi_conf['multi']:
        openerp.multi_process = True  # 多进程模式.

    openerp.netsvc.init_logger()

    openerp.modules.module.initialize_sys_path()

    load_server_wide_modules()

    config = openerp.tools.config

    if 'preload' in config.options:
        odoo_preload_registry(db_list())


config = openerp.tools.config


@postfork
def worker():
    mule_id = uwsgi.mule_id()
    if mule_id == 0:
        uwsgi.setprocname("%s worker %s" % (app_name, uwsgi.worker_id()))
    else:
        uwsgi.setprocname("%s mule %s" % (app_name, uwsgi.mule_id()))


def application2(environ, start_response):
    if config['proxy_mode'] and 'HTTP_X_FORWARDED_HOST' in environ:
        return werkzeug.contrib.fixers.ProxyFix(application_unproxied)(environ, start_response)
    else:
        return application_unproxied(environ, start_response)


def v9_application():
    print 'Starting [%s] Service ....' % app_name
    config = openerp.tools.config
    # 使用celery去触发定时器.
    period_sec = 60
    if 'cron_by_celery_beats' in config.options:
        print "NO CRON TRIGGER,PLEASE ENABLE CELERY BEATS!!"

    elif 'cron_by_celery_worker' in config.options:
        print "Using UWSGI TIMER TO TRIGGER CRON IN CELERY WORKER!"
        uwsgi.register_signal(99, "mule1", celery_cron_trigger)
        uwsgi.add_rb_timer(99, period_sec)
    else:
        uwsgi.register_signal(99, "mule1", cron_works)
        uwsgi.add_rb_timer(99, period_sec)

    # else:
    #     uwsgi.register_signal(99, "mule1", cron_works)
    #     # uwsgi.register_signal(101,"mule2", notify_wechat_news)
    #     print 'Register Signal 99 for mule1 as Cron workers'

    # linux 2.6.25以下内核.不支持timerfd.所以使用rb_timer.

    # uwsgi.add_rb_timer(101,60)
    # uwsgi.register_signal(100, "workers", v7_reload)
    # uwsgi.register_signal(101, "workers", service_active)
    # uwsgi.register_signal(102, "workers", service_deactive)

    return application2


def bootstrap():
    v9_load_conf()
    v9_init()
    return v9_application()

uwsgi.setprocname("%s master" % app_name)
