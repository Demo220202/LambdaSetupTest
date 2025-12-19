import json
import argparse
import boto3
from botocore.exceptions import ClientError
import zipfile
import io
import os
from aws_functions import *
from dotenv import load_dotenv

load_dotenv()

STATE_FILE = "env_inputs.json"

def load_state():
    global ENV_INPUTS
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            ENV_INPUTS = json.load(f)
        print("Loaded ENV_INPUTS from file")
    else:
        print("No existing state file found, using defaults")


def save_state():
    with open(STATE_FILE, "w") as f:
        json.dump(ENV_INPUTS, f, indent=2)
    print("Saved ENV_INPUTS to file")



# ENV_INPUTS = {
#     "common": {
#         "region": "us-west-2",
#         "vpc_name": "zen-common-vpc",   # OR vpc_id directly
#     },
#     "uat": {
#         "region": "us-west-2",
#         "vpc_name": "zen-uat-vpc",
#     },
#     "dr": {
#         "region": "us-east-1",
#         "vpc_name": "zen-dr-vpc",
#     }
# }

COMMON_ENVS = ["dev", "qa", "qa2", "qa3", "perf", "hotfixes", "beta", "prod"]


def parse_args():
    parser = argparse.ArgumentParser(description="Lambda creation automation")

    parser.add_argument(
        "--phase",
        required=True,
        choices=[
            "vpc_listing",
            "vpc_selection",
            "subnet_listing",
            "subnet_selection",
            "finalize"
        ],
        help="Pipeline execution phase"
    )

    # ===== finalize phase inputs =====
    parser.add_argument("--lambda_name", help="Base Lambda name (without env prefix)")
    parser.add_argument("--runtime", help="Lambda runtime (e.g. python3.9)")
    parser.add_argument("--role_name", help="IAM role name for Lambda")
    parser.add_argument("--memory", help="Memory size in MB")
    parser.add_argument("--timeout", help="Timeout in seconds")
    parser.add_argument("--ephemeral_storage", help="Ephemeral storage in MB")

    parser.add_argument(
        "--layers",
        nargs="*",
        default=[],
        help="Lambda layer names (space separated)"
    )

    parser.add_argument(
        "--enable_reserved_concurrency",
        help="Enable reserved concurrency"
    )

    parser.add_argument(
        "--reserved_concurrency",
        help="Reserved concurrency value"
    )

    return parser.parse_args()


def list_vpcs(region, session):
    vpcs = get_vpcs_list(region, session)

    print(f"\nVPCs in region {region}")
    print("-" * 60)
    for vpc in vpcs:
        print(f"Name: {vpc['Name']:<30} VpcId: {vpc['VpcId']}")


def phase_vpc_listing(session):
    regions = {
        "common": ENV_INPUTS["common"]["region"],
        "uat": ENV_INPUTS["uat"]["region"],
        "dr": ENV_INPUTS["dr"]["region"],
    }

    for env, region in regions.items():
        print(f"\n=== {env.upper()} ===")
        list_vpcs(region, session)

def phase_vpc_selection():
    """
    Expects:
    VPC_IDS=vpc-aaa,vpc-bbb,vpc-ccc
    """
    vpc_ids = os.environ.get("VPC_ID", "")
    if not vpc_ids:
        raise Exception("VPC_ID env var not provided")

    vpc_list = [v.strip() for v in vpc_ids.replace(",", " ").split()]

    if len(vpc_list) != 3:
        raise Exception("Expected 3 VPC IDs: common, uat, dr")

    ENV_INPUTS["common"]["vpc_id"] = vpc_list[0]
    ENV_INPUTS["uat"]["vpc_id"] = vpc_list[1]
    ENV_INPUTS["dr"]["vpc_id"] = vpc_list[2]

    print("Selected VPCs:")
    print(json.dumps(ENV_INPUTS, indent=2))


def list_subnets(region, vpc_id, session):
    subnets = get_vpc_subnets(vpc_id, region, session)

    print(f"\nSubnets for VPC {vpc_id}")
    print("-" * 60)
    for s in subnets:
        print(
            f"SubnetId: {s['SubnetId']} | "
            f"AZ: {s['AvailabilityZone']} | "
            f"Name: {s['Name']}"
        )

def phase_subnet_listing(session):
    for env in ["common", "uat", "dr"]:
        region = ENV_INPUTS[env]["region"]
        vpc_id = ENV_INPUTS[env]["vpc_id"]

        print(f"\n=== {env.upper()} ===")
        list_subnets(region, vpc_id, session)

