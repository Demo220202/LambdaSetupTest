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
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", required=True)
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

    # if True: # args.phase == "finalize":
    #
    #     lambda_initial_name = input("Enter the lambda name to create: ")
    #
    #     runtime = input("Enter the lambda runtime to use: ") # python3.9
    #     role_arn = input("Enter the role ARN to be added: ") #arn:aws:iam::186534707636:role/service-role/test-role
    #     memory = int(input("Enter the memory used in Gen Config: ")) # 512
    #     timeout = int(input("Enter the timeout used in Gen Config: ")) # 60
    #     ephemeral_storage = int(input("Enter the ephemeral memory used in Gen Config: ")) # 1024
    #     layers_string = input("Enter the layer(s) to be added to the lambda, separated by spaces or leave blank: ")
    #
    #     layers = layers_string.split() if len(layers_string) > 1 else []  # optional
    #
    #     reserved_concurrency = {"toggle": True, "val": 1}
    #
    #     environments = [
    #         "dev", "qa", "qa2", "qa3", "perf",
    #         "hotfixes", "beta", "uat", "prod", "dr"
    #     ]
    #
    #     for env in environments:
    #         cfg = ENV_CONFIG[env]
    #
    #         lambda_name = f"zen-{env}-{lambda_initial_name}"
    #
    #         sg_id = get_or_create_sg(
    #             session,
    #             cfg["region"],
    #             cfg["vpc_id"],
    #             lambda_name
    #         )
    #
    #         vpc_config = {
    #             "SubnetIds": cfg["subnets"],
    #             "SecurityGroupIds": [sg_id],
    #         }
    #
    #         tags = {"env": f"zenarate/{env}"}
    #
    #         create_lambda(
    #             session=session,
    #             lambda_name=lambda_name,
    #             region=cfg["region"],
    #             role_arn=role_arn,
    #             runtime=runtime,
    #             memory=memory,
    #             timeout=timeout,
    #             ephemeral_storage=ephemeral_storage,
    #             vpc_config=vpc_config,
    #             layers=layers,
    #             tags=tags,
    #             reserved_concurrency=reserved_concurrency,
    #         )

if __name__ == "__main__":
    main()