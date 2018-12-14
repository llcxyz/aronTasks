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
from openerp.modules.registry import RegistryManager
import ConfigParser
from string import Template

from odooUtils import connection_info_for
from odooUtils import odoo_preload_registry
from odooUtils import odoo_cron_polling_job

_logger = logging.getLogger('odooCelery')

# 替换
openerp.sql_db.connection_info_for = connection_info_for


app = Celery('odooCelery')

app.config_from_object('celeryconfig')


def start_odoo():
    # config_file = ".celery.odoo.conf"
    # with open(config_file, "r") as r:
    #     config_file = r.readline().strip().replace("\n", "")
    #     _logger.info("loading config file: %s " % config_file)

    config_file = generate_dynamic_config(sys.argv[1])

    argv = ["-c", config_file]
    openerp.tools.config.parse_config(argv)
    openerp.netsvc.init_logger()
    openerp.modules.module.initialize_sys_path()
    db_name = openerp.tools.config['db_name']
    print "odoo init Ok, try to preload %s "% db_name
    odoo_preload_registry([db_name])

    print "odoo preload %s  ok!" % db_name

    # 注意. 此处需要移除掉配置文件.celery worker 不支持你.
    del sys.argv[1]


def generate_dynamic_config(config_file):
    print 'read config file: [%s] ' % config_file

    def render(vars, val):
        val = val.replace("%(", "${").replace(")", "}")
        t = Template(val)
        return t.safe_substitute(**vars)

    # 把文件内的%(都提换成${
    new_config_file = ".autogen.odoo.conf"
    f2 = open(config_file, "r")
    content = f2.read()
    f2.close()

    content = content.replace("%(", "${").replace(")", "}")
    f3 = open(new_config_file, "wb")
    f3.write(content)
    f3.close()

    cfg = ConfigParser.ConfigParser()
    cfg.read(new_config_file)

    if cfg.has_section("options"):
        # 原始odoo 配置文件. 直接使用.
        return config_file
    elif cfg.has_section("uwsgi"):
        # uwsgi 配置文件.直接将uwsgi 替换成options.
        cfg2 = ConfigParser.ConfigParser()
        cfg2.add_section("options")
        # 模板变量.
        vars = {}
        for opt in cfg.options("uwsgi"):
            if cfg.get("uwsgi", opt).find("%(") == -1:
                # print 'reading %s ' % opt
                vars[opt] = cfg.get("uwsgi", opt)

        for opt in cfg.options("uwsgi"):
            cfg2.set("options", opt, render(vars, cfg.get("uwsgi", opt)))

        cfg2.write(open(new_config_file, "wb"))
        print "generate odoo config file: [%s] " % new_config_file
        return new_config_file


@app.on_after_configure.connect
def setup_odoo_cron_timer_tasks(sender, **kwargs):
    """
        每120秒触发一次odoo cron. 以轮询任务.

    :param sender:
    :param kwargs:
    :return:
    """
    trigger_for_each = 120
    sender.add_periodic_task(trigger_for_each, cronTaskDispatch.s(),
                             name='trigger[celery.odoo.cron.dispatch] for every 120 seconds')


@app.task(name="odoo.cron.dispatch")
def cronTaskDispatch():
    """
        定时任务分发器.
        每1分钟执行一次.
        遍历所有实例数据库. 去轮询定时任务.

    :return:
    """
    from odooUtils import DATABASES
    print 'start odoo cron dispatch !'
    for name in DATABASES.keys():
        _logger.info("beat database[%s] for cron job" % name)
        cronTaskExecutor.apply_async(args=[name])


@app.task(name="odoo.cron.executor")
def cronTaskExecutor(db_name):
    """
        执行具体轮询.

    :param db_name:
    :return:
    """
    odoo_cron_polling_job(db_name)


def start():
    start_odoo()
    app.start()