# def phase_subnet_selection():
#     """
#     Expects:
#     SUBNET_IDS=subnet-a subnet-b subnet-c
#     """
#     subnet_ids = os.environ.get("SUBNET_IDS", "")
#     if not subnet_ids:
#         raise Exception("SUBNET_IDS not provided")
#
#     subnets = subnet_ids.split()
#
#     for env in ["common", "uat", "dr"]:
#         ENV_INPUTS[env]["subnets"] = subnets
#
#     print("Final subnet configuration:")
#     print(json.dumps(ENV_INPUTS, indent=2))

def phase_subnet_selection():

    def parse(name):
        val = os.environ.get(name, "").strip()
        if not val:
            raise Exception(f"{name} is required")
        val_list = []

        for val in val.replace(",", " ").split():
            val_list.append(val)

        return val_list

    ENV_INPUTS["common"]["subnets"] = parse("COMMON_SUBNETS")
    ENV_INPUTS["uat"]["subnets"]    = parse("UAT_SUBNETS")
    ENV_INPUTS["dr"]["subnets"]     = parse("DR_SUBNETS")

    print("Subnet mapping completed:")
    print(json.dumps(ENV_INPUTS, indent=2))


def build_env_config_from_inputs():
    env_config = {}

    # Common environments
    for env in COMMON_ENVS:
        env_config[env] = {
            "region": ENV_INPUTS["common"]["region"],
            "vpc_id": ENV_INPUTS["common"]["vpc_id"],
            "subnets": ENV_INPUTS["common"]["subnets"],
        }

    # UAT
    env_config["uat"] = {
        "region": ENV_INPUTS["uat"]["region"],
        "vpc_id": ENV_INPUTS["uat"]["vpc_id"],
        "subnets": ENV_INPUTS["uat"]["subnets"],
    }

    # DR
    env_config["dr"] = {
        "region": ENV_INPUTS["dr"]["region"],
        "vpc_id": ENV_INPUTS["dr"]["vpc_id"],
        "subnets": ENV_INPUTS["dr"]["subnets"],
    }

    return env_config


