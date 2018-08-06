# coding: utf-8
broker_url = 'pyamqp://aron:aron@192.168.80.200'
task_serializer = 'json'
task_routes = {'feed.tasks.import_feed': {'queue': 'feeds'}}
task_ignore_result = False
result_backend = 'redis://192.168.80.200:6379/1'
