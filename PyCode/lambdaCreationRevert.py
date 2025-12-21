import boto3
import argparse
import json
import os
import time
from botocore.exceptions import ClientError

STATE_FILE_DEFAULT = "env_inputs.json"

COMMON_ENVS = [
    "dev", "qa", "qa2", "qa3", "perf",
    "hotfixes", "beta", "uat", "prod", "dr"
]


def select_state_file(region):
    if region == "us-west-1":
        return "env_inputs_usw1.json"
    elif region == "us-west-2":
        return "env_inputs_usw2.json"
    elif region == "eu-west-1":
        return "env_inputs_euw1.json"
    return STATE_FILE_DEFAULT


def load_state(state_file):
    if not os.path.exists(state_file):
        raise Exception(f"State file not found: {state_file}")

    with open(state_file, "r") as f:
        return json.load(f)


def build_env_config(env_inputs):
    env_config = {}

    for env in COMMON_ENVS:
        env_config[env] = {
            "region": env_inputs["common"]["region"],
            "vpc_id": env_inputs["common"]["vpc_id"],
        }

    env_config["uat"] = {
        "region": env_inputs["uat"]["region"],
        "vpc_id": env_inputs["uat"]["vpc_id"],
    }

    env_config["dr"] = {
        "region": env_inputs["dr"]["region"],
        "vpc_id": env_inputs["dr"]["vpc_id"],
    }

    return env_config


def delete_lambda(lambda_client, function_name):
    try:
        print(f"[DELETE LAMBDA] {function_name}")

        # Remove alias if exists
        try:
            lambda_client.delete_alias(
                FunctionName=function_name,
                Name="active"
            )
            print("  └─ Alias deleted")
        except lambda_client.exceptions.ResourceNotFoundException:
            pass

        # Remove reserved concurrency
        try:
            lambda_client.delete_function_concurrency(
                FunctionName=function_name
            )
            print("  └─ Reserved concurrency removed")
        except lambda_client.exceptions.ResourceNotFoundException:
            pass

        lambda_client.delete_function(FunctionName=function_name)
        print("  └─ Lambda deleted")

    except lambda_client.exceptions.ResourceNotFoundException:
        print(f"[SKIP] Lambda not found: {function_name}")


def wait_for_sg_detach(ec2, sg_id, max_wait_minutes=20):

    print(f"  └─ Waiting for ENIs to detach from SG {sg_id}")

    max_attempts = max_wait_minutes * 6  # 10s sleep

    for i in range(max_attempts):
        response = ec2.describe_network_interfaces(
            Filters=[{"Name": "group-id", "Values": [sg_id]}]
        )

        if not response["NetworkInterfaces"]:
            print("  └─ ENIs detached")
            return True

        if i % 30 == 0:
            print(f"  └─ Still waiting... ({i * 10}s elapsed)")

        time.sleep(10)

    print(
        f" ENIs still attached after {max_wait_minutes} minutes. "
        f"Skipping SG deletion."
    )
    return False



def delete_security_group(ec2, vpc_id, sg_name):

    sg_name = f"{sg_name}-sg"

    try:
        response = ec2.describe_security_groups(
            Filters=[
                {"Name": "group-name", "Values": [sg_name]},
                {"Name": "vpc-id", "Values": [vpc_id]},
            ]
        )

        if not response["SecurityGroups"]:
            print(f"[SKIP] SG not found: {sg_name}")
            return

        sg_id = response["SecurityGroups"][0]["GroupId"]

        detached = wait_for_sg_detach(ec2, sg_id)

        if not detached:
            return  # DO NOT FAIL PIPELINE

        ec2.delete_security_group(GroupId=sg_id)
        print(f"[DELETE SG] {sg_name} ({sg_id})")

    except ClientError as e:
        print(f"[ERROR] Failed deleting SG {sg_name}: {e}")


def parse_args():
    parser = argparse.ArgumentParser("Lambda rollback script")
    parser.add_argument(
        "--lambda_name",
        required=True,
        help="Base lambda name (same value used during creation)"
    )
    parser.add_argument(
        "--region",
        default=os.environ.get("REGION", "us-west-1"),
        help="Primary region"
    )
    return parser.parse_args()


def main():
    args = parse_args()
    session = boto3.Session(profile_name="Aditya-demo")

    region = os.environ.get("REGION", "us-west-1")

    state_file = select_state_file(region)
    env_inputs = load_state(state_file)
    env_config = build_env_config(env_inputs)

    for env in COMMON_ENVS:
        cfg = env_config[env]
        region = cfg["region"]
        vpc_id = cfg["vpc_id"]

        lambda_name = f"zen-{env}-{args.lambda_name}"

        print(f"\n=== ROLLBACK {env.upper()} ({region}) ===")

        lambda_client = session.client("lambda", region_name=region)
        ec2 = session.client("ec2", region_name=region)

        delete_lambda(lambda_client, lambda_name)
        delete_security_group(ec2, vpc_id, lambda_name)


if __name__ == "__main__":
    main()