# def fill_vpc_config(session):
#
#     common_vpc = dict(select_vpc(ENV_INPUTS["common"]["region"], session))
#     uat_vpc = dict(select_vpc(ENV_INPUTS["uat"]["region"], session))
#     dr_vpc = dict(select_vpc(ENV_INPUTS["dr"]["region"], session))
#
#
#     ENV_INPUTS["common"]["vpc_name"] = common_vpc["Name"] if len(common_vpc) > 0 else ENV_INPUTS["common"]["vpc_name"]
#     ENV_INPUTS["uat"]["vpc_name"] = uat_vpc["Name"] if len(uat_vpc) > 0 else ENV_INPUTS["uat"]["vpc_name"]
#     ENV_INPUTS["dr"]["vpc_name"] = dr_vpc["Name"] if len(dr_vpc) > 0 else ENV_INPUTS["dr"]["vpc_name"]
#
#     return common_vpc, uat_vpc, dr_vpc
#
#
# def select_vpc(region, session):
#     vpcs = get_vpcs_list(region, session)
#     if not vpcs:
#         print(f"No VPCs found in region {region}.")
#         return None
#
#     vpc_names = [f"{vpc['Name']} - ID: {vpc['VpcId']}" for vpc in vpcs]
#
#     title = "Select a VPC"
#     menu = TerminalMenu(
#         vpc_names,
#         title=title,
#         cursor_index=0,
#         show_search_hint=True,
#     )
#
#     selected_vpc_index = menu.show()
#     selected_vpc = vpcs[selected_vpc_index]
#
#     print(f"{title}: {vpc_names[selected_vpc_index]}")
#
#     return selected_vpc
#
#
# def select_vpc_subnets(vpc, session):
#     subnets = get_vpc_subnets(vpc["VpcId"], vpc["Region"], session)
#     if not subnets:
#         print(f"No subnets found in VPC {vpc['Name']}.")
#         return []
#
#     subnet_labels = [
#         f"{subnet['Name']} - AZ: {subnet['AvailabilityZone']} - Available IPs: {subnet['AvailableIpAddressCount']}"
#         for subnet in subnets
#     ]
#
#     title = "Select Subnets"
#     menu = TerminalMenu(
#         subnet_labels,
#         title=title,
#         cursor_index=0,
#         multi_select=True,
#         show_search_hint=True,
#     )
#
#     selected_indices = menu.show()
#
#     print(f"{title}: {', '.join([subnet_labels[i] for i in selected_indices])}")
#
#     return [subnets[i] for i in selected_indices]
#
# def resolve_vpc_id(region, vpc_name, session):
#     vpcs = get_vpcs_list(region, session)
#     # print(json.dumps(vpcs, indent=2))
#     #
#     # fill_vpc_config()
#     #
#     # print(json.dumps(ENV_INPUTS, indent=2))
#
#     for vpc in vpcs:
#         if vpc["Name"] == vpc_name:
#             return vpc["VpcId"]
#     raise Exception(f"VPC '{vpc_name}' not found in {region}")
#
# def resolve_subnet_ids(region, vpc_id, session):
#
#     subnets = select_vpc_subnets(vpc_id, session)
#     subnet_ids = []
#
#     if not subnets:
#         raise Exception(f"No private subnets found for {vpc_id} in {region}")
#
#     for subnet in subnets:
#         subnet_ids.append(subnet["SubnetId"])
#
#     return subnet_ids
#
#
# env_config = {}
#
# def build_env_config_vpc(session):
#     # Common VPC for most envs
#     common_region = ENV_INPUTS["common"]["region"]
#
#     # vpcs = get_vpcs_list(common_region, session)
#     # print(json.dumps(vpcs, indent=2))
#
#     common_vpc, uat_vpc, dr_vpc = fill_vpc_config(session)
#
#     common_vpc_id = resolve_vpc_id(
#         common_region, ENV_INPUTS["common"]["vpc_name"], session
#     )
#     common_subnets = resolve_subnet_ids(common_region, common_vpc, session)
#
#     for env in COMMON_ENVS:
#         env_config[env] = {
#             "region": common_region,
#             "vpc_id": common_vpc_id,
#             "subnets": common_subnets,
#         }
#
#     # UAT (different VPC, same region)
#     uat_region = ENV_INPUTS["uat"]["region"]
#
#     uat_vpc_id = resolve_vpc_id(uat_region, ENV_INPUTS["uat"]["vpc_name"], session)
#     uat_subnets = resolve_subnet_ids(uat_region, uat_vpc, session)
#
#     env_config["uat"] = {
#         "region": uat_region,
#         "vpc_id": uat_vpc_id,
#         "subnets": uat_subnets,
#     }
#
#     # DR (different region + VPC)
#     dr_region = ENV_INPUTS["dr"]["region"]
#
#     # vpcs = get_vpcs_list(dr_region)
#     # print(json.dumps(vpcs, indent=2))
#
#     dr_vpc_id = resolve_vpc_id(dr_region, ENV_INPUTS["dr"]["vpc_name"], session)
#     dr_subnets = resolve_subnet_ids(dr_region, dr_vpc, session)
#
#     env_config["dr"] = {
#         "region": dr_region,
#         "vpc_id": dr_vpc_id,
#         "subnets": dr_subnets,
#     }
#
#     return env_config
#
#

# def build_env_config(session):
#
#     env_config = {}
#
#     # Common VPC for most envs
#     common_region = ENV_INPUTS["common"]["region"]
#
#     # vpcs = get_vpcs_list(common_region, session)
#     # print(json.dumps(vpcs, indent=2))
#
#     common_vpc, uat_vpc, dr_vpc = fill_vpc_config(session)
#
#     common_vpc_id = resolve_vpc_id(
#         common_region, ENV_INPUTS["common"]["vpc_name"], session
#     )
#     common_subnets = resolve_subnet_ids(common_region, common_vpc, session)
#
#     for env in COMMON_ENVS:
#         env_config[env] = {
#             "region": common_region,
#             "vpc_id": common_vpc_id,
#             "subnets": common_subnets,
#         }
#
#     # UAT (different VPC, same region)
#     uat_region = ENV_INPUTS["uat"]["region"]
#
#     uat_vpc_id = resolve_vpc_id(uat_region, ENV_INPUTS["uat"]["vpc_name"], session)
#     uat_subnets = resolve_subnet_ids(uat_region, uat_vpc, session)
#
#     env_config["uat"] = {
#         "region": uat_region,
#         "vpc_id": uat_vpc_id,
#         "subnets": uat_subnets,
#     }
#
#     # DR (different region + VPC)
#     dr_region = ENV_INPUTS["dr"]["region"]
#
#     # vpcs = get_vpcs_list(dr_region)
#     # print(json.dumps(vpcs, indent=2))
#
#     dr_vpc_id = resolve_vpc_id(dr_region, ENV_INPUTS["dr"]["vpc_name"], session)
#     dr_subnets = resolve_subnet_ids(dr_region, dr_vpc, session)
#
#     env_config["dr"] = {
#         "region": dr_region,
#         "vpc_id": dr_vpc_id,
#         "subnets": dr_subnets,
#     }
#
#     return env_config

