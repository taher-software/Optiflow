---
name: async-job
description: async job design base for this code base
context: fork
disable-model-invocation: false
---

Create new async job:
1. Create a new file for the async job in the `src/app/async_jobs/` folder, e.g. `my_async_job.py` if the job is called `my_async_job` and the file file doesn' t exist yet.
2. the async shoudl use backoff strategy to retry, and the max retry times should be 3 by default.
3. the async job should be idempotent, which means it can be retried without causing unintended side effects. This is crucial for ensuring that retries do not lead to duplicate processing or inconsistent states. 
4. each async job handle functional failure and system failure separately. if the failure is caused by functional failure, which means the input data is invalid or some business logic condition is not met, the async job should log the error and skip the retry. if the failure is caused by system failure, which means some external system is down or some transient error happens, the async job should retry until the max retry times is reached. in case the max retry times is reached, the async job should log the error and return 200 response with error message in the body, so we can avoid the job requeud and retried for something that is not going to succeed.
5. Ensure that a new job type is added to the Jobtype enum in `src/app/globals/enum` and his router get mapped in the `src/app/async_jobs/__init__.py` file.