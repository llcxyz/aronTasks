---
title: Odoo与实时分布式任务系统Celery集成
date: 2018-08-07 23:06:29
categories: 码苑杂谈
tags:
- Odoo
- Celery
thumbnail: http://image.bubuko.com/info/201807/20180718223649676116.png

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
<!-- more -->
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

在同目录下创建celeryconfig.py 
配置如下:
```conf

# coding: utf-8
broker_url = 'redis://192.168.80.200:6379/0'
task_serializer = 'json'
task_routes = {'feed.tasks.import_feed': {'queue': 'feeds'}}
task_ignore_result = False
result_backend = 'redis://192.168.80.200:6379/1'
enable_celery_task = True
task_default_queue = 'aronTasks'
app_name = 'projectA'
event_queue_prefix = "*"
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
引入aronTask编写自定义的引导worker. 先初始化odoo.让所有celery task都被注册上.

新建文件名为 myOdooWorker.py

```python

#coding:utf-8
from aronTasks import odooCelery
if __name__ == "__main__":
    odooCelery.start()



```
启动实例:
```bash
[root@simple3 ~]# python myOdooWorker.py my_odoo.conf worker -Q campus.tasks.orm -n host1 --loglevel=DEBUG --concurrency=4
```

启动4个进程.处理celery任务. 同时监听队列: campus.tasks.orm, celeryWorker在启动前，先根据my_odoo.conf的odoo配置文件初始化odoo实例.

### 最后
**使用aronTasks的 celeryTask. 所有任务名称是以 [app_name][模型].[函数名] 组成.
比如示例的 present_voucher 方法.最后对应到celery的task name 是: projectA[res.users].present_voucher,
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
* priority
        优先级
        