def get_role_arn(session, role_name):
    iam = session.client("iam")

    try:
        response = iam.get_role(RoleName=role_name)
        return response["Role"]["Arn"]

    except iam.exceptions.NoSuchEntityException:
        raise Exception(f"IAM role '{role_name}' not found")

def wait_for_lambda_update(lambda_client, function_name):
    waiter = lambda_client.get_waiter("function_updated")
    waiter.wait(FunctionName=function_name)

def create_or_update_alias(lambda_client, function_name, alias_name="active"):
    # Publish new version
    response = lambda_client.publish_version(
        FunctionName=function_name
    )
    version = response["Version"]
    print(f"Version: {version}")

    try:
        lambda_client.get_alias(
            FunctionName=function_name,
            Name=alias_name
        )

        lambda_client.update_alias(
            FunctionName=function_name,
            Name=alias_name,
            FunctionVersion=version
        )
        print(f"[ALIAS UPDATED] {alias_name} → v{version}")

    except lambda_client.exceptions.ResourceNotFoundException:
        lambda_client.create_alias(
            FunctionName=function_name,
            Name=alias_name,
            FunctionVersion=version
        )
        print(f"[ALIAS CREATED] {alias_name} → v{version}")


def get_latest_layer_arn(session, layer_name, region):
    """
    Returns the ARN of the latest version of a Lambda Layer.
    """
    lambda_client = session.client("lambda", region_name=region)

    try:
        response = lambda_client.list_layer_versions(
            LayerName=layer_name
        )

        if not response.get("LayerVersions"):
            raise Exception(f"No versions found for layer: {layer_name}")

        # Versions are returned in descending order (latest first)
        latest_layer = response["LayerVersions"][0]
        return latest_layer["LayerVersionArn"]

    except lambda_client.exceptions.ResourceNotFoundException:
        raise Exception(f"Layer not found: {layer_name}")

    except ClientError as e:
        raise Exception(f"Failed to fetch layer ARN for {layer_name}: {e}")


def create_lambda(
    session,
    lambda_name,
    region,
    role_arn,
    runtime,
    memory,
    timeout,
    ephemeral_storage,
    vpc_config=None,
    layers=None,
    tags=None,
    reserved_concurrency=None
):
    lambda_client = session.client("lambda", region_name=region)

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(
            "lambda_function.py",
            "def lambda_handler(event, context):\n    return {'statusCode': 200, 'body': 'Hello'}"
        )
    zip_buffer.seek(0)

    try:
        lambda_client.get_function(FunctionName=lambda_name)
        print(f"[UPDATE] {lambda_name}")

        lambda_client.update_function_code(
            FunctionName=lambda_name,
            ZipFile=zip_buffer.read()
        )

        wait_for_lambda_update(lambda_client, lambda_name)

        lambda_client.update_function_configuration(
            FunctionName=lambda_name,
            Runtime=runtime,
            Role=role_arn,
            MemorySize=memory,
            Timeout=timeout,
            EphemeralStorage={"Size": ephemeral_storage},
            VpcConfig=vpc_config if vpc_config else {},
            Layers=layers or [],
        )

        wait_for_lambda_update(lambda_client, lambda_name)
        create_or_update_alias(lambda_client, lambda_name)

    except lambda_client.exceptions.ResourceNotFoundException:
        print(f"[CREATE] {lambda_name}")

        lambda_client.create_function(
            FunctionName=lambda_name,
            Runtime=runtime,
            Role=role_arn,
            Handler="lambda_function.lambda_handler",
            Code={"ZipFile": zip_buffer.read()},
            MemorySize=memory,
            Timeout=timeout,
            EphemeralStorage={"Size": ephemeral_storage},
            VpcConfig=vpc_config if vpc_config else {},
            Layers=layers or [],
            Tags=tags or {},
        )

        wait_for_lambda_update(lambda_client, lambda_name)
        create_or_update_alias(lambda_client, lambda_name)

    if reserved_concurrency and reserved_concurrency["toggle"]:
        lambda_client.put_function_concurrency(
            FunctionName=lambda_name,
            ReservedConcurrentExecutions=reserved_concurrency["val"]
        )

