---
name: endpoint-structure
description: endpoint design pattern for this code base
context: fork
disable-model-invocation: false
---

Create new endpoint:
1. Create all input base model in modelsIn file within the same router of endpoint
2. Add rich documentation for the endpoint
3. The response model of the endpoint should always of type ApiResponse
4. Create the base model of model response in modelsOut within the same router of the code.
5. Create the logic of the endpoint in the file services of the same folder of the router of the endpoint.
6. Treat every endpoint as a single atomic transaction. Any failure must trigger a complete rollback of all operations performed by that endpoint, including database changes and any resources created during execution whenever possible. The endpoint should either complete successfully or leave the system unchanged.