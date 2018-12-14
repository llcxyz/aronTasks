# coding: utf-8
broker_url = 'redis://192.168.80.200:6379/0'
task_serializer = 'json'
task_routes = {'feed.tasks.import_feed': {'queue': 'feeds'}}
task_ignore_result = False
result_backend = 'redis://192.168.80.200:6379/1'
enable_celery_task = True
task_default_queue = 'aronTasks'
app_name = 'aronTask'
event_queue_prefix = "*"