def get_or_create_sg(session, region, vpc_id, lambda_name):
    ec2 = session.client("ec2", region_name=region)
    sg_name = f"{lambda_name}-sg"

    sgs = ec2.describe_security_groups(
        Filters=[
            {"Name": "group-name", "Values": [sg_name]},
            {"Name": "vpc-id", "Values": [vpc_id]},
        ]
    )["SecurityGroups"]

    if sgs:
        return sgs[0]["GroupId"]

    sg = ec2.create_security_group(
        GroupName=sg_name,
        Description=f"SG for {lambda_name}",
        VpcId=vpc_id,
    )
    return sg["GroupId"]


def main():

    # parser = argparse.ArgumentParser()
    # parser.add_argument("--phase", choices=["vpc_selection", "subnet_selection", "finalize"], required=True,
    #                     help="Pipeline execution phase")
    # args = parser.parse_args()
    #
    # profile_name = "Aditya-demo"
    #
    # session = boto3.Session(profile_name=profile_name)
    #
    # ENV_CONFIG = {}
    #
    # if args.phase == "vpc_selection":
    #
    #     ENV_CONFIG = build_env_config(session)
    #
    #     print(json.dumps(ENV_CONFIG, indent=2))

    args = parse_args()
    session = boto3.Session(profile_name="Aditya-demo")

    load_state()

    ENV_CONFIG = {}

    if args.phase == "vpc_listing":
        phase_vpc_listing(session)

    elif args.phase == "vpc_selection":
        phase_vpc_selection()
        save_state()

    elif args.phase == "subnet_listing":
        phase_subnet_listing(session)

    elif args.phase == "subnet_selection":
        phase_subnet_selection()
        save_state()
        ENV_CONFIG = build_env_config_from_inputs()
        print(json.dumps(ENV_CONFIG, indent=2))

    if args.phase == "finalize":

        save_state()
        ENV_CONFIG = build_env_config_from_inputs()

        print(json.dumps(ENV_CONFIG, indent=2))

        lambda_initial_name = args.lambda_name
        runtime = args.runtime
        role_name = args.role_name
        memory = args.memory
        timeout = args.timeout
        ephemeral_storage = args.ephemeral_storage

        layers = args.layers.split() if len(args.layers) > 1 else []
        print(layers)
        print(args.layers)

        layer_list = []
        for layer_name in layers:
            layer_arn = get_latest_layer_arn(session, layer_name, region="us-west-2")
            layer_list.append(layer_arn)

        print(layer_list)

        role_arn = get_role_arn(session, role_name)

        reserved_concurrency = None

        enable_reserved_concurrency = args.enable_reserved_concurrency == "true"

        if enable_reserved_concurrency:
            if args.reserved_concurrency is None or args.reserved_concurrency == "":
                raise ValueError("Reserved concurrency value required when enabled")

            reserved_concurrency = {
                "toggle": True,
                "val": int(args.reserved_concurrency)
            }

        environments = [
            "dev", "qa", "qa2", "qa3", "perf",
            "hotfixes", "beta", "uat", "prod", "dr"
        ]

        for env in environments:
            cfg = ENV_CONFIG[env]

            lambda_name = f"zen-{env}-{lambda_initial_name}"

            sg_id = get_or_create_sg(
                session,
                cfg["region"],
                cfg["vpc_id"],
                lambda_name
            )

            vpc_config = {
                "SubnetIds": cfg["subnets"],
                "SecurityGroupIds": [sg_id],
            }

            tags = {"env": f"zenarate/{env}"}

            create_lambda(
                session=session,
                lambda_name=lambda_name,
                region=cfg["region"],
                role_arn=role_arn,
                runtime=runtime,
                memory=int(memory),
                timeout=int(timeout),
                ephemeral_storage=int(ephemeral_storage),
                vpc_config=vpc_config,
                layers=layer_list if env != "dr" else [],
                tags=tags,
                reserved_concurrency=reserved_concurrency,
            )

if __name__ == "__main__":
    main()