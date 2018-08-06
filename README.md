# aronTasks
odoo 与 celery 集成  odoo with celery support

原文见 : https://www.aron9g.com/2018/08/08/Odoo%E4%B8%8ECelery%E9%9B%86%E6%88%90.html

---
### [Odoo](https://www.odoo.com/zh_CN/)
Odoo 是一系列开源商业应用套件,通过不同的模块组合,可以满足大部分企业应用场景.
    比如ERP,CRM,WMS,在线商店,企业网站等等..., 同时其底层的基础应用框架.非常强大和灵活.
    基于Odoo框架的应用开发将大大缩短产品的交付周期。
    Odoo 是Python语言实现. 其前身是OpenERP, [Odoo 的开源协议已由 AGPL 转变为 LGPL v3](https://www.odoo.com/zh_CN/blog/odoo-news-5/post/adapting-our-open-source-license-245)

### [Celery](http://www.celeryproject.org/)
Celery 是一个简单、灵活且可靠的，处理大量消息的分布式系统，并且提供维护这样一个系统的必需工具。
它是一个专注于实时处理的任务队列，同时也支持任务调度,Odoo开源协议是[BSD 协议](http://www.opensource.org/licenses/BSD-3-Clause)

### [aronTasks](https://github.com/llcxyz/aronTasks)
aronTask就是odoo和celery的粘合剂.方便开发人员快速将celery应用到自己的odoo项目中.已有的项目只需要添加一个装饰器,
便可将任务变成异步处理.同步和异步处理可自由切换.

### Odoo 为什么需要 Celery
答案是任何需要异步处理的场合,celery都可以胜任。
1. 处理耗时任务
        对于上传的视频，图片，文件处理.交由celery处理.只要最后给个结果通知即可.
        celery支持将结果保存到redis. 同时支持任务状态更新.
        
3. 减少单系统负载.提高并发能力.
        对于某些单个请求包含多个并行任务的场景,可以将多个任务交由celery在其他机器处理.
        比如，用户注册时,需要给他发一封邮件，发一个短信. 并将该用户数据通知另外的业务系统.同时在redis里更新用户注册数量.
        发邮件/短信/通知第三方系统/更新统计数据. 这些任务是可以并行执行的.并且可以不在同一个业务实例或系统内.
        
### 如何快速集成
celery与odoo集成在github上有多个项目方案.经过我实测试.发现均不能满足我的需求.并且有各种问题未考虑周全.而无法应用到生产环境.
故结合这些项目的优缺点与自己的理解.重造了一个轮子[aronTask](), 目前已用在生产环境中.运行稳定。

#### 准备工作.
在你自己的odoo配置文件中增加以下几行.
```conf

celery_broker_url = pyamqp://aron:aron@127.0.0.1//  # 使用rabbitMQ 作为broker
celery_backend_url=redis://127.0.0.1:6379/1   # 使用redis保存结果.
enable_celery_task=True  # 是否启用celery.

```
####   Step 1 挂载装饰器.
在odoo模型上直接挂载装饰器.celeryTask.

```python
# coding:utf-8
from odoo.models import Model
from aronTasks.celeryTask import celeryTask
from odoo import api

class res_users(Model):
    _inherit = "res.users"
    
    @celeryTask(model=_inherit, name="present_gift")
    @api.model
    def present_voucher(self):
        """
            给用户发送优惠券.
            
        """
        # 发送优惠券的具体实现代码
        #  [.....]
        pass
        
    
```
###  Step2 调用目标方法.
实际上,调用目标方法时.已经将目标方法转换成celery的任务消息.并发送给broker. 这里是rabbitMQ
也就是说，调用方法并没有真正执行.真正执行是在celeryWorker 里面，
celery worker 接受到这个任务消息并匹配到这个方法. 才会执行.


```python
# coding:utf-8
from openerp import http
from openerp.http import request
import logging

_log = logging.getLogger(__name__)

class CampusApi(http.Controller):
    @http.route("/scl/register", type='json', auth='user')
    def register(self, **kwargs):
    """
        注册demo 
    """
    user = request.env.user
    user.present_voucher()
    ...
    
```


完全不必理会其中差异.按正常方法调用ORM方法调用即可.


####   Step 3 运行 odooCelery 实例.
在启动celery worker 之前.我们需要编写自定义的引导worker. 先初始化odoo.让所有celery task都被注册上.

odooCelery.py
```python
# coding:utf-8
import sys

import os
import openerp
import logging
from celery import Celery
from openerp.api import Environment
from openerp.modules.registry import Registry
from openerp.modules.registry import RegistryManager

app = Celery('odooCeleryTask')

app.config_from_object('celeryconfig')

odoo_loaded = False

_logger = logging.getLogger('odooCelery')


def start_odoo():
    config_file = ".celery.odoo.conf" #  这个文件内保存 odoo 的配置文件路径.以便根据此配置文件启动odoo服务.
    with open(config_file, "r") as r:
        config_file = r.readline().strip().replace("\n", "")
        _logger.info("loading config file: %s " % config_file)

    argv = ["-c", config_file]
    openerp.tools.config.parse_config(argv)
    openerp.netsvc.init_logger()
    openerp.modules.module.initialize_sys_path()
    openerp.multi_process = True # 多进程模式.
    db_name = openerp.tools.config['db_name']
    preload_registry([db_name]) # 这个地方先初始化db.让celery 的task 全部注册上去.
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



```
启动实例:
```bash
[root@simple3 ~]# python odooCelery.py worker -Q campus.tasks.orm -n host1 --loglevel=DEBUG --concurrency=4
```

启动4个进程.处理celery任务. 同时监听队列: campus.tasks.orm
### 最后
**使用aronTasks的 celeryTask. 所有任务名称是以 [模型].[函数名] 组成.
比如示例的 present_voucher 方法.最后对应到celery的task name 是: res.users.present_voucher,
这样的好处是对celery任务的管理更加方便.如果使用Flower 来监控与管理任务.会更清晰的看到具体的任务执行情况.**


**如果在celery worker 内执行的方法. env.context 对象里会有一个名称为celeryTask的Task对象实例.
通过调用该task对象的update_state方法来实现进度通知.**

```python

    task = self.env.context['celeryTask'] 
    for i in range(0, 10):
        time.sleep(1)
        task.update_state(state='PROGRESS', meta={'current': i, 'total': 10, 'status': "OK[%s]" % i})

```

**项目地址: [https://github.com/llcxyz/aronTasks](https://github.com/llcxyz/aronTasks)**

### celeryTask 支持的参数:
* name      
        方法名. 如不填,将使用当前函数的名字.
* model
        模型名称,odoo模型名称. _name
* queue
        任务队列. 任务将发往那个队列.如果不填，则默认使用 openerp.tools.config['celery_default_queue']
* dbname
        数据库名. 执行任务的数据库. 默认是本地. 当在不同的系统间只要都使用celery,那么可以将请求发送给其他系统数据库处理.
* countdown
        重试计算器.
* eta 
        逝去时间 
* expires
        过期时间
priority
        优先级




    



