import boto3
import json
import os
from typing import Optional


def get_identifier_list(name: str) -> list[str]:
    """Read an ECS identifier list from JSON or legacy comma-separated config."""
    raw_value = os.environ.get(name, "").strip()
    if not raw_value:
        return []

    try:
        values = json.loads(raw_value)
    except json.JSONDecodeError:
        values = [value.strip() for value in raw_value.split(",") if value.strip()]

    if not isinstance(values, list) or not all(
        isinstance(value, str) and value.strip() for value in values
    ):
        raise ValueError(
            f"{name} must be a JSON array of non-empty strings or a comma-separated list"
        )
    return values


class ECSHelper:
    def __init__(self, task_definition: Optional[str] = None):
        self.cluster = os.environ.get("CLUSTER")
        self.task_definition = task_definition or os.environ.get("TASK_DEFINITION")
        self.subnets = get_identifier_list("SUBNETS")
        self.security_groups = get_identifier_list("SECURITY_GROUPS")
        self.region = os.environ.get("AWS_REGION", "ap-southeast-1")
        self.ecs = boto3.client("ecs", region_name=self.region)

    def run_task(self, container_name: str, event: Optional[dict] = None) -> None:
        if not self.cluster or not self.task_definition or not self.subnets:
            raise ValueError("CLUSTER, TASK_DEFINITION, and at least one SUBNETS value must be set")

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
