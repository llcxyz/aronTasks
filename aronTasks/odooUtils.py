# coding:utf-8
import ConfigParser
import openerp
import logging
import urlparse
import os

from openerp.modules.registry import RegistryManager

global DATABASES
global DB_CLUSTERS

DATABASES = {}
DB_CLUSTERS = {}

_log = logging.getLogger(__name__)


def load_database_config():
    global DATABASES
    global DB_CLUSTERS
    if 'dbs_config' in openerp.tools.config.options:
        conf = openerp.tools.config['dbs_config']
        cp = ConfigParser.ConfigParser()
        cp.readfp(fp=open(conf))
        for sec in cp.sections():
            if sec.startswith("db-"):
                info = {'host': cp.get(sec, "host"), 'port': int(cp.get(sec, "port")),
                        'user': cp.get(sec, 'user'), 'password': cp.get(sec, 'password')}

                DB_CLUSTERS[sec[3:]] = info

        options = cp.options("databases")
        for opt in options:
            DATABASES[opt] = cp.get("databases", opt)

    for name, cluster in DATABASES.items():
        print 'Load Database ConnectionInfo %s = %s ' % (name, cluster)


def connection_info_for(db_or_uri):
    global DATABASES
    global DB_CLUSTERS
    if db_or_uri.startswith(('postgresql://', 'postgres://')):
        # extract db from uri
        us = urlparse.urlsplit(db_or_uri)
        if len(us.path) > 1:
            db_name = us.path[1:]
        elif us.username:
            db_name = us.username
        else:
            db_name = us.hostname
        return db_name, {'dsn': db_or_uri}

    # 获取db映射配置
    # dname = db_or_uri.replace(".xunjiexidi.com", "")
    connection_info = False
    if db_or_uri not in DATABASES:
        load_database_config()

    if db_or_uri in DATABASES:
        connection_info = DB_CLUSTERS[DATABASES[db_or_uri]]
        connection_info['database'] = db_or_uri
        #print 'connection_info = %s ' % connection_info
    else:
        connection_info = {'database': db_or_uri}
        for p in ('host', 'port', 'user', 'password'):
            cfg = openerp.tools.config['db_' + p]
            if cfg:
                connection_info[p] = cfg

    return db_or_uri, connection_info


def odoo_cron_polling_job(db_name):
    """
        执行具体轮询.

    :param db_name:
    :return:
    """
    _log.debug("polling for jobs %s " % db_name)
    print "CronJob[PID=%s]  polling [%s] for jobs ....." % (os.getpid(), db_name)
    try:
        register = openerp.registry(db_name)
        while True and register.ready:
            acquired = openerp.addons.base.ir.ir_cron.ir_cron._acquire_job(db_name)
            if not acquired:
                # openerp.modules.registry.RegistryManager.delete(db_name)
                break

        print "CronJob[PID=%s] polling [%s] for jobs         [OK]" % (os.getpid(), db_name)

    except Exception, ex:
        msg = "CronJob[PID=%s] polling [%s] for jobs  Exceptions Occured!" % (os.getpid(), db_name)
        _log.exception(msg)
        print msg

    finally:
        openerp.sql_db.close_db(db_name)


def odoo_preload_registry(dbnames):
    """ Preload a registry, and start the cron."""
    config = openerp.tools.config
    for db_name in dbnames:
        try:
            _log.info("preload registery[%s] dbname=%s" % (os.getpid(), db_name))
            update_module = config['init'] or config['update']
            modules = {}
            if config['init']:
                m = config['init'].split(",")
                for i in m:
                    modules[i] = True

                config['init'] = modules

            elif config['update']:
                m = config['update'].split(",")
                for i in m:
                    modules[i] = True

                config['update'] = modules

            registry = RegistryManager.new(db_name, update_module=update_module)

        except Exception, ex:
            _log.exception('Failed to initialize database `%s`.', db_name)
            _log.exception(ex)
