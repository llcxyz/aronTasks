# coding:utf-8
import sys

prj_base = "E:\\project2013\\clouderp\\platform\\myodoov9"
sys.path.append(prj_base)
prj_base = "/mnt/e/project2013/clouderp/platform/myodoov9"
sys.path.append(prj_base)

prj_base = "/root/clouderp/platform/myodoov9"
sys.path.append(prj_base)
import os
import openerp
import logging
from celery import Celery
from openerp.api import Environment
from openerp.modules.registry import Registry
from openerp.modules.registry import RegistryManager

_logger = logging.getLogger('workerCelery')


app = Celery('odooAsyncTask')

app.config_from_object('celeryconfig')

odoo_loaded = False


def start_odoo():
    config_file = ".celery.odoo.conf"
    with open(config_file, "r") as r:
        config_file = r.readline().strip().replace("\n", "")
        _logger.info("loading config file: %s " % config_file)

    argv = ["-c", config_file]
    openerp.tools.config.parse_config(argv)
    openerp.netsvc.init_logger()
    openerp.modules.module.initialize_sys_path()
    # openerp.multi_process = True
    preload_registry(["campus"])
    odoo_loaded = True


def preload_registry(dbnames):
    """ Preload a registry, and start the cron."""
    config = openerp.tools.config
    for dbname in dbnames:
        try:
            print "preload registery[%s] dbname=%s" % (os.getpid(), dbname)
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

            registry = RegistryManager.new(dbname, update_module=update_module)

        except Exception:
            _logger.exception('Failed to initialize database `%s`.', dbname)


start_odoo()

if __name__ == "__main__":
    app.start()
