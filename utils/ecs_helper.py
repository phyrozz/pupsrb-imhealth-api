import boto3
import json
import os
from typing import Optional


class ECSHelper:
    def __init__(self, task_definition: Optional[str] = None):
        self.cluster = os.environ.get("CLUSTER")
        self.task_definition = task_definition or os.environ.get("TASK_DEFINITION")
        self.subnets = json.loads(os.environ.get("SUBNETS", "[]"))
        self.security_groups = json.loads(os.environ.get("SECURITY_GROUPS", "[]"))
        self.region = os.environ.get("AWS_REGION", "ap-southeast-1")
        self.ecs = boto3.client("ecs", region_name=self.region)

    def run_task(self, container_name: str, event: Optional[dict] = None) -> None:
        if not self.cluster or not self.task_definition:
            raise ValueError("CLUSTER and TASK_DEFINITION must be set")

        env_vars = {k: v for k, v in os.environ.items() if v is not None}
        if event is not None:
            env_vars["TASK_EVENT"] = json.dumps(event, separators=(",", ":"), ensure_ascii=False)

        self.ecs.run_task(
            cluster=self.cluster,
            taskDefinition=self.task_definition,
            launchType="FARGATE",
            platformVersion="LATEST",
            networkConfiguration={
                "awsvpcConfiguration": {
                    "subnets": self.subnets,
                    "securityGroups": self.security_groups,
                    "assignPublicIp": "ENABLED",
                }
            },
            overrides={
                "containerOverrides": [{
                    "name": container_name,
                    "environment": [{"name": k, "value": v} for k, v in env_vars.items()],
                }]
            },
        )
